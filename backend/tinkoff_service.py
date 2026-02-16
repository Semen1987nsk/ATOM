"""
Tinkoff Invest API Integration Service — v2 (ПОЛНЫЙ РЕФАКТОРИНГ)

Автоматическая синхронизация сделок с брокером Тинькофф.
REST API: https://invest-public-api.tinkoff.ru/rest

АРХИТЕКТУРА ИМПОРТА:
  1. Загрузка операций за период (30-дневные чанки, дедупликация по id)
  2. Фильтрация: только BUY/SELL с executed qty > 0
  3. Группировка по FIGI → FIFO-трекинг signed net_qty
  4. При закрытии (net_qty → 0) или флипе → формируем Trade
  5. Остаток → открытый Trade (exit_at = None)
  6. Дедупликация в БД по набору operation-ID

PnL-ФОРМУЛЫ:
  - Акции:   PnL = Σpayment (buy-payments отрицательны, sell — положительны)
  - Фьючерсы: PnL = (exit − entry) × qty × (minPriceIncrementAmount / minPriceIncrement)
              Fallback — Σpayment если point_value недоступен
  - net_pnl = pnl − commission
  - commission из childOperations (OPERATION_TYPE_BROKER_FEE и др.)
"""

import logging
import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session
from models import Trade, TradeDirection, BrokerConnection, Account, BalanceSnapshot, CapitalOperation
from utils.datetime_utils import utc_now_naive

logger = logging.getLogger(__name__)

TINKOFF_API_BASE = "https://invest-public-api.tinkoff.ru/rest"


# ═══════════════════════════════════════════════════
#  FIFO Lot — единица учёта в FIFO-очереди
# ═══════════════════════════════════════════════════

@dataclass
class FifoLot:
    """Один лот (вход) в очереди FIFO."""
    price: Decimal
    qty: int
    date: Optional[datetime]   # naive UTC
    payment: Decimal           # payment из API (BUY < 0, SELL > 0)
    commission: Decimal        # |commission| из childOperations
    op_id: str                 # id операции


@dataclass
class ClosedTrade:
    """Результат закрытия позиции — материал для модели Trade."""
    figi: str
    direction: str                     # "LONG" / "SHORT"
    entry_lots: List[FifoLot]          # FIFO-лоты входов
    exit_lots: List[FifoLot]           # FIFO-лоты выходов
    entry_price: Decimal = Decimal(0)
    exit_price: Decimal = Decimal(0)
    total_qty: int = 0
    entry_at: Optional[datetime] = None
    exit_at: Optional[datetime] = None
    pnl: Optional[Decimal] = None
    net_pnl: Optional[Decimal] = None
    commission: Decimal = Decimal(0)
    op_ids: List[str] = field(default_factory=list)

    def compute(self, instrument: Dict):
        """Рассчитывает все поля на основе lots."""
        self.total_qty = sum(l.qty for l in self.entry_lots)
        exit_qty = sum(l.qty for l in self.exit_lots)

        if self.total_qty > 0:
            self.entry_price = (
                sum(l.price * l.qty for l in self.entry_lots) / Decimal(self.total_qty)
            ).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        if exit_qty > 0:
            self.exit_price = (
                sum(l.price * l.qty for l in self.exit_lots) / Decimal(exit_qty)
            ).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

        entry_dates = [l.date for l in self.entry_lots if l.date]
        exit_dates = [l.date for l in self.exit_lots if l.date]
        self.entry_at = min(entry_dates) if entry_dates else None
        self.exit_at = max(exit_dates) if exit_dates else None

        self.commission = (
            sum(l.commission for l in self.entry_lots)
            + sum(l.commission for l in self.exit_lots)
        )

        self.op_ids = sorted(set(
            [l.op_id for l in self.entry_lots]
            + [l.op_id for l in self.exit_lots]
        ))

        is_closed = exit_qty >= self.total_qty
        if is_closed and self.exit_lots:
            is_futures = instrument.get("instrument_type") == "INSTRUMENT_TYPE_FUTURES"
            if is_futures:
                self.pnl = self._futures_pnl(instrument)
            else:
                self.pnl = self._stock_pnl()
            self.net_pnl = self.pnl - self.commission
        else:
            self.pnl = None
            self.net_pnl = None

    def _stock_pnl(self) -> Decimal:
        """PnL акций = сумма всех payments (BUY < 0, SELL > 0)."""
        return sum(l.payment for l in self.entry_lots) + \
               sum(l.payment for l in self.exit_lots)

    def _futures_pnl(self, instrument: Dict) -> Decimal:
        """PnL фьючерсов = price_diff x qty x point_value."""
        min_inc = instrument.get("min_price_increment", Decimal(0))
        min_inc_amount = instrument.get("min_price_increment_amount", Decimal(0))

        if min_inc and min_inc > 0 and min_inc_amount and min_inc_amount > 0:
            point_value = min_inc_amount / min_inc
            price_diff = self.exit_price - self.entry_price
            if self.direction == "SHORT":
                price_diff = -price_diff
            return (price_diff * Decimal(self.total_qty) * point_value).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            logger.warning(f"point_value unavailable for {self.figi}, using payment-sum fallback")
            return self._stock_pnl()


# ═══════════════════════════════════════════════════
#  TinkoffService
# ═══════════════════════════════════════════════════

class TinkoffService:
    """Сервис для работы с Tinkoff Invest API (REST)."""

    def __init__(self, token: str):
        self.token = token
        self._instruments_cache: Dict[str, Dict] = {}
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

    # ───────────── HTTP ─────────────

    def _make_request(self, method: str, endpoint: str, data: dict = None) -> dict:
        url = f"{TINKOFF_API_BASE}{endpoint}"
        with httpx.Client(timeout=30.0) as client:
            if method == "GET":
                response = client.get(url, headers=self.headers, params=data)
            else:
                response = client.post(url, headers=self.headers, json=data or {})
            if response.status_code != 200:
                error_text = response.text
                logger.error(f"Tinkoff API error {response.status_code}: {error_text}")
                raise Exception(f"API Error {response.status_code}: {error_text}")
            return response.json()

    # ───────────── Token verification ─────────────

    def verify_token(self) -> Dict[str, Any]:
        try:
            result = self._make_request(
                "POST",
                "/tinkoff.public.invest.api.contract.v1.UsersService/GetAccounts",
            )
            accounts = []
            for acc in result.get("accounts", []):
                accounts.append({
                    "id": acc.get("id"),
                    "name": acc.get("name", "Счёт"),
                    "type": acc.get("type", "UNKNOWN"),
                    "status": acc.get("status", "UNKNOWN"),
                    "access_level": acc.get("accessLevel", "UNKNOWN"),
                })
            return {"valid": True, "accounts": accounts}
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            return {"valid": False, "error": str(e)}

    # ───────────── Instrument info (with cache) ─────────────

    def get_instrument_info(self, figi: str) -> Optional[Dict]:
        if figi in self._instruments_cache:
            return self._instruments_cache[figi]
        try:
            result = self._make_request(
                "POST",
                "/tinkoff.public.invest.api.contract.v1.InstrumentsService/GetInstrumentBy",
                {"idType": "INSTRUMENT_ID_TYPE_FIGI", "id": figi},
            )
            instrument = result.get("instrument", {})
            instrument_type = instrument.get("instrumentKind", "INSTRUMENT_TYPE_SHARE")

            if instrument_type == "INSTRUMENT_TYPE_FUTURES":
                try:
                    fr = self._make_request(
                        "POST",
                        "/tinkoff.public.invest.api.contract.v1.InstrumentsService/FutureBy",
                        {"idType": "INSTRUMENT_ID_TYPE_FIGI", "id": figi},
                    )
                    fi = fr.get("instrument", {})
                    if fi:
                        instrument = fi
                except Exception as fe:
                    logger.warning(f"FutureBy failed for {figi}: {fe}")

            info = {
                "figi": figi,
                "ticker": instrument.get("ticker", figi),
                "name": instrument.get("name", figi),
                "lot": instrument.get("lot", 1),
                "currency": instrument.get("currency", "RUB").upper(),
                "class_code": instrument.get("classCode", ""),
                "instrument_type": instrument_type,
                "min_price_increment": self._money_to_decimal(instrument.get("minPriceIncrement", {})),
                "min_price_increment_amount": self._money_to_decimal(instrument.get("minPriceIncrementAmount", {})),
                "basic_asset_size": self._money_to_decimal(instrument.get("basicAssetSize", {})),
            }
            self._instruments_cache[figi] = info
            return info
        except Exception as e:
            logger.warning(f"Failed to get instrument info for {figi}: {e}")
            return None

    # ───────────── Helpers ─────────────

    def _money_to_decimal(self, money) -> Decimal:
        if not money or not isinstance(money, dict):
            return Decimal(0)
        try:
            units = int(money.get("units", 0) or 0)
            nano = int(money.get("nano", 0) or 0)
            return Decimal(units) + Decimal(nano) / Decimal(1_000_000_000)
        except (ValueError, TypeError):
            return Decimal(0)

    @staticmethod
    def _get_executed_qty(op: Dict) -> int:
        """
        Реально исполненное количество.
        Приоритет: quantityDone -> sum(trades[].quantity) -> quantity - quantityRest -> quantity
        """
        qty_done = op.get("quantityDone")
        if qty_done is not None:
            try:
                val = int(qty_done)
                if val > 0:
                    return val
            except (ValueError, TypeError):
                pass
        trades_list = op.get("trades", [])
        if trades_list:
            try:
                val = sum(int(t.get("quantity", 0)) for t in trades_list)
                if val > 0:
                    return val
            except (ValueError, TypeError):
                pass
        raw_qty = op.get("quantity", 0)
        qty_rest = op.get("quantityRest", 0)
        try:
            raw_qty = int(raw_qty)
            qty_rest = int(qty_rest)
            if qty_rest > 0:
                return max(raw_qty - qty_rest, 0)
            return max(raw_qty, 0)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _get_commission_from_op(op: Dict, money_fn) -> Decimal:
        """Извлекает сумму комиссий из childOperations."""
        total = Decimal(0)
        for child in op.get("childOperations", []):
            child_payment = child.get("payment")
            if child_payment:
                val = money_fn(child_payment)
                if val != 0:
                    total += abs(val)
        return total

    def _to_timestamp(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Парсит дату из API. Возвращает naive datetime (UTC) или None."""
        if not date_str:
            return None
        try:
            clean = date_str.strip()
            if clean.endswith("Z"):
                clean = clean[:-1] + "+00:00"
            dt = datetime.fromisoformat(clean)
            return dt.replace(tzinfo=None)
        except (ValueError, AttributeError):
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.strptime(date_str.strip(), fmt)
                except ValueError:
                    continue
            logger.warning(f"Failed to parse date: {date_str!r}")
            return None

    @staticmethod
    def _map_instrument_type(tinkoff_type: str) -> str:
        mapping = {
            "INSTRUMENT_TYPE_SHARE": "Stock",
            "INSTRUMENT_TYPE_BOND": "Bond",
            "INSTRUMENT_TYPE_ETF": "ETF",
            "INSTRUMENT_TYPE_CURRENCY": "Currency",
            "INSTRUMENT_TYPE_FUTURES": "Futures",
            "INSTRUMENT_TYPE_OPTION": "Option",
        }
        return mapping.get(tinkoff_type, "Stock")

    # ───────────── Fetch operations ─────────────

    def get_operations(
        self,
        broker_account_id: str,
        from_date: datetime,
        to_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """Операции за период. Разбивка по 30 дней, дедупликация по id."""
        if to_date is None:
            to_date = utc_now_naive()

        all_operations: List[Dict] = []
        current_start = from_date

        logger.info(f"Fetching operations from {from_date} to {to_date}")

        while current_start < to_date:
            current_end = min(current_start + timedelta(days=30), to_date)
            if (current_end - current_start).total_seconds() < 1:
                break
            try:
                chunk = self._make_request(
                    "POST",
                    "/tinkoff.public.invest.api.contract.v1.OperationsService/GetOperations",
                    {
                        "accountId": broker_account_id,
                        "from": self._to_timestamp(current_start),
                        "to": self._to_timestamp(current_end),
                        "state": "OPERATION_STATE_EXECUTED",
                    },
                )
                all_operations.extend(chunk.get("operations", []))
            except Exception as e:
                logger.error(f"Error fetching chunk {current_start} - {current_end}: {e}")
            current_start = current_end

        unique = {op["id"]: op for op in all_operations if "id" in op}
        result = list(unique.values())
        logger.info(f"Fetched {len(result)} unique operations total")
        return result

    # ───────────── Portfolio ─────────────

    def get_portfolio(self, broker_account_id: str) -> Dict[str, Any]:
        result = self._make_request(
            "POST",
            "/tinkoff.public.invest.api.contract.v1.OperationsService/GetPortfolio",
            {"accountId": broker_account_id, "currency": "RUB"},
        )
        portfolio = {
            "total_balance": Decimal(0),
            "cash": self._money_to_decimal(result.get("totalAmountCurrencies", {})),
            "stocks_value": self._money_to_decimal(result.get("totalAmountShares", {})),
            "bonds_value": self._money_to_decimal(result.get("totalAmountBonds", {})),
            "etf_value": self._money_to_decimal(result.get("totalAmountEtf", {})),
            "futures_value": self._money_to_decimal(result.get("totalAmountFutures", {})),
            "unrealized_pnl": self._money_to_decimal(result.get("expectedYield", {})),
            "positions": [],
            "raw": result,
        }
        tap = result.get("totalAmountPortfolio")
        if tap:
            portfolio["total_balance"] = self._money_to_decimal(tap)
        else:
            portfolio["total_balance"] = (
                portfolio["cash"]
                + portfolio["stocks_value"]
                + portfolio["bonds_value"]
                + portfolio["etf_value"]
            )
        for pos in result.get("positions", []):
            figi = pos.get("figi", "")
            inst = self.get_instrument_info(figi)
            portfolio["positions"].append({
                "figi": figi,
                "ticker": inst.get("ticker", figi) if inst else figi,
                "name": inst.get("name", "") if inst else "",
                "quantity": self._money_to_decimal(pos.get("quantity", {})),
                "average_price": self._money_to_decimal(pos.get("averagePositionPrice", {})),
                "current_price": self._money_to_decimal(pos.get("currentPrice", {})),
                "unrealized_pnl": self._money_to_decimal(pos.get("expectedYield", {})),
                "instrument_type": pos.get("instrumentType", ""),
            })
        return portfolio

    # ═══════════════════════════════════════════════════
    #  SYNC TRADES — главный метод
    # ═══════════════════════════════════════════════════

    def sync_trades(
        self,
        db: Session,
        connection: BrokerConnection,
        from_date: Optional[datetime] = None,
        force_full_sync: bool = False,
    ) -> Dict[str, Any]:
        result = {
            "success": True,
            "new_trades": 0,
            "updated_trades": 0,
            "skipped": 0,
            "errors": [],
            "positions": {},
        }

        if from_date is None:
            if force_full_sync or connection.sync_from_date:
                from_date = connection.sync_from_date or datetime(2020, 1, 1)
            elif connection.last_sync_at:
                from_date = connection.last_sync_at - timedelta(days=1)
            else:
                from_date = utc_now_naive() - timedelta(days=30)

        to_date = utc_now_naive()
        logger.info(f"Syncing trades from {from_date} to {to_date}")

        try:
            operations = self.get_operations(connection.broker_account_id, from_date, to_date)

            # Capital operations (deposits/withdrawals)
            self._process_capital_operations(db, connection.account_id, operations)

            # FIFO-трекинг -> ClosedTrade + open positions
            closed_trades, open_positions = self._build_trades_fifo(operations)

            logger.info(
                f"FIFO result: {len(closed_trades)} closed trades, "
                f"{len(open_positions)} open positions"
            )

            # Сохраняем закрытые сделки
            for ct in closed_trades:
                try:
                    status = self._save_closed_trade(db, connection.account_id, ct)
                    if status == "new":
                        result["new_trades"] += 1
                    elif status == "updated":
                        result["updated_trades"] += 1
                    else:
                        result["skipped"] += 1
                except Exception as e:
                    import traceback
                    logger.error(f"Error saving closed trade {ct.figi}: {e}\n{traceback.format_exc()}")
                    result["errors"].append(f"{ct.figi}: {e}")

            # Сохраняем открытые позиции
            for op_pos in open_positions:
                try:
                    status = self._save_open_position(db, connection.account_id, op_pos)
                    if status == "new":
                        result["new_trades"] += 1
                    elif status == "updated":
                        result["updated_trades"] += 1
                    else:
                        result["skipped"] += 1
                except Exception as e:
                    import traceback
                    logger.error(f"Error saving open position {op_pos['figi']}: {e}\n{traceback.format_exc()}")
                    result["errors"].append(f"{op_pos['figi']} (open): {e}")

            # Статус подключения
            connection.last_sync_at = utc_now_naive()
            connection.last_sync_status = "success" if not result["errors"] else "partial"
            connection.last_sync_error = "; ".join(result["errors"][:3]) if result["errors"] else None
            connection.total_synced_trades = (connection.total_synced_trades or 0) + result["new_trades"]

            # Balance snapshot
            try:
                portfolio = self.get_portfolio(connection.broker_account_id)
                self._save_balance_snapshot(db, connection.account_id, portfolio)
                result["portfolio"] = {
                    "total_balance": float(portfolio["total_balance"]),
                    "cash": float(portfolio["cash"]),
                    "unrealized_pnl": float(portfolio["unrealized_pnl"]),
                }
            except Exception as e:
                logger.warning(f"Failed to save balance snapshot: {e}")

            db.commit()

            result["positions"] = {
                "total_operations": len(operations),
                "closed_trades": len(closed_trades),
                "open_positions": len(open_positions),
            }

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            connection.last_sync_status = "error"
            connection.last_sync_error = str(e)
            db.commit()
            result["success"] = False
            result["errors"].append(str(e))

        return result

    # ═══════════════════════════════════════════════════
    #  FIFO ENGINE — ядро импорта
    # ═══════════════════════════════════════════════════

    _BUY_TYPES = {"OPERATION_TYPE_BUY", "OPERATION_TYPE_BUY_CARD"}
    _SELL_TYPES = {"OPERATION_TYPE_SELL", "OPERATION_TYPE_SELL_CARD"}

    def _build_trades_fifo(
        self, operations: List[Dict]
    ) -> Tuple[List[ClosedTrade], List[Dict]]:
        """
        FIFO-группировка операций -> закрытые сделки + открытые позиции.

        Алгоритм для каждого FIGI:
          - signed net_qty: positive = LONG, negative = SHORT
          - Операция в направлении позиции -> добавляем лот в FIFO-очередь
          - Операция против позиции -> закрываем FIFO-лоты с фронта
            - Если net_qty -> 0: закрываем позицию целиком
            - Если net_qty меняет знак (flip): закрываем старую, открываем новую
          - В конце: оставшаяся FIFO-очередь -> открытая позиция
        """
        # 1. Фильтруем и сортируем
        trade_ops = []
        for op in operations:
            op_type = op.get("operationType", "")
            if op_type not in self._BUY_TYPES and op_type not in self._SELL_TYPES:
                continue
            figi = op.get("figi", "")
            if not figi:
                continue
            executed_qty = self._get_executed_qty(op)
            if executed_qty <= 0:
                logger.debug(f"Skip unfilled op {op.get('id')}")
                continue
            trade_ops.append(op)

        trade_ops.sort(key=lambda x: x.get("date", ""))

        # 2. Группируем по FIGI
        by_figi: Dict[str, List[Dict]] = defaultdict(list)
        for op in trade_ops:
            by_figi[op["figi"]].append(op)

        closed_trades: List[ClosedTrade] = []
        open_positions: List[Dict] = []

        # 3. Для каждого FIGI — FIFO
        for figi, ops in by_figi.items():
            instrument = self.get_instrument_info(figi)
            ct, op_pos = self._fifo_for_figi(figi, ops, instrument)
            closed_trades.extend(ct)
            if op_pos is not None:
                open_positions.append(op_pos)

        return closed_trades, open_positions

    def _fifo_for_figi(
        self,
        figi: str,
        ops: List[Dict],
        instrument: Optional[Dict],
    ) -> Tuple[List[ClosedTrade], Optional[Dict]]:
        """
        FIFO-трекинг для одного FIGI.
        Возвращает (closed_trades, open_position_dict_or_None).
        """
        closed: List[ClosedTrade] = []

        # Текущая открытая позиция
        fifo_queue: List[FifoLot] = []          # FIFO-очередь входов
        entry_lots_closed: List[FifoLot] = []   # лоты входов, уже закрытые (для ClosedTrade)
        exit_lots: List[FifoLot] = []           # выходы текущей позиции
        direction: Optional[str] = None         # "LONG" / "SHORT" / None

        def _emit_closed_trade():
            """Формирует ClosedTrade из entry_lots_closed + exit_lots."""
            nonlocal entry_lots_closed, exit_lots, direction
            if not entry_lots_closed:
                return
            ct = ClosedTrade(
                figi=figi,
                direction=direction or "LONG",
                entry_lots=list(entry_lots_closed),
                exit_lots=list(exit_lots),
            )
            ct.compute(instrument or {})
            closed.append(ct)
            entry_lots_closed = []
            exit_lots = []

        for op in ops:
            op_type = op.get("operationType", "")
            is_buy = op_type in self._BUY_TYPES
            qty = self._get_executed_qty(op)
            price = self._money_to_decimal(op.get("price", {}))
            payment = self._money_to_decimal(op.get("payment", {}))
            commission = self._get_commission_from_op(op, self._money_to_decimal)
            date = self._parse_date(op.get("date"))
            op_id = op.get("id", "")

            lot = FifoLot(
                price=price, qty=qty, date=date,
                payment=payment, commission=commission, op_id=op_id,
            )

            # Определяем направление
            if direction is None:
                # Первая операция -> открываем позицию
                direction = "LONG" if is_buy else "SHORT"
                fifo_queue.append(lot)
                continue

            is_same_direction = (
                (is_buy and direction == "LONG")
                or (not is_buy and direction == "SHORT")
            )

            if is_same_direction:
                # Добавление к позиции (масштабирование / усреднение)
                fifo_queue.append(lot)
            else:
                # Закрытие / частичное закрытие / flip
                remaining_qty = qty
                # Пропорции для payment/commission при разбиении exit-операции на части
                original_qty = qty

                while remaining_qty > 0 and fifo_queue:
                    front = fifo_queue[0]

                    if front.qty <= remaining_qty:
                        # Полностью закрываем этот FIFO-лот
                        closed_qty = front.qty
                        remaining_qty -= closed_qty

                        # Exit-лот (пропорция от exit-операции)
                        ratio = Decimal(closed_qty) / Decimal(original_qty)
                        exit_lot = FifoLot(
                            price=price, qty=closed_qty, date=date,
                            payment=payment * ratio,
                            commission=commission * ratio,
                            op_id=op_id,
                        )
                        exit_lots.append(exit_lot)
                        entry_lots_closed.append(fifo_queue.pop(0))
                    else:
                        # Частично закрываем фронтальный FIFO-лот
                        closed_qty = remaining_qty

                        # Split фронтального лота
                        front_close_ratio = Decimal(closed_qty) / Decimal(front.qty)
                        front_remain_ratio = Decimal(1) - front_close_ratio

                        closed_entry = FifoLot(
                            price=front.price, qty=closed_qty, date=front.date,
                            payment=front.payment * front_close_ratio,
                            commission=front.commission * front_close_ratio,
                            op_id=front.op_id,
                        )
                        remaining_entry = FifoLot(
                            price=front.price, qty=front.qty - closed_qty, date=front.date,
                            payment=front.payment * front_remain_ratio,
                            commission=front.commission * front_remain_ratio,
                            op_id=front.op_id,
                        )

                        # Exit-лот
                        exit_ratio = Decimal(closed_qty) / Decimal(original_qty)
                        exit_lot = FifoLot(
                            price=price, qty=closed_qty, date=date,
                            payment=payment * exit_ratio,
                            commission=commission * exit_ratio,
                            op_id=op_id,
                        )
                        exit_lots.append(exit_lot)
                        entry_lots_closed.append(closed_entry)

                        # Заменяем front на остаток
                        fifo_queue[0] = remaining_entry
                        remaining_qty = 0

                if not fifo_queue:
                    # Позиция полностью закрыта
                    _emit_closed_trade()
                    direction = None

                    if remaining_qty > 0:
                        # FLIP: остаток открывает позицию в противоположном направлении
                        direction = "LONG" if is_buy else "SHORT"
                        flip_ratio = Decimal(remaining_qty) / Decimal(original_qty)
                        flip_lot = FifoLot(
                            price=price, qty=remaining_qty, date=date,
                            payment=payment * flip_ratio,
                            commission=commission * flip_ratio,
                            op_id=op_id,
                        )
                        fifo_queue.append(flip_lot)

        # Конец цикла: оставшаяся открытая позиция
        open_pos = None
        if fifo_queue and direction:
            # Все лоты в fifo_queue — это текущие открытые входы
            all_entry_lots = list(fifo_queue)
            partial_exits = list(exit_lots) if exit_lots else []

            total_qty = sum(l.qty for l in all_entry_lots)
            entry_price = Decimal(0)
            if total_qty > 0:
                entry_price = sum(l.price * l.qty for l in all_entry_lots) / Decimal(total_qty)

            dates = [l.date for l in all_entry_lots if l.date]
            entry_at = min(dates) if dates else None

            entry_commission = sum(l.commission for l in all_entry_lots)
            exit_commission = sum(l.commission for l in partial_exits)

            op_ids = sorted(set(
                [l.op_id for l in all_entry_lots]
                + [l.op_id for l in partial_exits]
            ))

            # Operations JSON
            ops_json = []
            for lot in all_entry_lots:
                ops_json.append({
                    "type": "entry", "price": float(lot.price), "qty": lot.qty,
                    "time": lot.date.isoformat() if lot.date else None,
                    "payment": float(lot.payment), "commission": float(lot.commission),
                    "op_id": lot.op_id,
                })
            for lot in partial_exits:
                ops_json.append({
                    "type": "exit", "price": float(lot.price), "qty": lot.qty,
                    "time": lot.date.isoformat() if lot.date else None,
                    "payment": float(lot.payment), "commission": float(lot.commission),
                    "op_id": lot.op_id, "note": "partial_close",
                })

            open_pos = {
                "figi": figi,
                "direction": direction,
                "entry_price": entry_price,
                "total_qty": total_qty,
                "entry_at": entry_at,
                "commission": entry_commission + exit_commission,
                "op_ids": op_ids,
                "operations": ops_json,
            }

        return closed, open_pos

    # ═══════════════════════════════════════════════════
    #  DB SAVE — сохранение / дедупликация
    # ═══════════════════════════════════════════════════

    def _get_op_ids_set(self, trade: Trade) -> set:
        """Извлекает set op_id из trade.operations JSON."""
        if not trade.operations:
            return set()
        ids = set()
        for op in trade.operations:
            if isinstance(op, dict):
                oid = op.get("op_id") or op.get("id")
                if oid:
                    ids.add(str(oid))
        return ids

    def _build_operations_json(
        self, entry_lots: List[FifoLot], exit_lots: List[FifoLot]
    ) -> list:
        """Формирует JSON-массив для поля Trade.operations."""
        ops = []
        for lot in entry_lots:
            ops.append({
                "type": "entry", "price": float(lot.price), "qty": lot.qty,
                "time": lot.date.isoformat() if lot.date else None,
                "payment": float(lot.payment), "commission": float(lot.commission),
                "op_id": lot.op_id,
            })
        for lot in exit_lots:
            ops.append({
                "type": "exit", "price": float(lot.price), "qty": lot.qty,
                "time": lot.date.isoformat() if lot.date else None,
                "payment": float(lot.payment), "commission": float(lot.commission),
                "op_id": lot.op_id,
            })
        return ops

    def _find_existing_trade_by_ops(
        self, db: Session, account_id: int, op_ids: List[str], symbol: str
    ) -> Optional[Trade]:
        """
        Ищет Trade в БД, у которого operations содержит совпадающие op_id.
        Совпадение: >= 50% op_ids совпадают с любой стороны.
        """
        if not op_ids:
            return None

        candidates = db.query(Trade).filter(
            Trade.account_id == account_id,
            Trade.symbol == symbol,
        ).all()

        op_ids_set = set(op_ids)
        best_match = None
        best_overlap = 0

        for trade in candidates:
            existing_ids = self._get_op_ids_set(trade)
            if not existing_ids:
                continue
            overlap = len(op_ids_set & existing_ids)
            min_len = min(len(op_ids_set), len(existing_ids))
            if min_len > 0 and overlap / min_len >= 0.5:
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match = trade

        return best_match

    def _save_closed_trade(
        self, db: Session, account_id: int, ct: ClosedTrade
    ) -> str:
        """Сохраняет ClosedTrade в БД. Возвращает 'new' / 'updated' / 'skipped'."""
        instrument = self.get_instrument_info(ct.figi)
        if not instrument:
            instrument = {
                "ticker": ct.figi, "name": ct.figi, "lot": 1,
                "currency": "RUB", "instrument_type": "",
            }

        symbol = instrument["ticker"]
        direction = TradeDirection.LONG if ct.direction == "LONG" else TradeDirection.SHORT
        operations_json = self._build_operations_json(ct.entry_lots, ct.exit_lots)

        # Дедупликация по op_ids
        existing = self._find_existing_trade_by_ops(db, account_id, ct.op_ids, symbol)

        if existing:
            existing.entry_price = ct.entry_price
            existing.exit_price = ct.exit_price
            existing.quantity = Decimal(str(ct.total_qty))
            existing.direction = direction
            existing.pnl = ct.pnl
            existing.net_pnl = ct.net_pnl
            existing.commission = ct.commission
            existing.entry_at = ct.entry_at
            existing.exit_at = ct.exit_at
            existing.operations = operations_json
            existing.tags = ["#tinkoff", "#autosync"]
            if ct.entry_at and ct.exit_at:
                delta = ct.exit_at - ct.entry_at
                existing.holding_time_minutes = max(int(delta.total_seconds() / 60), 0)
            db.flush()
            return "updated"

        new_trade = Trade(
            account_id=account_id,
            symbol=symbol,
            asset_name=instrument.get("name", symbol),
            asset_type=self._map_instrument_type(instrument.get("instrument_type", "")),
            direction=direction,
            entry_price=ct.entry_price,
            exit_price=ct.exit_price,
            quantity=Decimal(str(ct.total_qty)),
            entry_at=ct.entry_at,
            exit_at=ct.exit_at,
            pnl=ct.pnl,
            net_pnl=ct.net_pnl,
            commission=ct.commission,
            currency=instrument.get("currency", "RUB"),
            operations=operations_json,
            tags=["#tinkoff", "#autosync"],
        )
        if ct.entry_at and ct.exit_at:
            delta = ct.exit_at - ct.entry_at
            new_trade.holding_time_minutes = max(int(delta.total_seconds() / 60), 0)

        db.add(new_trade)
        db.flush()
        return "new"

    def _save_open_position(
        self, db: Session, account_id: int, pos: Dict
    ) -> str:
        """Сохраняет открытую позицию в БД."""
        instrument = self.get_instrument_info(pos["figi"])
        if not instrument:
            instrument = {
                "ticker": pos["figi"], "name": pos["figi"], "lot": 1,
                "currency": "RUB", "instrument_type": "",
            }

        symbol = instrument["ticker"]
        direction = TradeDirection.LONG if pos["direction"] == "LONG" else TradeDirection.SHORT

        # Ищем существующую открытую сделку по символу
        existing = db.query(Trade).filter(
            Trade.account_id == account_id,
            Trade.symbol == symbol,
            Trade.exit_at == None,  # noqa: E711
        ).first()

        if existing:
            existing.entry_price = pos["entry_price"]
            existing.quantity = Decimal(str(pos["total_qty"]))
            existing.direction = direction
            existing.commission = pos["commission"]
            existing.entry_at = pos["entry_at"]
            existing.operations = pos["operations"]
            existing.tags = ["#tinkoff", "#autosync"]
            db.flush()
            return "updated"

        new_trade = Trade(
            account_id=account_id,
            symbol=symbol,
            asset_name=instrument.get("name", symbol),
            asset_type=self._map_instrument_type(instrument.get("instrument_type", "")),
            direction=direction,
            entry_price=pos["entry_price"],
            quantity=Decimal(str(pos["total_qty"])),
            entry_at=pos["entry_at"],
            exit_at=None,
            pnl=None,
            net_pnl=None,
            commission=pos["commission"],
            currency=instrument.get("currency", "RUB"),
            operations=pos["operations"],
            tags=["#tinkoff", "#autosync"],
        )
        db.add(new_trade)
        db.flush()
        return "new"

    # ═══════════════════════════════════════════════════
    #  CAPITAL OPERATIONS
    # ═══════════════════════════════════════════════════

    def _process_capital_operations(self, db: Session, account_id: int, operations: List[Dict]):
        input_types = {"OPERATION_TYPE_INPUT", "OPERATION_TYPE_INPUT_CARD"}
        output_types = {"OPERATION_TYPE_OUTPUT", "OPERATION_TYPE_OUTPUT_CARD"}

        count = 0
        for op in operations:
            op_type = op.get("operationType", "")
            if op_type not in input_types and op_type not in output_types:
                continue
            op_id = op.get("id")
            if not op_id:
                continue
            existing = db.query(CapitalOperation).filter(
                CapitalOperation.account_id == account_id,
                CapitalOperation.broker_id == op_id,
            ).first()
            if existing:
                continue
            is_input = op_type in input_types
            amount = abs(self._money_to_decimal(op.get("payment", {})))
            capital_op = CapitalOperation(
                account_id=account_id,
                broker_id=op_id,
                operation_type="deposit" if is_input else "withdrawal",
                amount=amount,
                currency=op.get("payment", {}).get("currency", "rub"),
                date=self._parse_date(op.get("date")),
                description=op_type,
            )
            db.add(capital_op)
            count += 1

        if count > 0:
            db.commit()
            logger.info(f"Processed {count} capital operations")
            deposits = db.query(CapitalOperation).filter(
                CapitalOperation.account_id == account_id,
                CapitalOperation.operation_type == "deposit",
            ).all()
            withdrawals = db.query(CapitalOperation).filter(
                CapitalOperation.account_id == account_id,
                CapitalOperation.operation_type == "withdrawal",
            ).all()
            total_dep = sum(o.amount for o in deposits)
            total_wd = sum(o.amount for o in withdrawals)
            net_deposit = total_dep - total_wd
            account = db.query(Account).filter(Account.id == account_id).first()
            if account and total_dep > 0:
                account.initial_balance = net_deposit
                logger.info(f"Account initial_balance = {net_deposit} (Dep: {total_dep}, Wd: {total_wd})")
                db.commit()

    # ───────────── Balance snapshot ─────────────

    def _save_balance_snapshot(
        self, db: Session, account_id: int, portfolio: Dict[str, Any]
    ) -> Optional[BalanceSnapshot]:
        today = utc_now_naive().replace(hour=0, minute=0, second=0, microsecond=0)
        existing = db.query(BalanceSnapshot).filter(
            BalanceSnapshot.account_id == account_id,
            BalanceSnapshot.date >= today,
            BalanceSnapshot.source == "tinkoff_api",
        ).first()
        if existing:
            existing.balance = portfolio["total_balance"]
            existing.cash = portfolio["cash"]
            existing.stocks_value = portfolio["stocks_value"]
            existing.bonds_value = portfolio["bonds_value"]
            existing.etf_value = portfolio["etf_value"]
            existing.futures_value = portfolio["futures_value"]
            existing.unrealized_pnl = portfolio["unrealized_pnl"]
            return existing
        snapshot = BalanceSnapshot(
            account_id=account_id,
            date=utc_now_naive(),
            balance=portfolio["total_balance"],
            cash=portfolio["cash"],
            stocks_value=portfolio["stocks_value"],
            bonds_value=portfolio["bonds_value"],
            etf_value=portfolio["etf_value"],
            futures_value=portfolio["futures_value"],
            unrealized_pnl=portfolio["unrealized_pnl"],
            source="tinkoff_api",
        )
        db.add(snapshot)
        account = db.query(Account).filter(Account.id == account_id).first()
        if account:
            account.balance = portfolio["total_balance"]
        logger.info(f"Balance snapshot: {portfolio['total_balance']}")
        return snapshot


def create_tinkoff_service(token: str) -> TinkoffService:
    """Factory function для создания сервиса."""
    return TinkoffService(token)

