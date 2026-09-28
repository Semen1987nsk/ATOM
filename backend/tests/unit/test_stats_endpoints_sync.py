"""S2-01 (partial): тяжёлые синхронные (DB + чистый Python) эндпоинты не должны
быть `async def` — иначе синхронная работа блокирует event loop под нагрузкой.
FastAPI исполняет обычные `def` path-operations в threadpool.

Покрываем 2 из 3 эндпоинтов задачи S2-01. Третий, `get_stats`, остаётся `async`
намеренно: в теле реальный `await _build_imoex_overlay_async` (сетевой I/O к MOEX
ISS) — его конверсия требует отдельного async-рефактора overlay (бэклог).
"""
import inspect

from routers.stats_advanced import get_advanced_stats
from routers.trades import read_position_trades


def test_get_advanced_stats_is_sync_def():
    assert not inspect.iscoroutinefunction(get_advanced_stats)


def test_read_position_trades_is_sync_def():
    assert not inspect.iscoroutinefunction(read_position_trades)
