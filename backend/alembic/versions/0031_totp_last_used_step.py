"""S4-10: users.totp_last_used_step — replay-guard для TOTP.

Revision ID: 0031_totp_last_used_step
Revises: 0030_trades_account_entry_exit_index
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031_totp_last_used_step"
down_revision: Union[str, Sequence[str], None] = "0030_trades_account_entry_exit_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from _guards import has_column
    bind = op.get_bind()
    if not has_column(bind, "users", "totp_last_used_step"):
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("totp_last_used_step", sa.Integer(), nullable=True))


def downgrade() -> None:
    from _guards import has_column
    bind = op.get_bind()
    if has_column(bind, "users", "totp_last_used_step"):
        with op.batch_alter_table("users") as batch:
            batch.drop_column("totp_last_used_step")
