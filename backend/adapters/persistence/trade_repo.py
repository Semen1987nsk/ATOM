# mypy: disable-error-code="arg-type,assignment"

"""
TradeRepository — запись закрытых сделок журнала.

В PR 5 pipeline вызывает `FIFOMatchingService.match()` для каждого инструмента
и получает `list[Trade]` (закрытые). Этот репозиторий сохраняет их в БД
(таблица `trades`, см. models.py).

Стратегия: `replace_for_instrument()` удаляет все trade'ы с
`data_source='tinkoff_v2'` по инструменту и вставляет новые. Это
обеспечивает идемпотентность при повторном запуске FIFO на пересекающемся
наборе операций (например, после full_sync с самого начала).

Старые `data_source='legacy'` (импортированные старым tinkoff_service) и
'manual' (ручной ввод) остаются нетронутыми.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from sqlalchemy.orm import Session

from domain.entities import Instrument, Trade
from domain.enums import TradeDataSource, TradeDirection
from logger import get_logger
from models import Trade as TradeORM
from models import TradeDirection as TradeDirectionORM
from utils.datetime_utils import utc_now_naive

log = get_logger("trade_repo")

# DATA-02: пользовательские аннотации, которые user проставляет на
# sync-сделках через PATCH /trades/{id}. FIFO-пересборка пересоздаёт строки —
# эти поля обязаны переехать на новые, иначе re-sync молча стирает журнал.
_ANNOTATION_FIELDS = (
    "notes",
    "tags",
    "mood",
    "discipline",
    "confidence",
    "setup_id",
    "screenshot_url",
)


def _domain_to_orm_direction(d: TradeDirection):
    """domain TradeDirection -> ORM enum (значения совпадают по str, но
    мы используем разные enum-классы для domain/ORM)."""
    if d == TradeDirection.LONG:
        return TradeDirectionORM.LONG
    if d == TradeDirection.SHORT:
        return TradeDirectionORM.SHORT
    raise ValueError(f"unknown direction: {d}")


class TradeRepository:
    def replace_for_instrument(
        self,
        session: Session,
        *,
        account_id: int,
        instrument_uid: str,
        trades: Sequence[Trade],
        instrument: Instrument | None = None,
        data_source: str = TradeDataSource.TINKOFF_V2.value,
    ) -> int:
        """
        Удалить все trade'ы по этому инструменту с `data_source` и вставить
        новые. Возвращает кол-во вставленных.

        Транзакция управляется снаружи — здесь только session.add()/flush(),
        commit делает вызывающий код.

        `instrument` нужен чтобы записать в Trade.symbol человекочитаемый
        ticker (SBER, GAZP) вместо FIGI/UID. Опционально для обратной
        совместимости с тестами и старыми вызовами.
        """
        # 0) DATA-02: снять аннотации с перезаписываемых строк, чтобы вернуть
        # их на пересозданные. Column-tuple query — не загружаем ORM-объекты
        # в identity map перед bulk-delete.
        scope = (
            TradeORM.account_id == account_id,
            TradeORM.instrument_uid == instrument_uid,
            TradeORM.data_source == data_source,
        )
        exact_annotations: dict[tuple, dict] = {}
        fallback_annotations: dict[tuple, list[dict]] = {}
        for row in session.query(
            TradeORM.entry_at,
            TradeORM.exit_at,
            TradeORM.direction,
            TradeORM.quantity,
            *(getattr(TradeORM, f) for f in _ANNOTATION_FIELDS),
        ).filter(*scope):
            ann = dict(zip(_ANNOTATION_FIELDS, row[4:]))
            # Пустые значения (None/""/[]) — не аннотация, такие строки
            # в переносе не участвуют.
            if not any(ann.values()):
                continue
            exact_annotations[(row.entry_at, row.direction, row.quantity, row.exit_at)] = ann
            fallback_annotations.setdefault((row.entry_at, row.direction), []).append(ann)

        # 1) Удалить старые записи (только своего data_source!).
        session.query(TradeORM).filter(*scope).delete(synchronize_session=False)

        # 2) Вставить новые.
        now = utc_now_naive()
        new_rows = [
            self._trade_to_orm(trade, account_id, data_source, now, instrument)
            for trade in trades
        ]

        # 2a) Перенос аннотаций. Два прохода: сперва точные match'и по
        # (entry_at, direction, quantity, exit_at) — иначе fallback-кандидат
        # мог бы «увести» аннотацию у точного совпадения; затем fallback по
        # (entry_at, direction) для сделок, у которых брокер дослал операции
        # и exit_at/quantity сместились — только при единственном кандидате
        # (при нескольких привязка неоднозначна, лучше потерять молча).
        unmatched_rows = []
        for orm_row in new_rows:
            key = (orm_row.entry_at, orm_row.direction, orm_row.quantity, orm_row.exit_at)
            ann = exact_annotations.pop(key, None)
            if ann is None:
                unmatched_rows.append(orm_row)
                continue
            ann["_consumed"] = True
            self._apply_annotations(orm_row, ann)
        for orm_row in unmatched_rows:
            candidates = [
                a
                for a in fallback_annotations.get((orm_row.entry_at, orm_row.direction), [])
                if not a.get("_consumed")
            ]
            if len(candidates) != 1:
                continue
            candidates[0]["_consumed"] = True
            self._apply_annotations(orm_row, candidates[0])

        for orm_row in new_rows:
            session.add(orm_row)
        session.flush()
        return len(trades)

    def replace_for_account(
        self,
        session: Session,
        *,
        account_id: int,
        trades_by_instrument: dict[str, Sequence[Trade]],
        data_source: str = TradeDataSource.TINKOFF_V2.value,
    ) -> int:
        """Удобный batch-помощник: разом перезаписать trades по нескольким инструментам."""
        total = 0
        for uid, trades in trades_by_instrument.items():
            total += self.replace_for_instrument(
                session,
                account_id=account_id,
                instrument_uid=uid,
                trades=trades,
                data_source=data_source,
            )
        return total

    def count_for_account(
        self,
        session: Session,
        *,
        account_id: int,
        data_source: str | None = None,
    ) -> int:
        q = session.query(TradeORM).filter(TradeORM.account_id == account_id)
        if data_source is not None:
            q = q.filter(TradeORM.data_source == data_source)
        return q.count()

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _apply_annotations(orm_row: TradeORM, ann: dict) -> None:
        for field in _ANNOTATION_FIELDS:
            setattr(orm_row, field, ann[field])

    @staticmethod
    def _trade_to_orm(
        trade: Trade,
        account_id: int,
        data_source: str,
        synced_at,
        instrument: Instrument | None = None,
    ) -> TradeORM:
        # Symbol — человекочитаемый ticker (SBER/GAZP/USDRUB) если справочник
        # доступен, иначе FIGI, иначе UID. Это то, что видит пользователь
        # в таблице сделок — нужен normal ticker, не технический ID.
        ticker = instrument.ticker if (instrument and instrument.ticker) else None
        symbol = ticker or trade.instrument_figi or trade.instrument_uid

        # Полное название бумаги ("ETHA-6.26 Ethereum ETF", "Софтлайн", "Сбер").
        # Берём из Instrument.name — это то что пользователь хочет видеть рядом
        # с тикером в журнале. Без instrument'а оставляем None (legacy/manual).
        asset_name = instrument.name if (instrument and instrument.name) else None

        # naive UTC для БД.
        entry_at = (
            trade.entry_at.replace(tzinfo=None)
            if trade.entry_at.tzinfo
            else trade.entry_at
        )
        exit_at = None
        if trade.exit_at is not None:
            exit_at = (
                trade.exit_at.replace(tzinfo=None)
                if trade.exit_at.tzinfo
                else trade.exit_at
            )

        # Holding time в минутах — для трейдинговой аналитики и UI колонки.
        # Только для closed-trades (exit_at не None).
        holding_minutes = None
        if exit_at is not None and entry_at is not None:
            delta_sec = (exit_at - entry_at).total_seconds()
            if delta_sec >= 0:
                holding_minutes = int(delta_sec / 60)

        return TradeORM(
            account_id=account_id,
            symbol=symbol,
            asset_name=asset_name,
            asset_type=(
                trade.instrument_type.value if trade.instrument_type else None
            ),
            direction=_domain_to_orm_direction(trade.direction),
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            quantity=Decimal(trade.quantity),
            entry_at=entry_at,
            exit_at=exit_at,
            pnl=trade.pnl,
            net_pnl=trade.net_pnl,
            commission=trade.commission_total,
            entry_value=trade.entry_value,
            exit_value=trade.exit_value,
            currency=trade.currency or "RUB",
            data_source=data_source,
            instrument_uid=trade.instrument_uid,
            instrument_figi=trade.instrument_figi,
            instrument_type_v2=(
                trade.instrument_type.value if trade.instrument_type else None
            ),
            holding_time_minutes=holding_minutes,
            operations=[
                {"role": "entry", "operation_id": op_id}
                for op_id in trade.entry_operation_ids
            ]
            + [
                {"role": "exit", "operation_id": op_id}
                for op_id in trade.exit_operation_ids
            ],
            # TR1: round-trip group ID для журнала.
            position_id=trade.position_id,
            # TR1.3: per-trade attribution для account-level fees.
            # Заполняется в pipeline._stage_attribute_fees после FIFO match —
            # здесь обычно None (will be filled на next stage). Если уже
            # установлено в domain Trade — pass through.
            varmargin_attributed=trade.varmargin_attributed,
            margin_fee_attributed=trade.margin_fee_attributed,
            service_fee_attributed=trade.service_fee_attributed,
            other_fees_attributed=trade.other_fees_attributed,
            # Phase 9: point_value snapshot для futures (защищает historical
            # P&L от dynamic FX-scaling в InstrumentORM cache).
            point_value=trade.point_value,
            point_value_source=trade.point_value_source,
        )
