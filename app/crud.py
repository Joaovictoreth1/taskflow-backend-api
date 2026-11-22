"""CRUD operations for all models (Students, Profiles, Projects, Tasks, Users)."""

from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

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
        assignee_id=task.assignee_id,
        title=task.title,
        description=task.description,
        status=models.TaskStatus(task.status),
        priority=models.TaskPriority(task.priority),
        due_date=task.due_date,
    )

    if getattr(task, "tag_ids", None):
        tags = db.query(models.Tag).filter(models.Tag.id.in_(task.tag_ids)).all()
        db_task.tags = tags

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
    assignee_id: Optional[int] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    tag: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[models.Task], int]:
    """Filter tasks with multiple criteria and return both items and total count."""
    query = db.query(models.Task)

    if project_id is not None:
        query = query.filter(models.Task.project_id == project_id)
    if assignee_id is not None:
        query = query.filter(models.Task.assignee_id == assignee_id)
    if status is not None:
        query = query.filter(models.Task.status == models.TaskStatus(status))
    if priority is not None:
        query = query.filter(models.Task.priority == models.TaskPriority(priority))
    if tag:
        query = query.join(models.Task.tags).filter(models.Tag.name == tag.lower().strip())
    if search:
        query = query.filter(
            or_(
                models.Task.title.ilike(f"%{search}%"),
                models.Task.description.ilike(f"%{search}%"),
            )
        )

    total = query.distinct().count()
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


# ══════════════════════════════════════════════════════════════════════════════
# USER PROFILE & PASSWORD CRUD
# ══════════════════════════════════════════════════════════════════════════════

def change_user_password(db: Session, user: models.User, new_password: str) -> None:
    """Update user password with new bcrypt hash."""
    user.hashed_password = hash_password(new_password)
    db.commit()
    db.refresh(user)


def update_user_email(db: Session, user: models.User, new_email: str) -> models.User:
    """Update user email address."""
    user.email = new_email.lower().strip()
    db.commit()
    db.refresh(user)
    return user


# ══════════════════════════════════════════════════════════════════════════════
# TASK COMMENTS CRUD
# ══════════════════════════════════════════════════════════════════════════════

def create_task_comment(
    db: Session,
    task_id: int,
    comment: schemas.TaskCommentCreate,
    user: Optional[models.User] = None,
    guest_name: str = "Anonymous",
) -> models.TaskComment | None:
    """Create a new comment on a task."""
    task = get_task(db, task_id)
    if not task:
        return None

    author = user.username if user else guest_name
    user_id = user.id if user else None

    db_comment = models.TaskComment(
        task_id=task_id,
        user_id=user_id,
        author_name=author,
        content=comment.content.strip(),
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment


def get_task_comments(db: Session, task_id: int) -> list[models.TaskComment]:
    """Retrieve all comments for a task ordered chronologically."""
    return (
        db.query(models.TaskComment)
        .filter(models.TaskComment.task_id == task_id)
        .order_by(models.TaskComment.id.asc())
        .all()
    )


def delete_task_comment(db: Session, comment_id: int) -> bool:
    """Delete a comment by ID."""
    comment = db.query(models.TaskComment).filter(models.TaskComment.id == comment_id).first()
    if not comment:
        return False
    db.delete(comment)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# TAG CRUD
# ══════════════════════════════════════════════════════════════════════════════

def create_tag(db: Session, tag: schemas.TagCreate) -> models.Tag:
    """Create a new tag."""
    db_tag = models.Tag(name=tag.name.lower().strip(), color=tag.color.lower().strip())
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag


def get_tags(db: Session) -> list[models.Tag]:
    """Retrieve all available tags."""
    return db.query(models.Tag).order_by(models.Tag.name.asc()).all()


def get_tag(db: Session, tag_id: int) -> models.Tag | None:
    return db.query(models.Tag).filter(models.Tag.id == tag_id).first()


def get_tag_by_name(db: Session, name: str) -> models.Tag | None:
    return db.query(models.Tag).filter(models.Tag.name == name.lower().strip()).first()


def delete_tag(db: Session, tag_id: int) -> bool:
    db_tag = get_tag(db, tag_id)
    if not db_tag:
        return False
    db.delete(db_tag)
    db.commit()
    return True


def add_tag_to_task(db: Session, task_id: int, tag_id: int) -> models.Task | None:
    task = get_task(db, task_id)
    tag = get_tag(db, tag_id)
    if not task or not tag:
        return None
    if tag not in task.tags:
        task.tags.append(tag)
        db.commit()
        db.refresh(task)
    return task


def remove_tag_from_task(db: Session, task_id: int, tag_id: int) -> models.Task | None:
    task = get_task(db, task_id)
    tag = get_tag(db, tag_id)
    if not task or not tag:
        return None
    if tag in task.tags:
        task.tags.remove(tag)
        db.commit()
        db.refresh(task)
    return task


# ══════════════════════════════════════════════════════════════════════════════
# ANALYTICS & STATISTICS CRUD
# ══════════════════════════════════════════════════════════════════════════════

def get_analytics_overview(db: Session) -> dict:
    """Compute global task management analytics and KPIs."""
    total_projects = db.query(models.Project).count()
    all_tasks = db.query(models.Task).all()
    total_tasks = len(all_tasks)

    tasks_by_status = {"todo": 0, "in_progress": 0, "done": 0}
    tasks_by_priority = {"low": 0, "medium": 0, "high": 0, "urgent": 0}

    now = datetime.now(timezone.utc)
    overdue_count = 0

    for task in all_tasks:
        s_val = task.status.value if hasattr(task.status, "value") else str(task.status)
        p_val = task.priority.value if hasattr(task.priority, "value") else str(task.priority)

        if s_val in tasks_by_status:
            tasks_by_status[s_val] += 1
        if p_val in tasks_by_priority:
            tasks_by_priority[p_val] += 1

        if task.due_date:
            due = task.due_date
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            if due < now and s_val != "done":
                overdue_count += 1

    completed = tasks_by_status["done"]
    in_progress = tasks_by_status["in_progress"]
    todo = tasks_by_status["todo"]
    completion_rate = round((completed / total_tasks) * 100, 2) if total_tasks > 0 else 0.0

    return {
        "total_projects": total_projects,
        "total_tasks": total_tasks,
        "completed_tasks": completed,
        "in_progress_tasks": in_progress,
        "todo_tasks": todo,
        "overdue_tasks": overdue_count,
        "completion_rate_percent": completion_rate,
        "tasks_by_priority": tasks_by_priority,
        "tasks_by_status": tasks_by_status,
    }


def get_project_stats(db: Session, project_id: int) -> dict | None:
    """Compute metrics for a specific project."""
    project = get_project(db, project_id)
    if not project:
        return None

    tasks = project.tasks
    total = len(tasks)
    completed = sum(1 for t in tasks if (t.status.value if hasattr(t.status, "value") else str(t.status)) == "done")
    in_progress = sum(1 for t in tasks if (t.status.value if hasattr(t.status, "value") else str(t.status)) == "in_progress")
    todo = sum(1 for t in tasks if (t.status.value if hasattr(t.status, "value") else str(t.status)) == "todo")
    rate = round((completed / total) * 100, 2) if total > 0 else 0.0

    return {
        "project_id": project.id,
        "project_name": project.name,
        "total_tasks": total,
        "completed_tasks": completed,
        "in_progress_tasks": in_progress,
        "todo_tasks": todo,
        "completion_rate_percent": rate,
    }
