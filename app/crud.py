"""CRUD operations for all models (Students, Profiles, Projects, Tasks, Users)."""

import csv
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from io import StringIO
from typing import Optional

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app import models, schemas
from app.security import hash_password, verify_password


class WriteConflict(Exception):
    """A concurrent write or stale reference violated a database constraint."""


@contextmanager
def write(db: Session) -> Iterator[None]:
    try:
        yield
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        state = getattr(exc.orig, "sqlstate", None)
        sqlite_error = getattr(exc.orig, "sqlite_errorname", None)
        if state in {"23503", "23505"} or sqlite_error in {
            "SQLITE_CONSTRAINT_FOREIGNKEY",
            "SQLITE_CONSTRAINT_UNIQUE",
            "SQLITE_CONSTRAINT_PRIMARYKEY",
        }:
            raise WriteConflict from exc
        raise
    except Exception:
        db.rollback()
        raise


def commit(db: Session) -> None:
    with write(db):
        pass


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
    commit(db)
    db.refresh(db_user)
    return db_user


def get_user(db: Session, user_id: int) -> models.User | None:
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> models.User | None:
    return db.query(models.User).filter(models.User.username == username.lower()).first()


def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email.lower()).first()


def authenticate_user(db: Session, username_or_email: str, password: str) -> models.User | None:
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
    if student.profile:
        db_student.profile = models.Profile(
            bio=student.profile.bio,
            avatar_url=student.profile.avatar_url,
        )

    db.add(db_student)
    commit(db)
    db.refresh(db_student)
    return db_student


def get_student(db: Session, student_id: int) -> models.Student | None:
    return db.query(models.Student).filter(models.Student.id == student_id).first()


def get_student_by_email(db: Session, email: str) -> models.Student | None:
    return db.query(models.Student).filter(models.Student.email == email.lower()).first()


def get_students(db: Session, skip: int = 0, limit: int = 100) -> list[models.Student]:
    return (
        db.query(models.Student)
        .options(selectinload(models.Student.profile))
        .order_by(models.Student.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_student(
    db: Session, student_id: int, student: schemas.StudentUpdate
) -> models.Student | None:
    db_student = get_student(db, student_id)
    if not db_student:
        return None

    update_data = student.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_student, key, value)

    commit(db)
    db.refresh(db_student)
    return db_student


def delete_student(db: Session, student_id: int) -> bool:
    db_student = get_student(db, student_id)
    if not db_student:
        return False
    db.delete(db_student)
    commit(db)
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
    commit(db)
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

    commit(db)
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
    commit(db)
    db.refresh(db_project)
    return db_project


def get_project(db: Session, project_id: int, *, owner_id: int) -> models.Project | None:
    return db.query(models.Project).filter_by(id=project_id, owner_id=owner_id).first()


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
    return query.order_by(models.Project.id).offset(skip).limit(limit).all()


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
    db: Session, db_project: models.Project, project: schemas.ProjectUpdate
) -> models.Project:
    update_data = project.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_project, key, value)

    commit(db)
    db.refresh(db_project)
    return db_project


def delete_project(db: Session, db_project: models.Project) -> None:
    db.delete(db_project)
    commit(db)


# ══════════════════════════════════════════════════════════════════════════════
# TASK CRUD
# ══════════════════════════════════════════════════════════════════════════════


def create_task(
    db: Session,
    project: models.Project,
    task: schemas.TaskCreate,
) -> models.Task:
    validate_assignee(db, task.assignee_id)
    db_task = models.Task(
        project_id=project.id,
        assignee_id=task.assignee_id,
        title=task.title,
        description=task.description,
        status=models.TaskStatus(task.status),
        priority=models.TaskPriority(task.priority),
        due_date=task.due_date.replace(tzinfo=None) if task.due_date else None,
    )

    if task.tag_ids:
        tags = (
            db.query(models.Tag)
            .filter(models.Tag.owner_id == project.owner_id, models.Tag.id.in_(task.tag_ids))
            .all()
        )
        if len(tags) != len(set(task.tag_ids)):
            raise InvalidReference("One or more tags were not found")
        db_task.tags = tags

    db.add(db_task)
    commit(db)
    db.refresh(db_task)
    return db_task


class InvalidReference(Exception):
    """An input references an unavailable resource."""


def validate_assignee(db: Session, assignee_id: int | None) -> None:
    if (
        assignee_id is not None
        and not db.query(models.User.id)
        .filter_by(
            id=assignee_id,
            is_active=True,
        )
        .first()
    ):
        raise InvalidReference("Assignee was not found")


def task_access(actor_id: int, *, owner_only: bool = False) -> ColumnElement[bool]:
    owned = models.Task.project.has(models.Project.owner_id == actor_id)
    if owner_only:
        return owned
    return or_(
        owned,
        (models.Task.assignee_id == actor_id)
        & models.Task.project.has(models.Project.owner_id.is_not(None)),
    )


def get_task(
    db: Session,
    task_id: int,
    *,
    actor_id: int,
    owner_only: bool = False,
) -> models.Task | None:
    return (
        db.query(models.Task)
        .filter(models.Task.id == task_id, task_access(actor_id, owner_only=owner_only))
        .first()
    )


def get_tasks_by_project(
    db: Session, project_id: int, skip: int = 0, limit: int = 100
) -> list[models.Task]:
    return (
        db.query(models.Task)
        .filter(models.Task.project_id == project_id)
        .options(selectinload(models.Task.tags))
        .order_by(models.Task.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def filter_tasks(
    db: Session,
    *,
    actor_id: int,
    project_id: Optional[int] = None,
    assignee_id: Optional[int] = None,
    status: models.TaskStatus | None = None,
    priority: models.TaskPriority | None = None,
    search: Optional[str] = None,
    tag: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[models.Task], int]:
    """Filter tasks with multiple criteria and return both items and total count."""
    query = db.query(models.Task).filter(task_access(actor_id))

    if project_id is not None:
        query = query.filter(models.Task.project_id == project_id)
    if assignee_id is not None:
        query = query.filter(models.Task.assignee_id == assignee_id)
    if status is not None:
        query = query.filter(models.Task.status == status)
    if priority is not None:
        query = query.filter(models.Task.priority == priority)
    if tag:
        query = query.filter(models.Task.tags.any(models.Tag.name == tag.lower().strip()))
    if search:
        query = query.filter(
            or_(
                models.Task.title.ilike(f"%{search}%"),
                models.Task.description.ilike(f"%{search}%"),
            )
        )

    total = query.count()
    items = (
        query.options(selectinload(models.Task.tags))
        .order_by(models.Task.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return items, total


def update_task(db: Session, db_task: models.Task, task: schemas.TaskUpdate) -> models.Task:
    validate_assignee(db, task.assignee_id)
    update_data = task.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "status" and value is not None:
            value = models.TaskStatus(value)
        elif key == "priority" and value is not None:
            value = models.TaskPriority(value)
        elif key == "due_date" and value is not None:
            value = value.replace(tzinfo=None)
        setattr(db_task, key, value)

    commit(db)
    db.refresh(db_task)
    return db_task


def delete_task(db: Session, db_task: models.Task) -> None:
    db.delete(db_task)
    commit(db)


# ══════════════════════════════════════════════════════════════════════════════
# USER PROFILE & PASSWORD CRUD
# ══════════════════════════════════════════════════════════════════════════════


def change_user_password(db: Session, user: models.User, new_password: str) -> None:
    """Change a password only if no concurrent rotation has won."""
    with write(db):
        changed = db.scalar(
            update(models.User)
            .where(models.User.id == user.id, models.User.hashed_password == user.hashed_password)
            .values(hashed_password=hash_password(new_password))
            .returning(models.User.id)
        )
        if changed is None:
            raise WriteConflict


def update_user_email(db: Session, user: models.User, new_email: str) -> models.User:
    """Update user email address."""
    user.email = new_email.lower().strip()
    commit(db)
    db.refresh(user)
    return user


# ══════════════════════════════════════════════════════════════════════════════
# TASK COMMENTS CRUD
# ══════════════════════════════════════════════════════════════════════════════


def create_task_comment(
    db: Session,
    task: models.Task,
    comment: schemas.TaskCommentCreate,
    user: models.User,
) -> models.TaskComment:
    """Create a new comment on a task."""
    db_comment = models.TaskComment(
        task_id=task.id,
        user_id=user.id,
        author_name=user.username,
        content=comment.content.strip(),
    )
    db.add(db_comment)
    commit(db)
    db.refresh(db_comment)
    return db_comment


def get_task_comments(
    db: Session,
    task_id: int,
    *,
    skip: int,
    limit: int,
) -> list[models.TaskComment]:
    """Retrieve all comments for a task ordered chronologically."""
    return (
        db.query(models.TaskComment)
        .filter(models.TaskComment.task_id == task_id)
        .order_by(models.TaskComment.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def delete_task_comment(db: Session, task_id: int, comment_id: int, actor_id: int) -> bool:
    """Delete a comment by ID."""
    comment = (
        db.query(models.TaskComment)
        .filter_by(id=comment_id, task_id=task_id)
        .filter(
            or_(
                models.TaskComment.user_id == actor_id,
                models.TaskComment.task.has(task_access(actor_id, owner_only=True)),
            )
        )
        .first()
    )
    if not comment:
        return False
    db.delete(comment)
    commit(db)
    return True


# ══════════════════════════════════════════════════════════════════════════════
# TAG CRUD
# ══════════════════════════════════════════════════════════════════════════════


def create_tag(db: Session, tag: schemas.TagCreate, *, owner_id: int) -> models.Tag:
    """Create a new tag."""
    db_tag = models.Tag(name=tag.name, color=tag.color, owner_id=owner_id)
    db.add(db_tag)
    commit(db)
    db.refresh(db_tag)
    return db_tag


def get_tags(db: Session, *, owner_id: int, skip: int, limit: int) -> list[models.Tag]:
    return (
        db.query(models.Tag)
        .filter_by(owner_id=owner_id)
        .order_by(models.Tag.name)
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_tag(db: Session, tag_id: int, *, owner_id: int) -> models.Tag | None:
    return db.query(models.Tag).filter_by(id=tag_id, owner_id=owner_id).first()


def get_tag_by_name(db: Session, name: str, *, owner_id: int) -> models.Tag | None:
    return db.query(models.Tag).filter_by(name=name, owner_id=owner_id).first()


def delete_tag(db: Session, tag_id: int, *, owner_id: int) -> bool:
    db_tag = get_tag(db, tag_id, owner_id=owner_id)
    if not db_tag:
        return False
    db.delete(db_tag)
    commit(db)
    return True


def set_task_tag(
    db: Session,
    task: models.Task,
    tag_id: int,
    *,
    owner_id: int,
    attached: bool,
) -> models.Task:
    if get_tag(db, tag_id, owner_id=owner_id) is None:
        raise InvalidReference("Tag not found")
    links = models.task_tags
    with write(db):
        if attached:
            if db.get_bind().dialect.name == "postgresql":
                db.execute(
                    pg_insert(links)
                    .values(task_id=task.id, tag_id=tag_id)
                    .on_conflict_do_nothing(index_elements=[links.c.task_id, links.c.tag_id])
                )
            else:
                db.execute(
                    sqlite_insert(links)
                    .values(task_id=task.id, tag_id=tag_id)
                    .on_conflict_do_nothing(index_elements=[links.c.task_id, links.c.tag_id])
                )
        else:
            db.execute(delete(links).where(links.c.task_id == task.id, links.c.tag_id == tag_id))
    db.expire(task, ["tags"])
    return task


# ══════════════════════════════════════════════════════════════════════════════
# ANALYTICS & STATISTICS CRUD
# ══════════════════════════════════════════════════════════════════════════════


def get_analytics_overview(db: Session, *, owner_id: int) -> schemas.AnalyticsOverviewResponse:
    task = models.Task
    project = models.Project
    project_count = (
        select(func.count(project.id)).where(project.owner_id == owner_id).scalar_subquery()
    )
    statuses = list(models.TaskStatus)
    priorities = list(models.TaskPriority)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    projects, total, overdue, *counts = db.execute(
        select(
            project_count,
            func.count(task.id),
            func.count(task.id).filter(task.due_date < now, task.status != models.TaskStatus.DONE),
            *(func.count(task.id).filter(task.status == status) for status in statuses),
            *(func.count(task.id).filter(task.priority == priority) for priority in priorities),
        )
        .join(task.project)
        .where(project.owner_id == owner_id)
    ).one()
    by_status = dict(
        zip((status.value for status in statuses), counts[: len(statuses)], strict=True)
    )
    by_priority = dict(
        zip((priority.value for priority in priorities), counts[len(statuses) :], strict=True)
    )
    completed = by_status["done"]
    return schemas.AnalyticsOverviewResponse(
        total_projects=projects,
        total_tasks=total,
        completed_tasks=completed,
        in_progress_tasks=by_status["in_progress"],
        todo_tasks=by_status["todo"],
        overdue_tasks=overdue,
        completion_rate_percent=round(completed * 100 / total, 2) if total else 0.0,
        tasks_by_priority=by_priority,
        tasks_by_status=by_status,
    )


def get_project_stats(db: Session, project: models.Project) -> schemas.ProjectStatsResponse:
    task = models.Task
    todo, in_progress, completed = db.execute(
        select(
            *(func.count(task.id).filter(task.status == status) for status in models.TaskStatus)
        ).where(task.project_id == project.id)
    ).one()
    total = todo + in_progress + completed
    return schemas.ProjectStatsResponse(
        project_id=project.id,
        project_name=project.name,
        total_tasks=total,
        completed_tasks=completed,
        in_progress_tasks=in_progress,
        todo_tasks=todo,
        completion_rate_percent=round(completed * 100 / total, 2) if total else 0.0,
    )


def csv_cell(value: str | None) -> str:
    value = value or ""
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def stream_project_csv(db: Session, project_id: int) -> Iterator[str]:
    task = models.Task
    query = (
        select(
            task.id,
            task.title,
            task.status,
            task.priority,
            task.due_date,
            task.created_at,
            task.description,
        )
        .where(task.project_id == project_id)
        .order_by(task.id)
        .execution_options(yield_per=256)
    )
    with db.execute(query) as result:
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            ["ID", "Title", "Status", "Priority", "Due Date", "Created At", "Description"]
        )
        for rows in result.partitions(256):
            for task_id, title, status, priority, due, created, description in rows:
                writer.writerow(
                    [
                        task_id,
                        csv_cell(title),
                        status.value,
                        priority.value,
                        due.isoformat() if due else "",
                        created.isoformat() if created else "",
                        csv_cell(description),
                    ]
                )
            yield output.getvalue()
            output.seek(0)
            output.truncate()
        if output.tell():
            yield output.getvalue()
