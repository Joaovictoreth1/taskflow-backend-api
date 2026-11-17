"""CRUD operations for all models."""

from sqlalchemy.orm import Session
from app import models, schemas


# ── Student CRUD ─────────────────────────────────────────────────────────────

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


# ── Profile CRUD ─────────────────────────────────────────────────────────────

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


# ── Project CRUD ─────────────────────────────────────────────────────────────

def create_project(db: Session, project: schemas.ProjectCreate) -> models.Project:
    db_project = models.Project(name=project.name, description=project.description)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


def get_project(db: Session, project_id: int) -> models.Project | None:
    return db.query(models.Project).filter(models.Project.id == project_id).first()


def get_projects(db: Session, skip: int = 0, limit: int = 100) -> list[models.Project]:
    return db.query(models.Project).offset(skip).limit(limit).all()


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


# ── Task CRUD ────────────────────────────────────────────────────────────────

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
