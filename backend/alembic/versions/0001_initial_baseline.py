"""initial_baseline: full current schema in a single migration

Revision ID: 0001_initial_baseline
Revises:
Create Date: 2026-05-06 14:00:00.000000

Консолидация всех ранее существовавших миграций (60a8c581cd18, 798ef8d328bd,
a1b2c3d4e5f6, b2c3d4e5f6a7) в одну отправную точку.

ПРИЧИНА: предыдущая цепочка была структурно сломана —
- 60a8c581cd18 (initial) делал ALTER COLUMN TYPE на subscriptions, но не
  создавал НИ ОДНУ таблицу. Работало только если БД до этого бутстрапилась
  через AUTO_INIT_DB → SQLAlchemy create_all(), что в проде неприемлемо.
- На SQLite alter_column TYPE без batch_alter_table = синтаксис-эррор.
- На fresh Postgres падал на «relation 'subscriptions' does not exist».
- Documented prod-bootstrap путь `alembic upgrade head` НЕ РАБОТАЛ.

РЕШЕНИЕ: drop старой цепочки, baseline через `Base.metadata.create_all(...)`.
Для DEV-БД, которые были stamp'ed на `b2c3d4e5f6a7`, нужно одноразово:
  alembic stamp 0001_initial_baseline

Все будущие миграции ссылаются на этот ID как down_revision.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa  # noqa: F401  (keeps tests compatible)


revision: str = "0001_initial_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Build the entire current schema from SQLAlchemy models."""
    # Импорт внутри функции, чтобы alembic-скрипт мог быть собран без models
    # на этапе импорта (при автогенерации миграций).
    from models import Base

    bind = op.get_bind()
    # checkfirst=True — миграция идемпотентна: если кто-то уже бутстрапил БД
    # через AUTO_INIT_DB (как мы делали в dev), повторный upgrade не упадёт.
    Base.metadata.create_all(bind, checkfirst=True)


def downgrade() -> None:
    """Drop the entire schema. Используется только для local-reset."""
    from models import Base

    bind = op.get_bind()
    Base.metadata.drop_all(bind)
