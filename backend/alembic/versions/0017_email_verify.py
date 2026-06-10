"""PR 26 (Phase 3): email verification + BackupRunORM

Revision ID: 0017_email_verify
Revises: 0016_phase2_tables
Create Date: 2026-05-14 17:00:00.000000

Финальная миграция перед launch:

1. **users.email_verified / email_verification_token / *_sent_at** — флоу
   подтверждения email с magic-link. Закрывает #22 enumeration:
   регистрация всегда возвращает 202, даже для уже занятого email
   (письмо «вы уже зарегистрированы — вот ссылка для сброса»).

2. **backup_runs** — tracking nightly pg_dump + weekly restore-test.
   Replaces filesystem-based listing в /admin/backups/status.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0017_email_verify"
down_revision: Union[str, Sequence[str], None] = "0016_phase2_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from _guards import has_column, has_table

    bind = op.get_bind()

    # DATA-01: на чистой БД объекты уже создал 0001 (create_all из models).
    if not has_column(bind, "users", "email_verified"):
        with op.batch_alter_table("users", schema=None) as batch:
            batch.add_column(sa.Column("email_verified", sa.Boolean(), nullable=True, server_default="0"))
            batch.add_column(sa.Column("email_verification_token", sa.String(length=64), nullable=True))
            batch.add_column(sa.Column("email_verification_sent_at", sa.DateTime(), nullable=True))
            batch.create_index("ix_users_email_verification_token", ["email_verification_token"])

    if has_table(bind, "backup_runs"):
        return

    op.create_table(
        "backup_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),  # success|failed|restore_test_ok|restore_test_failed
        sa.Column("kind", sa.String(length=32), nullable=False),  # nightly_backup|restore_test
        sa.Column("filename", sa.String(length=256), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("s3_uploaded", sa.Boolean(), nullable=True, server_default="0"),
        sa.Column("error_message", sa.String(length=512), nullable=True),
    )
    op.create_index("ix_backup_runs_started", "backup_runs", ["started_at"])
    op.create_index("ix_backup_runs_kind", "backup_runs", ["kind"])


def downgrade() -> None:
    from _guards import has_column, has_table

    bind = op.get_bind()

    if has_table(bind, "backup_runs"):
        op.drop_index("ix_backup_runs_kind", table_name="backup_runs")
        op.drop_index("ix_backup_runs_started", table_name="backup_runs")
        op.drop_table("backup_runs")

    if has_column(bind, "users", "email_verified"):
        with op.batch_alter_table("users", schema=None) as batch:
            batch.drop_index("ix_users_email_verification_token")
            batch.drop_column("email_verification_sent_at")
            batch.drop_column("email_verification_token")
            batch.drop_column("email_verified")
