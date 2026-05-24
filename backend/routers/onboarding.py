"""
PR 26 (Phase 3, D6) — Onboarding reconciliation endpoint.

После первого full sync новый юзер вызывает POST /onboarding/reconcile —
система запускает 3-way reconciliation за последние 30 дней и возвращает
результат для отображения wizard'ом в UI.

Soft warning (по выбору user в Phase 3 plan): даже при breaks юзер
может продолжать пользоваться сервисом, но видит баннер.
"""

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import database
import models
import auth_service
from logger import get_logger
from utils.datetime_utils import utc_now_naive

log = get_logger("onboarding")

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/reconcile")
async def onboarding_reconcile(
    account_id: Optional[int] = Query(None, description="Specific account or all of user"),
    days: int = Query(30, ge=1, le=90),
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db),
):
    """Запускает reconciliation для нового юзера + сохраняет run в БД.

    Trigger='onboarding_wizard'. Используется wizard'ом сразу после
    первого full sync с Tinkoff. Возвращает результат для UI:
    `{ runs: [{run_id, status, breaks_count, metrics, transformation_warnings}] }`.

    Если status != 'ok' — фронт показывает баннер «Найдены расхождения
    с Tinkoff» с CTA «Связаться с поддержкой».
    """
    from services.reconciliation_service import (
        reconcile_account,
        persist_reconciliation_run,
    )

    accounts_query = db.query(models.Account).filter_by(user_id=current_user.id)
    if account_id is not None:
        accounts_query = accounts_query.filter(models.Account.id == account_id)
    accounts = accounts_query.all()
    if not accounts:
        raise HTTPException(status_code=404, detail="no accounts to reconcile")

    period_end = utc_now_naive()
    period_start = period_end - timedelta(days=days)

    runs = []
    for acc in accounts:
        try:
            result = await reconcile_account(
                db,
                acc.id,
                period_start=period_start,
                period_end=period_end,
                fetch_broker_report=True,
                trigger="onboarding_wizard",
            )
            persisted = persist_reconciliation_run(
                db, result, trigger="onboarding_wizard"
            )
            runs.append({
                "run_id": persisted.id,
                "account_id": acc.id,
                "account_name": acc.name,
                "status": result.status,
                "breaks_count": result.breaks_count,
                "hard_breaks_count": result.hard_breaks_count,
                "metrics": [m.to_dict() for m in result.metrics],
                "transformation_warnings": result.transformation_warnings,
            })
        except Exception as exc:
            log.exception("onboarding_reconcile_failed", extra={
                "account_id": acc.id, "user_id": current_user.id,
            })
            runs.append({
                "account_id": acc.id,
                "status": "error",
                "error": str(exc),
            })

    return {
        "user_id": current_user.id,
        "period_days": days,
        "runs": runs,
    }


@router.get("/reconciliation-banner")
def get_reconciliation_banner_status(
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db),
):
    """Используется Header для решения «показать ли ReconciliationBanner».

    Возвращает {"show": bool, "unresolved_breaks": N, "last_run_at": ...}.
    Показываем если есть unresolved breaks с severity=hard в любом из последних
    runs за последние 30 дней.
    """
    from datetime import timedelta as _td

    cutoff = utc_now_naive() - _td(days=30)
    recent_runs = (
        db.query(models.ReconciliationRunORM)
        .filter(
            models.ReconciliationRunORM.user_id == current_user.id,
            models.ReconciliationRunORM.started_at >= cutoff,
        )
        .order_by(models.ReconciliationRunORM.started_at.desc())
        .limit(10)
        .all()
    )

    if not recent_runs:
        return {"show": False, "unresolved_breaks": 0, "last_run_at": None}

    # Считаем unresolved hard breaks
    run_ids = [r.id for r in recent_runs]
    unresolved = (
        db.query(models.ReconciliationBreakORM)
        .filter(
            models.ReconciliationBreakORM.run_id.in_(run_ids),
            models.ReconciliationBreakORM.severity == "hard",
            models.ReconciliationBreakORM.resolved_at.is_(None),
        )
        .count()
    )

    last = recent_runs[0]
    return {
        "show": unresolved > 0 or last.status in {"break", "error"},
        "unresolved_breaks": unresolved,
        "last_run_at": last.started_at.isoformat() if last.started_at else None,
        "last_status": last.status,
    }
