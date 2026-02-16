"""
Stats Router — статистика торговли, аналитика, теги
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import hashlib
import json

import database
import models
import schemas
import analytics
import auth_service
from utils import utc_now_naive
from logger import get_logger
from tinkoff_service import TinkoffService

log = get_logger("stats")

router = APIRouter(tags=["stats"])

# Simple in-memory cache for stats
_stats_cache = {}
_cache_ttl = 30  # seconds

def _get_cache_key(account_id, **kwargs):
    """Generate cache key from parameters"""
    params = {k: v for k, v in kwargs.items() if v is not None}
    params['account_id'] = account_id
    key_str = json.dumps(params, sort_keys=True, default=str)
    return hashlib.md5(key_str.encode()).hexdigest()

def _get_cached(key):
    """Get value from cache if not expired"""
    if key in _stats_cache:
        value, timestamp = _stats_cache[key]
        if (datetime.now() - timestamp).total_seconds() < _cache_ttl:
            return value
        del _stats_cache[key]
    return None

def _set_cached(key, value):
    """Set value in cache"""
    _stats_cache[key] = (value, datetime.now())
    # Clean old entries (keep max 100)
    if len(_stats_cache) > 100:
        oldest_keys = sorted(_stats_cache.keys(), 
                           key=lambda k: _stats_cache[k][1])[:50]
        for k in oldest_keys:
            del _stats_cache[k]


# get_account_id is now centralized in auth_service


@router.get("/tags/")
async def get_all_tags(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Get all unique tags used in trades with their statistics."""
    account_id = auth_service.get_account_id(db, current_user)
    trades = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.pnl != None
    ).all()
    
    tag_stats = {}
    for t in trades:
        if not t.tags:
            continue
        for tag in t.tags:
            tag_lower = tag.lower()
            if tag_lower not in tag_stats:
                tag_stats[tag_lower] = {"tag": tag_lower, "count": 0, "pnl": 0, "wins": 0}
            tag_stats[tag_lower]["count"] += 1
            tag_stats[tag_lower]["pnl"] += float(t.pnl or 0)
            if t.pnl and t.pnl > 0:
                tag_stats[tag_lower]["wins"] += 1
    
    result = []
    for tag, data in tag_stats.items():
        result.append({
            "tag": data["tag"],
            "count": data["count"],
            "pnl": round(data["pnl"], 2),
            "win_rate": round((data["wins"] / data["count"]) * 100, 1) if data["count"] > 0 else 0
        })
    
    return sorted(result, key=lambda x: x["count"], reverse=True)


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
    
    # Check cache first
    cache_key = _get_cache_key(account_id, period=period, start_date=start_date, 
                               end_date=end_date, start_trade_id=start_trade_id,
                               tag=tag, limit=limit, mae_method=mae_method)
    cached = _get_cached(cache_key)
    if cached:
        log.debug(f"Stats cache hit for key {cache_key[:8]}")
        # Пересчитываем ROI с актуальным initial_deposit (не кэшируется)
        if initial_deposit and initial_deposit > 0:
            cached_copy = dict(cached)
            total_pnl = cached_copy.get('total_pnl', 0)
            cached_copy['total_roi'] = round((total_pnl / initial_deposit * 100), 2)
            return cached_copy
        return cached
    
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
    
    # Query trades with filter
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
    
    all_trades = query.order_by(models.Trade.exit_at.desc()).all()
    
    # Filter by tag if specified
    if tag:
        tag_lower = tag.lower()
        all_trades = [t for t in all_trades if t.tags and any(tg.lower() == tag_lower for tg in t.tags)]
    
    # Apply limit (last N trades)
    if limit and limit > 0:
        all_trades = all_trades[:limit]
    
    trades = all_trades
    
    total_trades = len(trades)
    if total_trades == 0:
        return {
            "total_pnl": 0,
            "win_rate": 0,
            "total_trades": 0,
            "profitable_trades": 0,
            "optimal_f": 0
        }
    
    # Use net_pnl if available, else pnl
    def get_pnl(t):
        return float(t.net_pnl if t.net_pnl is not None else t.pnl)
    
    total_pnl = sum(get_pnl(t) for t in trades)
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
    
    # Получаем начальный баланс из аккаунта
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    base_initial_balance = float(account.initial_balance or 0) if account else 0
    
    # Если применён фильтр, рассчитываем баланс на момент начала фильтра
    # путём суммирования PnL всех сделок ДО фильтра
    starting_balance = base_initial_balance
    if date_filter:
        # Получаем все закрытые сделки ДО даты фильтра
        trades_before_filter = db.query(models.Trade).filter(
            models.Trade.account_id == account_id,
            models.Trade.pnl != None,
            models.Trade.exit_at != None,
            models.Trade.exit_at < date_filter
        ).all()
        
        # Суммируем их PnL для получения баланса на начало фильтра
        pnl_before = sum(float(t.net_pnl if t.net_pnl is not None else t.pnl) for t in trades_before_filter)
        starting_balance = base_initial_balance + pnl_before
        log.debug(f"Filter applied: {len(trades_before_filter)} trades before, starting_balance={starting_balance:.2f}")
    
    equity_curve = []
    current_balance = starting_balance
    for t in sorted_trades:
        current_balance += get_pnl(t)
        equity_curve.append({
            "date": (t.exit_at if t.exit_at else t.entry_at).strftime("%Y-%m-%d %H:%M"),
            "balance": round(current_balance, 2)
        })
    
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
    
    # Расчет дополнительных метрик
    sortino_data = analytics.calculate_sharpe_sortino(pnls)
    drawdown_data = analytics.calculate_drawdown_stats(pnls_sorted)
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
    calmar_data = analytics.calculate_calmar_ratio(pnls_sorted, initial_balance=initial_deposit or 100000, period_years=period_years)
    
    # Risk of Ruin
    avg_win = win_loss_data.get("avg_win", 0)
    avg_loss = abs(win_loss_data.get("avg_loss", 1))
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 1
    risk_of_ruin_data = analytics.calculate_risk_of_ruin(win_rate / 100, payoff_ratio)

    # Get unrealized PnL from open positions
    unrealized_pnl = 0.0
    try:
        broker_conn = db.query(models.BrokerConnection).filter(
            models.BrokerConnection.account_id == account_id,
            models.BrokerConnection.is_active == True
        ).first()
        if broker_conn:
            service = TinkoffService(broker_conn.api_token)
            portfolio = service.get_portfolio(broker_conn.broker_account_id)
            if portfolio and portfolio.get('positions'):
                for pos in portfolio['positions']:
                    unrealized_pnl += float(pos.get('unrealized_pnl', 0) or 0)
    except Exception as e:
        log.warning(f"Failed to get unrealized PnL: {e}")

    result = {
        "total_pnl": total_pnl,
        "unrealized_pnl": unrealized_pnl,
        "total_pnl_with_unrealized": total_pnl + unrealized_pnl,
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
        "total_roi": round((total_pnl / initial_deposit * 100), 2) if initial_deposit and initial_deposit > 0 else 0,
        "expected_ghpr": opt_f_data.get("geometric_mean", 0),
        "sortino_ratio": sortino_data.get("sortino_ratio", 0),
        "max_drawdown_pct": drawdown_data.get("max_drawdown_pct", 0),
        "max_drawdown_abs": drawdown_data.get("max_drawdown_abs", 0),
        "current_drawdown_pct": drawdown_data.get("current_drawdown_pct", 0),
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
        "tag_stats": tag_stats,
        "initial_balance": base_initial_balance,
        "current_balance": current_balance if equity_curve else base_initial_balance,
    }
    
    # Cache the result
    _set_cached(cache_key, result)
    return result


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
        pnl = float(t.pnl) if t.pnl else 0
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
    profit_factor = sum(win_pnls) / sum(loss_pnls) if loss_pnls and sum(loss_pnls) > 0 else 0
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
        "profit_factor": round(profit_factor, 2),
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
    profit_factor = analysis.get("profit_factor", 0)
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
        pnl = float(t.pnl) if t.pnl else 0
        
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
        
        sym_data["by_direction"] = {
            "long": {"count": len(long_trades), "pnl": sum(float(t.pnl or 0) for t in long_trades)},
            "short": {"count": len(short_trades), "pnl": sum(float(t.pnl or 0) for t in short_trades)}
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
