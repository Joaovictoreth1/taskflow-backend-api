"""Application settings shared by the API, migrations, and tooling."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./taskflow.db"
    secret_key: SecretStr | None = None
    access_token_expire_minutes: int = Field(default=60, ge=1, le=1440)
    cors_origins: list[str] = Field(default_factory=list)
    rate_limit_storage_uri: SecretStr = SecretStr("memory://")
    max_request_body_bytes: int = Field(default=65_536, ge=32_768, le=1_048_576)

    @field_validator("database_url")
    @classmethod
    def supported_database(cls, value: str) -> str:
        try:
            url = make_url(value)
        except ArgumentError:
            raise ValueError("Invalid database URL") from None
        if url.drivername not in {"postgresql", "postgresql+psycopg", "sqlite", "sqlite+pysqlite"}:
            raise ValueError("Use a SQLite or PostgreSQL database URL")
        return value

    @field_validator("cors_origins")
    @classmethod
    def explicit_origins(cls, values: list[str]) -> list[str]:
        for origin in values:
            parts = urlsplit(origin)
            if (
                parts.scheme not in {"http", "https"}
                or not parts.hostname
                or parts.username is not None
                or parts.path
                or parts.query
                or parts.fragment
                or "*" in origin
            ):
                raise ValueError("CORS origins must be explicit HTTP(S) origins without a path")
        return values

    @model_validator(mode="after")
    def production_services(self) -> "Settings":
        if self.app_env == "production":
            if self.sqlalchemy_url.get_backend_name() != "postgresql":
                raise ValueError("Production requires PostgreSQL")
            if not self.rate_limit_storage_uri.get_secret_value().startswith(
                ("redis://", "rediss://")
            ):
                raise ValueError("Production requires shared Redis rate-limit storage")
        return self

    @property
    def sqlalchemy_url(self) -> URL:
        url = make_url(self.database_url)
        return url.set(drivername="postgresql+psycopg") if url.drivername == "postgresql" else url

    def signing_key(self) -> str:
        key = self.secret_key.get_secret_value() if self.secret_key else ""
        if (
            len(key.encode()) < 32
            or len(set(key)) < 12
            or "change" in key.lower()
            or "taskflow" in key.lower()
        ):
            raise RuntimeError("Set SECRET_KEY to a randomly generated value of at least 32 bytes")
        return key


settings = Settings()
