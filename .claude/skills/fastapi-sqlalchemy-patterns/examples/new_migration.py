"""add_tags_table

Revision ID: 0002_add_tags
Revises: 0001_initial_baseline
Create Date: 2026-05-06 12:00:00.000000

Добавляет таблицы tags и trade_tags (M2M между Trade и Tag).

Что делает миграция:
- tags: id, user_id (FK → users.id, ON DELETE CASCADE), name, color, created_at.
- UniqueConstraint (user_id, name) — пользователь не может создать два тега с одинаковым именем.
- trade_tags: связующая таблица M2M; PK = (trade_id, tag_id).

Совместимость с SQLite: все ALTER оборачивать в batch_alter_table.
В этой миграции только CREATE TABLE — batch не нужен.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# ==================== ALEMBIC METADATA ====================

revision: str = "0002_add_tags"
down_revision: Union[str, Sequence[str], None] = "0001_initial_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==================== UPGRADE ====================

def upgrade() -> None:
    # ── tags ──
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_tags_user_name"),
    )
    op.create_index("ix_tags_user_id", "tags", ["user_id"])
    op.create_index("ix_tags_name", "tags", ["name"])

    # ── trade_tags (M2M) ──
    # Композитный PK гарантирует, что одна и та же пара (trade, tag) не задвоится.
    op.create_table(
        "trade_tags",
        sa.Column(
            "trade_id",
            sa.Integer(),
            sa.ForeignKey("trades.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.Integer(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Индекс на tag_id для быстрых обратных join'ов (Tag → Trades).
    # PK уже даёт индекс на (trade_id, tag_id), но не на одиночный tag_id.
    op.create_index("ix_trade_tags_tag_id", "trade_tags", ["tag_id"])


# ==================== DOWNGRADE ====================

def downgrade() -> None:
    # Порядок обратный upgrade: сначала зависимая таблица, потом родитель.
    op.drop_index("ix_trade_tags_tag_id", table_name="trade_tags")
    op.drop_table("trade_tags")

    op.drop_index("ix_tags_name", table_name="tags")
    op.drop_index("ix_tags_user_id", table_name="tags")
    op.drop_table("tags")


# ==================== ENUM tip (для будущих миграций) ====================
# Если нужно добавить enum-колонку — на Postgres делайте так:
#
#     tag_kind = sa.Enum("system", "user", name="tag_kind_enum")
#     tag_kind.create(op.get_bind(), checkfirst=True)
#     op.add_column("tags", sa.Column("kind", tag_kind, nullable=False, server_default="user"))
#
# В downgrade:
#     op.drop_column("tags", "kind")
#     sa.Enum(name="tag_kind_enum").drop(op.get_bind(), checkfirst=True)
#
# Autogenerate Postgres-enum'ы НЕ создаёт сам — пишите руками.
