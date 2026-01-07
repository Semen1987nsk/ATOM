"""add_deposit_history

Revision ID: 798ef8d328bd
Revises: 60a8c581cd18
Create Date: 2026-01-07 05:53:59.283155

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '798ef8d328bd'
down_revision: Union[str, Sequence[str], None] = '60a8c581cd18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Добавляем колонку initial_balance в accounts
    op.add_column('accounts', sa.Column('initial_balance', sa.Numeric(precision=18, scale=8), nullable=True))
    
    # Создаём таблицу deposit_history
    op.create_table('deposit_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('operation_type', sa.Enum('INITIAL', 'DEPOSIT', 'WITHDRAWAL', name='depositoperationtype'), nullable=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('balance_after', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('date', sa.DateTime(), nullable=False),
        sa.Column('note', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_deposit_history_account_id'), 'deposit_history', ['account_id'], unique=False)
    op.create_index(op.f('ix_deposit_history_id'), 'deposit_history', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_deposit_history_id'), table_name='deposit_history')
    op.drop_index(op.f('ix_deposit_history_account_id'), table_name='deposit_history')
    op.drop_table('deposit_history')
    op.drop_column('accounts', 'initial_balance')
