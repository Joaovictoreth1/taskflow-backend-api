"""Pydantic v2 schemas with strict validation."""

import re
from datetime import datetime, timezone
from typing import Annotated, Generic, Optional, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

T = TypeVar("T")
MAX_ID = 2_147_483_647
PositiveID = Annotated[int, Field(gt=0, le=MAX_ID)]
StripText = Annotated[str, StringConstraints(strip_whitespace=True)]


def empty_text(value: object) -> object:
    return "" if value is None else value


LegacyText = Annotated[str, BeforeValidator(empty_text)]


def as_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


UTCDateTime = Annotated[datetime, AfterValidator(as_utc)]


def validate_bcrypt_length(value: str) -> str:
    if len(value.encode()) > 72:
        raise ValueError("Password must not exceed 72 UTF-8 bytes")
    return value


Password = Annotated[
    str, Field(min_length=8, max_length=72), AfterValidator(validate_bcrypt_length)
]


def reject_null(value: T | None) -> T:
    if value is None:
        raise ValueError("Field may be omitted but cannot be null")
    return value


# ── Generic Pagination Envelope ──────────────────────────────────────────────


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int


# ── Auth & User Schemas ──────────────────────────────────────────────────────


class UserBase(BaseModel):
    username: StripText = Field(..., min_length=3, max_length=50)
    email: str = Field(..., max_length=255)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Username may only contain letters, numbers, underscores, and hyphens")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, v):
            raise ValueError("Invalid email format")
        return v.lower().strip()


class UserCreate(UserBase):
    model_config = ConfigDict(extra="forbid")

    password: Password


class UserUpdate(BaseModel):
    email: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    is_active: Optional[bool] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, v):
            raise ValueError("Invalid email format")
        return v.lower().strip()


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    is_superuser: bool
    created_at: datetime


class UserLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int = 60
    user: UserResponse


class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None


# ── Profile Schemas ──────────────────────────────────────────────────────────


class ProfileBase(BaseModel):
    bio: str = Field(default="", max_length=2000)
    avatar_url: str = Field(default="", max_length=500)


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(BaseModel):
    bio: Optional[str] = Field(default=None, max_length=2000)
    avatar_url: Optional[str] = Field(default=None, max_length=500)
    _non_nullable = field_validator("bio", "avatar_url")(reject_null)


class ProfileResponse(ProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    bio: LegacyText
    avatar_url: LegacyText


# ── Student Schemas ──────────────────────────────────────────────────────────


class StudentBase(BaseModel):
    name: StripText = Field(..., min_length=2, max_length=120)
    email: str = Field(..., max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, v):
            raise ValueError("Invalid email format")
        return v.lower().strip()


class StudentCreate(StudentBase):
    profile: Optional[ProfileCreate] = None


class StudentUpdate(BaseModel):
    name: StripText | None = Field(default=None, min_length=2, max_length=120)
    email: Optional[str] = Field(default=None, max_length=255)
    _non_nullable = field_validator("name", "email")(reject_null)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, v):
            raise ValueError("Invalid email format")
        return v.lower().strip()


class StudentResponse(StudentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    profile: Optional[ProfileResponse] = None


# ── Tag Schemas ──────────────────────────────────────────────────────────────


class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    color: str = Field(default="#0ea5e9", max_length=7)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError("Tag name may only contain letters, numbers, hyphens, and underscores")
        return v.lower()

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", v):
            raise ValueError("Color must be a valid hex color code (e.g. #0ea5e9 or #fff)")
        return v


class TagCreate(TagBase):
    pass


class TagResponse(TagBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


# ── Task Schemas ─────────────────────────────────────────────────────────────


class TaskBase(BaseModel):
    title: StripText = Field(..., min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    status: str = Field(default="todo")
    priority: str = Field(default="medium")
    due_date: UTCDateTime | None = None
    assignee_id: PositiveID | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"todo", "in_progress", "done"}
        if v not in allowed:
            raise ValueError(f"Status must be one of: {', '.join(sorted(allowed))}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        allowed = {"low", "medium", "high", "urgent"}
        if v not in allowed:
            raise ValueError(f"Priority must be one of: {', '.join(sorted(allowed))}")
        return v


class TaskCreate(TaskBase):
    model_config = ConfigDict(extra="forbid")

    tag_ids: list[PositiveID] = Field(default_factory=list, max_length=100)


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: StripText | None = Field(default=None, min_length=1, max_length=300)
    description: Optional[str] = Field(default=None, max_length=5000)
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: UTCDateTime | None = None
    assignee_id: PositiveID | None = None

    _non_nullable = field_validator("title", "description", "status", "priority")(reject_null)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"todo", "in_progress", "done"}
        if v not in allowed:
            raise ValueError(f"Status must be one of: {', '.join(sorted(allowed))}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"low", "medium", "high", "urgent"}
        if v not in allowed:
            raise ValueError(f"Priority must be one of: {', '.join(sorted(allowed))}")
        return v


class TaskResponse(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_at: UTCDateTime
    description: LegacyText = ""
    tags: list[TagResponse] = Field(default_factory=list)


# ── Project Schemas ──────────────────────────────────────────────────────────


class ProjectBase(BaseModel):
    name: StripText = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)


class ProjectCreate(ProjectBase):
    model_config = ConfigDict(extra="forbid")


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: StripText | None = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    _non_nullable = field_validator("name", "description")(reject_null)


class ProjectSummary(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: Optional[int] = None
    created_at: UTCDateTime
    description: LegacyText = ""


class ProjectResponse(ProjectSummary):
    tasks: list[TaskResponse] = Field(default_factory=list)


# ── Task Comment Schemas ─────────────────────────────────────────────────────


class TaskCommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    model_config = ConfigDict(str_strip_whitespace=True)


class TaskCommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    user_id: Optional[int] = None
    author_name: str
    content: str
    created_at: datetime


# ── Password & Profile Management ────────────────────────────────────────────


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: Password


class UpdateProfileRequest(BaseModel):
    email: Optional[str] = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, v):
            raise ValueError("Invalid email format")
        return v.lower().strip()


# ── Analytics & Statistics Schemas ───────────────────────────────────────────


class AnalyticsOverviewResponse(BaseModel):
    total_projects: int
    total_tasks: int
    completed_tasks: int
    in_progress_tasks: int
    todo_tasks: int
    overdue_tasks: int
    completion_rate_percent: float
    tasks_by_priority: dict[str, int]
    tasks_by_status: dict[str, int]


class ProjectStatsResponse(BaseModel):
    project_id: int
    project_name: str
    total_tasks: int
    completed_tasks: int
    in_progress_tasks: int
    todo_tasks: int
    completion_rate_percent: float
