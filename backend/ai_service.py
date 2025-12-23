import os
import json
from typing import Dict, Optional

# В будущем здесь будет: import openai
# client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def analyze_trade_with_ai(trade_data: Dict) -> Dict:
    """
    Отправляет данные сделки в AI для анализа поведения и психологии.
    """
    # Имитация промпта для AI
    prompt = f"""
    Проанализируй сделку трейдера:
    Символ: {trade_data.get('symbol')}
    Направление: {trade_data.get('direction')}
    PnL: {trade_data.get('pnl')}
    MAE (Худшая цена): {trade_data.get('mae_price')}
    MFE (Лучшая цена): {trade_data.get('mfe_price')}
    Заметки трейдера: {trade_data.get('notes')}
    Эмоции: {trade_data.get('emotions')}
    
    Дай краткий разбор (до 3 предложений):
    1. Был ли это тильт или системный вход?
    2. Ошибка в управлении позицией?
    3. Психологический совет.
    """
    
    # Пока используем мок-логику, имитирующую "умный" ответ
    pnl = float(trade_data.get('pnl', 0))
    notes = str(trade_data.get('notes', '')).lower()
    
    if pnl < 0 and ("fomo" in notes or "догнал" in notes):
        return {
            "verdict": "FOMO Entry",
            "analysis": "Вы вошли в сделку из-за страха упущенной выгоды. Вход был совершен на импульсе без подтверждения системы.",
            "advice": "Сделайте паузу на 15 минут после такой сделки. Рынок никуда не убежит.",
            "score": 30
        }
    elif pnl > 0 and float(trade_data.get('mfe_price', 0)) > float(trade_data.get('exit_price', 0)) * 1.05:
        return {
            "verdict": "Early Exit",
            "analysis": "Хороший системный вход, но вы закрылись слишком рано, не дождавшись цели. Прибыль могла быть в 2 раза выше.",
            "advice": "Попробуйте переводить стоп в безубыток и давать части позиции 'дышать'.",
            "score": 75
        }
    else:
        return {
            "verdict": "Systematic Trade",
            "analysis": "Сделка выглядит дисциплинированной. Параметры риска соблюдены.",
            "advice": "Отличная работа. Продолжайте следовать чек-листу.",
            "score": 90
        }
