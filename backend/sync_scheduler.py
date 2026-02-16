"""
Фоновый планировщик для автоматической синхронизации с брокерами
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional
import traceback

from sqlalchemy.orm import Session
from database import SessionLocal
from models import BrokerConnection, BrokerType
from tinkoff_service import TinkoffService
from utils.datetime_utils import utc_now_naive
from logger import get_logger

log = get_logger("sync_scheduler")


class SyncScheduler:
    """Планировщик автоматической синхронизации"""
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_check = None
        self._sync_in_progress: Dict[int, bool] = {}  # connection_id -> is_syncing
        self._check_interval = 60  # Проверяем каждую минуту
    
    async def start(self):
        """Запускает планировщик"""
        if self._running:
            log.warning("Scheduler already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        log.info("🔄 Sync scheduler started")
    
    async def stop(self):
        """Останавливает планировщик"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("⏹️ Sync scheduler stopped")
    
    async def _run_loop(self):
        """Основной цикл планировщика"""
        while self._running:
            try:
                await self._check_and_sync()
                self._last_check = utc_now_naive()
            except Exception as e:
                log.error(f"Scheduler error: {e}")
                log.error(traceback.format_exc())
            
            # Ждём до следующей проверки
            await asyncio.sleep(self._check_interval)
    
    async def _check_and_sync(self):
        """Проверяет и запускает синхронизацию для нужных подключений"""
        db = SessionLocal()
        try:
            # Получаем все активные подключения с включённой автосинхронизацией
            connections = db.query(BrokerConnection).filter(
                BrokerConnection.is_active == True,
                BrokerConnection.auto_sync_enabled == True
            ).all()
            
            now = utc_now_naive()
            
            for conn in connections:
                # Пропускаем если синхронизация уже идёт
                if self._sync_in_progress.get(conn.id, False):
                    continue
                
                # Проверяем нужна ли синхронизация
                if self._should_sync(conn, now):
                    # Запускаем синхронизацию в отдельной задаче
                    asyncio.create_task(self._sync_connection(conn.id))
        finally:
            db.close()
    
    def _should_sync(self, conn: BrokerConnection, now: datetime) -> bool:
        """Определяет нужно ли синхронизировать подключение"""
        if not conn.last_sync_at:
            return True
        
        next_sync = conn.last_sync_at + timedelta(minutes=conn.sync_interval_minutes)
        return now >= next_sync
    
    async def _sync_connection(self, connection_id: int):
        """Синхронизирует конкретное подключение"""
        self._sync_in_progress[connection_id] = True
        db = SessionLocal()
        
        try:
            conn = db.query(BrokerConnection).filter(
                BrokerConnection.id == connection_id
            ).first()
            
            if not conn or not conn.is_active:
                return
            
            log.info(f"🔄 Auto-syncing broker connection #{connection_id}")
            
            if conn.broker == BrokerType.TINKOFF:
                service = TinkoffService(conn.api_token)
                result = service.sync_trades(db=db, connection=conn, force_full_sync=False)
                
                if result["success"]:
                    log.info(
                        f"✅ Auto-sync #{connection_id} complete: "
                        f"+{result['new_trades']} new, {result['updated_trades']} updated"
                    )
                else:
                    log.warning(f"⚠️ Auto-sync #{connection_id} partial: {result['errors'][:2]}")
            else:
                log.warning(f"Unknown broker type: {conn.broker}")
        
        except Exception as e:
            log.error(f"Auto-sync #{connection_id} failed: {e}")
            
            # Обновляем статус ошибки
            try:
                conn = db.query(BrokerConnection).filter(
                    BrokerConnection.id == connection_id
                ).first()
                if conn:
                    conn.last_sync_status = "error"
                    conn.last_sync_error = str(e)[:500]
                    conn.last_sync_at = utc_now_naive()
                    db.commit()
            except Exception:
                pass
        
        finally:
            db.close()
            self._sync_in_progress[connection_id] = False
    
    def get_status(self) -> dict:
        """Возвращает статус планировщика"""
        return {
            "running": self._running,
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "check_interval_seconds": self._check_interval,
            "syncing_connections": list(
                conn_id for conn_id, syncing in self._sync_in_progress.items() if syncing
            )
        }
    
    async def trigger_sync(self, connection_id: int) -> bool:
        """Принудительно запускает синхронизацию"""
        if self._sync_in_progress.get(connection_id, False):
            return False
        
        asyncio.create_task(self._sync_connection(connection_id))
        return True


# Глобальный экземпляр планировщика
scheduler = SyncScheduler()
