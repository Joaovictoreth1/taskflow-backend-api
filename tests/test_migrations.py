from collections.abc import Iterator
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.config import settings
from app.database import build_engine, get_db
from app.main import app
from tests.conftest import client, test_engine

PREVIOUS_HEAD = "204f57baebb7"


@pytest.fixture
def migration_database(tmp_path, monkeypatch) -> Iterator[Engine]:
    postgres = test_engine.dialect.name == "postgresql"
    if postgres:
        schema = f"migration_{uuid4().hex}"
        with test_engine.begin() as db:
            db.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = test_engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    else:
        url = f"sqlite:///{tmp_path / 'migration.sqlite3'}"
    db_engine = build_engine(url)
    monkeypatch.setattr(
        settings, "database_url", db_engine.url.render_as_string(hide_password=False)
    )
    try:
        yield db_engine
    finally:
        db_engine.dispose()
        if postgres:
            with test_engine.begin() as db:
                db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_empty_database_bootstrap_matches_models_and_readiness(migration_database):
    configuration = Config("alembic.ini")
    command.upgrade(configuration, "head")
    command.check(configuration)
    assert_ready(migration_database, status=200)
    command.downgrade(configuration, PREVIOUS_HEAD)
    assert_ready(migration_database, status=503)
    command.downgrade(configuration, "base")
    command.upgrade(configuration, "head")
    command.check(configuration)


def assert_ready(engine: Engine, *, status: int) -> None:
    make_session = sessionmaker(bind=engine)

    def override() -> Iterator[Session]:
        with make_session() as session:
            yield session

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = override
    try:
        response = client.get("/ready")
        assert response.status_code == status
    finally:
        app.dependency_overrides[get_db] = previous


def test_upgrade_preserves_legacy_labels_per_owner_and_keeps_unclaimed_data(migration_database):
    configuration = Config("alembic.ini")
    command.upgrade(configuration, PREVIOUS_HEAD)
    with migration_database.begin() as db:
        users = (
            db.execute(
                text("""
            INSERT INTO users (username, email, hashed_password, is_active, is_superuser)
            VALUES ('owner_a', 'a@example.test', 'not-for-login', TRUE, FALSE),
                   ('owner_b', 'b@example.test', 'not-for-login', TRUE, FALSE)
            RETURNING id
        """)
            )
            .scalars()
            .all()
        )
        projects = (
            db.execute(
                text("""
            INSERT INTO projects (name, owner_id) VALUES ('A', :a), ('B', :b), ('Unclaimed', NULL)
            RETURNING id
        """),
                {"a": users[0], "b": users[1]},
            )
            .scalars()
            .all()
        )
        tasks = (
            db.execute(
                text("""
            INSERT INTO tasks (title, project_id, status, priority)
            VALUES ('One', :a, 'todo', 'medium'), ('Two', :b, 'done', 'urgent'),
                   ('Three', :unclaimed, 'todo', 'low')
            RETURNING id
        """),
                dict(zip(("a", "b", "unclaimed"), projects, strict=True)),
            )
            .scalars()
            .all()
        )
        tag = db.execute(
            text("INSERT INTO tags (name, color) VALUES ('shared', '#102030') RETURNING id")
        ).scalar_one()
        db.execute(
            text("INSERT INTO task_tags VALUES (:task, :tag)"),
            [{"task": task, "tag": tag} for task in tasks],
        )
        db.execute(
            text(
                "INSERT INTO task_comments (task_id, author_name, content) VALUES (:task, 'Anonymous', 'Legacy comment')"
            ),
            {"task": tasks[0]},
        )

    command.upgrade(configuration, "head")
    with migration_database.connect() as db:
        assert db.execute(
            text("""
            SELECT task_id, owner_id, name, color FROM task_tags JOIN tags ON tags.id = tag_id
            ORDER BY task_id
        """)
        ).all() == [
            (tasks[0], users[0], "shared", "#102030"),
            (tasks[1], users[1], "shared", "#102030"),
            (tasks[2], None, "shared", "#102030"),
        ]
        assert db.scalar(text("SELECT content FROM task_comments")) == "Legacy comment"
        if migration_database.dialect.name == "sqlite":
            assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    command.downgrade(configuration, PREVIOUS_HEAD)
    with migration_database.connect() as db:
        assert db.execute(text("SELECT * FROM task_tags ORDER BY task_id")).all() == [
            (task, tag) for task in tasks
        ]
