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

    username: str = payload.get("sub")
    if username is None:
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
    """Retrieve authenticated user if token present, otherwise None without failing."""
    if not token:
        return None
    payload = decode_access_token(token)
    if payload is None:
        return None
    username = payload.get("sub")
    if not username:
        return None
    return crud.get_user_by_username(db, username=username)
