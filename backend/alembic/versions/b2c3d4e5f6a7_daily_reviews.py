"""phase2: daily_reviews table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-06 00:00:00.000000

Daily Review = ежедневная рефлексия + намерение на завтра + рейтинг 1-5.
Одна строка = один день для конкретного account. Per-trade reflections
хранятся в JSON-поле trade_reflections как { "trade_id": "комментарий" }.

UniqueConstraint(account_id, date) гарантирует одну запись на день/аккаунт —
upsert на бэкенде полагается на это.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'daily_reviews',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('account_id', sa.Integer(), nullable=True, index=True),
        sa.Column('date', sa.String(), nullable=False, index=True),
        sa.Column('reflection', sa.String(), server_default=''),
        sa.Column('intention', sa.String(), server_default=''),
        sa.Column('trade_reflections', sa.JSON(), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('account_id', 'date', name='uq_review_account_date'),
    )


def downgrade() -> None:
    op.drop_table('daily_reviews')
