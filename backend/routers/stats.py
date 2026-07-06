"""
Stats Router — статистика торговли, аналитика, теги
"""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

import database
import models
import schemas
import analytics
import auth_service
from capital_service import compute_balance_at, get_capital_flow_events, get_net_deposit_as_of, has_broker_capital_operations
from utils import utc_now_naive
from logger import get_logger
from rate_limiter import limiter, API_LIMIT
# tinkoff_service удалён в PR 0 (greenfield rewrite). Unrealized PnL пока
# не считается из портфеля — вернётся в PR 11 через positions repository.
from moex_service import get_moex_service
from services.stats_cache import (
    stats_cache,
    build_request_key as _get_cache_key,
)
from config import settings
from utils.downsample import lttb


def _downsample_equity_curve(curve: list[dict], max_points: int) -> list[dict]:
    """PERF-10: LTTB-сжатие equity_curve к max_points точкам.

    Сохраняет первую и последнюю точку (важно для UI: стартовый и текущий
    баланс). Работает по индексу события, чтобы вернуть оригинальные dict'ы
    (а не интерполированные значения), включая поле `date`.
    """
    if len(curve) <= max_points or max_points < 3:
        return curve
    indexed = [(float(i), float(p.get("balance", 0))) for i, p in enumerate(curve)]
    kept_indices = {int(p[0]) for p in lttb(indexed, max_points)}
    return [p for i, p in enumerate(curve) if i in kept_indices]


log = get_logger("stats")

router = APIRouter(tags=["stats"])


# Thin wrappers поверх services.stats_cache — сохраняют существующий
# call-site API в этом файле. После Phase 4 можно убрать алиасы и
# звать stats_cache.get/set напрямую.
def _get_cached(key):
    return stats_cache.get(key)


def _set_cached(key, value):
    stats_cache.set(key, value)


def _get_trades_state_fingerprint(db: Session, account_id: int) -> str:
    """PERF-07: дешёвый fingerprint без загрузки всех Trade-rows.

    Один aggregate-SQL: `max(id) || count(id)`. Меняется при любом
    INSERT/DELETE сделок аккаунта. UPDATE-only без изменения id/count
    fingerprint не ловит — но это редкий путь (re-attribution делает
    update в рамках того же sync, где также происходят inserts/deletes),
    а TTL stats_cache (30с) даёт страховку.

    Поднимается ДО загрузки трейдов в `get_stats`: при cache hit роутер
    не делает heavy `query.all()` (5k+ rows).

    Note: модель Trade не имеет `updated_at` — используем `max(id)` как
    proxy для «последний INSERT'нутый trade». `count(id)` детектит DELETE.
    """
    row = db.query(
        func.coalesce(func.max(models.Trade.id), 0),
        func.count(models.Trade.id),
    ).filter(models.Trade.account_id == account_id).one()
    max_id, total = row
    return f"{int(max_id or 0)}|{int(total or 0)}"


def _count_open_positions(db: Session, account_id: int) -> int:
    """Сколько открытых позиций в `positions` ORM (после mark-to-market)."""
    return (
        db.query(models.PositionORM)
        .filter(
            models.PositionORM.account_id == account_id,
            models.PositionORM.quantity != 0,
        )
        .count()
    )


async def _build_imoex_overlay_async(equity_curve: list) -> list:
    """
    IMOEX overlay для сравнения equity счёта с индексом MOEX.

    Берёт диапазон дат из equity_curve, тянет дневные значения IMOEX
    (с TTL-кэшем в MoexService — без него каждый /stats/ ходил бы в ISS).
    Возвращает [{date: 'YYYY-MM-DD HH:MM', value: float}] — формат подобран
    под точки equity_curve, чтобы фронт мог матчить по дате.

    Если кривая пуста или MOEX недоступен — пустой список (фронт скрывает overlay).

    SYNC-04 (Task 1.3): `MoexService.get_index_history` стал async — to_thread
    обёртка больше не нужна, await напрямую.
    """
    if not equity_curve:
        return []
    try:
        first_date = datetime.strptime(equity_curve[0]["date"][:10], "%Y-%m-%d")
        last_date = datetime.strptime(equity_curve[-1]["date"][:10], "%Y-%m-%d")
    except (ValueError, KeyError, TypeError) as exc:
        log.warning(f"_build_imoex_overlay: date parse failed: {exc}")
        return []
    # Расширяем окно на день в каждую сторону, чтобы поймать ближайшую
    # торговую сессию в случае выходных на границах.
    try:
        return await get_moex_service().get_index_history(
            "IMOEX",
            start=first_date - timedelta(days=2),
            end=last_date + timedelta(days=2),
        )
    except Exception as exc:
        log.warning(f"_build_imoex_overlay: fetch failed: {exc}")
        return []


# get_account_id is now centralized in auth_service


def _build_pnl_health_dict(account) -> dict:
    """Phase 10: dict для UI badge из cached `Account.last_pnl_health_*`.

    Если cached данные старше 7 дней — переопределяем status='stale' (UI
    показывает серый бейдж с подсказкой "запустить проверку"). Если NULL —
    status='stale' до первого backfill.
    """
    from services.pnl_health_service import is_stale

    if account.last_pnl_health_at is None:
        return {
            "status": "stale",
            "diff_pct": None,
            "diff_rub": None,
            "checked_at": None,
            "breakdown": None,
            "message": "Проверка ещё не выполнялась",
        }

    raw_status = account.last_pnl_health_status or "stale"
    effective_status = "stale" if is_stale(account) else raw_status

    return {
        "status": effective_status,
        "diff_pct": float(account.last_pnl_health_diff_pct) if account.last_pnl_health_diff_pct is not None else None,
        "diff_rub": float(account.last_pnl_health_diff_rub) if account.last_pnl_health_diff_rub is not None else None,
        "checked_at": account.last_pnl_health_at.isoformat() if account.last_pnl_health_at else None,
        "breakdown": account.last_pnl_health_breakdown,
    }


@router.get("/", response_model=schemas.DashboardStats)
async def get_stats(
    period: Optional[str] = Query(None, description="Period filter: all, today, week, month, 3months, year, custom"),
    start_date: Optional[str] = Query(None, description="Start date for custom period (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date for custom period (YYYY-MM-DD)"),
    start_trade_id: Optional[int] = Query(None, description="Start from specific trade ID"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    limit: Optional[int] = Query(None, description="Limit to last N trades"),
    initial_deposit: Optional[float] = Query(None, description="Initial deposit for ROI calculation"),
    mae_method: Optional[str] = Query('weighted_average', description="MAE calculation method: weighted_average or first_entry"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Get trading statistics with optional filters: time period, tag, and trade count limit."""
    account_id = auth_service.get_account_id(db, current_user)
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    account_initial_balance = float(account.initial_balance or 0) if account else 0
    broker_conn = db.query(models.BrokerConnection).filter(
        models.BrokerConnection.account_id == account_id,
        models.BrokerConnection.is_active == True
    ).first()
    broker_backed = has_broker_capital_operations(db, account_id)

    # Build date filter
    date_filter = None
    now = utc_now_naive()

    # Если указан конкретный trade_id — находим его и фильтруем по дате этой сделки
    if start_trade_id:
        start_trade = db.query(models.Trade).filter(
            models.Trade.id == start_trade_id,
            models.Trade.account_id == account_id
        ).first()
        if start_trade:
            date_filter = start_trade.entry_at
    elif period == "today":
        date_filter = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        date_filter = now - timedelta(days=7)
    elif period == "month":
        date_filter = now - timedelta(days=30)
    elif period == "3months":
        date_filter = now - timedelta(days=90)
    elif period == "year":
        date_filter = now - timedelta(days=365)
    elif period == "custom" and start_date:
        try:
            date_filter = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            pass

    # PERF-07: fingerprint считаем ДО загрузки trades. Aggregate-SQL
    # (max(id)+count(id)) — дешевле, чем грузить все Trade-rows. На cache hit
    # тяжёлый `query.all()` ниже вообще не выполняется. Сам fingerprint
    # покрывает все трейды аккаунта; tag/period/limit участвуют в cache_key
    # как отдельные параметры — разный фильтр → разный ключ → раздельный кэш.
    trades_fingerprint = _get_trades_state_fingerprint(db, account_id)
    cache_key = _get_cache_key(account_id, period=period, start_date=start_date,
                               end_date=end_date, start_trade_id=start_trade_id,
                               tag=tag, limit=limit, mae_method=mae_method,
                               initial_deposit=initial_deposit,
                               account_initial_balance=account_initial_balance,
                               trades_fingerprint=trades_fingerprint)
    cached = _get_cached(cache_key)
    if cached:
        log.debug(f"Stats cache hit for key {cache_key[:8]}")
        return cached

    # Query trades with filter (выполняется только при cache miss)
    query = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.pnl != None
    )

    if date_filter:
        query = query.filter(
            (models.Trade.exit_at >= date_filter) |
            ((models.Trade.exit_at == None) & (models.Trade.entry_at >= date_filter))
        )

    if period == "custom" and end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(
                (models.Trade.exit_at < end_dt) |
                ((models.Trade.exit_at == None) & (models.Trade.entry_at < end_dt))
            )
        except ValueError:
            pass

    # PERF-08b (2026-05-26): tag-фильтр dialect-aware.
    # Postgres: `tags @> '["FOMO"]'` через JSONB + GIN-индекс
    #   (миграция 0028) — фильтрует в БД, не тянет лишние строки.
    # SQLite (dev/tests): JSON `contains`-оператора нет → оставляем
    #   Python-loop fallback после `.all()`. Также fallback сохраняет
    #   case-insensitive семантику (legacy-поведение).
    is_postgres = db.bind.dialect.name == "postgresql"
    if tag and is_postgres:
        query = query.filter(models.Trade.tags.contains([tag]))

    all_trades = query.order_by(models.Trade.exit_at.desc()).all()

    # SQLite-fallback: фильтр в Python (case-insensitive, legacy).
    if tag and not is_postgres:
        tag_lower = tag.lower()
        all_trades = [t for t in all_trades if t.tags and any(tg.lower() == tag_lower for tg in t.tags)]

    # Apply limit (last N trades)
    if limit and limit > 0:
        all_trades = all_trades[:limit]

    trades = all_trades

    total_trades = len(trades)
    if total_trades == 0:
        # PR 22: для broker-юзера baseline = portfolio snapshot back-calculated;
        # для остальных fallback на account.initial_balance.
        empty_baseline = None
        if account is not None and account.last_portfolio_value is not None:
            empty_baseline = compute_balance_at(db, account_id, date_filter) if date_filter else float(account.last_portfolio_value)
        if empty_baseline is None:
            empty_baseline = account_initial_balance
        return {
            "total_pnl": 0,
            "unrealized_pnl": 0,
            "varmargin_total": 0,
            "total_pnl_with_unrealized": 0,
            "initial_balance": empty_baseline,
            "current_balance": empty_baseline,
            "period_start_balance": empty_baseline,
            "period_end_balance": empty_baseline,
            "period_start_date": date_filter.isoformat() if date_filter else None,
            "period_start_net_deposit": get_net_deposit_as_of(db, account_id, date_filter) if date_filter else account_initial_balance,
            "period_start_realized_pnl": 0,
            "period_start_balance_reliable": True,
            "period_start_balance_source": (
                "portfolio_snapshot_backtrack"
                if account is not None and account.last_portfolio_value is not None
                else "account_initial_balance"
            ),
            "period_start_balance_reason": None,
            "win_rate": 0,
            "total_trades": 0,
            "profitable_trades": 0,
            "optimal_f": 0
        }

    # Use net_pnl if available, else pnl
    def get_pnl(t):
        return float(t.net_pnl if t.net_pnl is not None else t.pnl)

    # Phase 11 (2026-05-17): gross variant — только body P&L без commissions/fees.
    # Используется когда settings.pnl_display_mode == 'gross' на фронте.
    def get_pnl_gross(t):
        return float(t.pnl if t.pnl is not None else 0)

    total_pnl = sum(get_pnl(t) for t in trades)
    total_pnl_gross = sum(get_pnl_gross(t) for t in trades)
    profitable_trades = len([t for t in trades if get_pnl(t) > 0])
    win_rate = (profitable_trades / total_trades) * 100

    # Расчет Optimal f
    pnls = [get_pnl(t) for t in trades]
    risks = [float(t.risk_amount) if t.risk_amount else 0 for t in trades]  # 0 если риск не указан
    opt_f_data = analytics.calculate_optimal_f(pnls, risks)

    # Расчет SQN
    sqn_data = analytics.calculate_sqn(pnls, risks)

    # Расчет Z-Score
    z_score_data = analytics.calculate_z_score(pnls)

    # Расчет Advanced Stats
    adv_stats = analytics.calculate_advanced_stats(pnls, risks)

    # Анализ MAE/MFE
    mae_mfe_data = analytics.analyze_mae_mfe(trades, mae_method=mae_method or 'weighted_average')

    # Расчет кривой эквити (хронологический порядок)
    sorted_trades = sorted(trades, key=lambda x: x.exit_at if x.exit_at else x.entry_at)
    pnls_sorted = [get_pnl(t) for t in sorted_trades]

    base_initial_balance = account_initial_balance

    period_start_date = date_filter
    if period_start_date is None and sorted_trades:
        first_trade = sorted_trades[0]
        period_start_date = first_trade.entry_at or first_trade.exit_at

    pnl_before = 0.0
    if period_start_date:
        trades_before_filter = db.query(models.Trade).filter(
            models.Trade.account_id == account_id,
            models.Trade.pnl != None,
            models.Trade.exit_at != None,
            models.Trade.exit_at < period_start_date
        ).all()
        pnl_before = sum(float(t.net_pnl if t.net_pnl is not None else t.pnl) for t in trades_before_filter)

    # PR 23: для broker-юзера НЕ пытаемся реконструировать «стартовый капитал»
    # — у Tinkoff API нет надёжного источника для margin/futures-трейдинга
    # (operation payments не отражают margin-кредиты, а historical snapshots
    # отсутствуют без GetBrokerReport). Показываем честно:
    #   - текущий баланс счёта = last_portfolio_value (cash)
    #   - equity curve = кумулятивный realized PnL (стартует от 0)
    #   - ROI/RoR не считаем (нет baseline)
    is_broker_user = account is not None and account.last_portfolio_value is not None
    current_cash_balance = float(account.last_portfolio_value) if is_broker_user else None

    # Всегда вычисляем для совместимости с response-полем period_start_net_deposit.
    starting_net_deposit = get_net_deposit_as_of(db, account_id, period_start_date) if period_start_date else get_net_deposit_as_of(db, account_id)

    if is_broker_user:
        if account_initial_balance > 0:
            # ADR-0010: есть опорная база капитала (anchor или manual) → ROI честен.
            # Equity curve по-прежнему от 0 (cumulative PnL); ROI-знаменатель отдельный.
            starting_balance = 0.0
            period_start_balance_source = "anchored_capital_base"
            period_start_balance_reliable = True
        else:
            # Без якоря базы нет — ROI по-прежнему скрыт.
            starting_balance = 0.0
            period_start_balance_source = "broker_cumulative_pnl"
            period_start_balance_reliable = False
    else:
        starting_balance = starting_net_deposit + pnl_before
        if not period_start_date:
            starting_balance = base_initial_balance if base_initial_balance > 0 else starting_balance
        period_start_balance_source = "derived"
        period_start_balance_reliable = True

    period_start_balance_reason = None
    if is_broker_user and period_start_balance_reliable and account_initial_balance > 0:
        # ADR-0010 / S2-06: anchored broker → ROI-знаменатель = anchor +
        # Σ NET_DEPOSIT из OperationORM (реальные завозы). ADR-0010 §"Реализующие
        # модули": stats.py база % = initial_balance + net_deposits (total).
        # get_net_deposit_as_of при пустой DepositHistory возвращал сам
        # initial_balance → база = anchor+anchor (double count). Берём depozits
        # из того же источника и по той же формуле, что drawdown_baseline ниже
        # и get_net_deposits_baseline_from_db — ЗНАКОВАЯ Σ NET_DEPOSIT (S3-14),
        # без date-фильтра: полный deployed capital. OUTPUT хранятся с
        # отрицательным payment_units → вывод средств УМЕНЬШАЕТ базу (signed),
        # согласовано с pnl_health effective_deposits и drawdown_baseline в этом
        # же ответе. acc#2 (только заводы): 99095 + 8556 = 107651; при выводе
        # −20000 сверх завода +8556: 99095 + (8556−20000) = 87651.
        from domain.pnl.cash_flow_classification import (
            CashFlowCategory as _CFC2,
            operation_types_in as _op_types_in2,
        )
        _dep_types2 = tuple(_op_types_in2(_CFC2.NET_DEPOSIT))
        net_dep_ops = 0.0
        if _dep_types2:
            _q = db.query(
                func.coalesce(func.sum(models.OperationORM.payment_units), 0),
                func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
            ).filter(
                models.OperationORM.account_id == account_id,
                models.OperationORM.operation_type.in_(_dep_types2),
                models.OperationORM.state == "executed",
            )
            # CR-1: числитель total_pnl period-scoped → знаменатель ROI тоже.
            # Триггер — date_filter is not None (явный период today/week/…/custom),
            # НЕ period_start_date (тот выставляется ВСЕГДА, для all = дата первой
            # сделки). При явном окне учитываем только капитал, задеплоенный ДО
            # старта окна: депозиты после начала периода = заводы посреди окна,
            # инъекция которых иначе занижает ROI короткого периода. Для period=all
            # (date_filter None) фильтра нет — полная Σ (deployed capital).
            if date_filter is not None:
                _q = _q.filter(models.OperationORM.executed_at <= date_filter)
            _r = _q.one()
            net_dep_ops = float(_r[0] or 0) + float(_r[1] or 0) / 1e9
        public_period_start_balance = account_initial_balance + net_dep_ops
    else:
        public_period_start_balance = (
            starting_balance if (not is_broker_user or period_start_balance_reliable) else None
        )

    if not is_broker_user and broker_backed and period_start_date:
        first_snapshot = db.query(models.BalanceSnapshot).filter(
            models.BalanceSnapshot.account_id == account_id,
        ).order_by(models.BalanceSnapshot.date.asc()).first()
        latest_snapshot_before_period = db.query(models.BalanceSnapshot).filter(
            models.BalanceSnapshot.account_id == account_id,
            models.BalanceSnapshot.date <= period_start_date,
        ).order_by(models.BalanceSnapshot.date.desc()).first()
        earliest_capital_op = db.query(models.CapitalOperation).filter(
            models.CapitalOperation.account_id == account_id,
        ).order_by(models.CapitalOperation.date.asc()).first()

        if latest_snapshot_before_period:
            snapshot_balance = float(latest_snapshot_before_period.balance or 0)
            snapshot_date = latest_snapshot_before_period.date
            delta_pnl_since_snapshot = db.query(models.Trade).filter(
                models.Trade.account_id == account_id,
                models.Trade.exit_at.isnot(None),
                models.Trade.exit_at >= snapshot_date,
                models.Trade.exit_at < period_start_date,
            ).all()
            delta_pnl_value = sum(float(t.net_pnl if t.net_pnl is not None else t.pnl or 0) for t in delta_pnl_since_snapshot)
            delta_capital_value = sum(event["amount"] for event in get_capital_flow_events(
                db,
                account_id,
                start=snapshot_date,
                end=period_start_date,
            ))
            public_period_start_balance = snapshot_balance + delta_pnl_value + delta_capital_value
            period_start_balance_source = "snapshot_plus_events"
        elif first_snapshot and first_snapshot.date > period_start_date and earliest_capital_op and broker_conn and broker_conn.sync_from_date and earliest_capital_op.date < broker_conn.sync_from_date:
            period_start_balance_reliable = False
            public_period_start_balance = None
            period_start_balance_source = "unavailable_pre_snapshot"
            period_start_balance_reason = (
                "Нет снимка брокерского баланса на дату старта периода, а история счёта началась раньше даты синхронизации. "
                "Чтобы восстановить точный капитал, импортируйте брокерский отчёт с входящим/исходящим остатком за нужный период."
            )

    period_end_boundary = now
    if period == "custom" and end_date:
        try:
            period_end_boundary = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        except ValueError:
            period_end_boundary = now

    equity_events = []
    if period_start_date:
        for flow in get_capital_flow_events(db, account_id, start=period_start_date, end=period_end_boundary):
            equity_events.append({
                "date": flow["date"],
                "amount": float(flow["amount"]),
                "amount_gross": float(flow["amount"]),  # capital flows одинаковы в обоих режимах
                "kind": "capital",
            })
    for trade in sorted_trades:
        equity_events.append({
            "date": trade.exit_at if trade.exit_at else trade.entry_at,
            "amount": get_pnl(trade),
            "amount_gross": get_pnl_gross(trade),
            "kind": "trade",
        })

    equity_events.sort(key=lambda event: (event["date"], 0 if event["kind"] == "capital" else 1))
    equity_curve = []
    equity_curve_gross = []
    current_balance = starting_balance
    current_balance_gross = starting_balance
    for event in equity_events:
        current_balance += event["amount"]
        current_balance_gross += event["amount_gross"]
        event_date = event["date"]
        if event_date is None:
            continue
        date_str = event_date.strftime("%Y-%m-%d %H:%M")
        equity_curve.append({
            "date": date_str,
            "balance": round(current_balance, 2)
        })
        equity_curve_gross.append({
            "date": date_str,
            "balance": round(current_balance_gross, 2)
        })

    if period_start_date:
        log.debug(
            f"Period start recalculated: net_deposit={starting_net_deposit:.2f}, pnl_before={pnl_before:.2f}, starting_balance={starting_balance:.2f}"
        )

    # Расчет статистики по тегам
    tag_performance = {}
    for t in trades:
        if not t.tags:
            continue
        for tag_name in t.tags:
            tag_key = tag_name.lower()
            if tag_key not in tag_performance:
                tag_performance[tag_key] = {"pnl": 0, "total": 0, "wins": 0}
            tag_performance[tag_key]["pnl"] += get_pnl(t)
            tag_performance[tag_key]["total"] += 1
            if get_pnl(t) > 0:
                tag_performance[tag_key]["wins"] += 1

    tag_stats = []
    for tag_key, data in tag_performance.items():
        tag_stats.append({
            "tag": tag_key,
            "pnl": round(data["pnl"], 2),
            "win_rate": round((data["wins"] / data["total"]) * 100, 1),
            "count": data["total"]
        })
    tag_stats = sorted(tag_stats, key=lambda x: x["pnl"], reverse=True)

    # Baseline для %-метрик (просадка, Calmar, % изменения капитала).
    # Для broker_user используем Σ NET_DEPOSIT через OperationORM (то что реально
    # завёл через Tinkoff API) — это deployed capital. cash_truth_pnl формула:
    # last_portfolio_value - Σ NET_DEPOSIT — даёт реальную потерю, и % к Σ deposits
    # = "сколько % от вложенного потерял". Если из CapitalOperation посчитать
    # 1.05M (включая выведенные деньги), %-метрики занижаются в ~3 раза.
    drawdown_baseline = 0.0
    if is_broker_user:
        from domain.pnl.cash_flow_classification import (
            CashFlowCategory as _CFC,
            operation_types_in as _op_types_in,
        )
        _dep_types = tuple(_op_types_in(_CFC.NET_DEPOSIT))
        if _dep_types:
            _row = db.query(
                func.coalesce(func.sum(models.OperationORM.payment_units), 0),
                func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
            ).filter(
                models.OperationORM.account_id == account_id,
                models.OperationORM.operation_type.in_(_dep_types),
                models.OperationORM.state == "executed",
            ).one()
            drawdown_baseline = float(_row[0] or 0) + float(_row[1] or 0) / 1e9
        if drawdown_baseline <= 0 and starting_net_deposit > 0:
            drawdown_baseline = starting_net_deposit
        # ADR-0010: включаем восстановленный баланс открытия в развёрнутый капитал
        # → drawdown%/Calmar считаются от реальной базы (acc#2: 8556 → 107651).
        if account_initial_balance > 0:
            drawdown_baseline += account_initial_balance
    elif starting_balance > 0:
        drawdown_baseline = starting_balance
    if drawdown_baseline <= 0:
        drawdown_baseline = float(base_initial_balance) if base_initial_balance > 0 else 0

    # Расчет дополнительных метрик
    sortino_data = analytics.calculate_sharpe_sortino(pnls)
    trade_dates_sorted = [
        (t.exit_at or t.entry_at)
        for t in sorted_trades
        if (t.exit_at or t.entry_at) is not None
    ]
    dates_arg = trade_dates_sorted if len(trade_dates_sorted) == len(pnls_sorted) else None
    drawdown_data = analytics.calculate_drawdown_stats(
        pnls_sorted,
        initial_balance=drawdown_baseline,
        dates=dates_arg,
    )
    win_loss_data = analytics.calculate_win_loss_stats(pnls)
    streaks_data = analytics.calculate_streaks(pnls_sorted)
    tail_ratio_data = analytics.calculate_tail_ratio(pnls)
    r_distribution_data = analytics.calculate_r_distribution(pnls, risks)
    trade_duration_data = analytics.calculate_trade_duration(trades)

    # Monte Carlo и Time Patterns
    monte_carlo_data = analytics.monte_carlo_simulation(pnls)
    time_patterns_data = analytics.analyze_time_patterns(trades)

    # Calmar Ratio
    if len(sorted_trades) >= 2:
        first_trade_date = sorted_trades[0].entry_at
        last_trade_date = sorted_trades[-1].exit_at if sorted_trades[-1].exit_at else sorted_trades[-1].entry_at
        trading_days = (last_trade_date - first_trade_date).days
        period_years = max(trading_days / 365, 0.1)
    else:
        period_years = 1.0
    period_start_balance = public_period_start_balance if public_period_start_balance is not None else None
    if initial_deposit and initial_deposit > 0:
        period_start_balance = initial_deposit
        period_start_balance_reliable = True
        period_start_balance_source = "manual_override"
        period_start_balance_reason = None

    # Calmar baseline = drawdown_baseline (consistency: одна метрика «пик капитала»
    # для просадки И для CAGR). Раньше drawdown использовал starting_balance=0,
    # а Calmar fallback на account.initial_balance — давали разный max_drawdown_pct
    # в двух карточках. Теперь оба читают drawdown_baseline.
    calmar_initial_balance = drawdown_baseline if drawdown_baseline > 0 else base_initial_balance
    calmar_data = analytics.calculate_calmar_ratio(
        pnls_sorted,
        initial_balance=calmar_initial_balance,
        period_years=period_years,
    )

    # Risk of Ruin
    avg_win = win_loss_data.get("avg_win", 0)
    avg_loss = abs(win_loss_data.get("avg_loss", 1))
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 1
    risk_of_ruin_data = analytics.calculate_risk_of_ruin(win_rate / 100, payoff_ratio)

    # PR 21: возвращаем unrealized PnL из PositionORM (заполняется pipeline'ом
    # в _stage_mark_to_market из live Tinkoff get_portfolio). Это сумма всех
    # открытых позиций — то что у юзера «нереализованно болтается» прямо сейчас.
    from models import PositionORM, OperationORM
    unrealized_sum = (
        db.query(func.sum(PositionORM.unrealized_pnl))
        .filter(PositionORM.account_id == account_id)
        .scalar()
    )
    unrealized_pnl_position_based = float(unrealized_sum) if unrealized_sum is not None else 0.0

    # TR1.3: varmargin теперь attributed к Trade.net_pnl через
    # pipeline._stage_attribute_fees (proportional split). Поэтому
    # total_pnl (= Σ Trade.net_pnl закрытых) уже включает varmargin.
    # Здесь surface отдельной info-метрикой для admin debug/диагностики.
    varmargin_units = func.coalesce(func.sum(OperationORM.payment_units), 0)
    varmargin_nano = func.coalesce(func.sum(OperationORM.payment_nano), 0)
    vm_row = (
        db.query(varmargin_units, varmargin_nano)
        .filter(
            OperationORM.account_id == account_id,
            OperationORM.operation_type.in_(
                ["accruing_varmargin", "writing_off_varmargin"]
            ),
            OperationORM.state == "executed",
        )
        .one()
    )
    varmargin_total = float(vm_row[0] or 0) + float(vm_row[1] or 0) / 1e9

    # Phase 6.4 (2026-05-18): journal-style headline matches Дневник сделок
    # (realized + unrealized). cash_truth_pnl surface'ится отдельным полем для
    # PnLHealthBadge / broker reconciliation. account_level_adjustments теперь
    # = natural_residual (cash_truth − headline, info-only).
    # См. domain/pnl/dashboard_pnl.py + tests/unit/test_dashboard_pnl_headline.py.
    if is_broker_user and account is not None:
        from domain.pnl.cash_flow_classification import (
            CashFlowCategory,
            operation_types_in,
        )
        from domain.pnl.dashboard_pnl import compute_pnl_headline
        from domain.pnl.fee_attribution import (
            MARGIN_LIKE_FEE_TYPES,
            SERVICE_LIKE_FEE_TYPES,
        )
        from decimal import Decimal

        def _sum_category(cat: CashFlowCategory) -> float:
            types = tuple(operation_types_in(cat))
            if not types:
                return 0.0
            row = db.query(
                func.coalesce(func.sum(OperationORM.payment_units), 0),
                func.coalesce(func.sum(OperationORM.payment_nano), 0),
            ).filter(
                OperationORM.account_id == account_id,
                OperationORM.operation_type.in_(types),
                OperationORM.state == "executed",
            ).one()
            return float(row[0] or 0) + float(row[1] or 0) / 1e9

        def _sum_op_types(op_types: frozenset[str]) -> float:
            """Сумма payment по конкретным OperationType.value (для подкатегорий
            внутри ATTRIBUTABLE_FEE — margin vs service)."""
            if not op_types:
                return 0.0
            row = db.query(
                func.coalesce(func.sum(OperationORM.payment_units), 0),
                func.coalesce(func.sum(OperationORM.payment_nano), 0),
            ).filter(
                OperationORM.account_id == account_id,
                OperationORM.operation_type.in_(tuple(op_types)),
                OperationORM.state == "executed",
            ).one()
            return float(row[0] or 0) + float(row[1] or 0) / 1e9

        raw_attr_fee   = _sum_category(CashFlowCategory.ATTRIBUTABLE_FEE)
        raw_margin     = _sum_op_types(MARGIN_LIKE_FEE_TYPES)
        raw_service    = _sum_op_types(SERVICE_LIKE_FEE_TYPES)
        raw_tax        = _sum_category(CashFlowCategory.TAX)
        raw_income_tax = _sum_category(CashFlowCategory.INCOME_TAX)
        raw_broker     = _sum_category(CashFlowCategory.BROKER_COMMISSION)
        raw_deposits   = _sum_category(CashFlowCategory.NET_DEPOSIT)

        last_portfolio_value = float(account.last_portfolio_value or 0)

        headline = compute_pnl_headline(
            realized_closed=Decimal(str(total_pnl)),
            realized_closed_gross=Decimal(str(total_pnl_gross)),
            unrealized_position_based=Decimal(str(unrealized_pnl_position_based)),
            last_portfolio_value=Decimal(str(last_portfolio_value)),
            # ADR-0010: эффективные депозиты = реальные + восстановленный баланс открытия.
            net_deposits=Decimal(str(raw_deposits + account_initial_balance)),
            broker_commission_raw=Decimal(str(raw_broker)),
            attributable_fee_raw=Decimal(str(raw_attr_fee)),
            tax_raw=Decimal(str(raw_tax)),
            income_tax_raw=Decimal(str(raw_income_tax)),
        )

        unrealized_pnl                  = unrealized_pnl_position_based
        total_pnl_with_unrealized       = float(headline["total_pnl_with_unrealized"])
        total_pnl_with_unrealized_gross = float(headline["total_pnl_with_unrealized_gross"])
        cash_truth_pnl                  = float(headline["cash_truth_pnl"])
        total_costs                     = float(headline["total_costs"])

        # natural_residual = cash_truth − headline (orphan delta: post-clearing
        # varmargin, dividends на закрытых позициях). Info-only — surface через
        # account_level_adjustments для UI breakdown card. НЕ влияет на headline.
        account_level_adjustments       = float(headline["natural_residual"])
        # gross headline не имеет cash-truth-эквивалента (gross != broker view).
        account_level_adjustments_gross = 0.0

        total_costs_breakdown = {
            "broker_commission": float(raw_broker),
            "margin_fees":       float(raw_margin),
            "service_fees":      float(raw_service),
            "taxes":             float(raw_tax + raw_income_tax),
        }
    else:
        unrealized_pnl                  = unrealized_pnl_position_based
        total_pnl_with_unrealized       = total_pnl + unrealized_pnl
        total_pnl_with_unrealized_gross = total_pnl_gross + unrealized_pnl
        cash_truth_pnl                  = 0.0
        account_level_adjustments       = 0.0
        account_level_adjustments_gross = 0.0
        total_costs                     = 0.0
        total_costs_breakdown = {
            "broker_commission": 0.0,
            "margin_fees":       0.0,
            "service_fees":      0.0,
            "taxes":             0.0,
        }

    # Phase 6.4 (2026-05-18): equity_curve tail = realized cumulative + unrealized
    # (matches journal-style headline). account_level_adjustments не добавляем —
    # они info-only residual, не часть headline. Frontend опционально override'ит
    # tail с live unrealized из /trades/unrealized-pnl.
    _curve_tail_adjustment = unrealized_pnl
    if equity_curve and _curve_tail_adjustment != 0:
        last = equity_curve[-1]
        equity_curve = equity_curve[:-1] + [
            {
                "date": last["date"],
                "balance": round(last["balance"] + _curve_tail_adjustment, 2),
            }
        ]

    _curve_tail_adjustment_gross = unrealized_pnl
    if equity_curve_gross and _curve_tail_adjustment_gross != 0:
        last = equity_curve_gross[-1]
        equity_curve_gross = equity_curve_gross[:-1] + [
            {
                "date": last["date"],
                "balance": round(last["balance"] + _curve_tail_adjustment_gross, 2),
            }
        ]

    # PERF-10: LTTB-downsample equity_curve / equity_curve_gross.
    # ~5000 трейдов → 5000+ JSON-точек ломали фронт-чарт; LTTB даёт
    # визуально неотличимую кривую при N≤EQUITY_CURVE_MAX_POINTS точках.
    # Сохраняются первая и последняя точки (стартовый и текущий баланс).
    _max_points = settings.EQUITY_CURVE_MAX_POINTS
    equity_curve = _downsample_equity_curve(equity_curve, _max_points)
    equity_curve_gross = _downsample_equity_curve(equity_curve_gross, _max_points)

    result = {
        "total_pnl": total_pnl,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_position_based": unrealized_pnl_position_based,  # info: Σ Position.unrealized (predictive)
        "account_level_adjustments": account_level_adjustments,  # orphan cash flows (varmargin/fees not attributed)
        "varmargin_total": varmargin_total,  # info-only, не суммируем
        "total_pnl_with_unrealized": total_pnl_with_unrealized,
        # Phase 6.4: broker cash truth для PnLHealthBadge.
        "cash_truth_pnl": cash_truth_pnl,
        # Phase 11 (2026-05-17): gross variants — для пользовательской настройки
        # `settings.pnl_display_mode = 'gross'`. Frontend сам выбирает что показывать.
        # gross = только body P&L (от движения цены) без commissions/fees/taxes.
        # net = реальный финансовый результат (default, matches broker).
        "total_pnl_gross": total_pnl_gross,
        "total_pnl_with_unrealized_gross": total_pnl_with_unrealized_gross,
        "account_level_adjustments_gross": account_level_adjustments_gross,
        # Phase 12 (2026-05-17): separate «Расходы» card (best practices).
        # total_costs = разница net vs gross headline = broker + fees + taxes
        # (sum может слегка отличаться от breakdown из-за orphan/attributed split).
        "total_costs": total_costs,
        "total_costs_breakdown": total_costs_breakdown,
        # Phase 10 (2026-05-17): P&L Health Check status (cached на Account).
        # status: ok|warning|mismatch|na — UI показывает badge соответствующего цвета.
        # Если last_pnl_health_at старше 7 дней → status переопределяется на 'stale'.
        "pnl_health": _build_pnl_health_dict(account) if account else None,
        "win_rate": win_rate,
        "total_trades": total_trades,
        "profitable_trades": profitable_trades,
        "optimal_f": opt_f_data.get("optimal_f", 0),
        "optimal_f_data": opt_f_data,  # Полные данные с обоими методами
        "sqn": sqn_data,
        "z_score": z_score_data,
        "profit_factor": adv_stats.get("profit_factor", 0),
        "r_expectancy": adv_stats.get("r_expectancy", 0),
        "recovery_factor": adv_stats.get("recovery_factor", 0),
        "total_roi": round((total_pnl / period_start_balance * 100), 2) if period_start_balance and period_start_balance > 0 and period_start_balance_reliable else None,
        "expected_ghpr": opt_f_data.get("geometric_mean", 0),
        "sortino_ratio": sortino_data.get("sortino_ratio", 0),
        "max_drawdown_pct": drawdown_data.get("max_drawdown_pct", 0),
        "max_drawdown_abs": drawdown_data.get("max_drawdown_abs", 0),
        "current_drawdown_pct": drawdown_data.get("current_drawdown_pct", 0),
        "max_drawdown_peak_date":   drawdown_data.get("peak_date"),
        "max_drawdown_trough_date": drawdown_data.get("trough_date"),
        "max_drawdown_duration_days": drawdown_data.get("dd_duration_days"),
        "max_drawdown_peak_value":   drawdown_data.get("peak_value_on_curve"),
        "max_drawdown_trough_value": drawdown_data.get("trough_value_on_curve"),
        "drawdown_baseline":         float(drawdown_baseline),
        "avg_win": win_loss_data.get("avg_win", 0),
        "avg_loss": win_loss_data.get("avg_loss", 0),
        "largest_win": win_loss_data.get("largest_win", 0),
        "largest_loss": win_loss_data.get("largest_loss", 0),
        "max_win_streak": streaks_data.get("max_win_streak", 0),
        "max_loss_streak": streaks_data.get("max_loss_streak", 0),
        "current_streak": streaks_data.get("current_streak", 0),
        "current_streak_type": streaks_data.get("current_streak_type"),
        "tail_ratio": tail_ratio_data.get("tail_ratio", 0),
        "calmar_ratio": calmar_data,
        "risk_of_ruin": risk_of_ruin_data,
        "r_distribution": r_distribution_data,
        "trade_duration": trade_duration_data,
        "monte_carlo": monte_carlo_data,
        "time_patterns": time_patterns_data,
        "mae_mfe_analysis": mae_mfe_data,
        "equity_curve": equity_curve,
        "equity_curve_gross": equity_curve_gross,  # Phase 11: gross variant
        "imoex_curve": await _build_imoex_overlay_async(equity_curve),
        "tag_stats": tag_stats,
        "initial_balance": base_initial_balance,
        "initial_balance_source": getattr(account, "initial_balance_source", None),
        # PR 23: для broker-юзера current_cash_balance — это
        # `portfolio.total_amount_portfolio` от Тинькова (cash на счёте,
        # без учёта фьючерсов в пунктах). Это единственная честная цифра,
        # которой можно доверять при margin/futures-трейдинге.
        "current_cash_balance": current_cash_balance,
        "open_positions_count": _count_open_positions(db, account_id) if is_broker_user else None,
        "current_balance": current_balance if equity_curve else base_initial_balance,
        "period_start_balance": period_start_balance,
        "period_end_balance": current_balance if equity_curve else period_start_balance,
        "period_start_date": period_start_date.isoformat() if period_start_date else None,
        "period_start_net_deposit": starting_net_deposit,
        "period_start_realized_pnl": pnl_before,
        "period_start_balance_reliable": period_start_balance_reliable,
        "period_start_balance_source": period_start_balance_source,
        "period_start_balance_reason": period_start_balance_reason,
    }

    # Cache the result
    _set_cached(cache_key, result)
    return result


# ──────────────────────────────────────────────────────────────────
#  Helper: общая загрузка сделок для /advanced и /benchmark
# ──────────────────────────────────────────────────────────────────

# Helpers вынесены в services/stats_filtering для переиспользования
# в stats_advanced и других sub-роутерах (см. ADR-0005 если будет).
from services.stats_filtering import (  # noqa: E402
    load_filtered_trades as _load_filtered_trades,
    build_equity_curve as _build_equity_curve,
)


# /advanced и /benchmark вынесены в routers/stats_advanced.py


# ──────────────────────────────────────────────────────────────────
#  /setups — per-setup deep-dive (PnL, WR, RR, equity-curve)
# ──────────────────────────────────────────────────────────────────

@router.get("/setups")
async def get_setups_breakdown(
    period: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    """
    Группировка сделок по setup_name.

    Для каждого сетапа возвращаем: total_pnl, win_rate, count, avg_r,
    quality_score (composite), equity-curve (cum PnL по этому сетапу).
    """
    account_id = auth_service.get_account_id(db, current_user)
    trades = _load_filtered_trades(db, account_id, period, start_date, end_date,
                                   None, None, None)

    by_setup: Dict[str, list] = {}
    for t in trades:
        name = t.setup_name or "Без сетапа"
        by_setup.setdefault(name, []).append(t)

    result = []
    for name, group in by_setup.items():
        pnls = [float(tr.net_pnl if tr.net_pnl is not None else (tr.pnl or 0)) for tr in group]
        wins = sum(1 for p in pnls if p > 0)
        total = sum(pnls)
        rs = [float(tr.r_multiple) for tr in group if tr.r_multiple is not None]
        avg_r = round(sum(rs) / len(rs), 2) if rs else None
        # Mini equity-curve: cumulative PnL по этому сетапу
        cum = 0.0
        equity = []
        for tr, p in zip(group, pnls):
            cum += p
            equity.append({
                "date": tr.exit_at.isoformat() if tr.exit_at else (tr.entry_at.isoformat() if tr.entry_at else None),
                "balance": round(cum, 2),
            })
        # Quality score: 0-100, composite (WR×0.4 + AvgR_normalized×0.4 + low_dd×0.2)
        wr = (wins / len(group) * 100) if group else 0
        avg_r_score = max(0, min(40, (avg_r or 0) * 20))
        wr_score = wr * 0.4
        quality = round(min(100, wr_score + avg_r_score + 20), 0)
        result.append({
            "setup": name,
            "trades_count": len(group),
            "wins": wins,
            "losses": len(group) - wins,
            "win_rate": round(wr, 1),
            "total_pnl": round(total, 2),
            "avg_pnl": round(total / len(group), 2) if group else 0,
            "avg_r": avg_r,
            "quality_score": int(quality),
            "equity_curve": equity,
            "best_trade": round(max(pnls), 2) if pnls else 0,
            "worst_trade": round(min(pnls), 2) if pnls else 0,
        })
    # Сортируем по PnL
    result.sort(key=lambda s: s["total_pnl"], reverse=True)
    return {"total_trades": len(trades), "setups": result}


# ──────────────────────────────────────────────────────────────────
#  /calendar — daily PnL aggregation для Calendar heatmap
# ──────────────────────────────────────────────────────────────────

@router.get("/calendar")
async def get_calendar_pnl(
    period: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    """
    Дневная агрегация PnL для календарной heatmap.

    Возвращает [{ date: 'YYYY-MM-DD', pnl, trades_count, win_rate }, ...]
    отсортированные по дате. Фронт строит месячные сетки.
    """
    account_id = auth_service.get_account_id(db, current_user)
    trades = _load_filtered_trades(db, account_id, period, start_date, end_date,
                                   None, None, None)
    # MATH-01: дневной P&L для календарной heatmap — NET (после комиссий).
    trades_for_calendar = [
        {"entry_at": t.entry_at, "pnl": float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0))}
        for t in trades
    ]
    return {
        "total_trades": len(trades),
        "days": analytics.calculate_daily_pnl(trades_for_calendar),
    }


@router.get("/mae-mfe-analysis")
async def get_mae_mfe_analysis(
    group_by: str = Query('overall', description="Группировка: overall, tag, symbol, setup"),
    filter_value: Optional[str] = Query(None, description="Фильтр: конкретный тег/тикер/сетап"),
    asset_type: Optional[str] = Query(None, description="Тип актива: Stock, Futures, Bond"),
    direction: Optional[str] = Query(None, description="Направление: long, short"),
    limit: Optional[int] = Query(None, description="Лимит: последние N сделок"),
    period: Optional[str] = Query(None, description="Период: week, month, 3months, year"),
    start_trade_id: Optional[int] = Query(None, description="Начать с конкретной сделки (глобальный фильтр)"),
    mae_method: str = Query('weighted_average', description="Метод расчёта MAE"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """
    Универсальный MAE/MFE анализ с группировкой.

    group_by:
    - overall: общий анализ всех сделок
    - tag: группировка по тегам (стратегиям)
    - symbol: группировка по тикерам
    - setup: группировка по сетапам

    filter_value: конкретный тег/тикер/сетап для детального анализа
    limit: последние N сделок (20, 50, 100, 200)
    period: week, month, 3months, year
    start_trade_id: ID сделки с которой начинать (для применения глобального фильтра)
    """
    account_id = auth_service.get_account_id(db, current_user)
    now = utc_now_naive()

    # Базовый запрос
    query = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at != None,
        models.Trade.mae_price != None,
        models.Trade.mfe_price != None
    )

    # Фильтр по start_trade_id (глобальный фильтр из настроек)
    if start_trade_id:
        start_trade = db.query(models.Trade).filter(
            models.Trade.id == start_trade_id,
            models.Trade.account_id == account_id
        ).first()
        if start_trade:
            # Фильтруем сделки начиная с даты входа этой сделки
            query = query.filter(models.Trade.entry_at >= start_trade.entry_at)

    # Фильтр по периоду
    if period:
        if period == 'week':
            date_filter = now - timedelta(days=7)
        elif period == 'month':
            date_filter = now - timedelta(days=30)
        elif period == '3months':
            date_filter = now - timedelta(days=90)
        elif period == 'year':
            date_filter = now - timedelta(days=365)
        else:
            date_filter = None

        if date_filter:
            query = query.filter(models.Trade.exit_at >= date_filter)

    # Фильтры типа актива и направления
    if asset_type:
        query = query.filter(models.Trade.asset_type == asset_type)
    if direction:
        query = query.filter(models.Trade.direction == direction)

    # Сортировка по дате закрытия (новые сначала) для применения limit
    query = query.order_by(models.Trade.exit_at.desc())

    # Применяем лимит на последние N сделок
    if limit and limit > 0:
        query = query.limit(limit)

    trades = query.all()

    if not trades:
        return {
            "group_by": group_by,
            "items": [],
            "total_trades": 0,
            "summary": None
        }

    # Группировка
    from collections import defaultdict
    import numpy as np

    if group_by == 'overall':
        # Общий анализ
        result = _analyze_trades_mae_mfe(trades, mae_method)
        result["group_by"] = "overall"
        return result

    elif group_by == 'tag':
        # Группировка по тегам (включая системные для полноты анализа)
        groups = defaultdict(list)
        for t in trades:
            if t.tags:
                for tag in t.tags:
                    groups[tag].append(t)
            else:
                groups['Без тега'].append(t)

        if filter_value:
            if filter_value in groups:
                result = _analyze_trades_mae_mfe(groups[filter_value], mae_method)
                result["group_by"] = "tag"
                result["filter_value"] = filter_value
                result["recommendations"] = _generate_strategy_recommendations(result)
                result["trades"] = _trades_brief(groups[filter_value])
                return result
            return {"group_by": "tag", "filter_value": filter_value, "items": [], "total_trades": 0}

        items = []
        for name, group_trades in groups.items():
            if len(group_trades) >= 2:
                analysis = _analyze_trades_mae_mfe(group_trades, mae_method)
                items.append({
                    "name": name,
                    "trades_count": len(group_trades),
                    **analysis
                })

        items.sort(key=lambda x: x.get("edge_ratio", 0), reverse=True)

        return {
            "group_by": "tag",
            "items": items,
            "total_trades": len(trades),
            "total_groups": len(items)
        }

    elif group_by == 'symbol':
        # Группировка по тикерам
        groups = defaultdict(list)
        for t in trades:
            groups[t.symbol].append(t)

        if filter_value:
            if filter_value in groups:
                result = _analyze_trades_mae_mfe(groups[filter_value], mae_method)
                result["group_by"] = "symbol"
                result["filter_value"] = filter_value
                # Добавляем доп. инфо
                sample = groups[filter_value][0]
                result["asset_name"] = sample.asset_name
                result["asset_type"] = sample.asset_type
                result["recommendations"] = _generate_strategy_recommendations(result)
                result["trades"] = _trades_brief(groups[filter_value])
                return result
            return {"group_by": "symbol", "filter_value": filter_value, "items": [], "total_trades": 0}

        items = []
        for symbol, group_trades in groups.items():
            if len(group_trades) >= 1:
                analysis = _analyze_trades_mae_mfe(group_trades, mae_method)
                sample = group_trades[0]
                items.append({
                    "name": symbol,
                    "asset_name": sample.asset_name,
                    "asset_type": sample.asset_type,
                    "trades_count": len(group_trades),
                    **analysis
                })

        items.sort(key=lambda x: x.get("edge_ratio", 0), reverse=True)

        return {
            "group_by": "symbol",
            "items": items,
            "total_trades": len(trades),
            "total_groups": len(items)
        }

    elif group_by == 'setup':
        # Группировка по сетапам
        groups = defaultdict(list)
        setups = {s.id: s.name for s in db.query(models.Setup).filter(models.Setup.account_id == account_id).all()}

        for t in trades:
            if t.setup_id and t.setup_id in setups:
                groups[setups[t.setup_id]].append(t)
            else:
                groups['Без сетапа'].append(t)

        if filter_value:
            if filter_value in groups:
                result = _analyze_trades_mae_mfe(groups[filter_value], mae_method)
                result["group_by"] = "setup"
                result["filter_value"] = filter_value
                result["recommendations"] = _generate_strategy_recommendations(result)
                result["trades"] = _trades_brief(groups[filter_value])
                return result
            return {"group_by": "setup", "filter_value": filter_value, "items": [], "total_trades": 0}

        items = []
        for name, group_trades in groups.items():
            if len(group_trades) >= 1:
                analysis = _analyze_trades_mae_mfe(group_trades, mae_method)
                items.append({
                    "name": name,
                    "trades_count": len(group_trades),
                    **analysis
                })

        items.sort(key=lambda x: x.get("edge_ratio", 0), reverse=True)

        return {
            "group_by": "setup",
            "items": items,
            "total_trades": len(trades),
            "total_groups": len(items)
        }

    return {"error": "Invalid group_by parameter"}


def _trades_brief(trades, cap: int = 100) -> list[dict]:
    """Пер-сделочный список для drill-down в MAE/MFE панели.

    Даёт юзеру путь от агрегата группы к конкретной сделке и её Trade Replay
    (аудит 2026-06-10: строка таблицы выглядела кликабельной, но вела в никуда).
    Cap 100 — защита payload'а; сортировка по exit_at desc.
    """
    rows = sorted(trades, key=lambda t: t.exit_at or t.entry_at, reverse=True)[:cap]
    out = []
    for t in rows:
        entry = float(t.entry_price) if t.entry_price is not None else None

        def _pct(price):
            if price is None or not entry:
                return None
            return round(abs((float(price) - entry) / entry) * 100, 2)

        direction = t.direction.value if hasattr(t.direction, "value") else str(t.direction)
        out.append({
            "id": t.id,
            "symbol": t.symbol,
            "direction": direction,
            "entry_at": t.entry_at.isoformat() if t.entry_at else None,
            "exit_at": t.exit_at.isoformat() if t.exit_at else None,
            "pnl": float(t.pnl) if t.pnl is not None else None,
            "mae_pct": _pct(t.mae_price),
            "mfe_pct": _pct(t.mfe_price),
        })
    return out


def _analyze_trades_mae_mfe(trades, mae_method: str = 'weighted_average') -> dict:
    """Анализирует MAE/MFE для группы сделок

    mae_method:
        - 'weighted_average': от средневзвешенной цены входа (по умолчанию)
        - 'first_entry': от цены первого входа
    """
    import numpy as np

    mae_values = []
    mfe_values = []
    efficiencies = []
    pnl_sum = 0
    wins = 0
    win_pnls = []  # Для расчёта реального R:R
    loss_pnls = []

    for t in trades:
        # Определяем базовую цену в зависимости от метода
        if mae_method == 'first_entry' and t.operations:
            # Ищем первый вход в операциях
            entry_ops = [op for op in t.operations if op.get('type') == 'entry']
            if entry_ops:
                entry_price = float(entry_ops[0].get('price', t.entry_price))
            else:
                entry_price = float(t.entry_price) if t.entry_price else 0
        else:
            # По умолчанию - средневзвешенная цена
            entry_price = float(t.entry_price) if t.entry_price else 0

        if entry_price == 0:
            continue

        is_long = t.direction.value == 'long' if hasattr(t.direction, 'value') else t.direction == 'long'
        # MATH-01: NET-pnl (после комиссий) приоритетнее GROSS. GROSS-fallback
        # только если net_pnl ещё не посчитан (legacy / manual ввод без fees).
        pnl = float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0))
        pnl_sum += pnl
        if pnl > 0:
            wins += 1
            win_pnls.append(pnl)
        elif pnl < 0:
            loss_pnls.append(abs(pnl))

        mae_price = float(t.mae_price) if t.mae_price else entry_price
        mfe_price = float(t.mfe_price) if t.mfe_price else entry_price
        exit_price = float(t.exit_price) if t.exit_price else entry_price

        if is_long:
            mae_pct = max(0, (entry_price - mae_price) / entry_price * 100)
            mfe_pct = max(0, (mfe_price - entry_price) / entry_price * 100)
        else:
            mae_pct = max(0, (mae_price - entry_price) / entry_price * 100)
            mfe_pct = max(0, (entry_price - mfe_price) / entry_price * 100)

        if mfe_pct > 0:
            if is_long:
                actual_pct = (exit_price - entry_price) / entry_price * 100
            else:
                actual_pct = (entry_price - exit_price) / entry_price * 100
            efficiency = max(0, min(100, actual_pct / mfe_pct * 100))
        else:
            efficiency = 0

        mae_values.append(mae_pct)
        mfe_values.append(mfe_pct)
        efficiencies.append(efficiency)

    if not mae_values:
        return {"trades_count": 0, "avg_mae": 0, "avg_mfe": 0, "edge_ratio": 0}

    mae_arr = np.array(mae_values)
    mfe_arr = np.array(mfe_values)
    eff_arr = np.array(efficiencies)

    avg_mae = float(np.mean(mae_arr))
    avg_mfe = float(np.mean(mfe_arr))
    edge_ratio = avg_mfe / avg_mae if avg_mae > 0 else 0

    # Реальные показатели на основе фактических результатов
    avg_win = float(np.mean(win_pnls)) if win_pnls else 0
    avg_loss = float(np.mean(loss_pnls)) if loss_pnls else 0
    real_rr = avg_win / avg_loss if avg_loss > 0 else 0
    # MATH-05: profit_factor = None (UNDEFINED) при отсутствии лузеров.
    # Семантически 0 = "плохой PF"; all-winners = ∞, представляется как UNDEFINED
    # (так же, как в analytics.calculate_advanced_stats).
    total_losses = sum(loss_pnls)
    profit_factor = (sum(win_pnls) / total_losses) if total_losses > 0 else None
    required_winrate = 1 / (1 + real_rr) * 100 if real_rr > 0 else 100

    return {
        "trades_count": len(trades),
        "wins": wins,
        "losses": len(loss_pnls),
        "win_rate": round(wins / len(trades) * 100, 1) if trades else 0,
        "total_pnl": round(pnl_sum, 2),
        "avg_mae": round(avg_mae, 2),
        "avg_mfe": round(avg_mfe, 2),
        "avg_efficiency": round(float(np.mean(eff_arr)), 1),
        "edge_ratio": round(edge_ratio, 2),
        # Реальные показатели
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "real_rr": round(real_rr, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "required_winrate": round(required_winrate, 1),
        "mae_percentiles": {
            "p25": round(float(np.percentile(mae_arr, 25)), 2),
            "p50": round(float(np.percentile(mae_arr, 50)), 2),
            "p75": round(float(np.percentile(mae_arr, 75)), 2),
            "max": round(float(np.max(mae_arr)), 2)
        },
        "mfe_percentiles": {
            "p25": round(float(np.percentile(mfe_arr, 25)), 2),
            "p50": round(float(np.percentile(mfe_arr, 50)), 2),
            "p75": round(float(np.percentile(mfe_arr, 75)), 2),
            "max": round(float(np.max(mfe_arr)), 2)
        },
        "quality_score": _calculate_quality_score(avg_mae, avg_mfe, edge_ratio, wins / len(trades) if trades else 0)
    }


def _calculate_quality_score(avg_mae: float, avg_mfe: float, edge_ratio: float, win_rate: float) -> int:
    """Рассчитывает оценку качества от 0 до 100"""
    score = 0

    if edge_ratio >= 3:
        score += 40
    elif edge_ratio >= 2:
        score += 30
    elif edge_ratio >= 1.5:
        score += 20
    elif edge_ratio >= 1:
        score += 10

    score += min(30, win_rate * 40)

    if avg_mae <= 1:
        score += 30
    elif avg_mae <= 2:
        score += 20
    elif avg_mae <= 3:
        score += 10

    return min(100, int(score))


def _generate_strategy_recommendations(analysis: dict) -> list:
    """Генерирует рекомендации для стратегии/группы с иконками и обоснованием"""
    recommendations = []

    edge = analysis.get("edge_ratio", 0)
    mae = analysis.get("avg_mae", 0)
    mfe = analysis.get("avg_mfe", 0)
    eff = analysis.get("avg_efficiency", 0)
    wr = analysis.get("win_rate", 0)
    quality = analysis.get("quality_score", 0)
    trades_count = analysis.get("trades_count", 0)

    # Реальные показатели
    real_rr = analysis.get("real_rr", 0)
    profit_factor = analysis.get("profit_factor") or 0
    required_wr = analysis.get("required_winrate", 100)
    avg_win = analysis.get("avg_win", 0)
    avg_loss = analysis.get("avg_loss", 0)
    total_pnl = analysis.get("total_pnl", 0)

    mae_percentiles = analysis.get("mae_percentiles", {})
    mfe_percentiles = analysis.get("mfe_percentiles", {})

    # Edge Ratio Analysis - с учётом реальной прибыльности
    is_profitable = total_pnl > 0

    if edge >= 2.5:
        recommendations.append({
            "type": "success",
            "icon": "🚀",
            "text": f"Превосходный Edge Ratio ({edge:.2f}x). Цена идёт в вашу сторону в {edge:.1f} раза больше, чем против. Отличные точки входа!"
        })
    elif edge >= 1.5:
        recommendations.append({
            "type": "success",
            "icon": "✅",
            "text": f"Хороший Edge Ratio ({edge:.2f}x). Цена чаще движется в вашу пользу — точки входа работают."
        })
    elif edge >= 1:
        if is_profitable:
            recommendations.append({
                "type": "info",
                "icon": "📊",
                "text": f"Edge Ratio ({edge:.2f}x) — цена идёт в вашу сторону чуть больше. При высоком винрейте ({wr:.0f}%) это работает!"
            })
        else:
            recommendations.append({
                "type": "warning",
                "icon": "⚠️",
                "text": f"Edge Ratio ({edge:.2f}x). Движение примерно равное в обе стороны. Улучшите тайминг входов."
            })
    else:
        if is_profitable:
            recommendations.append({
                "type": "info",
                "icon": "💡",
                "text": f"Edge Ratio ({edge:.2f}x) ниже 1, но стратегия прибыльна за счёт высокого винрейта ({wr:.0f}%). Это допустимо!"
            })
        else:
            recommendations.append({
                "type": "warning",
                "icon": "⚠️",
                "text": f"Edge Ratio ({edge:.2f}x). Цена чаще идёт против вас. Улучшите точки входа или дождитесь лучших сетапов."
            })

    # MAE Analysis with actionable advice
    if mae > 5:
        recommendations.append({
            "type": "danger",
            "icon": "📉",
            "text": f"Очень высокий MAE ({mae:.1f}%). Позиции часто уходят в глубокий минус. Причины: плохой тайминг входа, торговля против тренда, или слишком широкие стопы."
        })
    elif mae > 3:
        recommendations.append({
            "type": "warning",
            "icon": "⚡",
            "text": f"Высокий MAE ({mae:.1f}%). Рекомендации: 1) Дождитесь подтверждения разворота перед входом; 2) Используйте лимитные ордера ближе к уровням поддержки/сопротивления."
        })
    elif mae <= 1:
        recommendations.append({
            "type": "success",
            "icon": "🎯",
            "text": f"Превосходный MAE ({mae:.1f}%). Ваши точки входа очень точные — позиции почти сразу идут в плюс. Сохраняйте эту дисциплину."
        })
    elif mae <= 2:
        recommendations.append({
            "type": "info",
            "icon": "👍",
            "text": f"Хороший MAE ({mae:.1f}%). Точки входа достаточно точные, минимальные просадки после открытия позиции."
        })

    # MFE Analysis
    if mfe >= 5:
        recommendations.append({
            "type": "success",
            "icon": "📈",
            "text": f"Высокий MFE ({mfe:.1f}%). Позиции достигают значительной прибыли. При эффективности {eff:.0f}% вы реализуете {eff/100*mfe:.1f}% из потенциальных {mfe:.1f}%."
        })
    elif mfe < 2 and mfe > 0:
        recommendations.append({
            "type": "warning",
            "icon": "📊",
            "text": f"Низкий MFE ({mfe:.1f}%). Позиции не достигают значительной прибыли. Возможно стоит удерживать позиции дольше или торговать более волатильные инструменты."
        })

    # Efficiency Analysis
    if eff < 25:
        recommendations.append({
            "type": "danger",
            "icon": "💨",
            "text": f"Очень низкая эффективность ({eff:.0f}%). Вы забираете менее четверти потенциальной прибыли. Используйте trailing stop вместо фиксированного тейка."
        })
    elif eff < 40:
        recommendations.append({
            "type": "warning",
            "icon": "⏱️",
            "text": f"Низкая эффективность ({eff:.0f}%). Вы закрываете позиции слишком рано. Рассмотрите: 1) Trailing stop; 2) Частичное закрытие; 3) Тейк на уровне p50 MFE."
        })
    elif eff >= 70:
        recommendations.append({
            "type": "success",
            "icon": "🏆",
            "text": f"Отличная эффективность ({eff:.0f}%). Вы хорошо реализуете потенциал движения. Продолжайте в том же духе."
        })

    # Stop-Loss Recommendation based on percentiles
    mae_p50 = mae_percentiles.get("p50", 0)
    mae_p75 = mae_percentiles.get("p75", 0)
    mae_max = mae_percentiles.get("max", 0)

    if mae_p75 > 0:
        # Calculate optimal stop based on distribution
        if mae_max > mae_p75 * 2:
            recommendations.append({
                "type": "warning",
                "icon": "🛡️",
                "text": f"СТОП-ЛОСС: Рекомендуется {mae_p75:.1f}% (p75). Обоснование: 75% сделок не уходят ниже этого уровня. ⚠️ Внимание: max MAE ({mae_max:.1f}%) значительно выше — бывают редкие глубокие просадки."
            })
        else:
            recommendations.append({
                "type": "info",
                "icon": "🛡️",
                "text": f"СТОП-ЛОСС: Оптимальный уровень {mae_p75:.1f}% (p75). Обоснование: 75% ваших сделок не уходят ниже этого уровня, при этом вы не выбиваетесь по шуму."
            })

    # Take-Profit Recommendation based on percentiles
    mfe_p25 = mfe_percentiles.get("p25", 0)
    mfe_p50 = mfe_percentiles.get("p50", 0)
    mfe_p75 = mfe_percentiles.get("p75", 0)

    if mfe_p25 > 0 and mfe_p50 > 0:
        if eff < 50:
            recommendations.append({
                "type": "info",
                "icon": "🎯",
                "text": f"ТЕЙК-ПРОФИТ: Консервативный — {mfe_p25:.1f}% (достижимо в 75% сделок). Агрессивный — {mfe_p50:.1f}% (достижимо в 50% сделок). При низкой эффективности ({eff:.0f}%) начните с консервативного."
            })
        else:
            recommendations.append({
                "type": "info",
                "icon": "🎯",
                "text": f"ТЕЙК-ПРОФИТ: Оптимальный — {mfe_p50:.1f}% (медиана, достижимо в 50% сделок). Для максимизации — {mfe_p75:.1f}% (только 25% сделок достигают этого уровня)."
            })

    # Risk/Reward recommendation - используем РЕАЛЬНЫЕ данные!
    if real_rr > 0:
        # Используем реальный R:R на основе фактических результатов
        is_profitable = total_pnl > 0
        winrate_ok = wr >= required_wr

        if is_profitable and profit_factor >= 1.5:
            recommendations.append({
                "type": "success",
                "icon": "💰",
                "text": f"РЕАЛЬНЫЙ R:R = {real_rr:.2f}:1 (ср. победа +{avg_win:.0f}₽ / ср. убыток -{avg_loss:.0f}₽). Profit Factor: {profit_factor:.2f}. Стратегия ПРИБЫЛЬНА!"
            })
        elif is_profitable:
            recommendations.append({
                "type": "info",
                "icon": "✅",
                "text": f"РЕАЛЬНЫЙ R:R = {real_rr:.2f}:1. При винрейте {wr:.0f}% (мин. требуется {required_wr:.0f}%) стратегия прибыльна. Profit Factor: {profit_factor:.2f}."
            })
        elif winrate_ok:
            recommendations.append({
                "type": "warning",
                "icon": "⚖️",
                "text": f"РЕАЛЬНЫЙ R:R = {real_rr:.2f}:1. Винрейт {wr:.0f}% >= {required_wr:.0f}%, но PnL отрицательный. Проверьте размеры позиций."
            })
        else:
            recommendations.append({
                "type": "warning",
                "icon": "⚖️",
                "text": f"РЕАЛЬНЫЙ R:R = {real_rr:.2f}:1. Требуется винрейт {required_wr:.0f}%, у вас {wr:.0f}%. Увеличьте тейки или сократите стопы."
            })
    elif mae_p75 > 0 and mfe_p25 > 0:
        # Fallback на потенциальный R:R если нет реальных данных
        rr = mfe_p25 / mae_p75
        recommendations.append({
            "type": "info",
            "icon": "⚖️",
            "text": f"Потенциальный R:R = {rr:.2f}:1 (тейк {mfe_p25:.1f}% / стоп {mae_p75:.1f}%)."
        })

    # Quality Score recommendation - с учётом реальной прибыльности
    if is_profitable and profit_factor >= 1.5:
        recommendations.append({
            "type": "success",
            "icon": "⭐",
            "text": f"Стратегия ПРИБЫЛЬНА (PnL: {'+' if total_pnl >= 0 else ''}{total_pnl:,.0f}₽, PF: {profit_factor:.2f}). Рейтинг {quality}/100. Продолжайте в том же духе!"
        })
    elif is_profitable:
        recommendations.append({
            "type": "info",
            "icon": "📋",
            "text": f"Стратегия прибыльна (PnL: +{total_pnl:,.0f}₽). Рейтинг {quality}/100. Есть потенциал для улучшения эффективности."
        })
    elif quality >= 50:
        recommendations.append({
            "type": "warning",
            "icon": "🔧",
            "text": f"Рейтинг {quality}/100, но PnL отрицательный ({total_pnl:,.0f}₽). Проанализируйте убыточные сделки."
        })
    else:
        recommendations.append({
            "type": "warning",
            "icon": "📊",
            "text": f"Рейтинг {quality}/100. Требуется анализ: улучшите точки входа или управление позицией."
        })

    # Sample size warning
    if trades_count < 10:
        recommendations.append({
            "type": "warning",
            "icon": "📊",
            "text": f"Внимание: анализ основан на {trades_count} сделках. Для статистически значимых выводов рекомендуется минимум 30 сделок."
        })

    return recommendations


@router.get("/mae-mfe-by-symbol")
async def get_mae_mfe_by_symbol(
    symbol: Optional[str] = Query(None, description="Конкретный тикер для детального анализа"),
    asset_type: Optional[str] = Query(None, description="Тип актива: Stock, Futures, Bond"),
    direction: Optional[str] = Query(None, description="Направление: long, short"),
    mae_method: str = Query('weighted_average', description="Метод расчёта MAE"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """
    MAE/MFE анализ по тикерам.

    - Без параметров: возвращает сводку по всем тикерам
    - С symbol: детальный анализ конкретного тикера
    - Фильтры: asset_type (Stock/Futures), direction (long/short)
    """
    account_id = auth_service.get_account_id(db, current_user)

    # Базовый запрос
    query = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at != None,
        models.Trade.mae_price != None,
        models.Trade.mfe_price != None
    )

    # Применяем фильтры
    if asset_type:
        query = query.filter(models.Trade.asset_type == asset_type)
    if direction:
        query = query.filter(models.Trade.direction == direction)
    if symbol:
        query = query.filter(models.Trade.symbol == symbol)

    trades = query.all()

    if not trades:
        return {
            "symbols": [],
            "total_trades": 0,
            "filters_applied": {"symbol": symbol, "asset_type": asset_type, "direction": direction}
        }

    # Группируем по тикерам
    from collections import defaultdict
    symbol_data = defaultdict(lambda: {
        "trades": [],
        "mae_values": [],
        "mfe_values": [],
        "efficiencies": [],
        "pnl_sum": 0,
        "wins": 0,
        "total": 0
    })

    for t in trades:
        s = t.symbol
        entry_price = float(t.entry_price) if t.entry_price else 0
        if entry_price == 0:
            continue

        is_long = t.direction.value == 'long' if hasattr(t.direction, 'value') else t.direction == 'long'
        # MATH-01: NET-pnl (после комиссий) приоритетнее GROSS.
        pnl = float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0))

        # Рассчитываем MAE/MFE в процентах
        mae_price = float(t.mae_price) if t.mae_price else entry_price
        mfe_price = float(t.mfe_price) if t.mfe_price else entry_price
        exit_price = float(t.exit_price) if t.exit_price else entry_price

        if is_long:
            mae_pct = max(0, (entry_price - mae_price) / entry_price * 100)
            mfe_pct = max(0, (mfe_price - entry_price) / entry_price * 100)
        else:
            mae_pct = max(0, (mae_price - entry_price) / entry_price * 100)
            mfe_pct = max(0, (entry_price - mfe_price) / entry_price * 100)

        # Эффективность: сколько от MFE забрали
        if mfe_pct > 0:
            if is_long:
                actual_profit_pct = (exit_price - entry_price) / entry_price * 100
            else:
                actual_profit_pct = (entry_price - exit_price) / entry_price * 100
            efficiency = max(0, min(100, actual_profit_pct / mfe_pct * 100))
        else:
            efficiency = 0

        symbol_data[s]["trades"].append(t)
        symbol_data[s]["mae_values"].append(mae_pct)
        symbol_data[s]["mfe_values"].append(mfe_pct)
        symbol_data[s]["efficiencies"].append(efficiency)
        symbol_data[s]["pnl_sum"] += pnl
        symbol_data[s]["wins"] += 1 if pnl > 0 else 0
        symbol_data[s]["total"] += 1

    # Формируем результат
    import numpy as np
    symbols_result = []

    for sym, data in symbol_data.items():
        if not data["mae_values"]:
            continue

        mae_arr = np.array(data["mae_values"])
        mfe_arr = np.array(data["mfe_values"])
        eff_arr = np.array(data["efficiencies"])

        # Получаем название актива из первой сделки
        first_trade = data["trades"][0]
        asset_name = first_trade.asset_name or sym
        asset_type_val = first_trade.asset_type or "Unknown"

        avg_mae = float(np.mean(mae_arr))
        avg_mfe = float(np.mean(mfe_arr))
        edge_ratio = avg_mfe / avg_mae if avg_mae > 0 else 0

        symbols_result.append({
            "symbol": sym,
            "asset_name": asset_name,
            "asset_type": asset_type_val,
            "trades_count": data["total"],
            "wins": data["wins"],
            "win_rate": round(data["wins"] / data["total"] * 100, 1) if data["total"] > 0 else 0,
            "total_pnl": round(data["pnl_sum"], 2),
            "avg_mae_pct": round(avg_mae, 2),
            "avg_mfe_pct": round(avg_mfe, 2),
            "avg_efficiency": round(float(np.mean(eff_arr)), 1),
            "edge_ratio": round(edge_ratio, 2),
            "mae_percentiles": {
                "p25": round(float(np.percentile(mae_arr, 25)), 2),
                "p50": round(float(np.percentile(mae_arr, 50)), 2),
                "p75": round(float(np.percentile(mae_arr, 75)), 2),
                "max": round(float(np.max(mae_arr)), 2)
            },
            "mfe_percentiles": {
                "p25": round(float(np.percentile(mfe_arr, 25)), 2),
                "p50": round(float(np.percentile(mfe_arr, 50)), 2),
                "p75": round(float(np.percentile(mfe_arr, 75)), 2),
                "max": round(float(np.max(mfe_arr)), 2)
            },
            # Оценка качества тикера
            "quality_score": _calculate_symbol_quality(avg_mae, avg_mfe, edge_ratio, data["wins"] / data["total"] if data["total"] > 0 else 0)
        })

    # Сортируем по edge_ratio (лучшие сверху)
    symbols_result.sort(key=lambda x: x["edge_ratio"], reverse=True)

    # Если запросили конкретный тикер - добавляем рекомендации
    if symbol and len(symbols_result) == 1:
        sym_data = symbols_result[0]
        sym_data["recommendations"] = _generate_symbol_recommendations(sym_data)

        # Добавляем детальную статистику по направлениям
        long_trades = [t for t in symbol_data[symbol]["trades"]
                       if (t.direction.value if hasattr(t.direction, 'value') else t.direction) == 'long']
        short_trades = [t for t in symbol_data[symbol]["trades"]
                        if (t.direction.value if hasattr(t.direction, 'value') else t.direction) == 'short']

        # MATH-01: NET-pnl суммы в by-direction breakdown.
        sym_data["by_direction"] = {
            "long": {
                "count": len(long_trades),
                "pnl": sum(
                    float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0))
                    for t in long_trades
                ),
            },
            "short": {
                "count": len(short_trades),
                "pnl": sum(
                    float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0))
                    for t in short_trades
                ),
            },
        }

    # Добавляем общую статистику
    all_edge_ratios = [s["edge_ratio"] for s in symbols_result if s["edge_ratio"] > 0]

    return {
        "symbols": symbols_result,
        "total_trades": len(trades),
        "total_symbols": len(symbols_result),
        "filters_applied": {"symbol": symbol, "asset_type": asset_type, "direction": direction},
        "summary": {
            "best_symbol": symbols_result[0]["symbol"] if symbols_result else None,
            "worst_symbol": symbols_result[-1]["symbol"] if symbols_result else None,
            "avg_edge_ratio": round(np.mean(all_edge_ratios), 2) if all_edge_ratios else 0,
            "symbols_with_good_edge": len([s for s in symbols_result if s["edge_ratio"] >= 1.5]),
            "symbols_with_bad_edge": len([s for s in symbols_result if s["edge_ratio"] < 1.0])
        }
    }


def _calculate_symbol_quality(avg_mae: float, avg_mfe: float, edge_ratio: float, win_rate: float) -> int:
    """
    Рассчитывает оценку качества тикера от 0 до 100.

    Факторы:
    - Edge Ratio (MFE/MAE): чем выше, тем лучше
    - Win Rate: процент выигрышей
    - Низкий MAE: меньше просадка = лучше
    """
    score = 0

    # Edge Ratio (до 40 баллов)
    if edge_ratio >= 3:
        score += 40
    elif edge_ratio >= 2:
        score += 30
    elif edge_ratio >= 1.5:
        score += 20
    elif edge_ratio >= 1:
        score += 10

    # Win Rate (до 30 баллов)
    score += min(30, win_rate * 0.4)

    # Низкий MAE (до 30 баллов) - меньше 2% = отлично
    if avg_mae <= 1:
        score += 30
    elif avg_mae <= 2:
        score += 20
    elif avg_mae <= 3:
        score += 10

    return min(100, int(score))


def _generate_symbol_recommendations(sym_data: dict) -> list:
    """Генерирует рекомендации для конкретного тикера."""
    recommendations = []

    edge_ratio = sym_data["edge_ratio"]
    avg_mae = sym_data["avg_mae_pct"]
    avg_mfe = sym_data["avg_mfe_pct"]
    efficiency = sym_data["avg_efficiency"]
    win_rate = sym_data["win_rate"]
    quality = sym_data["quality_score"]

    # Оценка edge ratio
    if edge_ratio >= 2:
        recommendations.append({
            "type": "success",
            "icon": "✅",
            "text": f"Отличный Edge Ratio ({edge_ratio}x) — потенциал прибыли значительно превышает риск"
        })
    elif edge_ratio >= 1.5:
        recommendations.append({
            "type": "info",
            "icon": "👍",
            "text": f"Хороший Edge Ratio ({edge_ratio}x) — приемлемое соотношение риск/прибыль"
        })
    elif edge_ratio < 1:
        recommendations.append({
            "type": "danger",
            "icon": "⚠️",
            "text": f"Низкий Edge Ratio ({edge_ratio}x) — риск превышает потенциал прибыли. Рассмотрите исключение из торговли"
        })

    # Оценка MAE
    if avg_mae > 3:
        recommendations.append({
            "type": "warning",
            "icon": "📉",
            "text": f"Высокий MAE ({avg_mae:.1f}%) — позиции уходят в глубокий минус. Ужесточите стоп-лоссы"
        })
    elif avg_mae <= 1:
        recommendations.append({
            "type": "success",
            "icon": "🎯",
            "text": f"Низкий MAE ({avg_mae:.1f}%) — отличные точки входа с минимальной просадкой"
        })

    # Оценка эффективности
    if efficiency < 30:
        recommendations.append({
            "type": "warning",
            "icon": "💸",
            "text": f"Низкая эффективность ({efficiency:.0f}%) — вы забираете мало от потенциальной прибыли. Подержите позиции дольше"
        })
    elif efficiency >= 70:
        recommendations.append({
            "type": "success",
            "icon": "💰",
            "text": f"Высокая эффективность ({efficiency:.0f}%) — вы хорошо забираете прибыль"
        })

    # Общая рекомендация
    if quality >= 70:
        recommendations.append({
            "type": "insight",
            "icon": "⭐",
            "text": f"Рейтинг {quality}/100 — это один из ваших лучших инструментов. Увеличьте размер позиции"
        })
    elif quality < 40:
        recommendations.append({
            "type": "danger",
            "icon": "🚫",
            "text": f"Рейтинг {quality}/100 — рассмотрите исключение этого инструмента из торговли"
        })

    return recommendations


@router.post("/pnl-health/refresh")
async def refresh_pnl_health(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    """Phase 10 (2026-05-17): принудительный пересчёт P&L Health Check.

    Кнопка "Проверить сейчас" на дашборде. ~50-150ms на средние счета,
    до 500ms на очень большие (10k+ trades).

    Возвращает свежий PnLHealthResult в JSON формате.
    """
    from services import pnl_health_service

    account_id = auth_service.get_account_id(db, current_user)
    if not account_id:
        raise HTTPException(status_code=404, detail="Account not found")
    result = pnl_health_service.compute_and_persist(db, account_id)
    return result.to_breakdown_json()


@router.get("/audit")
async def audit_trades(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """
    Полный аудит всех сделок - проверяет корректность PnL
    """
    account_id = auth_service.get_account_id(db, current_user)

    trades = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at != None,
        models.Trade.pnl != None
    ).order_by(models.Trade.exit_at).all()

    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    initial_balance = float(account.initial_balance or 0) if account else 0

    errors = []
    warnings = []
    total_gross_pnl = 0
    total_commission = 0
    total_net_pnl = 0

    for t in trades:
        pnl = float(t.pnl) if t.pnl else 0
        net_pnl = float(t.net_pnl) if t.net_pnl else 0
        commission = float(t.commission) if t.commission else 0

        direction = str(t.direction).split('.')[-1]
        entry = float(t.entry_price) if t.entry_price else 0
        exit_p = float(t.exit_price) if t.exit_price else 0
        qty = float(t.quantity) if t.quantity else 0

        total_gross_pnl += pnl
        total_commission += commission
        total_net_pnl += net_pnl

        # Check 1: net_pnl = pnl - commission?
        expected_net = pnl - commission
        if abs(net_pnl - expected_net) > 0.1:
            errors.append({
                'id': t.id,
                'symbol': t.symbol,
                'type': 'net_pnl_mismatch',
                'stored_net': net_pnl,
                'expected_net': expected_net,
                'diff': net_pnl - expected_net
            })

        # Check 2: PnL direction matches price movement (skip futures)
        is_futures = any(c.isdigit() for c in t.symbol[-3:]) if t.symbol else False
        if not is_futures and entry > 0 and exit_p > 0:
            if direction == 'LONG':
                expected_profit = exit_p > entry
                calc_pnl = (exit_p - entry) * qty
            else:
                expected_profit = exit_p < entry
                calc_pnl = (entry - exit_p) * qty

            actual_profit = pnl > 0

            if expected_profit != actual_profit and abs(pnl) > 1:
                errors.append({
                    'id': t.id,
                    'symbol': t.symbol,
                    'type': 'direction_mismatch',
                    'direction': direction,
                    'entry': entry,
                    'exit': exit_p,
                    'pnl': pnl
                })

            # Large diff from calculated
            if abs(pnl - calc_pnl) > 100:
                warnings.append({
                    'id': t.id,
                    'symbol': t.symbol,
                    'type': 'calc_diff',
                    'stored_pnl': pnl,
                    'calculated_pnl': calc_pnl,
                    'diff': pnl - calc_pnl
                })

    return {
        'total_trades': len(trades),
        'date_range': {
            'first': trades[0].exit_at.isoformat() if trades else None,
            'last': trades[-1].exit_at.isoformat() if trades else None
        },
        'summary': {
            'initial_balance': initial_balance,
            'gross_pnl': round(total_gross_pnl, 2),
            'commission': round(total_commission, 2),
            'net_pnl': round(total_net_pnl, 2),
            'check_gross_minus_comm': round(total_gross_pnl - total_commission, 2),
            'diff_from_net': round(total_net_pnl - (total_gross_pnl - total_commission), 2),
            'final_balance': round(initial_balance + total_net_pnl, 2)
        },
        'errors_count': len(errors),
        'warnings_count': len(warnings),
        'errors': errors[:20],
        'warnings': warnings[:20]
    }
