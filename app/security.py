"""Password hashing and signed access tokens."""

import hmac
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.config import settings

TOKEN_ALGORITHM = "HS256"
SIGNING_KEY = settings.signing_key()
ISSUER = "taskflow-api"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    except ValueError:
        return False


def credential_stamp(hashed_password: str) -> str:
    return hmac.digest(
        SIGNING_KEY.encode(), b"password:" + hashed_password.encode(), "sha256"
    ).hex()


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    now = datetime.now(timezone.utc)
    ttl = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    claims = {**data, "exp": now + ttl, "iat": now, "iss": ISSUER}
    return jwt.encode(claims, SIGNING_KEY, algorithm=TOKEN_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(
            token,
            SIGNING_KEY,
            algorithms=[TOKEN_ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "iat", "iss", "sub", "pwd", "user_id"]},
        )
    except jwt.InvalidTokenError:
        return None
