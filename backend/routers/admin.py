"""
Admin Router — управление пользователями, аналитика, статистика
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from typing import Optional

import database
import models
import schemas
import auth_service
import admin_service
import blog_service
from logger import get_logger
from services.admin_audit import audit_admin_action

log = get_logger("admin")

router = APIRouter(prefix="/admin", tags=["admin"])

# Допустимый набор feature-flag имён. Неизвестные отклоняются, чтобы опечатка
# или будущий код-путь не активировал гейтинг платных фич молча.
ALLOWED_FEATURE_FLAGS = frozenset({"mae-mfe-beta", "trade-replay-beta", "ai-insights-beta"})


def require_admin(current_user: models.User = Depends(auth_service.get_current_user)):
    """Dependency для проверки прав администратора"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Требуются права администратора"
        )
    return current_user


# ==================== STATS ENDPOINTS ====================

@router.get("/stats")
def admin_get_stats(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Основные метрики для дашборда администратора"""
    return admin_service.get_overview_stats(db)


@router.get("/users")
def admin_get_users(
    skip: int = 0,
    limit: int = 50,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    search: Optional[str] = None,
    registration_source: Optional[str] = None,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Список пользователей с фильтрацией и пагинацией"""
    return admin_service.get_users_list(
        db, skip, limit, sort_by, sort_order, search, registration_source
    )


@router.get("/registration-sources")
def admin_get_registration_sources(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Распределение пользователей по источникам регистрации"""
    return admin_service.get_registration_sources(db)


@router.get("/utm-analytics")
def admin_get_utm_analytics(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Аналитика UTM меток"""
    return admin_service.get_utm_analytics(db)


@router.get("/growth")
def admin_get_growth(
    days: int = 30,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """График роста пользователей"""
    return admin_service.get_user_growth(db, days)


@router.get("/cohorts")
def admin_get_cohorts(
    weeks: int = 8,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Когортный анализ retention"""
    return admin_service.get_cohort_retention(db, weeks)


@router.get("/power-users")
def admin_get_power_users(
    limit: int = 20,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Топ активных пользователей"""
    return admin_service.get_power_users(db, limit)


@router.get("/inactive-users")
def admin_get_inactive_users(
    days: int = 30,
    limit: int = 50,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Неактивные пользователи (churn risk)"""
    return admin_service.get_inactive_users(db, days, limit)


@router.get("/funnel")
def admin_get_funnel(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Воронка конверсии"""
    return admin_service.get_conversion_funnel(db)


# ==================== USER MANAGEMENT ====================

@router.post("/users/{user_id}/toggle-admin")
def admin_toggle_admin(
    user_id: int,
    is_admin: bool,
    request: Request,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Установить/снять права администратора. PR 26: audit-logged."""
    try:
        user = admin_service.set_user_admin(db, user_id, is_admin)
        audit_admin_action(
            db,
            actor_user_id=admin.id,
            action="toggle_admin",
            target_user_id=user_id,
            details={"is_admin": is_admin},
            request=request,
        )
        return {"message": f"Права администратора {'выданы' if is_admin else 'отозваны'}", "user_id": user.id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/users/{user_id}/toggle-active")
def admin_toggle_active(
    user_id: int,
    request: Request,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Активировать/деактивировать пользователя. PR 26: audit-logged."""
    try:
        user = admin_service.toggle_user_active(db, user_id)
        audit_admin_action(
            db,
            actor_user_id=admin.id,
            action="toggle_active",
            target_user_id=user_id,
            details={"new_is_active": bool(user.is_active)},
            request=request,
        )
        return {"message": f"Пользователь {'активирован' if user.is_active else 'деактивирован'}", "user_id": user.id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==================== REVENUE ====================

@router.get("/revenue")
def admin_get_revenue(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Метрики по выручке и платным подпискам"""
    return admin_service.get_revenue_stats(db)


@router.get("/revenue-growth")
def admin_get_revenue_growth(
    days: int = 30,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """График выручки по дням"""
    return admin_service.get_revenue_growth(db, days)


@router.get("/subscription-analytics")
def admin_get_subscription_analytics(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Аналитика по подпискам"""
    return admin_service.get_subscription_analytics(db)


@router.get("/top-paying-users")
def admin_get_top_paying_users(
    limit: int = 10,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Топ платящих пользователей"""
    return admin_service.get_top_paying_users(db, limit)


# ==================== 152-ФЗ ADMIN ENDPOINTS ====================

@router.get("/pd-deletions/status", response_model=schemas.PdDeletionsStatusResponse)
def admin_pd_deletions_status(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """
    Статус очереди удалений ПД (152-ФЗ ст. 21 ч. 5).

    Симметрично к юзерскому GET /auth/me/export — даёт оператору видеть
    очередь финализаций. Поле last_scheduler_run_at — когда scheduler
    последний раз пытался обработать pending-аккаунты (полезно для
    диагностики «почему до сих пор pending=N >0»).
    """
    from datetime import timedelta
    from sqlalchemy import func, and_, not_
    from services.pd_deletion import GRACE_PERIOD_DAYS
    from sync_scheduler import scheduler
    from utils.datetime_utils import utc_now_naive

    now = utc_now_naive()
    threshold = now - timedelta(days=GRACE_PERIOD_DAYS)

    # Уже анонимизированные: email вида deleted-{id}@anon.empirik
    finalized_count = db.query(func.count(models.User.id)).filter(
        models.User.email.like("deleted-%@anon.empirik")
    ).scalar() or 0

    # В очереди (deletion_requested_at IS NOT NULL и НЕ анонимизирован)
    pending_q = db.query(models.User).filter(
        and_(
            models.User.deletion_requested_at.isnot(None),
            not_(models.User.email.like("deleted-%@anon.empirik")),
        )
    )
    pending_count = pending_q.count()

    # Overdue: уже истёк grace period, но scheduler ещё не дотронулся
    overdue_count = pending_q.filter(
        models.User.deletion_requested_at <= threshold
    ).count()

    # Ближайшая финализация: min(deletion_requested_at) + 30 дней
    earliest = pending_q.with_entities(
        func.min(models.User.deletion_requested_at)
    ).scalar()
    next_finalization_at = (
        earliest + timedelta(days=GRACE_PERIOD_DAYS) if earliest else None
    )

    return {
        "pending_count": pending_count,
        "overdue_count": overdue_count,
        "finalized_count": finalized_count,
        "grace_period_days": GRACE_PERIOD_DAYS,
        "next_finalization_at": next_finalization_at,
        "last_scheduler_run_at": scheduler._last_pd_finalize_at,
    }


# ==================== ADMIN BLOG ENDPOINTS ====================

@router.get("/articles", tags=["blog"])
def admin_get_all_articles(
    skip: int = 0,
    limit: int = 50,
    category: Optional[str] = None,
    published: Optional[bool] = None,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Получение всех статей (включая черновики) для админа"""
    query = db.query(models.Article)
    
    if category:
        try:
            cat = models.ArticleCategory(category)
            query = query.filter(models.Article.category == cat)
        except ValueError:
            pass
    
    if published is not None:
        query = query.filter(models.Article.is_published == (1 if published else 0))
    
    articles = query.order_by(models.Article.created_at.desc()).offset(skip).limit(limit).all()
    return [blog_service.article_to_response(a, db) for a in articles]


@router.get("/articles/{article_id}", tags=["blog"])
def admin_get_article(
    article_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Получение статьи по ID для редактирования"""
    article = blog_service.get_article_by_id(db, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return blog_service.article_to_response(article, db)


@router.post("/articles", tags=["blog"])
def admin_create_article(
    article_data: schemas.ArticleCreate,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Создание новой статьи"""
    article = blog_service.create_article(db, article_data, admin.id)
    return blog_service.article_to_response(article, db)


@router.put("/articles/{article_id}", tags=["blog"])
def admin_update_article(
    article_id: int,
    article_data: schemas.ArticleUpdate,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Обновление статьи"""
    article = blog_service.update_article(db, article_id, article_data)
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return blog_service.article_to_response(article, db)


@router.delete("/articles/{article_id}", tags=["blog"])
def admin_delete_article(
    article_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Удаление статьи"""
    success = blog_service.delete_article(db, article_id)
    if not success:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return {"message": "Статья удалена"}


@router.post("/articles/{article_id}/publish", tags=["blog"])
def admin_publish_article(
    article_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Публикация статьи"""
    article = blog_service.update_article(db, article_id, schemas.ArticleUpdate(is_published=True))
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return {"message": "Статья опубликована", "published_at": article.published_at}


@router.post("/articles/{article_id}/unpublish", tags=["blog"])
def admin_unpublish_article(
    article_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Снятие статьи с публикации"""
    article = blog_service.update_article(db, article_id, schemas.ArticleUpdate(is_published=False))
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return {"message": "Статья снята с публикации"}


# ==================== SYNC HEALTH (PR 20) ====================


@router.get("/sync-health")
def admin_sync_health_overview(
    status_filter: Optional[str] = Query(None, pattern="^(ok|warning|error)$"),
    limit: int = Query(200, ge=1, le=1000),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """
    PR 20: Все аккаунты с их последним health-check.

    Возвращает: список аккаунтов (sort: error → warning → ok) + summary
    счётчики. Для admin-вкладки «Здоровье синхронизации».
    """
    import hashlib

    from models import (
        Account,
        BrokerConnection,
        SyncHealthCheckORM,
        User,
    )

    # 1) Последний health-check per account (subquery «max(checked_at)»).
    latest_subq = (
        db.query(
            SyncHealthCheckORM.account_id,
            db.query(SyncHealthCheckORM.id)
            .filter(SyncHealthCheckORM.account_id == SyncHealthCheckORM.account_id)
            .order_by(SyncHealthCheckORM.checked_at.desc())
            .limit(1)
            .scalar_subquery()
            .label("latest_id"),
        )
        .distinct()
        .subquery()
    )

    rows = (
        db.query(
            SyncHealthCheckORM,
            Account,
            User,
            BrokerConnection,
        )
        .join(Account, Account.id == SyncHealthCheckORM.account_id)
        .join(User, User.id == Account.user_id)
        .outerjoin(
            BrokerConnection,
            (BrokerConnection.account_id == Account.id)
            & (BrokerConnection.is_active.is_(True)),
        )
        .filter(SyncHealthCheckORM.id.in_(db.query(latest_subq.c.latest_id)))
    )

    if status_filter:
        rows = rows.filter(SyncHealthCheckORM.status == status_filter)

    # Сортировка: сначала error, потом warning, потом ok; внутри — свежайшие.
    severity_order = case(
        {"error": 0, "warning": 1, "ok": 2},
        value=SyncHealthCheckORM.status,
        else_=3,
    )
    rows = rows.order_by(severity_order, SyncHealthCheckORM.checked_at.desc()).limit(limit)

    accounts: list[dict] = []
    summary = {"ok": 0, "warning": 0, "error": 0}
    for hc, account, user, conn in rows.all():
        summary[hc.status] = summary.get(hc.status, 0) + 1
        issues = hc.issues_json or []
        # Хешируем email для приватности в admin-таблице.
        email_hash = hashlib.sha256(
            (user.email or "").encode("utf-8")
        ).hexdigest()[:12]
        accounts.append(
            {
                "account_id": account.id,
                "user_email_hash": email_hash,
                "user_email": user.email,  # admin видит, обычный user — нет.
                "broker_account_id": hc.broker_account_id,
                "checked_at": hc.checked_at.isoformat() if hc.checked_at else None,
                "status": hc.status,
                "total_trades_checked": hc.total_trades_checked,
                "trades_with_issues": hc.trades_with_issues,
                "main_issue": issues[0]["check_id"] if issues else None,
                "issues_count": len(issues),
                "last_sync_at": conn.last_sync_at.isoformat()
                if conn and conn.last_sync_at
                else None,
                "circuit_open_until": conn.circuit_open_until.isoformat()
                if conn and conn.circuit_open_until
                else None,
            }
        )

    # Total accounts с любым health-check (для % здоровых).
    total_accounts = db.query(latest_subq).count()

    return {
        "accounts": accounts,
        "summary": {
            "ok": summary.get("ok", 0),
            "warning": summary.get("warning", 0),
            "error": summary.get("error", 0),
            "total_with_checks": total_accounts,
        },
    }


@router.get("/sync-health/{account_id}")
def admin_sync_health_detail(
    account_id: int,
    request: Request,
    history_days: int = Query(30, ge=1, le=90),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """Полная история health-чеков по аккаунту для drill-down.

    PR 26 security hardening:
    - 404 на несуществующий account_id (раньше возвращал пустой history,
      что позволяло enumeration через timing).
    - Audit log просмотра (admin_audit_log) — кто и когда смотрел чей
      account для compliance.
    """
    from datetime import timedelta
    from models import SyncHealthCheckORM, Account
    from utils.datetime_utils import utc_now_naive

    # PR 26: проверяем что аккаунт существует. 404 не утекает информацию
    # о существовании account_id, потому что 404 одинаков для всех несуществующих.
    account = db.query(Account).filter(Account.id == account_id).first()
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")

    # PR 26: audit просмотра — кто, когда, чьи данные смотрел.
    audit_admin_action(
        db,
        actor_user_id=admin.id,
        action="view_sync_health",
        target_user_id=account.user_id,
        target_account_id=account_id,
        details={"history_days": history_days},
        request=request,
    )

    threshold = utc_now_naive() - timedelta(days=history_days)
    rows = (
        db.query(SyncHealthCheckORM)
        .filter(
            SyncHealthCheckORM.account_id == account_id,
            SyncHealthCheckORM.checked_at >= threshold,
        )
        .order_by(SyncHealthCheckORM.checked_at.desc())
        .all()
    )
    return {
        "account_id": account_id,
        "history": [
            {
                "id": r.id,
                "checked_at": r.checked_at.isoformat() if r.checked_at else None,
                "sync_id": r.sync_id,
                "status": r.status,
                "total_trades_checked": r.total_trades_checked,
                "trades_with_issues": r.trades_with_issues,
                "issues": r.issues_json or [],
            }
            for r in rows
        ],
    }


# ==================== PR 26: USER 360 + IMPERSONATE + AUDIT ====================

@router.get("/users/{user_id}/snapshot")
def admin_user_snapshot(
    user_id: int,
    request: Request,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A1: «User 360» — компактный snapshot пользователя.

    Возвращает: профиль, подписку, все аккаунты, last_sync per account,
    счёт trade'ов, total_pnl, последний health-check, last_login.
    """
    from datetime import timedelta
    from sqlalchemy import func as sa_func

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    audit_admin_action(
        db,
        actor_user_id=admin.id,
        action="view_user_snapshot",
        target_user_id=user_id,
        request=request,
    )

    # Аккаунты юзера + последний sync per broker connection.
    accounts = db.query(models.Account).filter(models.Account.user_id == user_id).all()
    account_summaries = []
    for acc in accounts:
        conn = db.query(models.BrokerConnection).filter(
            models.BrokerConnection.account_id == acc.id,
            models.BrokerConnection.is_active.is_(True),
        ).first()
        trades_count = db.query(sa_func.count(models.Trade.id)).filter(
            models.Trade.account_id == acc.id
        ).scalar() or 0
        pnl_sum = db.query(sa_func.sum(models.Trade.net_pnl)).filter(
            models.Trade.account_id == acc.id,
            models.Trade.exit_at.isnot(None),
        ).scalar()
        positions_count = db.query(sa_func.count(models.PositionORM.id)).filter(
            models.PositionORM.account_id == acc.id,
            models.PositionORM.quantity != 0,
        ).scalar() or 0
        last_health = db.query(models.SyncHealthCheckORM).filter(
            models.SyncHealthCheckORM.account_id == acc.id
        ).order_by(models.SyncHealthCheckORM.checked_at.desc()).first()
        account_summaries.append({
            "id": acc.id,
            "name": acc.name,
            "currency": acc.currency,
            "initial_balance": float(acc.initial_balance or 0),
            "last_portfolio_value": float(acc.last_portfolio_value) if acc.last_portfolio_value else None,
            "last_portfolio_at": acc.last_portfolio_at.isoformat() if acc.last_portfolio_at else None,
            "broker_account_id": conn.broker_account_id if conn else None,
            "last_sync_at": conn.last_sync_at.isoformat() if conn and conn.last_sync_at else None,
            "consecutive_failures": getattr(conn, "consecutive_failures", 0) if conn else 0,
            "trades_count": int(trades_count),
            "net_pnl_total": float(pnl_sum) if pnl_sum else 0,
            "open_positions": int(positions_count),
            "last_health_status": last_health.status if last_health else None,
            "last_health_at": last_health.checked_at.isoformat() if last_health and last_health.checked_at else None,
        })

    subscription = db.query(models.Subscription).filter(
        models.Subscription.user_id == user_id,
        models.Subscription.is_active == 1,
    ).first()

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": getattr(user, "name", None),
            "is_admin": bool(user.is_admin),
            "is_active": bool(user.is_active),
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": user.last_login_at.isoformat() if getattr(user, "last_login_at", None) else None,
            "registration_source": getattr(user, "registration_source", None),
        },
        "subscription": {
            "plan": subscription.plan if subscription else "free",
            "expires_at": subscription.expires_at.isoformat() if subscription and subscription.expires_at else None,
            "auto_renew": getattr(subscription, "auto_renew", False) if subscription else False,
        } if True else None,
        "accounts": account_summaries,
    }


@router.get("/sync-queue")
def admin_sync_queue(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A6: текущая очередь синков — что прямо сейчас выполняется или зависло.

    Это «диагностический» endpoint: видим аккаунты с активным sync (по
    last_sync_at и consecutive_failures) и подозрительно долгие операции.
    """
    from datetime import timedelta
    from utils.datetime_utils import utc_now_naive

    now = utc_now_naive()
    # Активные брокер-соединения с информацией о последнем синке.
    rows = (
        db.query(
            models.BrokerConnection.id.label("conn_id"),
            models.BrokerConnection.account_id,
            models.BrokerConnection.broker_account_id,
            models.BrokerConnection.last_sync_at,
            models.BrokerConnection.consecutive_failures,
            models.BrokerConnection.circuit_open_until,
            models.Account.user_id,
        )
        .join(models.Account, models.Account.id == models.BrokerConnection.account_id)
        .filter(models.BrokerConnection.is_active.is_(True))
        .all()
    )

    stale_threshold = now - timedelta(hours=24)
    circuit_open = []
    stale = []
    healthy = []
    for r in rows:
        entry = {
            "user_id": r.user_id,
            "account_id": r.account_id,
            "broker_account_id": r.broker_account_id,
            "last_sync_at": r.last_sync_at.isoformat() if r.last_sync_at else None,
            "consecutive_failures": r.consecutive_failures or 0,
        }
        if r.circuit_open_until and r.circuit_open_until > now:
            entry["circuit_open_until"] = r.circuit_open_until.isoformat()
            circuit_open.append(entry)
        elif not r.last_sync_at or r.last_sync_at < stale_threshold:
            stale.append(entry)
        else:
            healthy.append(entry)

    return {
        "circuit_open": circuit_open,
        "stale_24h": stale,
        "healthy": healthy,
        "total_active": len(rows),
    }


@router.get("/payments/recent")
def admin_payments_recent(
    limit: int = Query(50, ge=1, le=200),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A9: последние N платежей. Сейчас читаем из Payment-history таблицы
    (если она есть) или возвращаем заглушку. Подключим к PaymentAttemptORM
    когда YooKassa интеграция будет в Phase 0.15."""
    payments_attr = getattr(models, "PaymentAttemptORM", None)
    if payments_attr is None:
        return {"payments": [], "note": "PaymentAttemptORM not yet wired (Phase 0.15)"}

    rows = (
        db.query(payments_attr)
        .order_by(payments_attr.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "payments": [
            {
                "id": p.id,
                "external_id": p.external_id,
                "user_id": p.user_id,
                "amount_rub": float(p.amount_rub) if p.amount_rub else None,
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in rows
        ],
        "count": len(rows),
    }


@router.post("/users/{user_id}/impersonate")
def admin_impersonate(
    user_id: int,
    request: Request,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A11: выпускает short-lived (15min) JWT для имперсонации.

    Использование: support может «войти как пользователь» для отладки.
    JWT содержит claim `impersonated_by` для аудита всех действий.
    """
    from datetime import timedelta

    target = db.query(models.User).filter(models.User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="user not found")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="cannot impersonate yourself")
    if target.is_admin:
        raise HTTPException(status_code=403, detail="cannot impersonate an admin user")

    audit_admin_action(
        db,
        actor_user_id=admin.id,
        action="impersonate",
        target_user_id=user_id,
        details={"target_email": target.email},
        request=request,
    )

    token = auth_service.create_access_token(
        data={
            "sub": str(target.id),
            "email": target.email,
            "impersonated_by": admin.id,
        },
        expires_delta=timedelta(minutes=15),
    )
    return {"access_token": token, "expires_in_minutes": 15, "target_user_id": target.id}


@router.get("/audit-log")
def admin_audit_log(
    actor_user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    target_user_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A12: лог admin actions для compliance.

    Фильтрация по actor, action, target.
    """
    q = db.query(models.AdminAuditLogORM)
    if actor_user_id is not None:
        q = q.filter(models.AdminAuditLogORM.actor_user_id == actor_user_id)
    if action:
        q = q.filter(models.AdminAuditLogORM.action == action)
    if target_user_id is not None:
        q = q.filter(models.AdminAuditLogORM.target_user_id == target_user_id)

    rows = q.order_by(models.AdminAuditLogORM.created_at.desc()).limit(limit).all()
    return {
        "entries": [
            {
                "id": r.id,
                "actor_user_id": r.actor_user_id,
                "action": r.action,
                "target_user_id": r.target_user_id,
                "target_account_id": r.target_account_id,
                "details": r.details,
                "ip_address": r.ip_address,
                "user_agent": r.user_agent,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.post("/users/{user_id}/reset-broker")
def admin_reset_broker(
    user_id: int,
    request: Request,
    account_id: int = Query(..., description="confirm: account_id which is being reset"),
    confirm: int = Query(..., description="should equal account_id"),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A14: сбрасывает данные broker-аккаунта (опасная операция).

    Защита от misuse:
    - account_id и confirm должны совпадать (double-check)
    - account.user_id должен совпадать с user_id
    - Записываем в audit-log ДО выполнения

    Удаляет: trades, positions, operations; сбрасывает sync_cursor,
    consecutive_failures, circuit_open_until.
    """
    if account_id != confirm:
        raise HTTPException(
            status_code=400,
            detail="confirm parameter must equal account_id (sanity check)",
        )

    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    if account.user_id != user_id:
        raise HTTPException(
            status_code=400,
            detail="account does not belong to target user",
        )

    # Audit ДО выполнения — даже если что-то упадёт.
    audit_admin_action(
        db,
        actor_user_id=admin.id,
        action="reset_broker_account",
        target_user_id=user_id,
        target_account_id=account_id,
        request=request,
    )

    # Удаление данных.
    trades_deleted = db.query(models.Trade).filter(
        models.Trade.account_id == account_id
    ).delete(synchronize_session=False)
    positions_deleted = db.query(models.PositionORM).filter(
        models.PositionORM.account_id == account_id
    ).delete(synchronize_session=False)
    operations_deleted = db.query(models.OperationORM).filter(
        models.OperationORM.account_id == account_id
    ).delete(synchronize_session=False)

    # Сброс broker connection state.
    conn = db.query(models.BrokerConnection).filter(
        models.BrokerConnection.account_id == account_id
    ).first()
    if conn:
        conn.sync_cursor = ""
        conn.consecutive_failures = 0
        conn.circuit_open_until = None
        conn.last_sync_at = None

    db.commit()

    log.warning(
        "admin reset_broker: actor=%s target_user=%s account=%s trades=%d positions=%d ops=%d",
        admin.id, user_id, account_id, trades_deleted, positions_deleted, operations_deleted,
    )

    return {
        "ok": True,
        "deleted": {
            "trades": trades_deleted,
            "positions": positions_deleted,
            "operations": operations_deleted,
        },
    }


@router.post("/broker-connections/{connection_id}/stream-toggle")
async def admin_stream_toggle(
    connection_id: int,
    request: Request,
    enabled: bool = Query(..., description="True to start stream, False to stop"),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """AU-stream Phase 1+: включает/выключает real-time push-syncing для
    конкретного BrokerConnection.

    Когда enabled=True:
        1. UPDATE broker_connections SET stream_enabled=True
        2. stream_manager.start_task(connection_id) — поднимает long-lived
           asyncio task, который держит open gRPC stream и push'ит ops
           в режиме real-time.
        3. cursor-based polling продолжает работать как catch-up.

    Когда enabled=False:
        1. stream_manager.stop_task(connection_id) — graceful cancel
        2. UPDATE broker_connections SET stream_enabled=False
        3. cursor-based polling остаётся единственным механизмом sync.

    Все действия в audit-log.
    """
    conn = db.query(models.BrokerConnection).filter_by(id=connection_id).first()
    if conn is None:
        raise HTTPException(status_code=404, detail="broker_connection not found")
    if not conn.is_active:
        raise HTTPException(status_code=400, detail="connection is not active")

    audit_admin_action(
        db,
        actor_user_id=admin.id,
        action=f"stream_toggle_{'enable' if enabled else 'disable'}",
        target_user_id=None,
        target_account_id=conn.account_id,
        request=request,
        details={"connection_id": connection_id, "enabled": enabled},
    )

    # Update DB first; stream_manager сам прочитает stream_enabled при старте
    conn.stream_enabled = bool(enabled)
    db.commit()

    from application.sync.stream_manager import stream_manager
    if enabled:
        await stream_manager.start_task(connection_id)
    else:
        await stream_manager.stop_task(connection_id)

    log.info(
        "admin stream_toggle: actor=%s connection_id=%s enabled=%s",
        admin.id, connection_id, enabled,
    )
    return {
        "ok": True,
        "connection_id": connection_id,
        "stream_enabled": conn.stream_enabled,
        "active_streams_total": stream_manager.active_task_count(),
    }


# ==================== PR 26: PHASE 1 ADMIN ENDPOINTS ====================

@router.get("/users/{user_id}/verify")
async def admin_verify_user(
    user_id: int,
    request: Request,
    account_id: Optional[int] = Query(None),
    skip_live: bool = Query(False, description="Skip Tinkoff API calls"),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A4: запускает verify_user проверки для одного юзера.

    Возвращает JSON с 12 проверками: positions match, balance match,
    operations completeness, FIFO completeness, cursor monotonicity и т.д.
    Полная диагностика для support workflow.
    """
    from services.verify_service import verify_user as _verify

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    audit_admin_action(
        db,
        actor_user_id=admin.id,
        action="run_verify",
        target_user_id=user_id,
        details={"account_id": account_id, "skip_live": skip_live},
        request=request,
    )

    report = await _verify(db, user_id=user_id, account_id=account_id, skip_live=skip_live)
    return report.to_dict()


@router.get("/api-health")
def admin_api_health(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A5: статус Tinkoff API integration.

    Возвращает аггрегированные метрики из token_audit_log + sync_health_checks
    за последние 24 часа: req/min, error rate, 429 count, circuit-open accounts.
    """
    from datetime import timedelta
    from sqlalchemy import func as sa_func
    from utils.datetime_utils import utc_now_naive

    now = utc_now_naive()
    last_24h = now - timedelta(hours=24)

    # Из token_audit_log: distribution status codes за 24h
    by_status = (
        db.query(
            models.TokenAuditLogORM.status_code,
            sa_func.count().label("cnt"),
            sa_func.avg(models.TokenAuditLogORM.latency_ms).label("avg_ms"),
        )
        .filter(models.TokenAuditLogORM.created_at >= last_24h)
        .group_by(models.TokenAuditLogORM.status_code)
        .all()
    )
    total_calls = sum(int(r.cnt) for r in by_status)
    error_calls = sum(int(r.cnt) for r in by_status if r.status_code and r.status_code >= 400)
    rate_429 = sum(int(r.cnt) for r in by_status if r.status_code == 429)

    # Аккаунты с open circuit
    circuit_open = (
        db.query(models.BrokerConnection)
        .filter(
            models.BrokerConnection.is_active.is_(True),
            models.BrokerConnection.circuit_open_until.isnot(None),
            models.BrokerConnection.circuit_open_until > now,
        )
        .count()
    )

    # Distribution: top error endpoints
    error_endpoints = (
        db.query(
            models.TokenAuditLogORM.method,
            sa_func.count().label("cnt"),
        )
        .filter(
            models.TokenAuditLogORM.created_at >= last_24h,
            models.TokenAuditLogORM.status_code >= 400,
        )
        .group_by(models.TokenAuditLogORM.method)
        .order_by(sa_func.count().desc())
        .limit(10)
        .all()
    )

    error_rate = (error_calls / total_calls * 100) if total_calls > 0 else 0

    return {
        "window_hours": 24,
        "total_calls": total_calls,
        "error_calls": error_calls,
        "error_rate_pct": round(error_rate, 2),
        "rate_limited_429": rate_429,
        "circuit_open_accounts": circuit_open,
        "status_distribution": [
            {"code": int(r.status_code) if r.status_code else 0,
             "count": int(r.cnt),
             "avg_latency_ms": int(r.avg_ms) if r.avg_ms else 0}
            for r in by_status
        ],
        "top_error_endpoints": [
            {"method": r.method, "errors": int(r.cnt)} for r in error_endpoints
        ],
    }


@router.get("/db-stats")
def admin_db_stats(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A15: размер БД и счёт строк по основным таблицам."""
    from sqlalchemy import func as sa_func, text

    tables_to_count = [
        ("users", models.User),
        ("accounts", models.Account),
        ("broker_connections", models.BrokerConnection),
        ("trades", models.Trade),
        ("positions", models.PositionORM),
        ("operations", models.OperationORM),
        ("instruments", models.InstrumentORM),
        ("sync_health_checks", models.SyncHealthCheckORM),
        ("admin_audit_log", models.AdminAuditLogORM),
        ("revoked_tokens", models.RevokedTokenORM),
        ("payment_attempts", models.PaymentAttemptORM),
        ("subscriptions", models.Subscription),
        ("payments", models.Payment),
    ]
    counts = {}
    for name, orm in tables_to_count:
        try:
            counts[name] = db.query(sa_func.count()).select_from(orm).scalar() or 0
        except Exception:
            counts[name] = None

    # DB size — Postgres-specific, fallback для SQLite
    db_size_bytes = None
    db_type = "unknown"
    try:
        from database import IS_POSTGRES, IS_SQLITE
        if IS_POSTGRES:
            db_type = "postgresql"
            result = db.execute(text("SELECT pg_database_size(current_database())")).scalar()
            db_size_bytes = int(result) if result else None
        elif IS_SQLITE:
            db_type = "sqlite"
            import os
            from config import settings
            db_path = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
            if os.path.exists(db_path):
                db_size_bytes = os.path.getsize(db_path)
    except Exception:
        pass

    return {
        "db_type": db_type,
        "db_size_bytes": db_size_bytes,
        "db_size_mb": round(db_size_bytes / 1024 / 1024, 2) if db_size_bytes else None,
        "row_counts": counts,
    }


@router.get("/slo")
def admin_slo(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A19: SLO дашборд — readiness uptime %, p95 sync duration, success rate."""
    from datetime import timedelta
    from sqlalchemy import func as sa_func
    from utils.datetime_utils import utc_now_naive

    now = utc_now_naive()
    last_7d = now - timedelta(days=7)

    # Sync success rate из SyncHealthCheckORM
    total = (
        db.query(sa_func.count())
        .select_from(models.SyncHealthCheckORM)
        .filter(models.SyncHealthCheckORM.checked_at >= last_7d)
        .scalar() or 0
    )
    ok_count = (
        db.query(sa_func.count())
        .select_from(models.SyncHealthCheckORM)
        .filter(
            models.SyncHealthCheckORM.checked_at >= last_7d,
            models.SyncHealthCheckORM.status == "ok",
        )
        .scalar() or 0
    )
    error_count = (
        db.query(sa_func.count())
        .select_from(models.SyncHealthCheckORM)
        .filter(
            models.SyncHealthCheckORM.checked_at >= last_7d,
            models.SyncHealthCheckORM.status == "error",
        )
        .scalar() or 0
    )

    sync_success_rate = (ok_count / total * 100) if total > 0 else 100.0

    # p95 latency Tinkoff API (last 24h)
    latencies = (
        db.query(models.TokenAuditLogORM.latency_ms)
        .filter(
            models.TokenAuditLogORM.created_at >= now - timedelta(hours=24),
            models.TokenAuditLogORM.status_code < 400,
        )
        .order_by(models.TokenAuditLogORM.latency_ms.asc())
        .all()
    )
    p50_ms = p95_ms = p99_ms = None
    if latencies:
        sorted_ms = sorted(int(r.latency_ms) for r in latencies)
        n = len(sorted_ms)
        p50_ms = sorted_ms[int(n * 0.50)]
        p95_ms = sorted_ms[min(int(n * 0.95), n - 1)]
        p99_ms = sorted_ms[min(int(n * 0.99), n - 1)]

    return {
        "window_7d": {
            "sync_total": int(total),
            "sync_ok": int(ok_count),
            "sync_error": int(error_count),
            "sync_success_rate_pct": round(sync_success_rate, 2),
        },
        "tinkoff_latency_24h_ms": {
            "p50": p50_ms,
            "p95": p95_ms,
            "p99": p99_ms,
            "samples": len(latencies),
        },
    }


@router.get("/users/{user_id}/accounts")
def admin_user_accounts(
    user_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A2: детали всех аккаунтов юзера — для drill-down в support."""
    from sqlalchemy import func as sa_func

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    rows = []
    for acc in db.query(models.Account).filter(models.Account.user_id == user_id).all():
        conn = db.query(models.BrokerConnection).filter(
            models.BrokerConnection.account_id == acc.id
        ).first()
        trades_count = db.query(sa_func.count(models.Trade.id)).filter(
            models.Trade.account_id == acc.id
        ).scalar() or 0
        ops_count = db.query(sa_func.count(models.OperationORM.id)).filter(
            models.OperationORM.account_id == acc.id
        ).scalar() or 0
        rows.append({
            "account_id": acc.id,
            "name": acc.name,
            "currency": acc.currency,
            "initial_balance": float(acc.initial_balance or 0),
            "last_portfolio_value": float(acc.last_portfolio_value) if acc.last_portfolio_value else None,
            "last_portfolio_at": acc.last_portfolio_at.isoformat() if acc.last_portfolio_at else None,
            "broker": {
                "broker_account_id": conn.broker_account_id if conn else None,
                "is_active": bool(conn.is_active) if conn else False,
                "sync_cursor": (conn.sync_cursor[:32] + "...") if conn and conn.sync_cursor and len(conn.sync_cursor) > 32 else (conn.sync_cursor if conn else None),
                "last_sync_at": conn.last_sync_at.isoformat() if conn and conn.last_sync_at else None,
                "consecutive_failures": getattr(conn, "consecutive_failures", 0) if conn else 0,
                "circuit_open_until": conn.circuit_open_until.isoformat() if conn and conn.circuit_open_until else None,
            } if conn else None,
            "stats": {
                "trades": int(trades_count),
                "operations": int(ops_count),
            },
        })
    return {"user_id": user_id, "accounts": rows}


@router.get("/rate-limits/status")
def admin_rate_limit_status(
    admin: models.User = Depends(require_admin),
):
    """A8: статус rate-limiter'а."""
    from rate_limiter import limiter, RATE_LIMIT_STORAGE_URI
    from config import settings as _settings
    return {
        "enabled": _settings.RATE_LIMIT_ENABLED,
        "backend": "redis" if RATE_LIMIT_STORAGE_URI else "in-memory",
        "storage_uri": (RATE_LIMIT_STORAGE_URI.split("@")[-1] if RATE_LIMIT_STORAGE_URI and "@" in RATE_LIMIT_STORAGE_URI else (RATE_LIMIT_STORAGE_URI or None)),
        "strategy": _settings.RATE_LIMIT_STRATEGY,
        "trusted_proxies": len(getattr(_settings, "TRUSTED_PROXY_NETWORKS", []) or []),
    }


@router.get("/payments/discrepancies")
def admin_payments_discrepancies(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A10: расхождения между Subscription и PaymentAttemptORM.

    Категории:
    - active_no_payment: PRO/CORPORATE подписка без записи в payment_attempts
    - payment_no_subscription: успешный платёж без активной подписки
    """
    from sqlalchemy import or_, and_

    # 1. Active paid subs
    active_paid_subs = (
        db.query(models.Subscription)
        .filter(
            models.Subscription.is_active == 1,
            models.Subscription.plan.in_([models.SubscriptionPlan.PRO, models.SubscriptionPlan.CORPORATE]),
        )
        .all()
    )

    paid_user_ids = {s.user_id for s in active_paid_subs}
    paid_users_with_payment = {
        r.user_id for r in db.query(models.PaymentAttemptORM.user_id)
            .filter(models.PaymentAttemptORM.status == "succeeded")
            .distinct()
            .all()
    }
    active_no_payment = sorted(paid_user_ids - paid_users_with_payment)

    # 2. Succeeded payments без active sub
    succeeded_payments = (
        db.query(models.PaymentAttemptORM.user_id, models.PaymentAttemptORM.external_id)
        .filter(models.PaymentAttemptORM.status == "succeeded")
        .all()
    )
    payment_no_subscription = []
    for user_id, ext_id in succeeded_payments:
        has_active = db.query(models.Subscription).filter(
            models.Subscription.user_id == user_id,
            models.Subscription.is_active == 1,
        ).first()
        if not has_active:
            payment_no_subscription.append({"user_id": user_id, "external_id": ext_id})

    return {
        "active_no_payment": active_no_payment,
        "payment_no_subscription": payment_no_subscription[:50],
        "total_paid_subs": len(active_paid_subs),
    }


@router.get("/users/{user_id}/sync-timeline")
def admin_user_sync_timeline(
    user_id: int,
    days: int = Query(7, ge=1, le=90),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A3: timeline всех sync events юзера за N дней.

    Источник — `sync_events` (PR 26 Phase 1). Каждая запись — попытка
    sync (success/failed/interrupted/timeout) с длительностью, cursor,
    количеством операций.
    """
    from datetime import timedelta
    from utils.datetime_utils import utc_now_naive

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    threshold = utc_now_naive() - timedelta(days=days)
    account_ids = [a.id for a in db.query(models.Account).filter(
        models.Account.user_id == user_id
    ).all()]
    if not account_ids:
        return {"user_id": user_id, "events": []}

    events = (
        db.query(models.SyncEventORM)
        .filter(
            models.SyncEventORM.account_id.in_(account_ids),
            models.SyncEventORM.started_at >= threshold,
        )
        .order_by(models.SyncEventORM.started_at.desc())
        .limit(500)
        .all()
    )
    return {
        "user_id": user_id,
        "window_days": days,
        "events": [
            {
                "id": e.id,
                "account_id": e.account_id,
                "sync_id": e.sync_id,
                "started_at": e.started_at.isoformat() if e.started_at else None,
                "finished_at": e.finished_at.isoformat() if e.finished_at else None,
                "duration_ms": e.duration_ms,
                "status": e.status,
                "pages_fetched": e.pages_fetched,
                "operations_new_or_updated": e.operations_new_or_updated,
                "trades_built": e.trades_built,
                "error_type": e.error_type,
                "error_message": e.error_message,
            }
            for e in events
        ],
    }


@router.get("/errors/recent")
def admin_errors_recent(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(50, ge=1, le=200),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A7: последние ошибки приложения за N часов.

    Источник — access_log (PR 26 Phase 2): берём 4xx/5xx запросы с
    request_id для воспроизведения через Sentry.

    Top errors сгруппированы по path для быстрого scan.
    """
    from datetime import timedelta
    from sqlalchemy import func as sa_func
    from utils.datetime_utils import utc_now_naive

    threshold = utc_now_naive() - timedelta(hours=hours)

    # Recent errors raw
    recent = (
        db.query(models.AccessLogORM)
        .filter(
            models.AccessLogORM.created_at >= threshold,
            models.AccessLogORM.status_code >= 400,
        )
        .order_by(models.AccessLogORM.created_at.desc())
        .limit(limit)
        .all()
    )

    # Aggregated by (path, status)
    aggregated = (
        db.query(
            models.AccessLogORM.path,
            models.AccessLogORM.status_code,
            sa_func.count().label("cnt"),
        )
        .filter(
            models.AccessLogORM.created_at >= threshold,
            models.AccessLogORM.status_code >= 400,
        )
        .group_by(models.AccessLogORM.path, models.AccessLogORM.status_code)
        .order_by(sa_func.count().desc())
        .limit(20)
        .all()
    )

    return {
        "window_hours": hours,
        "recent": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "method": r.method,
                "path": r.path,
                "status_code": r.status_code,
                "duration_ms": r.duration_ms,
                "request_id": r.request_id,
                "ip_address": r.ip_address,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent
        ],
        "top_by_path": [
            {"path": r.path, "status": int(r.status_code), "count": int(r.cnt)}
            for r in aggregated
        ],
    }


@router.get("/pd-deletions/list")
def admin_pd_deletions_list(
    status_filter: Optional[str] = Query(None, pattern="^(pending|overdue|finalized)$"),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A17: drill-down PD deletions — список юзеров pending/overdue/finalized.

    Phase 1 endpoint /admin/pd-deletions/status возвращал только counts;
    A17 даёт actual список для review.
    """
    from datetime import timedelta
    from utils.datetime_utils import utc_now_naive

    now = utc_now_naive()
    grace_threshold = now - timedelta(days=30)

    q = db.query(models.User).filter(models.User.deletion_requested_at.isnot(None))
    pending = []
    overdue = []
    finalized = []
    for u in q.order_by(models.User.deletion_requested_at.desc()).limit(500).all():
        is_anonymized = u.email.endswith("@anon.empirik")
        entry = {
            "user_id": u.id,
            "email": u.email if not is_anonymized else "[anonymized]",
            "deletion_requested_at": u.deletion_requested_at.isoformat() if u.deletion_requested_at else None,
            "is_anonymized": is_anonymized,
        }
        if is_anonymized:
            finalized.append(entry)
        elif u.deletion_requested_at and u.deletion_requested_at < grace_threshold:
            overdue.append(entry)
        else:
            pending.append(entry)

    response = {"pending": pending, "overdue": overdue, "finalized": finalized}
    if status_filter:
        return {status_filter: response[status_filter]}
    return response


@router.get("/users/{user_id}/feature-flags")
def admin_get_feature_flags(
    user_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A18: текущие feature flags юзера."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    rows = db.query(models.FeatureFlagORM).filter(
        models.FeatureFlagORM.user_id == user_id
    ).all()
    return {
        "user_id": user_id,
        "flags": {r.flag_name: r.enabled for r in rows},
    }


@router.patch("/users/{user_id}/feature-flags")
def admin_set_feature_flags(
    user_id: int,
    request: Request,
    flags: dict[str, bool],
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A18: установить feature flags юзера. Body: {"mae-mfe-beta": true, ...}."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    unknown = set(flags) - ALLOWED_FEATURE_FLAGS
    if unknown:
        log.warning("admin_set_feature_flags: unknown flags rejected: %s", unknown)
        audit_admin_action(
            db,
            actor_user_id=admin.id,
            action="set_feature_flags_rejected",
            target_user_id=user_id,
            details={"unknown_flags": sorted(unknown)},
            request=request,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестные feature-флаги: {', '.join(sorted(unknown))}",
        )

    for flag_name, enabled in flags.items():
        existing = db.query(models.FeatureFlagORM).filter(
            models.FeatureFlagORM.user_id == user_id,
            models.FeatureFlagORM.flag_name == flag_name,
        ).first()
        if existing:
            existing.enabled = bool(enabled)
        else:
            db.add(models.FeatureFlagORM(
                user_id=user_id,
                flag_name=flag_name[:64],
                enabled=bool(enabled),
            ))
            try:
                db.commit()
            except IntegrityError:
                # TOCTOU: concurrent PATCH инсертнул ту же (user_id, flag_name)
                # между нашим SELECT и INSERT — откатываемся и делаем UPDATE.
                db.rollback()
                existing = db.query(models.FeatureFlagORM).filter(
                    models.FeatureFlagORM.user_id == user_id,
                    models.FeatureFlagORM.flag_name == flag_name,
                ).first()
                existing.enabled = bool(enabled)
    db.commit()

    audit_admin_action(
        db,
        actor_user_id=admin.id,
        action="set_feature_flags",
        target_user_id=user_id,
        details={"flags": flags},
        request=request,
    )
    return {"ok": True, "flags": flags}


@router.get("/users/{user_id}/access-log")
def admin_user_access_log(
    user_id: int,
    limit: int = Query(100, ge=1, le=500),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A20: последние HTTP requests юзера (sampled 10% + все ошибки)."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    rows = (
        db.query(models.AccessLogORM)
        .filter(models.AccessLogORM.user_id == user_id)
        .order_by(models.AccessLogORM.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "user_id": user_id,
        "entries": [
            {
                "method": r.method,
                "path": r.path,
                "status_code": r.status_code,
                "duration_ms": r.duration_ms,
                "request_id": r.request_id,
                "ip_address": r.ip_address,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.get("/backups/status")
def admin_backups_status(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A16: статус backup'ов — читаем `backup_runs` (PR 26 Phase 3) + fallback
    на filesystem listing если таблица пуста (для legacy-deploy'ев)."""
    import os
    from pathlib import Path
    from datetime import datetime as _dt

    backup_dir = os.getenv("BACKUP_DIR", "/var/lib/empirik/backups")

    # 1. Сначала пытаемся читать из БД (backup_runs)
    db_rows = (
        db.query(models.BackupRunORM)
        .order_by(models.BackupRunORM.started_at.desc())
        .limit(20)
        .all()
    )
    db_entries = [
        {
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "status": r.status,
            "kind": r.kind,
            "filename": r.filename,
            "size_bytes": r.size_bytes,
            "size_mb": round(r.size_bytes / 1024 / 1024, 2) if r.size_bytes else None,
            "s3_uploaded": bool(r.s3_uploaded),
            "error_message": r.error_message,
        }
        for r in db_rows
    ]

    # 2. Last restore-test status (для UI badge)
    last_restore_test = (
        db.query(models.BackupRunORM)
        .filter(models.BackupRunORM.kind == "restore_test")
        .order_by(models.BackupRunORM.started_at.desc())
        .first()
    )
    last_backup = (
        db.query(models.BackupRunORM)
        .filter(models.BackupRunORM.kind == "nightly_backup",
                models.BackupRunORM.status == "success")
        .order_by(models.BackupRunORM.started_at.desc())
        .first()
    )

    # 3. Fallback: если в БД ничего нет, листим файлы (legacy)
    fs_entries = []
    p = Path(backup_dir)
    if p.exists():
        files = sorted(p.glob("empirik-*.sql.gz"), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files[:20]:
            st = f.stat()
            fs_entries.append({
                "filename": f.name,
                "size_bytes": st.st_size,
                "size_mb": round(st.st_size / 1024 / 1024, 2),
                "created_at": _dt.utcfromtimestamp(st.st_mtime).isoformat(),
            })

    return {
        "backup_dir": backup_dir,
        "exists": p.exists(),
        "from_db": db_entries,
        "from_filesystem": fs_entries,
        "last_backup": {
            "filename": last_backup.filename if last_backup else None,
            "started_at": last_backup.started_at.isoformat() if last_backup and last_backup.started_at else None,
            "size_mb": round(last_backup.size_bytes / 1024 / 1024, 2) if last_backup and last_backup.size_bytes else None,
        } if last_backup else None,
        "last_restore_test": {
            "status": last_restore_test.status if last_restore_test else None,
            "started_at": last_restore_test.started_at.isoformat() if last_restore_test and last_restore_test.started_at else None,
        } if last_restore_test else None,
    }


# ════════════════════════════════════════════════════════════════════════
# PR 26 (Phase 3) — Reconciliation endpoints (A21/A22/A23)
# ════════════════════════════════════════════════════════════════════════


@router.get("/users/{user_id}/reconciliation")
def admin_list_reconciliation_runs(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A21: список последних reconciliation runs для юзера.

    Используется в User-360 Reconciliation tab. Возвращает по убыванию
    started_at, без deep deserialization metrics (для краткости).
    """
    user = db.query(models.User).filter_by(id=user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    runs = (
        db.query(models.ReconciliationRunORM)
        .filter(models.ReconciliationRunORM.user_id == user_id)
        .order_by(models.ReconciliationRunORM.started_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "user_id": user_id,
        "runs": [
            {
                "id": r.id,
                "account_id": r.account_id,
                "period_start": r.period_start.isoformat() if r.period_start else None,
                "period_end": r.period_end.isoformat() if r.period_end else None,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "status": r.status,
                "breaks_count": r.breaks_count,
                "mode": r.mode,
                "trigger": r.trigger,
                "error_message": r.error_message,
            }
            for r in runs
        ],
    }


@router.get("/reconciliation/{run_id}")
def admin_get_reconciliation_run(
    run_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A22: drill-down одного reconciliation run.

    Возвращает все 8 метрик + список breaks + полный JSON metrics.
    """
    run = db.query(models.ReconciliationRunORM).filter_by(id=run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    breaks = (
        db.query(models.ReconciliationBreakORM)
        .filter_by(run_id=run_id)
        .all()
    )

    # PR 26 (Phase 3) — прогоняем transformation_audit заново для этого
    # account_id. Это pure SQL queries (T1-T8), занимает доли секунды.
    # transformation_warnings НЕ сохраняются в БД с run'ом, чтобы они
    # всегда отражали ТЕКУЩЕЕ состояние данных (а не slogan на момент run).
    transformation_warnings: list[dict] = []
    try:
        from services.transformation_audit import audit_account
        warnings = audit_account(db, run.account_id)
        transformation_warnings = [w.to_dict() for w in warnings]
    except Exception:
        log.exception("transformation_audit_failed_in_drilldown",
                      extra={"run_id": run_id, "account_id": run.account_id})

    # Если broker_value=0 у ВСЕХ финансовых метрик — это значит broker_report
    # не загрузился (token decrypt fail или Tinkoff API сбой). Помечаем это
    # явно чтобы юзер не путал ложные breaks с реальными.
    broker_report_loaded = False
    if isinstance(run.metrics, dict):
        non_zero_broker = sum(
            1 for m in run.metrics.values()
            if isinstance(m, dict) and m.get("broker") not in (None, "0", "0.0", "")
        )
        broker_report_loaded = non_zero_broker > 0

    return {
        "id": run.id,
        "user_id": run.user_id,
        "account_id": run.account_id,
        "period_start": run.period_start.isoformat() if run.period_start else None,
        "period_end": run.period_end.isoformat() if run.period_end else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "status": run.status,
        "breaks_count": run.breaks_count,
        "mode": run.mode,
        "trigger": run.trigger,
        "error_message": run.error_message,
        "metrics": run.metrics or {},
        "broker_report_loaded": broker_report_loaded,
        "transformation_warnings": transformation_warnings,
        "breaks": [
            {
                "id": b.id,
                "metric": b.metric,
                "our_value": str(b.our_value) if b.our_value is not None else None,
                "broker_value": str(b.broker_value) if b.broker_value is not None else None,
                "diff_abs": str(b.diff_abs) if b.diff_abs is not None else None,
                "diff_pct": str(b.diff_pct) if b.diff_pct is not None else None,
                "severity": b.severity,
                "note": b.note,
                "resolved_at": b.resolved_at.isoformat() if b.resolved_at else None,
                "resolved_by_user_id": b.resolved_by_user_id,
                "resolution_note": b.resolution_note,
            }
            for b in breaks
        ],
    }


@router.post("/users/{user_id}/reconciliation/run")
async def admin_run_reconciliation(
    user_id: int,
    request: Request,
    account_id: Optional[int] = Query(None),
    days: int = Query(30, ge=1, le=31, description="Max 31 — T-Bank broker_report API limit (ERR-113)"),
    skip_broker_report: bool = Query(False),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """A23: запуск reconciliation немедленно.

    Параметры:
    - account_id: если задан — только этот аккаунт; иначе все аккаунты юзера
    - days: период reconciliation (по умолчанию 30 дней)
    - skip_broker_report: пропустить fetch broker report (для быстрой проверки invariants only)

    Audit-logged. Возвращает список созданных run_id для drill-down.
    """
    from datetime import datetime as _dt, timedelta as _td
    from services.reconciliation_service import (
        reconcile_account,
        persist_reconciliation_run,
    )
    from utils.datetime_utils import utc_now_naive

    user = db.query(models.User).filter_by(id=user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    audit_admin_action(
        db,
        actor_user_id=admin.id,
        action="run_reconciliation",
        target_user_id=user_id,
        details={
            "account_id": account_id,
            "days": days,
            "skip_broker_report": skip_broker_report,
        },
        request=request,
    )

    # Найти аккаунты для reconciliation
    accounts_query = db.query(models.Account).filter_by(user_id=user_id)
    if account_id is not None:
        accounts_query = accounts_query.filter(models.Account.id == account_id)
    accounts = accounts_query.all()
    if not accounts:
        raise HTTPException(status_code=404, detail="no accounts for user")

    period_end = utc_now_naive()
    period_start = period_end - _td(days=days)

    runs_created = []
    for acc in accounts:
        try:
            result = await reconcile_account(
                db,
                acc.id,
                period_start=period_start,
                period_end=period_end,
                fetch_broker_report=not skip_broker_report,
                trigger="admin_manual",
            )
            persisted = persist_reconciliation_run(db, result, trigger="admin_manual")
            runs_created.append({
                "run_id": persisted.id,
                "account_id": acc.id,
                "status": result.status,
                "breaks_count": result.breaks_count,
                "transformation_warnings": len(result.transformation_warnings),
            })
        except Exception as exc:
            log.exception("admin_reconciliation_failed", extra={"account_id": acc.id})
            runs_created.append({
                "account_id": acc.id,
                "status": "error",
                "error": str(exc),
            })

    return {"user_id": user_id, "runs": runs_created}


# ==================== PHASE 10: P&L HEALTH CHECK ====================

@router.get("/pnl-health")
def admin_pnl_health(
    skip: int = 0,
    limit: int = 50,
    status_filter: Optional[str] = Query(None, description="ok|warning|mismatch|na|stale"),
    sort: str = Query("diff_pct_desc", description="diff_pct_desc|diff_pct_asc|checked_at_desc"),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """Phase 10 (2026-05-17): paginated список всех accounts + их P&L Health status.

    FAST: читает только cached `Account.last_pnl_health_*` columns — O(1) per row.
    Для 1000+ accounts работает за < 100ms.

    Query params:
      - skip/limit: pagination
      - status_filter: фильтр по конкретному статусу
      - sort: diff_pct_desc (default — самые проблемные сверху)

    Returns:
      {
        accounts: [{account_id, user_id, user_email, status, diff_pct, diff_rub, checked_at, ...}],
        summary: {ok: N, warning: M, mismatch: K, na: L, stale: O, total: T},
        skip, limit, total
      }
    """
    from services.pnl_health_service import is_stale, STALE_AFTER_DAYS

    # Summary counts (efficient — single GROUP BY).
    summary_rows = (
        db.query(
            models.Account.last_pnl_health_status,
            func.count(models.Account.id),
        )
        .group_by(models.Account.last_pnl_health_status)
        .all()
    )
    summary = {"ok": 0, "warning": 0, "mismatch": 0, "na": 0, "stale": 0, "null": 0}
    for status, cnt in summary_rows:
        if status is None:
            summary["null"] += cnt
            summary["stale"] += cnt  # NULL == not yet checked == stale в UI
        elif status in summary:
            summary[status] += cnt

    # Effective status: NULL → stale.
    # SQLAlchemy case() для status маппинга.
    effective_status = case(
        (models.Account.last_pnl_health_status.is_(None), "stale"),
        else_=models.Account.last_pnl_health_status,
    )

    q = db.query(
        models.Account,
        models.User.email,
        models.User.id.label("user_id"),
    ).join(models.User, models.User.id == models.Account.user_id)

    if status_filter:
        if status_filter == "stale":
            # Filter for stale: NULL OR старее N дней
            from datetime import timedelta
            from utils.datetime_utils import utc_now_naive
            cutoff = utc_now_naive() - timedelta(days=STALE_AFTER_DAYS)
            q = q.filter(
                (models.Account.last_pnl_health_at.is_(None)) |
                (models.Account.last_pnl_health_at < cutoff)
            )
        else:
            q = q.filter(models.Account.last_pnl_health_status == status_filter)

    # Sort
    if sort == "diff_pct_desc":
        q = q.order_by(
            func.coalesce(func.abs(models.Account.last_pnl_health_diff_pct), 0).desc()
        )
    elif sort == "diff_pct_asc":
        q = q.order_by(
            func.coalesce(func.abs(models.Account.last_pnl_health_diff_pct), 0).asc()
        )
    elif sort == "checked_at_desc":
        q = q.order_by(models.Account.last_pnl_health_at.desc().nullslast())

    total = q.count()
    rows = q.offset(skip).limit(limit).all()

    accounts_out = []
    for account, email, user_id in rows:
        stale_now = is_stale(account)
        effective = "stale" if stale_now else (account.last_pnl_health_status or "stale")
        accounts_out.append({
            "account_id": account.id,
            "account_name": account.name,
            "user_id": user_id,
            "user_email": email,
            "status": effective,
            "diff_pct": float(account.last_pnl_health_diff_pct) if account.last_pnl_health_diff_pct is not None else None,
            "diff_rub": float(account.last_pnl_health_diff_rub) if account.last_pnl_health_diff_rub is not None else None,
            "checked_at": account.last_pnl_health_at.isoformat() if account.last_pnl_health_at else None,
            "currency": account.currency,
            "last_portfolio_value": float(account.last_portfolio_value) if account.last_portfolio_value is not None else None,
        })

    return {
        "accounts": accounts_out,
        "summary": summary,
        "skip": skip,
        "limit": limit,
        "total": total,
    }


@router.post("/pnl-health/{account_id}/refresh")
def admin_refresh_pnl_health(
    account_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """Phase 10: ручной запуск health check для конкретного аккаунта (admin)."""
    from services import pnl_health_service

    account = db.get(models.Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    result = pnl_health_service.compute_and_persist(db, account_id)
    return result.to_breakdown_json()


@router.get("/pnl-health/{account_id}")
def admin_pnl_health_detail(
    account_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    """Phase 10: drill-down breakdown для одного аккаунта (читает cached)."""
    account = db.get(models.Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    user = db.get(models.User, account.user_id)
    return {
        "account_id": account_id,
        "account_name": account.name,
        "user_id": account.user_id,
        "user_email": user.email if user else None,
        "status": account.last_pnl_health_status or "stale",
        "diff_pct": float(account.last_pnl_health_diff_pct) if account.last_pnl_health_diff_pct is not None else None,
        "diff_rub": float(account.last_pnl_health_diff_rub) if account.last_pnl_health_diff_rub is not None else None,
        "checked_at": account.last_pnl_health_at.isoformat() if account.last_pnl_health_at else None,
        "breakdown": account.last_pnl_health_breakdown,
    }
