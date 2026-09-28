"""
Market Router — рыночные данные, котировки
"""
from fastapi import APIRouter, HTTPException, Request, Depends
from logger import get_logger
import market_service
import auth_service
import models
from rate_limiter import limiter, MARKET_LIMIT

log = get_logger("market")

router = APIRouter(prefix="/market", tags=["market"])

market_data_service = market_service.MarketService()

MAX_TICKERS = 50  # Limit to prevent abuse


@router.get("/prices")
@limiter.limit(MARKET_LIMIT)
async def get_prices(
    request: Request,
    tickers: str,
    current_user: models.User = Depends(auth_service.get_current_user),
):
    """
    Получить текущие цены для списка тикеров.
    Тикеры передаются через запятую: /market/prices?tickers=SBER,GAZP,LKOH
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="Не указаны тикеры")
    if len(ticker_list) > MAX_TICKERS:
        raise HTTPException(status_code=400, detail=f"Максимум {MAX_TICKERS} тикеров за запрос")
    try:
        prices = await market_data_service.get_current_prices(ticker_list)
        return {"prices": prices}
    except Exception as e:
        log.error(f"Error fetching prices for {ticker_list}: {e}")
        raise HTTPException(status_code=502, detail="Ошибка получения рыночных данных")


@router.get("/futures-specs")
@limiter.limit(MARKET_LIMIT)
async def get_futures_specs(
    request: Request,
    tickers: str,
    current_user: models.User = Depends(auth_service.get_current_user),
):
    """
    Получить спецификации фьючерсов (MINSTEP, STEPPRICE).
    Тикеры передаются через запятую.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="Не указаны тикеры")
    if len(ticker_list) > MAX_TICKERS:
        raise HTTPException(status_code=400, detail=f"Максимум {MAX_TICKERS} тикеров за запрос")
    try:
        specs = await market_data_service.get_futures_specs(ticker_list)
        return {"specs": specs}
    except Exception as e:
        log.error(f"Error fetching futures specs for {ticker_list}: {e}")
        raise HTTPException(status_code=502, detail="Ошибка получения спецификаций фьючерсов")
