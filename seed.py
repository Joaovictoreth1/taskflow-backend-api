"""Create one opt-in collaboration demo in a migrated development database."""

import os

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Project, Tag, Task, TaskComment, TaskPriority, User
from app.schemas import UserCreate
from app.security import hash_password


def seed() -> None:
    if settings.app_env != "development":
        raise SystemExit("Seeding is only available in development")
    password = os.environ.get("SEED_PASSWORD")
    if not password:
        raise SystemExit("Set SEED_PASSWORD before seeding")
    with SessionLocal.begin() as db:
        if db.scalar(select(User.id).where(User.username == "demo_owner")) is not None:
            print("Demo already exists")
            return
        owner_input = UserCreate(
            username="demo_owner", email="demo_owner@example.test", password=password
        )
        collaborator_input = UserCreate(
            username="demo_collab", email="demo_collab@example.test", password=password
        )
        owner = User(
            username=owner_input.username,
            email=owner_input.email,
            hashed_password=hash_password(owner_input.password),
            is_superuser=True,
        )
        collaborator = User(
            username=collaborator_input.username,
            email=collaborator_input.email,
            hashed_password=hash_password(collaborator_input.password),
        )
        db.add_all([owner, collaborator])
        db.flush()
        task = Task(
            project=Project(name="Demo project", owner=owner),
            assignee=collaborator,
            title="Review the demo",
            priority=TaskPriority.HIGH,
            tags=[Tag(name="demo", owner_id=owner.id)],
            comments=[
                TaskComment(user=owner, author_name=owner.username, content="Ready for review.")
            ],
        )
        db.add(task)
    print("Demo accounts: demo_owner and demo_collab")


if __name__ == "__main__":
    seed()
