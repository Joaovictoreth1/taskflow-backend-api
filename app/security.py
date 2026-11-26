"""Security and authentication utilities (JWT, password hashing)."""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.config import jwt_settings

PASSWORD_MAX_BYTES = 72
SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES = jwt_settings()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    except ValueError:
        return False


def create_access_token(
    data: dict[str, Any], expires_delta: timedelta | None = None
) -> str:
    now = datetime.now(timezone.utc)
    duration = (
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        if expires_delta is None
        else expires_delta
    )
    return jwt.encode(
        {**data, "exp": now + duration, "iat": now}, SECRET_KEY, algorithm=ALGORITHM
    )


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM], options={"require": ["exp"]}
        )
    except jwt.InvalidTokenError:
        return None
