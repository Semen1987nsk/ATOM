"""
Stats Router — статистика торговли, аналитика, теги
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

import database
import models
import schemas
import analytics
import auth_service
from utils import utc_now_naive
from logger import get_logger

log = get_logger("stats")

router = APIRouter(tags=["stats"])


def get_account_id(db: Session, user: Optional[models.User] = None) -> int:
    """Получить account_id для текущего пользователя или вернуть 1 для анонима"""
    if user:
        account = auth_service.get_user_account(db, user)
        return account.id
    return 1


@router.get("/tags/")
async def get_all_tags(
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """Get all unique tags used in trades with their statistics."""
    account_id = get_account_id(db, current_user)
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


@router.get("/stats/", response_model=schemas.DashboardStats)
async def get_stats(
    period: Optional[str] = Query(None, description="Period filter: all, today, week, month, 3months, year, custom"),
    start_date: Optional[str] = Query(None, description="Start date for custom period (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date for custom period (YYYY-MM-DD)"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    limit: Optional[int] = Query(None, description="Limit to last N trades"),
    initial_deposit: Optional[float] = Query(None, description="Initial deposit for ROI calculation"),
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """Get trading statistics with optional filters: time period, tag, and trade count limit."""
    account_id = get_account_id(db, current_user)
    
    # Build date filter
    date_filter = None
    now = utc_now_naive()
    
    if period == "today":
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
    risks = [float(t.risk_amount) if t.risk_amount else float(abs(t.pnl)) for t in trades]
    opt_f_data = analytics.calculate_optimal_f(pnls, risks)
    
    # Расчет SQN
    sqn_data = analytics.calculate_sqn(pnls, risks)

    # Расчет Z-Score
    z_score_data = analytics.calculate_z_score(pnls)
    
    # Расчет Advanced Stats
    adv_stats = analytics.calculate_advanced_stats(pnls, risks)

    # Анализ MAE/MFE
    mae_mfe_data = analytics.analyze_mae_mfe(trades)
    
    # Расчет кривой эквити (хронологический порядок)
    sorted_trades = sorted(trades, key=lambda x: x.exit_at if x.exit_at else x.entry_at)
    pnls_sorted = [get_pnl(t) for t in sorted_trades]
    
    # Получаем начальный баланс из аккаунта
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    initial_balance = float(account.initial_balance or 0) if account else 0
    
    equity_curve = []
    current_balance = initial_balance
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

    return {
        "total_pnl": total_pnl,
        "win_rate": win_rate,
        "total_trades": total_trades,
        "profitable_trades": profitable_trades,
        "optimal_f": opt_f_data.get("optimal_f", 0),
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
        "initial_balance": initial_balance,
        "current_balance": current_balance if equity_curve else initial_balance,
    }
