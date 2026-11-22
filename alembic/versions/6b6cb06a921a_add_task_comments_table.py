"""add task_comments table

Revision ID: 6b6cb06a921a
Revises: 11421dc4ab5a
Create Date: 2026-11-22 02:51:52.154459

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b6cb06a921a'
down_revision: Union[str, Sequence[str], None] = '11421dc4ab5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'task_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('author_name', sa.String(length=100), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('task_comments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_task_comments_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_comments_task_id'), ['task_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_comments_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('task_comments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_task_comments_user_id'))
        batch_op.drop_index(batch_op.f('ix_task_comments_task_id'))
        batch_op.drop_index(batch_op.f('ix_task_comments_id'))
    op.drop_table('task_comments')
