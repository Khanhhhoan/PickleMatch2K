"""Bảng pair_feedback: nhãn khảo sát thật cho mô hình ghép cặp người chơi

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-10 22:37:06.119890

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pair_feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rater_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(), server_default='survey', nullable=False),
        sa.Column('level_diff', sa.Float(), nullable=False),
        sa.Column('distance_km', sa.Float(), nullable=False),
        sa.Column('availability_overlap', sa.Float(), nullable=False),
        sa.Column('purpose_match', sa.Integer(), nullable=False),
        sa.Column('style_match', sa.Integer(), nullable=False),
        sa.Column('label', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['rater_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pair_feedback_id'), 'pair_feedback', ['id'], unique=False)
    op.create_index(op.f('ix_pair_feedback_rater_id'), 'pair_feedback', ['rater_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_pair_feedback_rater_id'), table_name='pair_feedback')
    op.drop_index(op.f('ix_pair_feedback_id'), table_name='pair_feedback')
    op.drop_table('pair_feedback')
