"""create_comments_table

Revision ID: 15e897521cd6
Revises: d662e37c6bc5
Create Date: 2026-11-16 19:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15e897521cd6'
down_revision: Union[str, Sequence[str], None] = 'd662e37c6bc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema: create comments table and indexes."""
    op.create_table(
        'comments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['parent_id'], ['comments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_comments_author_id'), 'comments', ['author_id'], unique=False)
    op.create_index(op.f('ix_comments_parent_id'), 'comments', ['parent_id'], unique=False)
    op.create_index(op.f('ix_comments_ticket_id'), 'comments', ['ticket_id'], unique=False)


def downgrade() -> None:
    """Downgrade database schema: drop comments indexes and table."""
    op.drop_index(op.f('ix_comments_ticket_id'), table_name='comments')
    op.drop_index(op.f('ix_comments_parent_id'), table_name='comments')
    op.drop_index(op.f('ix_comments_author_id'), table_name='comments')
    op.drop_table('comments')

