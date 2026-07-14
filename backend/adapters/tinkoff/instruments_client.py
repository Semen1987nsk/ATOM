"""
TinkoffInstrumentsClient — обёртка над `services.instruments.*`.

Что делает:

* `get_instrument_by(uid=...)` — точечный lookup по UID (primary).
* `get_bond_coupons(uid, from_, to)` — schedule купонов для облигации (PR 8).
* `get_accrued_interests(uid, date)` — НКД на дату (PR 8 + 11).
* `bootstrap_*()` — массовая выгрузка справочника (Shares/Bonds/...)
  для PR 6 (instrument cache).

Клиент работает с UID — это primary identifier в T-Invest API (стабилен,
обязателен для опционов).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from logger import get_logger

from adapters.tinkoff.error_mapper import wrap_sdk_errors
from adapters.tinkoff.proto_to_domain import (
    instrument_from_proto,
    money_to_decimal,
)
from domain.entities import Instrument
from domain.enums import InstrumentType
from domain.exceptions import InstrumentNotFound

log = get_logger("tinkoff.instruments_client")


class TinkoffInstrumentsClient:
    def __init__(self, services: Any) -> None:
        self._svc = services

    async def get_instrument_by_uid(self, uid: str) -> Instrument:
        """Универсальный lookup. Достаёт raw + правильно типизирует."""
        from t_tech.invest.schemas import InstrumentIdType

        # AU1: per-RPC rate-limit gate
        async with self._svc.limiter:
            with wrap_sdk_errors():
                response = await self._svc.instruments.get_instrument_by(
                    id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_UID,
                    id=uid,
                )

        raw = getattr(response, "instrument", None)
        if raw is None:
            raise InstrumentNotFound(f"instrument {uid} not found", code="NOT_FOUND")

        # `Instrument` proto-сообщение не содержит type-specific полей
        # (это generic struct). Для bond/future/option нужны ОТДЕЛЬНЫЕ
        # вызовы — bond_by/future_by/option_by, чтобы получить полный объект.
        # На уровне generic instrument мы получаем только базу + ticker/figi
        # + instrument_type. Дальше дотягиваем специфику.
        inst_type = self._parse_kind(getattr(raw, "instrument_kind", None))
        if inst_type in (InstrumentType.BOND, InstrumentType.FUTURES, InstrumentType.OPTION):
            return await self._enrich_typed(uid, inst_type, fallback_raw=raw)
        return instrument_from_proto(raw, inst_type)

    async def _enrich_typed(
        self, uid: str, inst_type: InstrumentType, *, fallback_raw: Any
    ) -> Instrument:
        """Дотянуть type-specific поля (купоны для bond, маржа для future)."""
        from t_tech.invest.schemas import InstrumentIdType

        method_map = {
            InstrumentType.BOND: ("bond_by", InstrumentType.BOND),
            InstrumentType.FUTURES: ("future_by", InstrumentType.FUTURES),
            InstrumentType.OPTION: ("option_by", InstrumentType.OPTION),
            InstrumentType.SHARE: ("share_by", InstrumentType.SHARE),
            InstrumentType.ETF: ("etf_by", InstrumentType.ETF),
            InstrumentType.CURRENCY: ("currency_by", InstrumentType.CURRENCY),
        }
        method_name, target_type = method_map.get(
            inst_type, ("get_instrument_by", inst_type)
        )

        if method_name == "get_instrument_by":
            # Не нашли typed-метод — возвращаем generic.
            return instrument_from_proto(fallback_raw, inst_type)

        method = getattr(self._svc.instruments, method_name)
        # AU1: per-RPC rate-limit gate
        async with self._svc.limiter:
            with wrap_sdk_errors():
                response = await method(
                    id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_UID,
                    id=uid,
                )

        instrument_raw = getattr(response, "instrument", None)
        if instrument_raw is None:
            return instrument_from_proto(fallback_raw, inst_type)
        return instrument_from_proto(instrument_raw, target_type)

    @staticmethod
    def _parse_kind(value: Any) -> InstrumentType:
        from adapters.tinkoff.proto_to_domain import parse_instrument_type

        return parse_instrument_type(value) or InstrumentType.UNSPECIFIED

    async def get_bond_coupons(
        self,
        instrument_id: str,
        *,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """
        Schedule купонов облигации. Возвращает список словарей с полями:
        coupon_date, pay_one_share (Decimal), coupon_period (days),
        coupon_type. Используется в PR 8 для расчёта PnL и прогноза дохода.
        """
        # AU1: per-RPC rate-limit gate
        async with self._svc.limiter:
            with wrap_sdk_errors():
                response = await self._svc.instruments.get_bond_coupons(
                    instrument_id=instrument_id,
                    from_=from_dt,
                    to=to_dt,
                )

        events = list(getattr(response, "events", []) or [])
        result: list[dict[str, Any]] = []
        for ev in events:
            result.append(
                {
                    "coupon_date": getattr(ev, "coupon_date", None),
                    "pay_one_share": money_to_decimal(getattr(ev, "pay_one_share", None)),
                    "coupon_period": int(getattr(ev, "coupon_period", 0) or 0),
                    "coupon_type": str(getattr(ev, "coupon_type", "")),
                    "coupon_number": int(getattr(ev, "coupon_number", 0) or 0),
                    "fix_date": getattr(ev, "fix_date", None),
                }
            )
        return result

    async def get_accrued_interest(
        self, instrument_id: str, *, on_date: Optional[datetime] = None
    ) -> Optional[Decimal]:
        """
        НКД (накопленный купонный доход) на дату для облигации.

        В T-Invest API метод возвращает `value` за период `[from, to]`;
        для журнала достаточно последнего значения. Если on_date=None,
        берём today.
        """
        target = on_date or datetime.now(tz=timezone.utc)
        # AU1: per-RPC rate-limit gate
        async with self._svc.limiter:
            with wrap_sdk_errors():
                response = await self._svc.instruments.get_accrued_interests(
                    instrument_id=instrument_id,
                    from_=target,
                    to=target,
                )

        items = list(getattr(response, "accrued_interests", []) or [])
        if not items:
            return None
        last = items[-1]  # самое свежее значение в окне
        return money_to_decimal(getattr(last, "value", None))

    # ── Bootstrap (PR 6) ──

    async def list_shares(self) -> list[Instrument]:
        return await self._list_typed("shares", InstrumentType.SHARE)

    async def list_bonds(self) -> list[Instrument]:
        return await self._list_typed("bonds", InstrumentType.BOND)

    async def list_etfs(self) -> list[Instrument]:
        return await self._list_typed("etfs", InstrumentType.ETF)

    async def list_futures(self) -> list[Instrument]:
        return await self._list_typed("futures", InstrumentType.FUTURES)

    async def list_options(self) -> list[Instrument]:
        return await self._list_typed("options", InstrumentType.OPTION)

    async def list_currencies(self) -> list[Instrument]:
        return await self._list_typed("currencies", InstrumentType.CURRENCY)

    async def _list_typed(self, method_name: str, inst_type: InstrumentType) -> list[Instrument]:
        method = getattr(self._svc.instruments, method_name)
        # AU1: per-RPC rate-limit gate
        async with self._svc.limiter:
            with wrap_sdk_errors():
                response = await method()
        instruments = list(getattr(response, "instruments", []) or [])
        return [instrument_from_proto(raw, inst_type) for raw in instruments]
