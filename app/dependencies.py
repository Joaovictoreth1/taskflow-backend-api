"""FastAPI dependency injection utilities for authentication and database sessions."""

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app import crud, models
from app.database import get_db
from app.schemas import MAX_ID
from app.security import credential_stamp, decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    """Retrieve the authenticated user from the Bearer JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    username = payload.get("sub")
    if not isinstance(username, str):
        raise credentials_exception

    stamp = payload.get("pwd")
    if not isinstance(stamp, str) or not stamp.isascii() or type(payload.get("user_id")) is not int:
        raise credentials_exception
    user = crud.get_user(db, user_id=payload["user_id"])
    if (
        user is None
        or user.username != username
        or not hmac.compare_digest(
            stamp,
            credential_stamp(user.hashed_password),
        )
    ):
        raise credentials_exception

    return user


def get_current_active_user(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    """Ensure the authenticated user account is active."""
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user account")
    return current_user


CurrentUser = Annotated[models.User, Depends(get_current_active_user)]
Database = Annotated[Session, Depends(get_db)]
ResourceID = Annotated[int, Path(gt=0, le=MAX_ID)]


def require_directory_admin(user: CurrentUser) -> None:
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Directory administrator required")


def require_owned_project(
    project_id: ResourceID, user: CurrentUser, db: Database
) -> models.Project:
    project = crud.get_project(db, project_id, owner_id=user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def require_owned_task(task_id: ResourceID, user: CurrentUser, db: Database) -> models.Task:
    task = crud.get_task(db, task_id, actor_id=user.id, owner_only=True)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def require_visible_task(task_id: ResourceID, user: CurrentUser, db: Database) -> models.Task:
    task = crud.get_task(db, task_id, actor_id=user.id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


OwnedProject = Annotated[models.Project, Depends(require_owned_project)]
OwnedTask = Annotated[models.Task, Depends(require_owned_task)]
VisibleTask = Annotated[models.Task, Depends(require_visible_task)]
