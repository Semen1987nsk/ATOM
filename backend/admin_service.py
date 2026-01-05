"""
Admin Service - сервис для административной панели
Метрики, аналитика пользователей, бизнес-показатели
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, distinct, and_, or_, case
from datetime import datetime, timedelta
from typing import Optional
import models
from utils import utc_now_naive


def get_current_admin(db: Session, user: models.User) -> models.User:
    """Проверка что пользователь является администратором"""
    if not user.is_admin:
        raise PermissionError("Требуются права администратора")
    return user


# ==================== USER ANALYTICS ====================

def get_users_list(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    search: Optional[str] = None,
    registration_source: Optional[str] = None
) -> dict:
    """Получить список пользователей с фильтрацией"""
    query = db.query(models.User)
    
    # Поиск
    if search:
        query = query.filter(
            or_(
                models.User.email.ilike(f"%{search}%"),
                models.User.name.ilike(f"%{search}%")
            )
        )
    
    # Фильтр по источнику
    if registration_source:
        query = query.filter(models.User.registration_source == registration_source)
    
    # Подсчёт общего количества
    total = query.count()
    
    # Сортировка
    sort_column = getattr(models.User, sort_by, models.User.created_at)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Пагинация
    users = query.offset(skip).limit(limit).all()
    
    # Добавляем статистику по сделкам для каждого пользователя
    users_data = []
    for user in users:
        # Получаем количество сделок через аккаунты
        trades_count = 0
        for account in user.accounts:
            trades_count += db.query(models.Trade).filter(
                models.Trade.account_id == account.id
            ).count()
        
        users_data.append({
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "is_active": bool(user.is_active),
            "is_admin": bool(user.is_admin),
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "registration_source": user.registration_source or "email",
            "oauth_provider": user.oauth_provider,
            "utm_source": user.utm_source,
            "utm_medium": user.utm_medium,
            "utm_campaign": user.utm_campaign,
            "trades_count": trades_count,
            "accounts_count": len(user.accounts),
        })
    
    return {
        "users": users_data,
        "total": total,
        "skip": skip,
        "limit": limit
    }


# ==================== DASHBOARD METRICS ====================

def get_overview_stats(db: Session) -> dict:
    """Основные метрики для дашборда"""
    now = utc_now_naive()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    # Общее количество пользователей
    total_users = db.query(models.User).count()
    
    # Новые пользователи
    new_today = db.query(models.User).filter(
        models.User.created_at >= today_start
    ).count()
    
    new_this_week = db.query(models.User).filter(
        models.User.created_at >= week_ago
    ).count()
    
    new_this_month = db.query(models.User).filter(
        models.User.created_at >= month_ago
    ).count()
    
    # Активные пользователи (заходили)
    dau = db.query(models.User).filter(
        models.User.last_login >= today_start
    ).count()
    
    wau = db.query(models.User).filter(
        models.User.last_login >= week_ago
    ).count()
    
    mau = db.query(models.User).filter(
        models.User.last_login >= month_ago
    ).count()
    
    # Общее количество сделок
    total_trades = db.query(models.Trade).count()
    
    # Сделки за периоды
    trades_today = db.query(models.Trade).filter(
        models.Trade.entry_at >= today_start
    ).count()
    
    trades_this_week = db.query(models.Trade).filter(
        models.Trade.entry_at >= week_ago
    ).count()
    
    # Среднее количество сделок на пользователя
    avg_trades_per_user = total_trades / total_users if total_users > 0 else 0
    
    return {
        "users": {
            "total": total_users,
            "new_today": new_today,
            "new_this_week": new_this_week,
            "new_this_month": new_this_month,
        },
        "activity": {
            "dau": dau,
            "wau": wau,
            "mau": mau,
            "dau_mau_ratio": round(dau / mau * 100, 1) if mau > 0 else 0,  # Stickiness
        },
        "engagement": {
            "total_trades": total_trades,
            "trades_today": trades_today,
            "trades_this_week": trades_this_week,
            "avg_trades_per_user": round(avg_trades_per_user, 1),
        }
    }


def get_registration_sources(db: Session) -> list:
    """Распределение пользователей по источникам регистрации"""
    results = db.query(
        models.User.registration_source,
        func.count(models.User.id).label("count")
    ).group_by(models.User.registration_source).all()
    
    total = sum(r.count for r in results)
    
    return [
        {
            "source": r.registration_source or "email",
            "count": r.count,
            "percentage": round(r.count / total * 100, 1) if total > 0 else 0
        }
        for r in results
    ]


def get_utm_analytics(db: Session) -> dict:
    """Аналитика UTM меток"""
    # По источникам
    sources = db.query(
        models.User.utm_source,
        func.count(models.User.id).label("count")
    ).filter(
        models.User.utm_source.isnot(None)
    ).group_by(models.User.utm_source).order_by(
        func.count(models.User.id).desc()
    ).limit(10).all()
    
    # По каналам
    mediums = db.query(
        models.User.utm_medium,
        func.count(models.User.id).label("count")
    ).filter(
        models.User.utm_medium.isnot(None)
    ).group_by(models.User.utm_medium).order_by(
        func.count(models.User.id).desc()
    ).limit(10).all()
    
    # По кампаниям
    campaigns = db.query(
        models.User.utm_campaign,
        func.count(models.User.id).label("count")
    ).filter(
        models.User.utm_campaign.isnot(None)
    ).group_by(models.User.utm_campaign).order_by(
        func.count(models.User.id).desc()
    ).limit(10).all()
    
    return {
        "sources": [{"name": s.utm_source, "count": s.count} for s in sources],
        "mediums": [{"name": m.utm_medium, "count": m.count} for m in mediums],
        "campaigns": [{"name": c.utm_campaign, "count": c.count} for c in campaigns],
    }


# ==================== GROWTH & RETENTION ====================

def get_user_growth(db: Session, days: int = 30) -> list:
    """График роста пользователей по дням"""
    now = utc_now_naive()
    start_date = now - timedelta(days=days)
    
    # Получаем регистрации по дням
    results = db.query(
        func.date(models.User.created_at).label("date"),
        func.count(models.User.id).label("count")
    ).filter(
        models.User.created_at >= start_date
    ).group_by(
        func.date(models.User.created_at)
    ).order_by(
        func.date(models.User.created_at)
    ).all()
    
    # Кумулятивный рост
    data = []
    cumulative = db.query(models.User).filter(
        models.User.created_at < start_date
    ).count()
    
    for r in results:
        cumulative += r.count
        # r.date может быть строкой из SQLite или datetime
        date_str = r.date if isinstance(r.date, str) else (r.date.isoformat() if r.date else None)
        data.append({
            "date": date_str,
            "new_users": r.count,
            "total_users": cumulative
        })
    
    return data


def get_cohort_retention(db: Session, weeks: int = 8) -> dict:
    """Когортный анализ retention"""
    now = utc_now_naive()
    cohorts = {}
    
    for week_offset in range(weeks):
        cohort_start = now - timedelta(weeks=week_offset + 1)
        cohort_end = now - timedelta(weeks=week_offset)
        
        # Пользователи в когорте
        cohort_users = db.query(models.User).filter(
            and_(
                models.User.created_at >= cohort_start,
                models.User.created_at < cohort_end
            )
        ).all()
        
        cohort_size = len(cohort_users)
        if cohort_size == 0:
            continue
        
        cohort_key = cohort_start.strftime("%Y-W%W")
        retention = {"cohort": cohort_key, "size": cohort_size, "weeks": {}}
        
        # Retention для каждой недели
        for ret_week in range(week_offset + 1):
            ret_start = cohort_start + timedelta(weeks=ret_week)
            ret_end = ret_start + timedelta(weeks=1)
            
            # Сколько пользователей заходили на этой неделе
            active_count = sum(
                1 for u in cohort_users
                if u.last_login and ret_start <= u.last_login < ret_end
            )
            
            retention["weeks"][f"week_{ret_week}"] = {
                "active": active_count,
                "rate": round(active_count / cohort_size * 100, 1)
            }
        
        cohorts[cohort_key] = retention
    
    return cohorts


# ==================== ENGAGEMENT METRICS ====================

def get_power_users(db: Session, limit: int = 20) -> list:
    """Топ активных пользователей по количеству сделок"""
    # Получаем пользователей с количеством сделок
    results = db.query(
        models.User,
        func.count(models.Trade.id).label("trades_count")
    ).join(
        models.Account, models.Account.user_id == models.User.id
    ).join(
        models.Trade, models.Trade.account_id == models.Account.id
    ).group_by(
        models.User.id
    ).order_by(
        func.count(models.Trade.id).desc()
    ).limit(limit).all()
    
    return [
        {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "trades_count": trades_count,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
        }
        for user, trades_count in results
    ]


def get_inactive_users(db: Session, days: int = 30, limit: int = 50) -> list:
    """Пользователи без активности за N дней (churn risk)"""
    threshold = utc_now_naive() - timedelta(days=days)
    
    users = db.query(models.User).filter(
        or_(
            models.User.last_login < threshold,
            models.User.last_login.is_(None)
        )
    ).order_by(
        models.User.last_login.desc().nullsfirst()
    ).limit(limit).all()
    
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "days_inactive": (utc_now_naive() - u.last_login).days if u.last_login else None,
        }
        for u in users
    ]


# ==================== BUSINESS METRICS ====================

def get_conversion_funnel(db: Session) -> dict:
    """Воронка конверсии"""
    total_registered = db.query(models.User).count()
    
    # С хотя бы одной сделкой
    users_with_trades = db.query(
        func.count(distinct(models.Account.user_id))
    ).join(
        models.Trade, models.Trade.account_id == models.Account.id
    ).scalar() or 0
    
    # С 5+ сделками (активные)
    active_traders = db.query(
        models.Account.user_id
    ).join(
        models.Trade, models.Trade.account_id == models.Account.id
    ).group_by(
        models.Account.user_id
    ).having(
        func.count(models.Trade.id) >= 5
    ).count()
    
    # С 20+ сделками (power users)
    power_traders = db.query(
        models.Account.user_id
    ).join(
        models.Trade, models.Trade.account_id == models.Account.id
    ).group_by(
        models.Account.user_id
    ).having(
        func.count(models.Trade.id) >= 20
    ).count()
    
    return {
        "steps": [
            {
                "name": "Зарегистрировались",
                "count": total_registered,
                "rate": 100
            },
            {
                "name": "Добавили сделку",
                "count": users_with_trades,
                "rate": round(users_with_trades / total_registered * 100, 1) if total_registered > 0 else 0
            },
            {
                "name": "Активные (5+ сделок)",
                "count": active_traders,
                "rate": round(active_traders / total_registered * 100, 1) if total_registered > 0 else 0
            },
            {
                "name": "Power Users (20+ сделок)",
                "count": power_traders,
                "rate": round(power_traders / total_registered * 100, 1) if total_registered > 0 else 0
            },
        ]
    }


def set_user_admin(db: Session, user_id: int, is_admin: bool) -> models.User:
    """Установить/снять права администратора"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise ValueError("Пользователь не найден")
    
    user.is_admin = 1 if is_admin else 0
    db.commit()
    db.refresh(user)
    return user


def toggle_user_active(db: Session, user_id: int) -> models.User:
    """Активировать/деактивировать пользователя"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise ValueError("Пользователь не найден")
    
    user.is_active = 0 if user.is_active else 1
    db.commit()
    db.refresh(user)
    return user


# ==================== REVENUE & SUBSCRIPTION METRICS ====================

def get_revenue_stats(db: Session) -> dict:
    """Метрики по выручке и платным подпискам"""
    now = utc_now_naive()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_ago = now - timedelta(days=30)
    
    # Всего пользователей и платных
    total_users = db.query(models.User).count()
    
    # Активные платные подписки (не FREE и активные)
    paid_subscriptions = db.query(models.Subscription).filter(
        models.Subscription.is_active == 1,
        models.Subscription.plan != models.SubscriptionPlan.FREE
    ).count()
    
    # Количество подписок по планам
    plan_distribution = db.query(
        models.Subscription.plan,
        func.count(models.Subscription.id).label("count")
    ).filter(
        models.Subscription.is_active == 1
    ).group_by(models.Subscription.plan).all()
    
    plans = {
        "free": 0,
        "pro": 0,
        "corporate": 0
    }
    for plan, count in plan_distribution:
        plans[plan.value] = count
    
    # Выручка за всё время (только COMPLETED)
    total_revenue = db.query(func.sum(models.Payment.amount)).filter(
        models.Payment.status == models.PaymentStatus.COMPLETED
    ).scalar() or 0
    
    # Выручка за текущий месяц
    month_revenue = db.query(func.sum(models.Payment.amount)).filter(
        models.Payment.status == models.PaymentStatus.COMPLETED,
        models.Payment.created_at >= month_ago
    ).scalar() or 0
    
    # Выручка за сегодня
    today_revenue = db.query(func.sum(models.Payment.amount)).filter(
        models.Payment.status == models.PaymentStatus.COMPLETED,
        models.Payment.created_at >= today_start
    ).scalar() or 0
    
    # Количество платежей
    total_payments = db.query(models.Payment).filter(
        models.Payment.status == models.PaymentStatus.COMPLETED
    ).count()
    
    # Средний чек
    avg_payment = float(total_revenue) / total_payments if total_payments > 0 else 0
    
    # Конверсия в платных
    conversion_rate = (paid_subscriptions / total_users * 100) if total_users > 0 else 0
    
    # MRR (Monthly Recurring Revenue)
    # Тарифы для РФ: Pro = 399₽, Corporate = индивидуально (считаем условно 5000₽)
    plan_prices = {"pro": 399, "corporate": 5000}
    mrr = sum(plans.get(plan, 0) * price for plan, price in plan_prices.items())
    
    # ARR
    arr = mrr * 12
    
    # Churn - подписки, которые закончились за последние 30 дней
    churned = db.query(models.Subscription).filter(
        models.Subscription.is_active == 0,
        models.Subscription.expires_at >= month_ago,
        models.Subscription.expires_at < now,
        models.Subscription.plan != models.SubscriptionPlan.FREE
    ).count()
    
    # Churn rate
    churn_rate = (churned / (paid_subscriptions + churned) * 100) if (paid_subscriptions + churned) > 0 else 0
    
    # Новые платные за месяц
    new_paid_this_month = db.query(models.Subscription).filter(
        models.Subscription.started_at >= month_ago,
        models.Subscription.plan != models.SubscriptionPlan.FREE
    ).count()
    
    return {
        "overview": {
            "total_users": total_users,
            "paid_users": paid_subscriptions,
            "free_users": total_users - paid_subscriptions,
            "conversion_rate": round(conversion_rate, 2),
        },
        "revenue": {
            "total": float(total_revenue),
            "this_month": float(month_revenue),
            "today": float(today_revenue),
            "avg_payment": round(avg_payment, 2),
            "mrr": mrr,
            "arr": arr,
        },
        "plans": plans,
        "health": {
            "churn_rate": round(churn_rate, 2),
            "churned_this_month": churned,
            "new_paid_this_month": new_paid_this_month,
            "total_payments": total_payments,
        }
    }


def get_revenue_growth(db: Session, days: int = 30) -> list:
    """График выручки по дням"""
    now = utc_now_naive()
    start_date = now - timedelta(days=days)
    
    results = db.query(
        func.date(models.Payment.created_at).label("date"),
        func.sum(models.Payment.amount).label("amount"),
        func.count(models.Payment.id).label("count")
    ).filter(
        models.Payment.status == models.PaymentStatus.COMPLETED,
        models.Payment.created_at >= start_date
    ).group_by(
        func.date(models.Payment.created_at)
    ).order_by(
        func.date(models.Payment.created_at)
    ).all()
    
    # Кумулятивный рост
    data = []
    cumulative = db.query(func.sum(models.Payment.amount)).filter(
        models.Payment.status == models.PaymentStatus.COMPLETED,
        models.Payment.created_at < start_date
    ).scalar() or 0
    
    for r in results:
        cumulative += float(r.amount or 0)
        date_str = r.date if isinstance(r.date, str) else (r.date.isoformat() if r.date else None)
        data.append({
            "date": date_str,
            "revenue": float(r.amount or 0),
            "payments": r.count,
            "cumulative": float(cumulative)
        })
    
    return data


def get_subscription_analytics(db: Session) -> dict:
    """Аналитика по подпискам"""
    now = utc_now_naive()
    
    # Подписки по методам оплаты
    payment_methods = db.query(
        models.Payment.payment_method,
        func.count(models.Payment.id).label("count"),
        func.sum(models.Payment.amount).label("amount")
    ).filter(
        models.Payment.status == models.PaymentStatus.COMPLETED
    ).group_by(models.Payment.payment_method).all()
    
    # Auto-renew статистика
    auto_renew_enabled = db.query(models.Subscription).filter(
        models.Subscription.is_active == 1,
        models.Subscription.auto_renew == 1,
        models.Subscription.plan != models.SubscriptionPlan.FREE
    ).count()
    
    auto_renew_disabled = db.query(models.Subscription).filter(
        models.Subscription.is_active == 1,
        models.Subscription.auto_renew == 0,
        models.Subscription.plan != models.SubscriptionPlan.FREE
    ).count()
    
    # Подписки, истекающие в ближайшие 7 дней
    week_ahead = now + timedelta(days=7)
    expiring_soon = db.query(models.Subscription).filter(
        models.Subscription.is_active == 1,
        models.Subscription.expires_at.isnot(None),
        models.Subscription.expires_at <= week_ahead,
        models.Subscription.expires_at > now
    ).count()
    
    # LTV примерная оценка (total revenue / paid users)
    total_revenue = db.query(func.sum(models.Payment.amount)).filter(
        models.Payment.status == models.PaymentStatus.COMPLETED
    ).scalar() or 0
    
    paid_users_ever = db.query(func.count(distinct(models.Payment.user_id))).filter(
        models.Payment.status == models.PaymentStatus.COMPLETED
    ).scalar() or 0
    
    ltv = float(total_revenue) / paid_users_ever if paid_users_ever > 0 else 0
    
    return {
        "payment_methods": [
            {
                "method": pm.payment_method or "unknown",
                "count": pm.count,
                "amount": float(pm.amount or 0)
            }
            for pm in payment_methods
        ],
        "auto_renew": {
            "enabled": auto_renew_enabled,
            "disabled": auto_renew_disabled,
            "rate": round(auto_renew_enabled / (auto_renew_enabled + auto_renew_disabled) * 100, 1) if (auto_renew_enabled + auto_renew_disabled) > 0 else 0
        },
        "expiring_soon": expiring_soon,
        "ltv": round(ltv, 2),
        "paying_users_total": paid_users_ever
    }


def get_top_paying_users(db: Session, limit: int = 10) -> list:
    """Топ платящих пользователей"""
    results = db.query(
        models.User,
        func.sum(models.Payment.amount).label("total_paid"),
        func.count(models.Payment.id).label("payments_count")
    ).join(
        models.Payment, models.Payment.user_id == models.User.id
    ).filter(
        models.Payment.status == models.PaymentStatus.COMPLETED
    ).group_by(
        models.User.id
    ).order_by(
        func.sum(models.Payment.amount).desc()
    ).limit(limit).all()
    
    return [
        {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "total_paid": float(total_paid or 0),
            "payments_count": payments_count,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
        }
        for user, total_paid, payments_count in results
    ]
