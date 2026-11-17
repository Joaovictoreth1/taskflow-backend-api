"""FastAPI application with CORS, Rate Limiting, and all routes."""

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.database import engine, get_db, Base
from app import crud, schemas

# ── Create tables ────────────────────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

# ── Rate Limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="TaskFlow API",
    description="Professional task and project management API with relational models.",
    version="1.0.0",
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
    return {"status": "ok", "message": "TaskFlow API is running 🚀"}


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}


# ══════════════════════════════════════════════════════════════════════════════
# STUDENT ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/students", response_model=schemas.StudentResponse, status_code=201, tags=["Students"])
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


@app.delete("/students/{student_id}", status_code=204, tags=["Students"])
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
    status_code=201,
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

@app.post("/projects", response_model=schemas.ProjectResponse, status_code=201, tags=["Projects"])
@limiter.limit("30/minute")
def create_project(
    request: Request,
    project: schemas.ProjectCreate,
    db: Session = Depends(get_db),
):
    return crud.create_project(db, project)


@app.get("/projects", response_model=list[schemas.ProjectResponse], tags=["Projects"])
@limiter.limit("60/minute")
def list_projects(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return crud.get_projects(db, skip=skip, limit=limit)


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


@app.delete("/projects/{project_id}", status_code=204, tags=["Projects"])
@limiter.limit("30/minute")
def delete_project(request: Request, project_id: int, db: Session = Depends(get_db)):
    if not crud.delete_project(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")


# ══════════════════════════════════════════════════════════════════════════════
# TASK ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/projects/{project_id}/tasks",
    response_model=schemas.TaskResponse,
    status_code=201,
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
def list_tasks(
    request: Request,
    project_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return crud.get_tasks_by_project(db, project_id, skip=skip, limit=limit)


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


@app.delete("/tasks/{task_id}", status_code=204, tags=["Tasks"])
@limiter.limit("30/minute")
def delete_task(request: Request, task_id: int, db: Session = Depends(get_db)):
    if not crud.delete_task(db, task_id):
        raise HTTPException(status_code=404, detail="Task not found")
