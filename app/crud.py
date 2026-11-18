"""CRUD operations for all models (Students, Profiles, Projects, Tasks, Users)."""

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app import models, schemas
from app.security import hash_password, verify_password


# ══════════════════════════════════════════════════════════════════════════════
# USER CRUD (Authentication & Security)
# ══════════════════════════════════════════════════════════════════════════════

def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    """Create a new user with bcrypt-hashed password."""
    db_user = models.User(
        username=user.username.lower(),
        email=user.email.lower(),
        hashed_password=hash_password(user.password),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user(db: Session, user_id: int) -> models.User | None:
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> models.User | None:
    return db.query(models.User).filter(models.User.username == username.lower()).first()


def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email.lower()).first()


def authenticate_user(
    db: Session, username_or_email: str, password: str
) -> models.User | None:
    """Authenticate a user by username or email and plaintext password."""
    identifier = username_or_email.lower().strip()
    user = (
        db.query(models.User)
        .filter(or_(models.User.username == identifier, models.User.email == identifier))
        .first()
    )
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ══════════════════════════════════════════════════════════════════════════════
# STUDENT CRUD
# ══════════════════════════════════════════════════════════════════════════════

def create_student(db: Session, student: schemas.StudentCreate) -> models.Student:
    db_student = models.Student(name=student.name, email=student.email)
    db.add(db_student)
    db.flush()

    if student.profile:
        db_profile = models.Profile(
            student_id=db_student.id,
            bio=student.profile.bio,
            avatar_url=student.profile.avatar_url,
        )
        db.add(db_profile)

    db.commit()
    db.refresh(db_student)
    return db_student


def get_student(db: Session, student_id: int) -> models.Student | None:
    return db.query(models.Student).filter(models.Student.id == student_id).first()


def get_student_by_email(db: Session, email: str) -> models.Student | None:
    return db.query(models.Student).filter(models.Student.email == email.lower()).first()


def get_students(db: Session, skip: int = 0, limit: int = 100) -> list[models.Student]:
    return db.query(models.Student).offset(skip).limit(limit).all()


def update_student(
    db: Session, student_id: int, student: schemas.StudentUpdate
) -> models.Student | None:
    db_student = get_student(db, student_id)
    if not db_student:
        return None

    update_data = student.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_student, key, value)

    db.commit()
    db.refresh(db_student)
    return db_student


def delete_student(db: Session, student_id: int) -> bool:
    db_student = get_student(db, student_id)
    if not db_student:
        return False
    db.delete(db_student)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# PROFILE CRUD
# ══════════════════════════════════════════════════════════════════════════════

def create_profile(
    db: Session, student_id: int, profile: schemas.ProfileCreate
) -> models.Profile | None:
    db_student = get_student(db, student_id)
    if not db_student:
        return None
    if db_student.profile:
        return None  # Already has a profile (1:1)

    db_profile = models.Profile(
        student_id=student_id, bio=profile.bio, avatar_url=profile.avatar_url
    )
    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)
    return db_profile


def update_profile(
    db: Session, student_id: int, profile: schemas.ProfileUpdate
) -> models.Profile | None:
    db_student = get_student(db, student_id)
    if not db_student or not db_student.profile:
        return None

    update_data = profile.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_student.profile, key, value)

    db.commit()
    db.refresh(db_student.profile)
    return db_student.profile


# ══════════════════════════════════════════════════════════════════════════════
# PROJECT CRUD
# ══════════════════════════════════════════════════════════════════════════════

def create_project(
    db: Session, project: schemas.ProjectCreate, owner_id: Optional[int] = None
) -> models.Project:
    db_project = models.Project(
        name=project.name,
        description=project.description,
        owner_id=owner_id,
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


def get_project(db: Session, project_id: int) -> models.Project | None:
    return db.query(models.Project).filter(models.Project.id == project_id).first()


def get_projects(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    owner_id: Optional[int] = None,
) -> list[models.Project]:
    query = db.query(models.Project)
    if owner_id is not None:
        query = query.filter(models.Project.owner_id == owner_id)
    if search:
        query = query.filter(models.Project.name.ilike(f"%{search}%"))
    return query.offset(skip).limit(limit).all()


def count_projects(
    db: Session, search: Optional[str] = None, owner_id: Optional[int] = None
) -> int:
    query = db.query(models.Project)
    if owner_id is not None:
        query = query.filter(models.Project.owner_id == owner_id)
    if search:
        query = query.filter(models.Project.name.ilike(f"%{search}%"))
    return query.count()


def update_project(
    db: Session, project_id: int, project: schemas.ProjectUpdate
) -> models.Project | None:
    db_project = get_project(db, project_id)
    if not db_project:
        return None

    update_data = project.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_project, key, value)

    db.commit()
    db.refresh(db_project)
    return db_project


def delete_project(db: Session, project_id: int) -> bool:
    db_project = get_project(db, project_id)
    if not db_project:
        return False
    db.delete(db_project)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# TASK CRUD
# ══════════════════════════════════════════════════════════════════════════════

def create_task(
    db: Session, project_id: int, task: schemas.TaskCreate
) -> models.Task | None:
    db_project = get_project(db, project_id)
    if not db_project:
        return None

    db_task = models.Task(
        project_id=project_id,
        title=task.title,
        description=task.description,
        status=models.TaskStatus(task.status),
        priority=models.TaskPriority(task.priority),
        due_date=task.due_date,
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def get_task(db: Session, task_id: int) -> models.Task | None:
    return db.query(models.Task).filter(models.Task.id == task_id).first()


def get_tasks_by_project(
    db: Session, project_id: int, skip: int = 0, limit: int = 100
) -> list[models.Task]:
    return (
        db.query(models.Task)
        .filter(models.Task.project_id == project_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def filter_tasks(
    db: Session,
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[models.Task], int]:
    """Filter tasks with multiple criteria and return both items and total count."""
    query = db.query(models.Task)

    if project_id is not None:
        query = query.filter(models.Task.project_id == project_id)
    if status is not None:
        query = query.filter(models.Task.status == models.TaskStatus(status))
    if priority is not None:
        query = query.filter(models.Task.priority == models.TaskPriority(priority))
    if search:
        query = query.filter(
            or_(
                models.Task.title.ilike(f"%{search}%"),
                models.Task.description.ilike(f"%{search}%"),
            )
        )

    total = query.count()
    items = query.order_by(models.Task.id.desc()).offset(skip).limit(limit).all()
    return items, total


def update_task(
    db: Session, task_id: int, task: schemas.TaskUpdate
) -> models.Task | None:
    db_task = get_task(db, task_id)
    if not db_task:
        return None

    update_data = task.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "status" and value is not None:
            value = models.TaskStatus(value)
        elif key == "priority" and value is not None:
            value = models.TaskPriority(value)
        setattr(db_task, key, value)

    db.commit()
    db.refresh(db_task)
    return db_task


def delete_task(db: Session, task_id: int) -> bool:
    db_task = get_task(db, task_id)
    if not db_task:
        return False
    db.delete(db_task)
    db.commit()
    return True
