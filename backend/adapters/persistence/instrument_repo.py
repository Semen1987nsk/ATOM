# mypy: disable-error-code="arg-type,assignment"

"""
InstrumentRepository — кэш справочника инструментов (PR 6).

Сейчас (PR 5) используется pipeline'ом для resolve uid → ticker/figi/type
без вызова Tinkoff API на каждую операцию. PR 6 добавит bootstrap-задачу
для массового первичного заполнения.

Stable identifier — UID (PK). FIGI и ticker — secondary, могут отсутствовать
у опционов и при ребрендинге.

Type-checker note: проект использует legacy `declarative_base()`-стиль
SQLAlchemy (без `Mapped[]`-аннотаций). Mypy/pyright ругаются что
`row.uid` имеет тип `Column[str]`, хотя на runtime это скаляр. Подавляем
на уровне модуля до миграции на SQLAlchemy 2.0 typed style (отдельный PR).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterable, Optional, Sequence

from sqlalchemy.orm import Session

from domain.entities import Instrument
from domain.enums import InstrumentType
from logger import get_logger
from models import InstrumentORM
from utils.datetime_utils import utc_now_naive

log = get_logger("instrument_repo")

# Чанкование UPSERT (см. operation_repo.py — тот же сценарий с лимитом
# SQLite на параметры). InstrumentORM имеет ~32 колонки → 999/32 ≈ 31.
_UPSERT_CHUNK_SIZE_SQLITE = 25
_UPSERT_CHUNK_SIZE_POSTGRES = 500


# ── helpers ───────────────────────────────────────────────────────────


def _decimal_or_none(value) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _instrument_to_row(inst: Instrument, *, cached_at: datetime) -> dict:
    return {
        "uid": inst.uid,
        "figi": inst.figi,
        "ticker": inst.ticker,
        "class_code": inst.class_code,
        "instrument_type": inst.instrument_type.value,
        "isin": inst.isin,
        "name": inst.name,
        "lot": inst.lot,
        "currency": inst.currency,
        "nominal": inst.nominal,
        "min_price_increment": inst.min_price_increment,
        "min_price_increment_amount": inst.min_price_increment_amount,
        "coupon_quantity_per_year": inst.coupon_quantity_per_year,
        "amortization_flag": bool(inst.amortization_flag),
        "floating_coupon_flag": bool(inst.floating_coupon_flag),
        "maturity_date": (
            inst.maturity_date.replace(tzinfo=None)
            if inst.maturity_date and inst.maturity_date.tzinfo
            else inst.maturity_date
        ),
        "placement_price": inst.placement_price,
        "expiration_date": (
            inst.expiration_date.replace(tzinfo=None)
            if inst.expiration_date and inst.expiration_date.tzinfo
            else inst.expiration_date
        ),
        "basic_asset_size": inst.basic_asset_size,
        "basic_asset_uid": inst.basic_asset_uid,
        "strike_price": inst.strike_price,
        "option_direction": inst.option_direction,
        "option_style": inst.option_style,
        "option_multiplier": inst.option_multiplier,
        "extra": None,
        "cached_at": cached_at,
        "updated_at": cached_at,
    }


def _row_to_instrument(row: InstrumentORM) -> Instrument:
    return Instrument(
        uid=row.uid,
        figi=row.figi,
        ticker=row.ticker,
        class_code=row.class_code,
        instrument_type=InstrumentType(row.instrument_type)
        if row.instrument_type in {it.value for it in InstrumentType}
        else InstrumentType.UNSPECIFIED,
        isin=row.isin,
        name=row.name,
        lot=int(row.lot or 1),
        currency=row.currency or "rub",
        nominal=_decimal_or_none(row.nominal),
        min_price_increment=_decimal_or_none(row.min_price_increment),
        min_price_increment_amount=_decimal_or_none(row.min_price_increment_amount),
        coupon_quantity_per_year=row.coupon_quantity_per_year,
        amortization_flag=bool(row.amortization_flag),
        floating_coupon_flag=bool(row.floating_coupon_flag),
        maturity_date=row.maturity_date,
        placement_price=_decimal_or_none(row.placement_price),
        expiration_date=row.expiration_date,
        basic_asset_size=_decimal_or_none(row.basic_asset_size),
        basic_asset_uid=row.basic_asset_uid,
        strike_price=_decimal_or_none(row.strike_price),
        option_direction=row.option_direction,
        option_style=row.option_style,
        option_multiplier=row.option_multiplier,
        cached_at=row.cached_at,
    )


# ── репозиторий ───────────────────────────────────────────────────────


class InstrumentRepository:
    def upsert(self, session: Session, instrument: Instrument) -> None:
        self.upsert_many(session, [instrument])

    def upsert_many(
        self, session: Session, instruments: Sequence[Instrument]
    ) -> int:
        if not instruments:
            return 0

        now = utc_now_naive()
        rows = [_instrument_to_row(inst, cached_at=now) for inst in instruments]

        dialect = session.bind.dialect.name if session.bind else "sqlite"
        chunk_size = (
            _UPSERT_CHUNK_SIZE_POSTGRES
            if dialect == "postgresql"
            else _UPSERT_CHUNK_SIZE_SQLITE
        )

        updateable_cols = [c for c in rows[0].keys() if c not in {"uid", "cached_at"}]

        for start in range(0, len(rows), chunk_size):
            chunk = rows[start : start + chunk_size]
            if dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                stmt = pg_insert(InstrumentORM).values(chunk)
            else:
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert

                stmt = sqlite_insert(InstrumentORM).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["uid"],
                set_={c: getattr(stmt.excluded, c) for c in updateable_cols},
            )
            session.execute(stmt)
        return len(rows)

    def get_by_uid(self, session: Session, uid: str) -> Optional[Instrument]:
        row = session.query(InstrumentORM).filter(InstrumentORM.uid == uid).first()
        return _row_to_instrument(row) if row else None

    def get_many_by_uids(
        self, session: Session, uids: Iterable[str]
    ) -> dict[str, Instrument]:
        uid_list = [u for u in uids if u]
        if not uid_list:
            return {}
        rows = (
            session.query(InstrumentORM)
            .filter(InstrumentORM.uid.in_(uid_list))
            .all()
        )
        return {row.uid: _row_to_instrument(row) for row in rows}

    def missing_uids(
        self, session: Session, uids: Iterable[str]
    ) -> list[str]:
        """Вернёт те UID, которых ещё нет в кэше — pipeline их подгрузит из API."""
        uid_list = [u for u in uids if u]
        if not uid_list:
            return []
        existing = {
            row[0]
            for row in session.query(InstrumentORM.uid)
            .filter(InstrumentORM.uid.in_(uid_list))
            .all()
        }
        return [u for u in uid_list if u not in existing]

    def count(self, session: Session) -> int:
        return session.query(InstrumentORM).count()
