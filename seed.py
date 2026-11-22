"""
Database Seeder for TaskFlow API.
Populates realistic demo users, projects, tasks, tags, and comments.

Usage:
    python seed.py
"""

from datetime import datetime, timezone, timedelta
from app.database import Base, engine, get_db
from app import models, crud, schemas


def seed():
    print("🌱 Initializing TaskFlow database schema...")
    Base.metadata.create_all(bind=engine)

    with next(get_db()) as db:
        # Check if already seeded
        if db.query(models.User).filter_by(username="admin").first():
            print("⚠️  Database appears to be already seeded. Skipping.")
            return

        print("👤 Creating demo users...")
        admin = crud.create_user(db, schemas.UserCreate(
            username="admin",
            email="admin@taskflow.dev",
            password="AdminPassword123!",
        ))
        admin.is_superuser = True
        db.commit()

        dev1 = crud.create_user(db, schemas.UserCreate(
            username="lucas_backend",
            email="lucas@taskflow.dev",
            password="DevPassword123!",
        ))
        dev2 = crud.create_user(db, schemas.UserCreate(
            username="mariana_design",
            email="mariana@taskflow.dev",
            password="DevPassword123!",
        ))

        print("🏷️  Creating tags...")
        tags_data = [
            ("backend", "#0ea5e9"),
            ("frontend", "#8b5cf6"),
            ("bug", "#ef4444"),
            ("feature", "#10b981"),
            ("devops", "#f59e0b"),
            ("docs", "#64748b"),
        ]
        tag_map = {}
        for name, color in tags_data:
            tag_map[name] = crud.create_tag(db, schemas.TagCreate(name=name, color=color))

        print("📁 Creating projects...")
        p1 = crud.create_project(db, schemas.ProjectCreate(
            name="E-Commerce Core Refactoring",
            description="Microservices migration and payment gateway integration.",
        ), owner_id=admin.id)

        p2 = crud.create_project(db, schemas.ProjectCreate(
            name="Mobile App React Native",
            description="Cross-platform iOS and Android client application.",
        ), owner_id=dev1.id)

        p3 = crud.create_project(db, schemas.ProjectCreate(
            name="Cloud Infrastructure & Observability",
            description="Kubernetes clusters, Prometheus metrics and Grafana dashboards.",
        ), owner_id=admin.id)

        print("✅ Creating tasks with tags, priorities, and assignees...")
        now = datetime.now(timezone.utc)

        t1 = crud.create_task(db, p1.id, schemas.TaskCreate(
            title="Design idempotency keys for Stripe checkout",
            description="Prevent double-charges during network timeouts with Redis distributed locks.",
            status="done",
            priority="urgent",
            assignee_id=dev1.id,
            tag_ids=[tag_map["backend"].id, tag_map["feature"].id],
        ))

        t2 = crud.create_task(db, p1.id, schemas.TaskCreate(
            title="Audit SQL N+1 queries in product listing endpoint",
            description="Use SQLAlchemy joinedload to optimize eager loading across categories.",
            status="in_progress",
            priority="high",
            due_date=now - timedelta(days=1),  # Overdue
            assignee_id=dev1.id,
            tag_ids=[tag_map["backend"].id, tag_map["bug"].id],
        ))

        t3 = crud.create_task(db, p2.id, schemas.TaskCreate(
            title="Implement biometric face-id authentication",
            description="Integrate react-native-keychain with Secure Enclave.",
            status="todo",
            priority="medium",
            due_date=now + timedelta(days=5),
            assignee_id=dev2.id,
            tag_ids=[tag_map["frontend"].id, tag_map["feature"].id],
        ))

        t4 = crud.create_task(db, p3.id, schemas.TaskCreate(
            title="Configure GitHub Actions CI/CD matrix pipeline",
            description="Automate Docker build, vulnerability scan with Trivy, and push to ECR.",
            status="done",
            priority="high",
            assignee_id=admin.id,
            tag_ids=[tag_map["devops"].id],
        ))

        print("💬 Adding collaboration comments...")
        crud.create_task_comment(db, t1.id, schemas.TaskCommentCreate(
            content="Validated with Stripe CLI test webhooks, latency under 45ms.",
        ), user=dev1)
        crud.create_task_comment(db, t1.id, schemas.TaskCommentCreate(
            content="Great work! Approved for staging deployment.",
        ), user=admin)
        crud.create_task_comment(db, t2.id, schemas.TaskCommentCreate(
            content="Identified query bottleneck in category relationship, working on patch.",
        ), user=dev1)

        print("\n✨ Database successfully seeded with demo data!")
        print(f"   - Users: admin, lucas_backend, mariana_design")
        print(f"   - Projects: 3")
        print(f"   - Tasks: 4 (with tags and assignees)")
        print(f"   - Tags: 6")
        print(f"   - Comments: 3")


if __name__ == "__main__":
    seed()
