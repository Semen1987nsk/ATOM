"""
Sync scheduler — ВРЕМЕННАЯ ЗАГЛУШКА (PR 0 greenfield rewrite).

Старый scheduler вызывал TinkoffService.sync_trades() для каждого активного
BrokerConnection. Tinkoff-интеграция удалена в PR 0; новый orchestrator
появится в PR 5 (`application/sync/orchestrator.py`).

Чтобы main.py не падал и не пришлось менять lifespan-контракт, оставляем
объект `scheduler` с тем же публичным API, но все методы — no-op, кроме
финализации удалений 152-ФЗ (которая не зависит от брокера и должна
продолжать работать каждые 24 часа).

Activate via settings.BROKER_SYNC_V2_ENABLED — пока False, broker-цикл
полностью отключён.
"""

import asyncio
import traceback
from datetime import datetime, timedelta
from typing import Dict, Optional

from database import SessionLocal, engine
from utils.datetime_utils import utc_now_naive
from logger import get_logger
from config import settings

log = get_logger("sync_scheduler")


class SyncScheduler:
    """No-op scheduler stub on the broker side; PD finalization preserved."""

    def __init__(self) -> None:
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_check: Optional[datetime] = None
        # Сохраняем поле для совместимости с routers/broker.py (он читает is_syncing).
        self._sync_in_progress: Dict[int, bool] = {}
        # S2-16: оркестратор (и его Redis-клиент IpCooldownGate) строим один раз.
        self._orchestrator = None
        self._check_interval = 60
        # 152-ФЗ ст. 21 ч. 5: финализация удалений раз в сутки.
        self._last_pd_finalize_at: Optional[datetime] = None
        self._pd_finalize_interval = timedelta(hours=24)
        # PR 6: refresh справочника инструментов раз в сутки. Сам bootstrap
        # внутри сравнит cached_at с max_age=7 дней — если ещё свежо,
        # вернёт None без запроса к API.
        self._last_instruments_check_at: Optional[datetime] = None
        self._instruments_check_interval = timedelta(hours=24)
        # Phase 10 (2026-05-17): nightly P&L Health Check для ВСЕХ accounts.
        # Дополнительно к post-sync hook'у в pipeline — на случай accounts
        # без активного sync (manual, paused, etc).
        self._last_pnl_health_at: Optional[datetime] = None
        self._pnl_health_interval = timedelta(hours=24)
        # PERF-09 (Sprint 3, 2026-05-26): retention/cleanup для безграничных
        # таблиц (access_log, sync_events, revoked_tokens). Интервал задаётся
        # через settings.RETENTION_CLEANUP_INTERVAL_HOURS (default 24h).
        self._last_retention_run: Optional[datetime] = None
        # MATH-03 (Sprint 4, Task 5.1): nightly safety-net MAE/MFE backfill
        # для трейдов с NULL mae_price. Дополняет inline-расчёт в routers и
        # import-hook — на случай если оба пути пропустили (сбой MOEX, ручной
        # INSERT, etc). Интервал через settings.MAE_MFE_BACKFILL_INTERVAL_HOURS.
        self._last_mae_mfe_backfill_run: Optional[datetime] = None

    async def start(self) -> None:
        """
        Запускает scheduler.

        Под флаг IS_SCHEDULER_WORKER (как и раньше) — на multi-worker деплоях
        broker-цикл должен крутиться ровно на одном воркере. PD-финализация
        тоже одна — она в том же loop.
        """
        from worker_role import is_scheduler_worker

        if not is_scheduler_worker():
            log.info("⏭️ Sync scheduler skipped on this worker (IS_SCHEDULER_WORKER=false)")
            return

        if self._running:
            log.warning("Scheduler already running")
            return

        if not settings.BROKER_SYNC_V2_ENABLED:
            log.info(
                "⏸️ Broker sync v2 disabled (BROKER_SYNC_V2_ENABLED=false). "
                "Tinkoff integration is being rewritten — only PD-finalize loop is running."
            )

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        log.info("🔄 Sync scheduler started (broker sync: stub; pd-finalize: active)")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("⏹️ Sync scheduler stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                # AU14: PostgreSQL advisory lock защищает от дублирования
                # iteration если backend поднят на нескольких worker'ах
                # (uvicorn --workers N или Kubernetes replicas) без явного
                # IS_SCHEDULER_WORKER=false на лишних. На SQLite — no-op
                # (in-process `_running` flag уже защищает).
                if not _acquire_scheduler_lock():
                    log.debug("scheduler.lock_busy_other_worker_active")
                    await asyncio.sleep(self._check_interval)
                    continue
                try:
                    await self._check_pd_finalizations()
                    await self._check_broker_sync()
                    await self._check_instruments_refresh()
                    await self._check_pnl_health_nightly()
                    await self._check_retention_cleanup()
                    await self._check_mae_mfe_backfill()
                    self._last_check = utc_now_naive()
                finally:
                    _release_scheduler_lock()
            except Exception as e:
                log.error(f"Scheduler error: {e}")
                log.error(traceback.format_exc())

            await asyncio.sleep(self._check_interval)

    async def _check_instruments_refresh(self) -> None:
        """
        PR 6: раз в сутки проверяет stale справочник инструментов и при
        необходимости перетягивает его (TTL по умолчанию 7 дней).

        Требует:
        * BROKER_SYNC_V2_ENABLED=true (иначе нет сценария когда справочник
          нужен — pipeline всё равно не работает);
        * Хотя бы одно активное `BrokerConnection` с расшифровываемым токеном.
        """
        if not settings.BROKER_SYNC_V2_ENABLED:
            return
        now = utc_now_naive()
        if self._last_instruments_check_at is not None:
            if now - self._last_instruments_check_at < self._instruments_check_interval:
                return

        # Импорты ленивые — модули могут не быть готовы при первом старте.
        from adapters.security.token_encryption import (
            TokenEncryptionError,
            TokenEncryptionService,
        )
        from adapters.persistence.token_repo import TokenRepository
        from application.sync.instrument_bootstrap import InstrumentBootstrapService
        from models import BrokerConnection, BrokerType

        db = SessionLocal()
        try:
            try:
                encryption = TokenEncryptionService()
            except TokenEncryptionError as exc:
                log.warning("instruments refresh disabled: %s", exc)
                self._last_instruments_check_at = now
                return

            conn = (
                db.query(BrokerConnection)
                .filter(
                    BrokerConnection.is_active.is_(True),
                    BrokerConnection.broker == BrokerType.TINKOFF,
                )
                .first()
            )
            if conn is None:
                self._last_instruments_check_at = now
                return

            try:
                token = encryption.decrypt(conn.api_token) if conn.api_token else None
            except TokenEncryptionError as exc:
                log.warning(
                    "instruments refresh: cannot decrypt token for connection_id=%s: %s",
                    conn.id,
                    exc,
                )
                self._last_instruments_check_at = now
                return
            if not token:
                self._last_instruments_check_at = now
                return
        finally:
            db.close()

        service = InstrumentBootstrapService()
        try:
            report = await service.refresh_if_stale(token)
            if report is None:
                log.debug("instruments cache is fresh, skipping bootstrap")
            else:
                log.info(
                    "instruments refresh: total=%d success=%s duration=%.2fs",
                    report.total,
                    report.success,
                    report.duration_sec,
                )
        except Exception:
            log.exception("instruments refresh failed unexpectedly")
        finally:
            self._last_instruments_check_at = now

    def _get_orchestrator(self):
        # S2-16: строим оркестратор (и его Redis-клиент IpCooldownGate) один раз,
        # переиспользуем между 60с-итерациями. Иначе churn TCP-коннектов к Redis
        # + in-flight bulkhead живёт лишь один прогон.
        if getattr(self, "_orchestrator", None) is None:
            from application.sync.orchestrator import build_default_orchestrator
            self._orchestrator = build_default_orchestrator()
        return self._orchestrator

    async def _check_broker_sync(self) -> None:
        """
        PR 5: запуск Tinkoff sync orchestrator'а под флагом
        BROKER_SYNC_V2_ENABLED. Если флаг выключен или ключ шифрования не
        задан — no-op (старый sync уже удалён в PR 0).
        """
        if not settings.BROKER_SYNC_V2_ENABLED:
            return
        orchestrator = self._get_orchestrator()
        if orchestrator is None:
            return
        try:
            report = await orchestrator.run_due_accounts()
            if report.accounts_considered > 0:
                log.info(
                    "broker sync: considered=%d synced=%d skipped=%d failed=%d",
                    report.accounts_considered,
                    report.accounts_synced,
                    report.accounts_skipped,
                    report.accounts_failed,
                )
        except Exception:
            log.exception("broker sync run failed")

    async def _check_pnl_health_nightly(self) -> None:
        """Phase 10 (2026-05-17): nightly P&L Health Check для всех accounts.

        Дополняет post-sync hook в pipeline (auto-sync accounts получают свежий
        check сразу). Этот loop обеспечивает что **все** accounts (включая
        manual / paused) имеют badge не старше 24h.

        Throttling: batches по 20 accounts, паузы 100ms — для 1000 accounts
        полный цикл ~100s, well within night window.

        Non-fatal: ошибки только логируются.
        """
        now = utc_now_naive()
        if self._last_pnl_health_at is not None:
            if now - self._last_pnl_health_at < self._pnl_health_interval:
                return

        from services import pnl_health_service
        from models import Account

        db = SessionLocal()
        try:
            account_ids = [row[0] for row in db.query(Account.id).all()]
        finally:
            db.close()

        if not account_ids:
            self._last_pnl_health_at = now
            return

        log.info(f"pnl_health_nightly: starting for {len(account_ids)} accounts")
        ok_count = warn_count = mismatch_count = na_count = error_count = 0
        batch_size = 20

        for batch_start in range(0, len(account_ids), batch_size):
            batch = account_ids[batch_start:batch_start + batch_size]
            for aid in batch:
                session = SessionLocal()
                try:
                    result = await asyncio.to_thread(
                        pnl_health_service.compute_and_persist, session, aid
                    )
                    if result.status == "ok":
                        ok_count += 1
                    elif result.status == "warning":
                        warn_count += 1
                    elif result.status == "mismatch":
                        mismatch_count += 1
                    elif result.status == "na":
                        na_count += 1
                except Exception:
                    error_count += 1
                    log.exception(f"pnl_health_nightly: account_id={aid} failed")
                finally:
                    session.close()
            await asyncio.sleep(0.1)  # throttle между батчами

        self._last_pnl_health_at = now
        log.info(
            f"pnl_health_nightly done: ok={ok_count} warn={warn_count} "
            f"mismatch={mismatch_count} na={na_count} errors={error_count}"
        )

    async def _check_retention_cleanup(self) -> None:
        """PERF-09 (Sprint 3, 2026-05-26): cleanup безграничных таблиц.

        Раз в settings.RETENTION_CLEANUP_INTERVAL_HOURS чистим:
          * access_log → старше ACCESS_LOG_RETENTION_DAYS (default 30);
          * sync_events → старше SYNC_EVENTS_RETENTION_DAYS (default 90);
          * revoked_tokens → с expires_at < now (TTL самого токена истёк).

        Defensive: гард is_scheduler_worker() — на случай ручного вызова
        снаружи `_run_loop` (внутри loop уже отсечено start()-гардом).
        Non-fatal: исключения логируются, _last_retention_run сдвигается
        в любом случае, чтобы не зацикливаться при системной ошибке БД.
        """
        from worker_role import is_scheduler_worker

        if not is_scheduler_worker():
            return

        now = utc_now_naive()
        interval = timedelta(hours=settings.RETENTION_CLEANUP_INTERVAL_HOURS)
        if self._last_retention_run is not None:
            if now - self._last_retention_run < interval:
                return

        from jobs import retention as _retention

        try:
            db = SessionLocal()
            try:
                acc = await asyncio.to_thread(
                    _retention.cleanup_access_log,
                    db,
                    retention_days=settings.ACCESS_LOG_RETENTION_DAYS,
                )
                ev = await asyncio.to_thread(
                    _retention.cleanup_sync_events,
                    db,
                    retention_days=settings.SYNC_EVENTS_RETENTION_DAYS,
                )
                tok = await asyncio.to_thread(_retention.cleanup_revoked_tokens, db)
                log.info(
                    "retention cleanup: access_log=%d sync_events=%d revoked_tokens=%d",
                    acc, ev, tok,
                )
            finally:
                db.close()
        except Exception:
            log.exception("retention cleanup failed")
        finally:
            self._last_retention_run = now

    async def _check_mae_mfe_backfill(self) -> None:
        """MATH-03 (Sprint 4, Task 5.1): nightly safety-net для NULL MAE/MFE.

        Раз в settings.MAE_MFE_BACKFILL_INTERVAL_HOURS (default 24h) подметает
        recent (entry_at >= now - MAE_MFE_BACKFILL_MAX_AGE_DAYS) трейды с
        mae_price IS NULL — для случаев когда inline-расчёт в routers/trades.py
        и import-hook оба пропустили (MOEX timeout, ручной INSERT, race).

        Гард is_scheduler_worker() — на multi-worker деплое крутится только
        на одном воркере. Non-fatal: исключения логируются, _last_*_run
        сдвигается в любом случае (иначе hot-loop при системной ошибке БД).
        """
        from worker_role import is_scheduler_worker

        if not is_scheduler_worker():
            return

        now = utc_now_naive()
        interval = timedelta(hours=settings.MAE_MFE_BACKFILL_INTERVAL_HOURS)
        if self._last_mae_mfe_backfill_run is not None:
            if now - self._last_mae_mfe_backfill_run < interval:
                return

        try:
            from jobs.mae_mfe_backfill import backfill_missing_mae_mfe

            db = SessionLocal()
            try:
                report = await backfill_missing_mae_mfe(
                    db,
                    limit=settings.MAE_MFE_BACKFILL_BATCH_LIMIT,
                    max_age_days=settings.MAE_MFE_BACKFILL_MAX_AGE_DAYS,
                )
                log.info(
                    "mae_mfe nightly backfill: processed=%d succeeded=%d failed=%d",
                    report["processed"], report["succeeded"], report["failed"],
                )
            finally:
                db.close()
        except Exception:
            log.exception("mae_mfe nightly backfill failed")
        finally:
            self._last_mae_mfe_backfill_run = now

    async def _check_pd_finalizations(self) -> None:
        """152-ФЗ ст. 21 ч. 5: анонимизация аккаунтов через 30 дней."""
        now = utc_now_naive()
        if self._last_pd_finalize_at is not None:
            if now - self._last_pd_finalize_at < self._pd_finalize_interval:
                return

        from services import pd_deletion

        db = SessionLocal()
        try:
            count = await asyncio.to_thread(pd_deletion.run_pending_deletions, db)
            self._last_pd_finalize_at = now
            if count > 0:
                log.info(f"🗑 PD finalize: {count} accounts anonymized (152-ФЗ)")
            else:
                log.debug("PD finalize: nothing to process")
        except Exception as e:
            log.error(f"PD finalize failed: {e}")
            log.error(traceback.format_exc())
        finally:
            db.close()

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "check_interval_seconds": self._check_interval,
            "syncing_connections": [],
            "last_pd_finalize_at": (
                self._last_pd_finalize_at.isoformat() if self._last_pd_finalize_at else None
            ),
            "broker_sync_v2_enabled": settings.BROKER_SYNC_V2_ENABLED,
            "broker_sync_state": "stub_pending_pr5",
        }

    async def trigger_sync(self, connection_id: int) -> bool:
        """
        Ручной trigger sync для конкретного подключения (для UI / админки).
        Когда BROKER_SYNC_V2_ENABLED=True — делегирует в orchestrator.
        Иначе no-op (старая интеграция удалена в PR 0).
        """
        if not settings.BROKER_SYNC_V2_ENABLED:
            log.info(
                f"trigger_sync({connection_id}) → no-op (BROKER_SYNC_V2_ENABLED=False)"
            )
            return False

        orchestrator = self._get_orchestrator()
        if orchestrator is None:
            return False
        try:
            await orchestrator.sync_one_account(connection_id)
            return True
        except Exception:
            log.exception("trigger_sync failed for connection_id=%s", connection_id)
            return False


# ── AU14: scheduler advisory lock (PostgreSQL only; SQLite — no-op) ─────


# Уникальный 64-bit ключ для pg_try_advisory_lock. Просто constant — он
# должен быть стабилен across deployments чтобы все worker'ы боролись за
# один и тот же lock.
_SCHEDULER_LOCK_KEY = 0x4551494F535953  # "EMPIRIKSYS" в hex
_lock_connection = None  # держим коннект пока lock активен (session-level lock)


def _acquire_scheduler_lock() -> bool:
    """Пытается захватить scheduler advisory lock.

    Возвращает True если lock получен (или БД не поддерживает — SQLite),
    False если другой worker уже держит.

    Используется в `_run_loop` чтобы только один worker делал sync iteration
    одновременно, даже если IS_SCHEDULER_WORKER=true на нескольких.
    """
    global _lock_connection
    try:
        from sqlalchemy import text

        if not engine.dialect.name.startswith("postgres"):
            # SQLite / другая БД — нет advisory locks, надеемся на
            # IS_SCHEDULER_WORKER + in-process flag.
            return True

        conn = engine.connect()
        try:
            result = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _SCHEDULER_LOCK_KEY})
            got = bool(result.scalar())
        except BaseException:
            # Включая CancelledError на shutdown — коннект НЕ должен утечь.
            conn.close()
            raise
        if got:
            _lock_connection = conn   # держим открытым — пока коннект жив, lock наш
            return True
        conn.close()
        return False
    except Exception as exc:
        log.warning("scheduler.advisory_lock_failed: %s — proceeding anyway", exc)
        return True


def _release_scheduler_lock() -> None:
    """Освобождает scheduler advisory lock (close connection)."""
    global _lock_connection
    if _lock_connection is None:
        return
    try:
        from sqlalchemy import text
        _lock_connection.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SCHEDULER_LOCK_KEY})
    except Exception:
        log.exception("scheduler.advisory_unlock_failed (non-blocking)")
    finally:
        try:
            _lock_connection.close()
        except Exception:
            pass
        _lock_connection = None


scheduler = SyncScheduler()
