"""SQLAlchemy ORM models."""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey, DateTime, Boolean, Enum as SAEnum
)
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class TaskStatus(str, enum.Enum):
    """Enum for task status values."""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriority(str, enum.Enum):
    """Enum for task priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


# ── User (Authentication & Ownership) ────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    projects = relationship(
        "Project", back_populates="owner", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"


# ── Student ↔ Profile (One-to-One) ──────────────────────────────────────────

class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    profile = relationship(
        "Profile", back_populates="student", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Student(id={self.id}, name='{self.name}')>"


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    bio = Column(Text, default="")
    avatar_url = Column(String(500), default="")

    student = relationship("Student", back_populates="profile")

    def __repr__(self) -> str:
        return f"<Profile(id={self.id}, student_id={self.student_id})>"


# ── Project → Tasks (One-to-Many) ───────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="projects")
    tasks = relationship(
        "Task", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name='{self.name}', owner_id={self.owner_id})>"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(300), nullable=False)
    description = Column(Text, default="")
    status = Column(
        SAEnum(TaskStatus, values_callable=lambda x: [e.value for e in x]),
        default=TaskStatus.TODO,
        nullable=False,
        index=True,
    )
    priority = Column(
        SAEnum(TaskPriority, values_callable=lambda x: [e.value for e in x]),
        default=TaskPriority.MEDIUM,
        nullable=False,
        index=True,
    )
    due_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="tasks")

    def __repr__(self) -> str:
        return (
            f"<Task(id={self.id}, title='{self.title}', status='{self.status}', "
            f"priority='{self.priority}')>"
        )
