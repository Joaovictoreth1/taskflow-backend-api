"""Environment-backed application configuration."""

import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./taskflow.db")
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]


def jwt_settings() -> tuple[str, str, int]:
    secret = os.getenv("SECRET_KEY", "")
    algorithm = os.getenv("ALGORITHM", "HS256")
    minimum = {"HS256": 32, "HS384": 48, "HS512": 64}.get(algorithm)
    if minimum is None:
        raise RuntimeError("ALGORITHM must be HS256, HS384, or HS512")
    if len(secret) < minimum or any(not "!" <= char <= "~" for char in secret):
        raise RuntimeError(f"SECRET_KEY must contain at least {minimum} printable ASCII characters without spaces")
    try:
        minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    except ValueError:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be an integer") from None
    if not 1 <= minutes <= 1440:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 1440")
    return secret, algorithm, minutes
