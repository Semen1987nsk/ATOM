"""
Domain value objects — immutable безкомпромиссно денежные / идентифицирующие
типы. Никаких float'ов в финансовых расчётах: всё идёт через Decimal.

Источник истины — официальная дока T-Bank Developer Portal:
https://developer.tbank.ru/invest/intro/useful-info/points

Конвертация:

* T-Invest API возвращает деньги как `MoneyValue {units: int, nano: int, currency: str}`,
  цены как `Quotation {units: int, nano: int}`.
* Формула: `value = units + nano / 1_000_000_000`.
* `nano` может быть отрицательным (например, для убыточных varmargin payments
  одновременно с отрицательным `units`); знак units и nano всегда совпадает,
  поэтому простое сложение даёт верный знак.

Все типы — frozen dataclasses (для Hashable + read-only). Pydantic не нужен
здесь — value objects не валидируются из user input, они приходят из
`adapters/tinkoff/proto_to_domain.py` и используются внутри domain.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

# Знаменатель для перевода nano-долей в Decimal. Использование Decimal
# вместо int(1e9) обязательно, иначе деление вернёт float и испортит точность.
_NANO_DENOMINATOR: Decimal = Decimal(1_000_000_000)


@dataclass(frozen=True, slots=True)
class MoneyValue:
    """Денежная сумма в указанной валюте.

    Соответствует protobuf-типу `tinkoff.invest.MoneyValue`.

    >>> mv = MoneyValue(units=1, nano=500_000_000, currency='rub')
    >>> mv.to_decimal()
    Decimal('1.500000000')

    Отрицательные значения: и `units`, и `nano` имеют общий знак. Например,
    -1.5 RUB = MoneyValue(-1, -500_000_000, 'rub').
    """

    units: int
    nano: int
    currency: str

    def to_decimal(self) -> Decimal:
        return Decimal(self.units) + Decimal(self.nano) / _NANO_DENOMINATOR

    @classmethod
    def from_decimal(cls, value: Decimal, currency: str) -> "MoneyValue":
        """Обратная конвертация: Decimal → (units, nano).

        Полезно для тестов и логирования. В обычных продакшн-сценариях
        мы только декодируем из API, обратной конвертации не требуется.
        """
        # Рассчитываем sign отдельно, чтобы корректно обработать -0.5
        # (units=0, nano=-500_000_000).
        sign = -1 if value < 0 else 1
        abs_value = abs(value)
        units = int(abs_value)
        nano_decimal = (abs_value - Decimal(units)) * _NANO_DENOMINATOR
        nano = int(nano_decimal)
        return cls(units=sign * units, nano=sign * nano, currency=currency)

    def __str__(self) -> str:  # для логов
        return f"{self.to_decimal()} {self.currency.upper()}"


@dataclass(frozen=True, slots=True)
class Quotation:
    """Безвалютное число с фиксированной точностью (price, ratio и т.п.).

    Соответствует protobuf-типу `tinkoff.invest.Quotation`. От `MoneyValue`
    отличается отсутствием поля currency. Используется для цен инструментов,
    шагов цены, коэффициентов.
    """

    units: int
    nano: int

    def to_decimal(self) -> Decimal:
        return Decimal(self.units) + Decimal(self.nano) / _NANO_DENOMINATOR

    @classmethod
    def from_decimal(cls, value: Decimal) -> "Quotation":
        sign = -1 if value < 0 else 1
        abs_value = abs(value)
        units = int(abs_value)
        nano = int((abs_value - Decimal(units)) * _NANO_DENOMINATOR)
        return cls(units=sign * units, nano=sign * nano)

    def __str__(self) -> str:
        return str(self.to_decimal())


@dataclass(frozen=True, slots=True)
class InstrumentRef:
    """Тонкая ссылка на инструмент: `uid` обязательно, `figi` опционально.

    Использовать как ключ при работе с операциями/позициями. UID — primary
    в T-Invest API (стабилен при листинг-изменениях, единственный
    идентификатор у опционов). FIGI deprecated, но удобно для логов.
    """

    uid: str
    figi: Optional[str] = None
    instrument_type: Optional[str] = None  # 'share' | 'bond' | 'future' | 'option' | 'currency' | 'etf'

    def __str__(self) -> str:
        if self.figi:
            return f"{self.uid} ({self.figi})"
        return self.uid
