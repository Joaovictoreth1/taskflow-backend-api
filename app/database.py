"""Database configuration and session management."""

import sqlite3
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings


class Base(DeclarativeBase):
    pass


def build_engine(url: URL | str, *, shared_memory: bool = False) -> Engine:
    if make_url(url).get_backend_name() == "sqlite":
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool if shared_memory else None,
            hide_parameters=True,
        )

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection: sqlite3.Connection, record: object) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        return engine
    return create_engine(
        url, pool_pre_ping=True, connect_args={"connect_timeout": 5}, hide_parameters=True
    )


engine = build_engine(settings.sqlalchemy_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
