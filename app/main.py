"""FastAPI application with CORS, Rate Limiting, JWT Auth, and Relational CRUD."""

from collections.abc import Awaitable, Callable
from math import ceil
from pathlib import Path
from typing import Annotated

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.config import settings
from app.database import get_db
from app.dependencies import (
    CurrentUser,
    Database,
    OwnedProject,
    OwnedTask,
    ResourceID,
    VisibleTask,
    get_current_active_user,
    require_directory_admin,
)
from app.middleware import RequestBodyLimit
from app.security import create_access_token, credential_stamp, verify_password

# ── Rate Limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.rate_limit_storage_uri.get_secret_value(),
)

# ── FastAPI App ──────────────────────────────────────────────────────────────
tags_metadata = [
    {"name": "Health", "description": "Liveness and readiness health-check probes."},
    {
        "name": "Authentication",
        "description": "JWT OAuth2 user registration, login, profile, and password rotation.",
    },
    {
        "name": "Projects",
        "description": "Project workspace management, pagination, ownership, and CSV export.",
    },
    {
        "name": "Tasks",
        "description": "Task creation, priority levels, due dates, multi-field filtering, and status updates.",
    },
    {"name": "Tags", "description": "Color-coded tags and labels for categorizing tasks."},
    {
        "name": "Task Comments",
        "description": "Collaboration comments and discussion threads on tasks.",
    },
    {
        "name": "Analytics",
        "description": "System-wide and project-specific KPIs, completion rates, and overdue metrics.",
    },
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

directory = APIRouter(dependencies=[Depends(require_directory_admin)])


@app.exception_handler(crud.WriteConflict)
async def handle_write_conflict(request: Request, exc: crud.WriteConflict) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": "Resource changed or already exists"})


@app.exception_handler(crud.InvalidReference)
async def handle_invalid_reference(request: Request, exc: crud.InvalidReference) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


def project_response(db: Session, project: models.Project) -> schemas.ProjectResponse:
    details = schemas.ProjectSummary.model_validate(project).model_dump()
    tasks = crud.get_tasks_by_project(db, project.id, limit=100)
    return schemas.ProjectResponse(
        **details,
        tasks=[schemas.TaskResponse.model_validate(task) for task in tasks],
    )


def task_page(
    items: list[models.Task], total: int, page: int, size: int
) -> schemas.PaginatedResponse[schemas.TaskResponse]:
    return schemas.PaginatedResponse[schemas.TaskResponse](
        items=[schemas.TaskResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        size=size,
        pages=ceil(total / size),
    )


app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def limit_exceeded(request: Request, exc: RateLimitExceeded) -> Response:
    return _rate_limit_exceeded_handler(request, exc)


# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(RequestBodyLimit, max_bytes=settings.max_request_body_bytes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {key: error[key] for key in ("loc", "msg", "type") if key in error}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.middleware("http")
async def security_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


# ── Health Check ─────────────────────────────────────────────────────────────


@app.get("/", tags=["Health"])
@limiter.limit("60/minute")
def root(request: Request) -> dict[str, str]:
    return {
        "status": "ok",
        "message": "TaskFlow API v2.0 is running 🚀",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/ready", tags=["Health"])
def readiness_check(db: Database) -> dict[str, str]:
    try:
        heads = set(db.scalars(text("SELECT version_num FROM alembic_version")))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is not ready") from exc
    if heads != EXPECTED_MIGRATION_HEADS:
        raise HTTPException(status_code=503, detail="Database schema is not up to date")
    return {"status": "ready"}


EXPECTED_MIGRATION_HEADS = set(
    ScriptDirectory.from_config(
        Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    ).get_heads()
)


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
) -> models.User:
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
    return crud.create_user(db, user_in)


@app.post(
    "/auth/login",
    response_model=schemas.Token,
    tags=["Authentication"],
)
@limiter.limit("10/minute")
def login(
    request: Request,
    user_login: schemas.UserLogin,
    db: Database,
) -> schemas.Token:
    return authenticate(db, user_login.username, user_login.password)


@app.post("/auth/token", response_model=schemas.Token, tags=["Authentication"])
@limiter.limit("10/minute")
def login_form(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Database,
) -> schemas.Token:
    if not 1 <= len(form.username) <= 255 or not 1 <= len(form.password) <= 128:
        raise HTTPException(status_code=422, detail="Invalid credential length")
    return authenticate(db, form.username, form.password)


def authenticate(db: Session, username: str, password: str) -> schemas.Token:
    user = crud.authenticate_user(db, username_or_email=username, password=password)
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

    token = create_access_token(
        {"sub": user.username, "user_id": user.id, "pwd": credential_stamp(user.hashed_password)}
    )
    return schemas.Token(
        access_token=token,
        token_type="bearer",
        expires_in_minutes=settings.access_token_expire_minutes,
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
) -> models.User:
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
) -> models.User:
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
) -> dict[str, str]:
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


@directory.post(
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
) -> models.Student:
    existing = crud.get_student_by_email(db, student.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_student(db, student)


@directory.get("/students", response_model=list[schemas.StudentResponse], tags=["Students"])
@limiter.limit("60/minute")
def list_students(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[models.Student]:
    return crud.get_students(db, skip=skip, limit=limit)


@directory.get("/students/{student_id}", response_model=schemas.StudentResponse, tags=["Students"])
@limiter.limit("60/minute")
def get_student(
    request: Request, student_id: ResourceID, db: Session = Depends(get_db)
) -> models.Student:
    student = crud.get_student(db, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@directory.patch(
    "/students/{student_id}", response_model=schemas.StudentResponse, tags=["Students"]
)
@limiter.limit("30/minute")
def update_student(
    request: Request,
    student_id: ResourceID,
    student: schemas.StudentUpdate,
    db: Session = Depends(get_db),
) -> models.Student:
    updated = crud.update_student(db, student_id, student)
    if not updated:
        raise HTTPException(status_code=404, detail="Student not found")
    return updated


@directory.delete(
    "/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Students"]
)
@limiter.limit("30/minute")
def delete_student(request: Request, student_id: ResourceID, db: Session = Depends(get_db)) -> None:
    if not crud.delete_student(db, student_id):
        raise HTTPException(status_code=404, detail="Student not found")


# ══════════════════════════════════════════════════════════════════════════════
# PROFILE ROUTES
# ══════════════════════════════════════════════════════════════════════════════


@directory.post(
    "/students/{student_id}/profile",
    response_model=schemas.ProfileResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Profiles"],
)
@limiter.limit("30/minute")
def create_profile(
    request: Request,
    student_id: ResourceID,
    profile: schemas.ProfileCreate,
    db: Session = Depends(get_db),
) -> models.Profile:
    result = crud.create_profile(db, student_id, profile)
    if result is None:
        raise HTTPException(
            status_code=400,
            detail="Student not found or already has a profile",
        )
    return result


@directory.patch(
    "/students/{student_id}/profile",
    response_model=schemas.ProfileResponse,
    tags=["Profiles"],
)
@limiter.limit("30/minute")
def update_profile(
    request: Request,
    student_id: ResourceID,
    profile: schemas.ProfileUpdate,
    db: Session = Depends(get_db),
) -> models.Profile:
    result = crud.update_profile(db, student_id, profile)
    if result is None:
        raise HTTPException(status_code=404, detail="Student or profile not found")
    return result


# ══════════════════════════════════════════════════════════════════════════════
app.include_router(directory)


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
    request: Request, project: schemas.ProjectCreate, user: CurrentUser, db: Database
) -> models.Project:
    return crud.create_project(db, project, owner_id=user.id)


@app.get("/projects", response_model=list[schemas.ProjectSummary], tags=["Projects"])
@limiter.limit("60/minute")
def list_projects(
    request: Request,
    user: CurrentUser,
    db: Database,
    skip: int = Query(0, ge=0, le=1_000_000),
    limit: int = Query(100, ge=1, le=100),
    search: str | None = Query(None, max_length=200),
) -> list[models.Project]:
    return crud.get_projects(db, skip=skip, limit=limit, search=search, owner_id=user.id)


@app.get(
    "/projects/paginated",
    response_model=schemas.PaginatedResponse[schemas.ProjectSummary],
    tags=["Projects"],
)
@limiter.limit("60/minute")
def list_projects_paginated(
    request: Request,
    user: CurrentUser,
    db: Database,
    page: int = Query(1, ge=1, le=10_000),
    size: int = Query(10, ge=1, le=100),
    search: str | None = Query(None, max_length=200),
) -> schemas.PaginatedResponse[schemas.ProjectSummary]:
    skip = (page - 1) * size
    items = crud.get_projects(db, skip=skip, limit=size, search=search, owner_id=user.id)
    total = crud.count_projects(db, search=search, owner_id=user.id)
    return schemas.PaginatedResponse[schemas.ProjectSummary](
        items=[schemas.ProjectSummary.model_validate(item) for item in items],
        total=total,
        page=page,
        size=size,
        pages=ceil(total / size),
    )


@app.get("/projects/{project_id}", response_model=schemas.ProjectResponse, tags=["Projects"])
@limiter.limit("60/minute")
def get_project(request: Request, project: OwnedProject, db: Database) -> schemas.ProjectResponse:
    return project_response(db, project)


@app.patch("/projects/{project_id}", response_model=schemas.ProjectResponse, tags=["Projects"])
@limiter.limit("30/minute")
def update_project(
    request: Request,
    project: OwnedProject,
    payload: schemas.ProjectUpdate,
    db: Database,
) -> schemas.ProjectResponse:
    return project_response(db, crud.update_project(db, project, payload))


@app.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Projects"])
@limiter.limit("30/minute")
def delete_project(request: Request, project: OwnedProject, db: Database) -> None:
    crud.delete_project(db, project)


# ══════════════════════════════════════════════════════════════════════════════
# TASK ROUTES (Project Sub-Resource & Global Search / Filtering)
# ══════════════════════════════════════════════════════════════════════════════


@app.post(
    "/projects/{project_id}/tasks",
    response_model=schemas.TaskResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Tasks"],
)
@limiter.limit("30/minute")
def create_task(
    request: Request, project: OwnedProject, task: schemas.TaskCreate, db: Database
) -> models.Task:
    return crud.create_task(db, project, task)


@app.get(
    "/projects/{project_id}/tasks",
    response_model=list[schemas.TaskResponse],
    tags=["Tasks"],
)
@limiter.limit("60/minute")
def list_tasks_by_project(
    request: Request,
    project: OwnedProject,
    db: Database,
    skip: int = Query(0, ge=0, le=1_000_000),
    limit: int = Query(100, ge=1, le=100),
) -> list[models.Task]:
    return crud.get_tasks_by_project(db, project.id, skip=skip, limit=limit)


@app.get(
    "/tasks/my-tasks",
    response_model=schemas.PaginatedResponse[schemas.TaskResponse],
    tags=["Tasks"],
)
@limiter.limit("60/minute")
def list_my_tasks(
    request: Request,
    user: CurrentUser,
    db: Database,
    page: int = Query(1, ge=1, le=10_000),
    size: int = Query(10, ge=1, le=100),
    status: models.TaskStatus | None = None,
    priority: models.TaskPriority | None = None,
) -> schemas.PaginatedResponse[schemas.TaskResponse]:
    items, total = crud.filter_tasks(
        db,
        actor_id=user.id,
        assignee_id=user.id,
        status=status,
        priority=priority,
        skip=(page - 1) * size,
        limit=size,
    )
    return task_page(items, total, page, size)


@app.get(
    "/tasks",
    response_model=schemas.PaginatedResponse[schemas.TaskResponse],
    tags=["Tasks"],
)
@limiter.limit("60/minute")
def list_all_tasks(
    request: Request,
    user: CurrentUser,
    db: Database,
    page: int = Query(1, ge=1, le=10_000),
    size: int = Query(10, ge=1, le=100),
    project_id: int | None = Query(None, gt=0, le=schemas.MAX_ID),
    assignee_id: int | None = Query(None, gt=0, le=schemas.MAX_ID),
    status: models.TaskStatus | None = None,
    priority: models.TaskPriority | None = None,
    search: str | None = Query(None, max_length=200),
    tag: str | None = Query(None, max_length=50),
) -> schemas.PaginatedResponse[schemas.TaskResponse]:
    items, total = crud.filter_tasks(
        db,
        actor_id=user.id,
        project_id=project_id,
        assignee_id=assignee_id,
        status=status,
        priority=priority,
        search=search,
        tag=tag,
        skip=(page - 1) * size,
        limit=size,
    )
    return task_page(items, total, page, size)


@app.get("/tasks/{task_id}", response_model=schemas.TaskResponse, tags=["Tasks"])
@limiter.limit("60/minute")
def get_task(request: Request, task: VisibleTask) -> models.Task:
    return task


@app.patch("/tasks/{task_id}", response_model=schemas.TaskResponse, tags=["Tasks"])
@limiter.limit("30/minute")
def update_task(
    request: Request, task: OwnedTask, payload: schemas.TaskUpdate, db: Database
) -> models.Task:
    return crud.update_task(db, task, payload)


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tasks"])
@limiter.limit("30/minute")
def delete_task(request: Request, task: OwnedTask, db: Database) -> None:
    crud.delete_task(db, task)


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
    task: VisibleTask,
    comment_in: schemas.TaskCommentCreate,
    user: CurrentUser,
    db: Database,
) -> models.TaskComment:
    return crud.create_task_comment(db, task, comment_in, user)


@app.get(
    "/tasks/{task_id}/comments",
    response_model=list[schemas.TaskCommentResponse],
    tags=["Task Comments"],
)
@limiter.limit("60/minute")
def list_comments(
    request: Request,
    task: VisibleTask,
    db: Database,
    skip: int = Query(0, ge=0, le=1_000_000),
    limit: int = Query(100, ge=1, le=100),
) -> list[models.TaskComment]:
    return crud.get_task_comments(db, task.id, skip=skip, limit=limit)


@app.delete(
    "/tasks/{task_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Task Comments"],
)
@limiter.limit("30/minute")
def delete_comment(
    request: Request,
    task: VisibleTask,
    comment_id: ResourceID,
    user: CurrentUser,
    db: Database,
) -> None:
    if not crud.delete_task_comment(db, task.id, comment_id, user.id):
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
    user: CurrentUser,
    db: Database,
) -> models.Tag:
    if crud.get_tag_by_name(db, tag_in.name, owner_id=user.id):
        raise HTTPException(status_code=400, detail="Tag already exists")
    return crud.create_tag(db, tag_in, owner_id=user.id)


@app.get(
    "/tags",
    response_model=list[schemas.TagResponse],
    tags=["Tags"],
)
@limiter.limit("60/minute")
def list_tags(
    request: Request,
    user: CurrentUser,
    db: Database,
    skip: int = Query(0, ge=0, le=1_000_000),
    limit: int = Query(100, ge=1, le=100),
) -> list[models.Tag]:
    return crud.get_tags(db, owner_id=user.id, skip=skip, limit=limit)


@app.delete(
    "/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Tags"],
)
@limiter.limit("30/minute")
def delete_tag(request: Request, tag_id: ResourceID, user: CurrentUser, db: Database) -> None:
    if not crud.delete_tag(db, tag_id, owner_id=user.id):
        raise HTTPException(status_code=404, detail="Tag not found")


@app.post(
    "/tasks/{task_id}/tags/{tag_id}",
    response_model=schemas.TaskResponse,
    tags=["Tags"],
)
@limiter.limit("30/minute")
def assign_tag_to_task(
    request: Request, task: OwnedTask, tag_id: ResourceID, user: CurrentUser, db: Database
) -> models.Task:
    return crud.set_task_tag(db, task, tag_id, owner_id=user.id, attached=True)


@app.delete(
    "/tasks/{task_id}/tags/{tag_id}",
    response_model=schemas.TaskResponse,
    tags=["Tags"],
)
@limiter.limit("30/minute")
def remove_tag_from_task(
    request: Request, task: OwnedTask, tag_id: ResourceID, user: CurrentUser, db: Database
) -> models.Task:
    return crud.set_task_tag(db, task, tag_id, owner_id=user.id, attached=False)


# ══════════════════════════════════════════════════════════════════════════════
# ANALYTICS & STATS ROUTES
# ══════════════════════════════════════════════════════════════════════════════


@app.get(
    "/analytics/overview",
    response_model=schemas.AnalyticsOverviewResponse,
    tags=["Analytics"],
)
@limiter.limit("60/minute")
def get_analytics_overview(
    request: Request, user: CurrentUser, db: Database
) -> schemas.AnalyticsOverviewResponse:
    return crud.get_analytics_overview(db, owner_id=user.id)


@app.get(
    "/projects/{project_id}/stats",
    response_model=schemas.ProjectStatsResponse,
    tags=["Analytics"],
)
@limiter.limit("60/minute")
def get_project_stats(
    request: Request, project: OwnedProject, db: Database
) -> schemas.ProjectStatsResponse:
    return crud.get_project_stats(db, project)


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
    request: Request, project: OwnedProject, db: Database
) -> StreamingResponse:
    return StreamingResponse(
        crud.stream_project_csv(db, project.id),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=project_{project.id}_tasks.csv"},
    )
