"""DATA-03: broker_connections.account_id FK -> ON DELETE CASCADE

Revision ID: 0029_broker_conn_cascade
Revises: 0028_tags_jsonb_gin
Create Date: 2026-06-11 00:00:00.000000

BrokerConnection хранит зашифрованный api_token брокера (152-ФЗ). Удаление
Account не должно оставлять строку-сироту с токеном. ORM-сторона закрыта
cascade="all, delete-orphan" на Account.broker_connections; эта миграция
выравнивает DB-уровень: FK получает ON DELETE CASCADE (страховка для
raw-DELETE / bulk-операций мимо ORM).

На чистой БД 0001 уже создал FK с CASCADE через create_all из текущих
models.py — guard проверяет фактическую опцию FK и выходит no-op.
SQLite меняет FK только пересозданием таблицы (batch_alter_table);
безымянный FK получает детерминированное имя через naming_convention.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0029_broker_conn_cascade"
down_revision: Union[str, Sequence[str], None] = "0028_tags_jsonb_gin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "broker_connections"
_FK_NAME = "fk_broker_connections_account_id_accounts"
# Для SQLite batch: reflect присваивает безымянным constraint'ам имена по
# конвенции, иначе drop_constraint не может адресовать FK.
_NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def _account_fk(bind):
    """FK broker_connections.account_id -> accounts.id (dict из inspector) или None."""
    for fk in sa.inspect(bind).get_foreign_keys(_TABLE):
        if (
            fk.get("constrained_columns") == ["account_id"]
            and fk.get("referred_table") == "accounts"
        ):
            return fk
    return None


def _has_cascade(fk) -> bool:
    return (fk.get("options") or {}).get("ondelete", "").upper() == "CASCADE"


def upgrade() -> None:
    from _guards import has_table

    bind = op.get_bind()
    if not has_table(bind, _TABLE):
        return

    fk = _account_fk(bind)
    if fk is not None and _has_cascade(fk):
        # DATA-01: чистая БД — 0001 (create_all) уже создал FK с CASCADE.
        return

    if bind.dialect.name == "postgresql":
        if fk is not None and fk.get("name"):
            op.drop_constraint(fk["name"], _TABLE, type_="foreignkey")
        op.create_foreign_key(
            _FK_NAME, _TABLE, "accounts",
            ["account_id"], ["id"], ondelete="CASCADE",
        )
        return

    with op.batch_alter_table(
        _TABLE, schema=None, naming_convention=_NAMING
    ) as batch:
        if fk is not None:
            batch.drop_constraint(fk.get("name") or _FK_NAME, type_="foreignkey")
        batch.create_foreign_key(
            _FK_NAME, "accounts", ["account_id"], ["id"], ondelete="CASCADE",
        )


def downgrade() -> None:
    from _guards import has_table

    bind = op.get_bind()
    if not has_table(bind, _TABLE):
        return

    fk = _account_fk(bind)
    if fk is None or not _has_cascade(fk):
        return

    if bind.dialect.name == "postgresql":
        if fk.get("name"):
            op.drop_constraint(fk["name"], _TABLE, type_="foreignkey")
        op.create_foreign_key(
            _FK_NAME, _TABLE, "accounts", ["account_id"], ["id"],
        )
        return

    with op.batch_alter_table(
        _TABLE, schema=None, naming_convention=_NAMING
    ) as batch:
        batch.drop_constraint(fk.get("name") or _FK_NAME, type_="foreignkey")
        batch.create_foreign_key(_FK_NAME, "accounts", ["account_id"], ["id"])
