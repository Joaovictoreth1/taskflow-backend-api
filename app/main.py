"""FastAPI application with CORS, Rate Limiting, JWT Auth, and Relational CRUD."""

from math import ceil
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import CORS_ALLOWED_ORIGINS
from app.database import get_db
from app import crud, schemas, models
from app.security import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token, verify_password
from app.dependencies import (
    get_current_active_user,
    get_optional_user,
    require_project_write,
    require_task_write,
)

# ── Rate Limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── FastAPI App ──────────────────────────────────────────────────────────────
tags_metadata = [
    {"name": "Health", "description": "Liveness and readiness health-check probes."},
    {"name": "Authentication", "description": "JWT OAuth2 user registration, login, profile, and password rotation."},
    {"name": "Projects", "description": "Project workspace management, pagination, ownership, and CSV export."},
    {"name": "Tasks", "description": "Task creation, priority levels, due dates, multi-field filtering, and status updates."},
    {"name": "Tags", "description": "Color-coded tags and labels for categorizing tasks."},
    {"name": "Task Comments", "description": "Collaboration comments and discussion threads on tasks."},
    {"name": "Analytics", "description": "System-wide and project-specific KPIs, completion rates, and overdue metrics."},
    {"name": "Students", "description": "Academic student records management."},
    {"name": "Profiles", "description": "One-to-one student profiles (bio, avatar)."},
]

app = FastAPI(
    title="TaskFlow API",
    description=(
        "Production-ready task and project management RESTful API "
        "with JWT authentication, relational ORM, strict Pydantic validation, "
        "and advanced filtering/pagination."
    ),
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=tags_metadata,
)

app.state.limiter = limiter
@app.exception_handler(RateLimitExceeded)
def handle_rate_limit(request: Request, exc: RateLimitExceeded) -> Response:
    return _rate_limit_exceeded_handler(request, exc)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health Check ─────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
@limiter.limit("60/minute")
def root(request: Request):
    return {
        "status": "ok",
        "message": "TaskFlow API v2.0 is running 🚀",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}


# ══════════════════════════════════════════════════════════════════════════════
# AUTHENTICATION ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/auth/register",
    response_model=schemas.UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Authentication"],
)
@limiter.limit("20/minute")
def register_user(
    request: Request,
    user_in: schemas.UserCreate,
    db: Session = Depends(get_db),
):
    """Register a new user account."""
    if crud.get_user_by_username(db, user_in.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )
    if crud.get_user_by_email(db, user_in.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    try:
        return crud.create_user(db, user_in)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Username or email already registered") from None


async def login_credentials(request: Request) -> schemas.UserLogin:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    try:
        if content_type == "application/json":
            return schemas.UserLogin.model_validate(await request.json())
        if content_type == "application/x-www-form-urlencoded":
            async with request.form() as fields:
                return schemas.UserLogin.model_validate(dict(fields))
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid username or password fields") from None
    raise HTTPException(status_code=400, detail="Username and password are required")


@app.post(
    "/auth/login",
    response_model=schemas.Token,
    tags=["Authentication"],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                content_type: {"schema": schemas.UserLogin.model_json_schema()}
                for content_type in ("application/json", "application/x-www-form-urlencoded")
            },
        },
    },
)
@limiter.limit("30/minute")
def login(
    request: Request,
    user_login: schemas.UserLogin = Depends(login_credentials),
    db: Session = Depends(get_db),
):
    """Authenticate and receive a JWT Bearer access token."""
    user = crud.authenticate_user(db, user_login.username, user_login.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account is deactivated",
        )

    token = create_access_token(data={"sub": user.username, "user_id": user.id})
    return schemas.Token(
        access_token=token,
        token_type="bearer",
        expires_in_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
        user=schemas.UserResponse.model_validate(user),
    )


@app.get(
    "/auth/me",
    response_model=schemas.UserResponse,
    tags=["Authentication"],
)
@limiter.limit("60/minute")
def get_me(
    request: Request,
    current_user: models.User = Depends(get_current_active_user),
):
    """Get current authenticated user profile."""
    return current_user


@app.patch(
    "/auth/me",
    response_model=schemas.UserResponse,
    tags=["Authentication"],
)
@limiter.limit("20/minute")
def update_me(
    request: Request,
    profile_in: schemas.UpdateProfileRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update current user profile (email)."""
    if profile_in.email and profile_in.email != current_user.email:
        existing = crud.get_user_by_email(db, profile_in.email)
        if existing and existing.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use",
            )
        current_user = crud.update_user_email(db, current_user, profile_in.email)
    return current_user


@app.post(
    "/auth/change-password",
    status_code=status.HTTP_200_OK,
    tags=["Authentication"],
)
@limiter.limit("10/minute")
def change_password(
    request: Request,
    payload: schemas.ChangePasswordRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Change current authenticated user password."""
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect old password",
        )
    crud.change_user_password(db, current_user, payload.new_password)
    return {"status": "ok", "message": "Password updated successfully"}


# ══════════════════════════════════════════════════════════════════════════════
# STUDENT ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/students",
    response_model=schemas.StudentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Students"],
)
@limiter.limit("30/minute")
def create_student(
    request: Request,
    student: schemas.StudentCreate,
    db: Session = Depends(get_db),
):
    existing = crud.get_student_by_email(db, student.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_student(db, student)


@app.get("/students", response_model=list[schemas.StudentResponse], tags=["Students"])
@limiter.limit("60/minute")
def list_students(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return crud.get_students(db, skip=skip, limit=limit)


@app.get("/students/{student_id}", response_model=schemas.StudentResponse, tags=["Students"])
@limiter.limit("60/minute")
def get_student(request: Request, student_id: int, db: Session = Depends(get_db)):
    student = crud.get_student(db, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@app.patch("/students/{student_id}", response_model=schemas.StudentResponse, tags=["Students"])
@limiter.limit("30/minute")
def update_student(
    request: Request,
    student_id: int,
    student: schemas.StudentUpdate,
    db: Session = Depends(get_db),
):
    updated = crud.update_student(db, student_id, student)
    if not updated:
        raise HTTPException(status_code=404, detail="Student not found")
    return updated


@app.delete("/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Students"])
@limiter.limit("30/minute")
def delete_student(request: Request, student_id: int, db: Session = Depends(get_db)):
    if not crud.delete_student(db, student_id):
        raise HTTPException(status_code=404, detail="Student not found")


# ══════════════════════════════════════════════════════════════════════════════
# PROFILE ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/students/{student_id}/profile",
    response_model=schemas.ProfileResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Profiles"],
)
@limiter.limit("30/minute")
def create_profile(
    request: Request,
    student_id: int,
    profile: schemas.ProfileCreate,
    db: Session = Depends(get_db),
):
    result = crud.create_profile(db, student_id, profile)
    if result is None:
        raise HTTPException(
            status_code=400,
            detail="Student not found or already has a profile",
        )
    return result


@app.patch(
    "/students/{student_id}/profile",
    response_model=schemas.ProfileResponse,
    tags=["Profiles"],
)
@limiter.limit("30/minute")
def update_profile(
    request: Request,
    student_id: int,
    profile: schemas.ProfileUpdate,
    db: Session = Depends(get_db),
):
    result = crud.update_profile(db, student_id, profile)
    if result is None:
        raise HTTPException(status_code=404, detail="Student or profile not found")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# PROJECT ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/projects",
    response_model=schemas.ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Projects"],
)
@limiter.limit("30/minute")
def create_project(
    request: Request,
    project: schemas.ProjectCreate,
    current_user: Optional[models.User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    owner_id = current_user.id if current_user else None
    return crud.create_project(db, project, owner_id=owner_id)


@app.get("/projects", response_model=list[schemas.ProjectResponse], tags=["Projects"])
@limiter.limit("60/minute")
def list_projects(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by project name"),
    db: Session = Depends(get_db),
):
    return crud.get_projects(db, skip=skip, limit=limit, search=search)


@app.get(
    "/projects/paginated",
    response_model=schemas.PaginatedResponse[schemas.ProjectResponse],
    tags=["Projects"],
)
@limiter.limit("60/minute")
def list_projects_paginated(
    request: Request,
    page: int = Query(1, ge=1, description="Page number starting at 1"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    search: Optional[str] = Query(None, description="Search by project name"),
    db: Session = Depends(get_db),
):
    skip = (page - 1) * size
    items = crud.get_projects(db, skip=skip, limit=size, search=search)
    total = crud.count_projects(db, search=search)
    pages = ceil(total / size) if size > 0 else 0
    return schemas.PaginatedResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@app.get("/projects/{project_id}", response_model=schemas.ProjectResponse, tags=["Projects"])
@limiter.limit("60/minute")
def get_project(request: Request, project_id: int, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.patch("/projects/{project_id}", response_model=schemas.ProjectResponse, tags=["Projects"], dependencies=[Depends(require_project_write)])
@limiter.limit("30/minute")
def update_project(
    request: Request,
    project_id: int,
    project: schemas.ProjectUpdate,
    db: Session = Depends(get_db),
):
    updated = crud.update_project(db, project_id, project)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated


@app.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Projects"], dependencies=[Depends(require_project_write)])
@limiter.limit("30/minute")
def delete_project(request: Request, project_id: int, db: Session = Depends(get_db)):
    if not crud.delete_project(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")


# ══════════════════════════════════════════════════════════════════════════════
# TASK ROUTES (Project Sub-Resource & Global Search / Filtering)
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/projects/{project_id}/tasks",
    response_model=schemas.TaskResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Tasks"],
    dependencies=[Depends(require_project_write)],
)
@limiter.limit("30/minute")
def create_task(
    request: Request,
    project_id: int,
    task: schemas.TaskCreate,
    db: Session = Depends(get_db),
):
    if task.assignee_id is not None and crud.get_user(db, task.assignee_id) is None:
        raise HTTPException(status_code=422, detail="Assignee does not exist")
    result = crud.create_task(db, project_id, task)
    if result is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@app.get(
    "/projects/{project_id}/tasks",
    response_model=list[schemas.TaskResponse],
    tags=["Tasks"],
)
@limiter.limit("60/minute")
def list_tasks_by_project(
    request: Request,
    project_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return crud.get_tasks_by_project(db, project_id, skip=skip, limit=limit)


@app.get(
    "/tasks/my-tasks",
    response_model=schemas.PaginatedResponse[schemas.TaskResponse],
    tags=["Tasks"],
)
@limiter.limit("60/minute")
def list_my_tasks(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Retrieve tasks assigned to the currently authenticated user."""
    skip = (page - 1) * size
    items, total = crud.filter_tasks(
        db,
        assignee_id=current_user.id,
        status=status,
        priority=priority,
        skip=skip,
        limit=size,
    )
    pages = ceil(total / size) if size > 0 else 0
    return schemas.PaginatedResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@app.get(
    "/tasks",
    response_model=schemas.PaginatedResponse[schemas.TaskResponse],
    tags=["Tasks"],
)
@limiter.limit("60/minute")
def list_all_tasks(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    project_id: Optional[int] = Query(None, description="Filter by project ID"),
    assignee_id: Optional[int] = Query(None, description="Filter by assignee user ID"),
    status: Optional[str] = Query(None, description="Filter by status (todo, in_progress, done)"),
    priority: Optional[str] = Query(None, description="Filter by priority (low, medium, high, urgent)"),
    search: Optional[str] = Query(None, description="Search in title or description"),
    tag: Optional[str] = Query(None, description="Filter by tag name"),
    db: Session = Depends(get_db),
):
    """Global task query with multi-field filtering and paginated envelope."""
    skip = (page - 1) * size
    items, total = crud.filter_tasks(
        db,
        project_id=project_id,
        assignee_id=assignee_id,
        status=status,
        priority=priority,
        search=search,
        tag=tag,
        skip=skip,
        limit=size,
    )
    pages = ceil(total / size) if size > 0 else 0
    return schemas.PaginatedResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@app.get("/tasks/{task_id}", response_model=schemas.TaskResponse, tags=["Tasks"])
@limiter.limit("60/minute")
def get_task(request: Request, task_id: int, db: Session = Depends(get_db)):
    task = crud.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.patch("/tasks/{task_id}", response_model=schemas.TaskResponse, tags=["Tasks"], dependencies=[Depends(require_task_write)])
@limiter.limit("30/minute")
def update_task(
    request: Request,
    task_id: int,
    task: schemas.TaskUpdate,
    db: Session = Depends(get_db),
):
    if task.assignee_id is not None and crud.get_user(db, task.assignee_id) is None:
        raise HTTPException(status_code=422, detail="Assignee does not exist")
    updated = crud.update_task(db, task_id, task)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tasks"], dependencies=[Depends(require_task_write)])
@limiter.limit("30/minute")
def delete_task(request: Request, task_id: int, db: Session = Depends(get_db)):
    if not crud.delete_task(db, task_id):
        raise HTTPException(status_code=404, detail="Task not found")


# ══════════════════════════════════════════════════════════════════════════════
# TASK COMMENTS ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/tasks/{task_id}/comments",
    response_model=schemas.TaskCommentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Task Comments"],
)
@limiter.limit("30/minute")
def create_comment(
    request: Request,
    task_id: int,
    comment_in: schemas.TaskCommentCreate,
    current_user: Optional[models.User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Post a comment on a specific task."""
    result = crud.create_task_comment(db, task_id, comment_in, user=current_user)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@app.get(
    "/tasks/{task_id}/comments",
    response_model=list[schemas.TaskCommentResponse],
    tags=["Task Comments"],
)
@limiter.limit("60/minute")
def list_comments(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db),
):
    """List all comments on a specific task."""
    if not crud.get_task(db, task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return crud.get_task_comments(db, task_id)


@app.delete(
    "/tasks/{task_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Task Comments"],
    dependencies=[Depends(require_task_write)],
)
@limiter.limit("30/minute")
def delete_comment(
    request: Request,
    task_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
):
    """Delete a comment from a task."""
    if not crud.delete_task_comment(db, task_id, comment_id):
        raise HTTPException(status_code=404, detail="Comment not found")


# ══════════════════════════════════════════════════════════════════════════════
# TAG ROUTES (Labels & Categories)
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/tags",
    response_model=schemas.TagResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Tags"],
)
@limiter.limit("30/minute")
def create_tag(
    request: Request,
    tag_in: schemas.TagCreate,
    db: Session = Depends(get_db),
):
    """Create a new tag/label with a hex color code."""
    if crud.get_tag_by_name(db, tag_in.name):
        raise HTTPException(status_code=400, detail="Tag already exists")
    return crud.create_tag(db, tag_in)


@app.get(
    "/tags",
    response_model=list[schemas.TagResponse],
    tags=["Tags"],
)
@limiter.limit("60/minute")
def list_tags(request: Request, db: Session = Depends(get_db)):
    """List all available tags."""
    return crud.get_tags(db)


@app.delete(
    "/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Tags"],
)
@limiter.limit("30/minute")
def delete_tag(request: Request, tag_id: int, db: Session = Depends(get_db)):
    """Delete a tag globally."""
    if crud.tag_used_by_owned_project(db, tag_id):
        raise HTTPException(status_code=409, detail="Unassign this tag from owned projects before deleting it")
    if not crud.delete_tag(db, tag_id):
        raise HTTPException(status_code=404, detail="Tag not found")


@app.post(
    "/tasks/{task_id}/tags/{tag_id}",
    response_model=schemas.TaskResponse,
    tags=["Tags"],
    dependencies=[Depends(require_task_write)],
)
@limiter.limit("30/minute")
def assign_tag_to_task(
    request: Request,
    task_id: int,
    tag_id: int,
    db: Session = Depends(get_db),
):
    """Associate a tag with a task."""
    result = crud.add_tag_to_task(db, task_id, tag_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task or Tag not found")
    return result


@app.delete(
    "/tasks/{task_id}/tags/{tag_id}",
    response_model=schemas.TaskResponse,
    tags=["Tags"],
    dependencies=[Depends(require_task_write)],
)
@limiter.limit("30/minute")
def remove_tag_from_task(
    request: Request,
    task_id: int,
    tag_id: int,
    db: Session = Depends(get_db),
):
    """Disassociate a tag from a task."""
    result = crud.remove_tag_from_task(db, task_id, tag_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task or Tag not found")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# ANALYTICS & STATS ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/analytics/overview",
    response_model=schemas.AnalyticsOverviewResponse,
    tags=["Analytics"],
)
@limiter.limit("60/minute")
def get_analytics_overview(request: Request, db: Session = Depends(get_db)):
    """Global system-wide task management analytics, KPIs and completion rates."""
    return crud.get_analytics_overview(db)


@app.get(
    "/projects/{project_id}/stats",
    response_model=schemas.ProjectStatsResponse,
    tags=["Analytics"],
)
@limiter.limit("60/minute")
def get_project_stats(
    request: Request,
    project_id: int,
    db: Session = Depends(get_db),
):
    """Project-specific metrics, breakdown by status, and completion rate."""
    stats = crud.get_project_stats(db, project_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Project not found")
    return stats


# ══════════════════════════════════════════════════════════════════════════════
# PROJECT EXPORT ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/projects/{project_id}/export/csv",
    tags=["Projects"],
    summary="Export project tasks to CSV",
)
@limiter.limit("20/minute")
def export_project_tasks_csv(
    request: Request,
    project_id: int,
    db: Session = Depends(get_db),
):
    """Generate and download a CSV file of all tasks in a project."""
    import csv
    import io

    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Title", "Status", "Priority", "Due Date", "Created At", "Description"])

    for task in project.tasks:
        s_val = task.status.value if hasattr(task.status, "value") else str(task.status)
        p_val = task.priority.value if hasattr(task.priority, "value") else str(task.priority)
        due = task.due_date.isoformat() if task.due_date else ""
        created = task.created_at.isoformat() if task.created_at else ""
        writer.writerow([task.id, task.title, s_val, p_val, due, created, task.description])

    csv_data = output.getvalue()
    filename = f"project_{project_id}_tasks.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
