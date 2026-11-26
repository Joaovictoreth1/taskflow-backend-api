"""Scope tags to owners and preserve legacy task labels.

Revision ID: 9f63f1a9ad47
Revises: 204f57baebb7
"""

import sqlalchemy as sa

from alembic import op

revision = "9f63f1a9ad47"
down_revision = "204f57baebb7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE tasks SET assignee_id = NULL WHERE assignee_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM users WHERE users.id = tasks.assignee_id)
    """)
    with op.batch_alter_table("tags") as batch:
        batch.drop_index("ix_tags_name")
        batch.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_tags_owner_id_users", "users", ["owner_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_index("ix_tags_owner_name", ["owner_id", "name"], unique=True)
    op.create_index("ix_task_tags_tag_id", "task_tags", ["tag_id"])

    op.execute("""
        INSERT INTO tags (name, color, owner_id)
        SELECT DISTINCT tag.name, tag.color, project.owner_id
        FROM tags AS tag
        JOIN task_tags AS link ON link.tag_id = tag.id
        JOIN tasks AS task ON task.id = link.task_id
        JOIN projects AS project ON project.id = task.project_id
        WHERE tag.owner_id IS NULL AND project.owner_id IS NOT NULL
    """)
    op.execute("""
        INSERT INTO task_tags (task_id, tag_id)
        SELECT task.id, owned_tag.id
        FROM task_tags AS link
        JOIN tags AS old_tag ON old_tag.id = link.tag_id
        JOIN tasks AS task ON task.id = link.task_id
        JOIN projects AS project ON project.id = task.project_id
        JOIN tags AS owned_tag ON owned_tag.owner_id = project.owner_id AND owned_tag.name = old_tag.name
        WHERE old_tag.owner_id IS NULL
    """)
    op.execute("""
        DELETE FROM task_tags WHERE tag_id IN (SELECT id FROM tags WHERE owner_id IS NULL)
        AND task_id IN (
            SELECT tasks.id FROM tasks JOIN projects ON projects.id = tasks.project_id
            WHERE projects.owner_id IS NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute("""
        INSERT INTO tags (name, color)
        SELECT candidate.name, candidate.color FROM tags AS candidate
        WHERE candidate.id IN (
            SELECT MIN(id) FROM tags AS owned WHERE owned.owner_id IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM tags AS legacy WHERE legacy.owner_id IS NULL AND legacy.name = owned.name)
            GROUP BY owned.name
        )
    """)
    op.execute("""
        INSERT INTO task_tags (task_id, tag_id)
        SELECT DISTINCT link.task_id, legacy.id
        FROM task_tags AS link
        JOIN tags AS owned ON owned.id = link.tag_id AND owned.owner_id IS NOT NULL
        JOIN tags AS legacy ON legacy.name = owned.name AND legacy.owner_id IS NULL
        WHERE NOT EXISTS (
            SELECT 1 FROM task_tags AS existing WHERE existing.task_id = link.task_id
            AND existing.tag_id = legacy.id
        )
    """)
    op.execute(
        "DELETE FROM task_tags WHERE tag_id IN (SELECT id FROM tags WHERE owner_id IS NOT NULL)"
    )
    op.execute("DELETE FROM tags WHERE owner_id IS NOT NULL")
    op.drop_index("ix_task_tags_tag_id", table_name="task_tags")
    with op.batch_alter_table("tags") as batch:
        batch.drop_index("ix_tags_owner_name")
        batch.drop_constraint("fk_tags_owner_id_users", type_="foreignkey")
        batch.drop_column("owner_id")
        batch.create_index("ix_tags_name", ["name"], unique=True)
