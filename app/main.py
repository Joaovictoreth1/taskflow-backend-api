"""FastAPI application with CORS, Rate Limiting, JWT Auth, and Relational CRUD."""

from math import ceil
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.database import engine, get_db, Base
from app import crud, schemas, models
from app.security import create_access_token
from app.dependencies import (
    get_current_active_user,
    get_optional_user,
)

# ── Create tables ────────────────────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

# ── Rate Limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="TaskFlow API",
    description=(
        "Production-ready task and project management RESTful API "
        "with JWT authentication, relational ORM, strict Pydantic validation, "
        "and advanced filtering/pagination."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
    return crud.create_user(db, user_in)


@app.post(
    "/auth/login",
    response_model=schemas.Token,
    tags=["Authentication"],
)
@limiter.limit("30/minute")
def login(
    request: Request,
    user_login: Optional[schemas.UserLogin] = None,
    form_data: Optional[OAuth2PasswordRequestForm] = Depends(lambda: None),
    db: Session = Depends(get_db),
):
    """Authenticate and receive a JWT Bearer access token."""
    username = None
    password = None

    if user_login:
        username = user_login.username
        password = user_login.password
    elif form_data:
        username = form_data.username
        password = form_data.password

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required",
        )

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

    token = create_access_token(data={"sub": user.username, "user_id": user.id})
    return schemas.Token(
        access_token=token,
        token_type="bearer",
        expires_in_minutes=60,
        user=user,
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


@app.patch("/projects/{project_id}", response_model=schemas.ProjectResponse, tags=["Projects"])
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


@app.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Projects"])
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
)
@limiter.limit("30/minute")
def create_task(
    request: Request,
    project_id: int,
    task: schemas.TaskCreate,
    db: Session = Depends(get_db),
):
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
    status: Optional[str] = Query(None, description="Filter by status (todo, in_progress, done)"),
    priority: Optional[str] = Query(None, description="Filter by priority (low, medium, high, urgent)"),
    search: Optional[str] = Query(None, description="Search in title or description"),
    db: Session = Depends(get_db),
):
    """Global task query with multi-field filtering and paginated envelope."""
    skip = (page - 1) * size
    items, total = crud.filter_tasks(
        db,
        project_id=project_id,
        status=status,
        priority=priority,
        search=search,
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


@app.patch("/tasks/{task_id}", response_model=schemas.TaskResponse, tags=["Tasks"])
@limiter.limit("30/minute")
def update_task(
    request: Request,
    task_id: int,
    task: schemas.TaskUpdate,
    db: Session = Depends(get_db),
):
    updated = crud.update_task(db, task_id, task)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tasks"])
@limiter.limit("30/minute")
def delete_task(request: Request, task_id: int, db: Session = Depends(get_db)):
    if not crud.delete_task(db, task_id):
        raise HTTPException(status_code=404, detail="Task not found")
