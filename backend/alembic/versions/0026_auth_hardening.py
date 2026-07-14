"""Sprint 2A-1: auth-hardening columns on users

Revision ID: 0026_auth_hardening
Revises: 0025_account_pnl_health_cache
Create Date: 2026-05-24 12:00:00.000000

Sprint 2A-1 (API-07 + API-11): добавляем три поля в users для
account-lockout и инвалидации сессий:

  failed_login_count — счётчик подряд идущих неудачных входов (API-11).
                       server_default="0" обязателен — backfill существующих строк.
  locked_until       — до этого момента вход блокируется (API-11).
  tokens_valid_after — маркер инвалидации JWT: токены с iat раньше этого
                       момента отвергаются (API-07, reset/change-password).

batch_alter_table — SQLite-safe (ALTER ADD COLUMN под капотом).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0026_auth_hardening"
down_revision: Union[str, Sequence[str], None] = "0025_account_pnl_health_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from _guards import has_column

    bind = op.get_bind()
    # DATA-01: на чистой БД колонки уже создал 0001 (create_all из models).
    if has_column(bind, "users", "failed_login_count"):
        return

    with op.batch_alter_table("users", schema=None) as batch:
        batch.add_column(
            sa.Column(
                "failed_login_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
                comment="Подряд идущие неудачные входы (API-11 lockout)",
            )
        )
        batch.add_column(
            sa.Column(
                "locked_until",
                sa.DateTime(),
                nullable=True,
                comment="До этого момента вход заблокирован (API-11)",
            )
        )
        batch.add_column(
            sa.Column(
                "tokens_valid_after",
                sa.DateTime(),
                nullable=True,
                comment="JWT с iat раньше этого момента отвергаются (API-07)",
            )
        )


def downgrade() -> None:
    from _guards import has_column

    bind = op.get_bind()
    if not has_column(bind, "users", "failed_login_count"):
        return

    with op.batch_alter_table("users", schema=None) as batch:
        batch.drop_column("tokens_valid_after")
        batch.drop_column("locked_until")
        batch.drop_column("failed_login_count")
