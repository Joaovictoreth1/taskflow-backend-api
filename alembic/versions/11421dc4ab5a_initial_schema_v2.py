"""Create the complete base schema.

Revision ID: 11421dc4ab5a
"""

import sqlalchemy as sa

from alembic import op

revision = "11421dc4ab5a"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_students_id", "students", ["id"])
    op.create_index("ix_students_email", "students", ["email"], unique=True)
    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("students.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("bio", sa.Text()),
        sa.Column("avatar_url", sa.String(500)),
    )
    op.create_index("ix_profiles_id", "profiles", ["id"])
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", name="fk_projects_owner_id_users", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_projects_id", "projects", ["id"])
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column(
            "status", sa.Enum("todo", "in_progress", "done", name="taskstatus"), nullable=False
        ),
        sa.Column(
            "priority",
            sa.Enum("low", "medium", "high", "urgent", name="taskpriority"),
            nullable=False,
        ),
        sa.Column("due_date", sa.DateTime()),
        sa.Column("created_at", sa.DateTime()),
    )
    for field in ("id", "project_id", "status", "priority"):
        op.create_index(f"ix_tasks_{field}", "tasks", [field])


def downgrade() -> None:
    for table in ("tasks", "profiles", "students", "projects", "users"):
        op.drop_table(table)
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP TYPE taskstatus")
        op.execute("DROP TYPE taskpriority")
