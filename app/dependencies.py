"""FastAPI dependency injection utilities for authentication and database sessions."""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import decode_access_token
from app import crud, models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
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
    if not isinstance(username, str) or not username:
        raise credentials_exception

    user = crud.get_user_by_username(db, username=username)
    if user is None:
        raise credentials_exception

    return user


def get_current_active_user(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    """Ensure the authenticated user account is active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user account"
        )
    return current_user


def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    """Allow anonymous requests, but reject invalid supplied bearer tokens."""
    if token is None:
        return None
    return get_current_active_user(get_current_user(token, db))


def check_project_writer(project: models.Project, user: models.User | None) -> None:
    if project.owner_id is None:
        return
    if user is None:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    if user.id != project.owner_id and not user.is_superuser:
        raise HTTPException(403, "Project write access denied")


def require_project_write(
    project_id: int,
    user: models.User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> None:
    project = crud.get_project(db, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    check_project_writer(project, user)


def require_task_write(
    task_id: int,
    user: models.User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> None:
    task = crud.get_task(db, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    check_project_writer(task.project, user)
