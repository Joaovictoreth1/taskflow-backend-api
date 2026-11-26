"""add tags and task assignee

Revision ID: 204f57baebb7
Revises: 6b6cb06a921a
Create Date: 2026-11-22 03:05:22.209834

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "204f57baebb7"
down_revision: Union[str, Sequence[str], None] = "6b6cb06a921a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False, server_default="#0ea5e9"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("tags", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_tags_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_tags_name"), ["name"], unique=True)

    op.create_table(
        "task_tags",
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "tag_id"),
    )

    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("assignee_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_tasks_assignee_id_users", "users", ["assignee_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_index(batch_op.f("ix_tasks_assignee_id"), ["assignee_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tasks_assignee_id"))
        batch_op.drop_constraint("fk_tasks_assignee_id_users", type_="foreignkey")
        batch_op.drop_column("assignee_id")

    op.drop_table("task_tags")

    with op.batch_alter_table("tags", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tags_name"))
        batch_op.drop_index(batch_op.f("ix_tags_id"))

    op.drop_table("tags")
