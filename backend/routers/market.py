"""
Market Router — рыночные данные, котировки
"""
from fastapi import APIRouter
import market_service

router = APIRouter(prefix="/market", tags=["market"])

market_data_service = market_service.MarketService()


@router.get("/prices")
async def get_prices(tickers: str):
    """
    Получить текущие цены для списка тикеров.
    Тикеры передаются через запятую: /market/prices?tickers=SBER,GAZP,LKOH
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    prices = market_data_service.get_current_prices(ticker_list)
    return {"prices": prices}


@router.get("/futures-specs")
async def get_futures_specs(tickers: str):
    """
    Получить спецификации фьючерсов (MINSTEP, STEPPRICE).
    Тикеры передаются через запятую.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    specs = market_data_service.get_futures_specs(ticker_list)
    return {"specs": specs}
