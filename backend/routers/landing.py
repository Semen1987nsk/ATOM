"""Landing Router — публичные данные для гостевого лендинга (без auth).

Сейчас: /api/landing/ticker — биржевая строка MOEX (индекс IMOEX + ликвидные
акции) с last и change_pct. Данные кешируются на 60с в market_service, ISS
free-данные идут с ~15-мин задержкой. Эндпоинт без авторизации — лендинг
гостевой; rate-limit защищает от наплыва.
"""
from fastapi import APIRouter, Request

from logger import get_logger
import market_service
from rate_limiter import limiter, MARKET_LIMIT

log = get_logger("landing")

router = APIRouter(prefix="/api/landing", tags=["landing"])

_service = market_service.MarketService()


@router.get("/ticker")
@limiter.limit(MARKET_LIMIT)
async def landing_ticker(request: Request):
    """Биржевая строка MOEX для лендинга. {stale, tickers:[{symbol,last,change_pct}]}."""
    try:
        return await _service.get_landing_ticker()
    except Exception as e:  # noqa: BLE001 — graceful: фронт уйдёт в fallback
        log.warning(f"landing ticker failed: {e}")
        return {"stale": True, "tickers": []}
