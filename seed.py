"""Populate a migrated, local SQLite database with a sample workspace."""

import os

from app.database import SessionLocal, engine
from app.models import Project, Tag, Task, TaskComment, User
from app.security import hash_password


def seed() -> None:
    if os.getenv("TASKFLOW_SEED_DEMO") != "1" or engine.url.get_backend_name() != "sqlite":
        raise SystemExit("Demo seeding requires TASKFLOW_SEED_DEMO=1 and a local SQLite database")
    password = os.getenv("TASKFLOW_SEED_PASSWORD", "")
    if not 16 <= len(password.encode()) <= 72:
        raise SystemExit("TASKFLOW_SEED_PASSWORD must contain 16–72 UTF-8 bytes")

    with SessionLocal.begin() as db:
        if db.query(User).filter_by(username="taskflow_demo").first() is not None:
            print("Demo workspace already exists")
            return

        user = User(
            username="taskflow_demo",
            email="taskflow_demo@example.invalid",
            hashed_password=hash_password(password),
        )
        project = Project(name="TaskFlow demo", description="Sample workspace", owner=user)
        tag = db.query(Tag).filter_by(name="demo").first() or Tag(name="demo")
        task = Task(
            title="Review the TaskFlow API",
            project=project,
            tags=[tag],
            assignee=user,
            comments=[
                TaskComment(author_name=user.username, user=user, content="Welcome to TaskFlow")
            ],
        )
        db.add(task)
    print("Created demo workspace for taskflow_demo")


if __name__ == "__main__":
    seed()
