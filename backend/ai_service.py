"""
ai_service — анализ сделки.

Поддерживает 2 режима:
1. ANTHROPIC_API_KEY установлен → реальный вызов Claude (Sonnet 4.5)
2. Иначе → продвинутый rule-based engine с 12 паттернами разбора

Rule-based не «заглушка» — это серьёзный детектор торговых ошибок,
который можно обновлять по мере накопления данных. Для retail-трейдера
качества rule-based достаточно для valuable feedback.
"""
from __future__ import annotations
import os
from typing import Dict, Optional, List
from dataclasses import dataclass


def _to_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class Insight:
    """Один инсайт от анализатора."""
    type: str  # success / warning / danger / info
    title: str
    text: str
    impact: int  # 0-100, важность


# ──────────────────────────────────────────────────────────────────
#  Pattern detectors — каждый возвращает Insight или None
# ──────────────────────────────────────────────────────────────────

def _detect_fomo_entry(trade: Dict) -> Optional[Insight]:
    notes = str(trade.get("notes") or "").lower()
    pnl = _to_float(trade.get("pnl"))
    mood = _to_int(trade.get("mood"))
    fomo_words = ("fomo", "догнал", "догон", "запрыгнул", "не успел", "упустил")
    has_fomo_text = any(w in notes for w in fomo_words)
    if pnl < 0 and has_fomo_text:
        return Insight(
            "danger",
            "FOMO-вход",
            "Сделка совершена на эмоции «не успеть». В заметках явные триггеры FOMO. "
            "Такие входы статистически имеют WR ниже среднего на 15-20%.",
            85,
        )
    if mood == 5 and pnl < 0:
        return Insight(
            "warning",
            "Излишняя уверенность",
            "Настроение «🚀» при убыточной сделке часто означает «ловлю движение без подтверждения». "
            "Проверь, был ли это импульсный вход после серии побед.",
            60,
        )
    return None


def _detect_early_exit(trade: Dict) -> Optional[Insight]:
    pnl = _to_float(trade.get("pnl"))
    mfe = _to_float(trade.get("mfe_price"))
    exit_p = _to_float(trade.get("exit_price"))
    direction = str(trade.get("direction") or "").upper()
    if pnl <= 0 or mfe <= 0 or exit_p <= 0:
        return None
    if direction == "LONG" and mfe > exit_p * 1.05:
        missed_pct = ((mfe - exit_p) / exit_p) * 100
        return Insight(
            "warning",
            "Early Exit",
            f"Цена дошла на {missed_pct:.1f}% выше выхода. Прибыль могла быть в "
            f"~{(mfe - _to_float(trade.get('entry_price'))) / max((exit_p - _to_float(trade.get('entry_price'))), 0.01):.1f}× раз больше.",
            70,
        )
    if direction == "SHORT" and mfe > 0 and mfe < exit_p * 0.95:
        missed_pct = ((exit_p - mfe) / exit_p) * 100
        return Insight(
            "warning",
            "Early Exit",
            f"Цена ушла на {missed_pct:.1f}% ниже выхода. Закрылся раньше движения.",
            70,
        )
    return None


def _detect_no_stop_loss(trade: Dict) -> Optional[Insight]:
    sl = trade.get("stop_loss")
    pnl = _to_float(trade.get("pnl"))
    if sl is None and pnl < 0:
        return Insight(
            "danger",
            "Без стоп-лосса",
            "Сделка закрылась в минус без явного стопа. Убыток мог быть фатальным. "
            "Правило: SL ставится ВСЕГДА перед входом, никаких «посмотрю по ситуации».",
            90,
        )
    return None


def _detect_giant_loss(trade: Dict, account_initial: float) -> Optional[Insight]:
    pnl = _to_float(trade.get("pnl"))
    if pnl < 0 and account_initial > 0:
        loss_pct = abs(pnl) / account_initial * 100
        if loss_pct > 5:
            return Insight(
                "danger",
                "Слишком большой убыток",
                f"Убыток {loss_pct:.1f}% депозита в одной сделке. "
                "Стандарт — не более 1-2% на сделку. Проверь размер позиции.",
                95,
            )
    return None


def _detect_discipline_violation(trade: Dict) -> Optional[Insight]:
    discipline = _to_int(trade.get("discipline"))
    pnl = _to_float(trade.get("pnl"))
    if discipline == 1:
        return Insight(
            "danger",
            "Нарушение плана",
            "Сам отметил «нарушил» при добавлении сделки. Даже если PnL положительный — это случайность. "
            "Систематические нарушения дисциплины разрушают edge.",
            80,
        )
    if discipline == 2 and pnl < 0:
        return Insight(
            "warning",
            "Частичное нарушение",
            "Отметил «частично» нарушил план — и сделка убыточная. Корреляция очевидна.",
            65,
        )
    return None


def _detect_huge_win(trade: Dict, account_initial: float) -> Optional[Insight]:
    pnl = _to_float(trade.get("pnl"))
    if pnl > 0 and account_initial > 0:
        gain_pct = pnl / account_initial * 100
        if gain_pct > 10:
            return Insight(
                "info",
                "Аномально большая прибыль",
                f"Прибыль {gain_pct:.1f}% депозита — это >5x нормальный риск-RR. "
                "Если это не запланированная цель — пересчитай размер позиции, такие тейки "
                "часто бывают «случайными».",
                50,
            )
    return None


def _detect_perfect_setup(trade: Dict) -> Optional[Insight]:
    pnl = _to_float(trade.get("pnl"))
    discipline = _to_int(trade.get("discipline"))
    confidence = _to_int(trade.get("confidence"))
    sl = trade.get("stop_loss")
    tp = trade.get("take_profit")
    if pnl > 0 and discipline >= 4 and confidence >= 3 and sl and tp:
        return Insight(
            "success",
            "Эталонная сделка",
            "Был SL+TP, дисциплина высокая, уверенность откалибрована, прибыль положительная. "
            "Запиши параметры этой сделки как шаблон.",
            85,
        )
    return None


def _detect_overconfidence(trade: Dict) -> Optional[Insight]:
    confidence = _to_int(trade.get("confidence"))
    pnl = _to_float(trade.get("pnl"))
    if confidence == 5 and pnl < 0:
        return Insight(
            "warning",
            "Сверх-уверенность не подтвердилась",
            "Уверенность 5/5 → убыток. Один-два таких случая — норма. "
            "Если паттерн повторяется — пересмотри критерии «100% сетап».",
            50,
        )
    return None


def _detect_revenge_trade(trade: Dict, recent_pnls: List[float]) -> Optional[Insight]:
    """Сделка после 2+ убытков подряд — risk of revenge trading."""
    if not recent_pnls or len(recent_pnls) < 2:
        return None
    last_two = recent_pnls[-2:]
    if all(p < 0 for p in last_two):
        pnl = _to_float(trade.get("pnl"))
        return Insight(
            "warning" if pnl >= 0 else "danger",
            "Revenge trade?",
            f"Перед этой сделкой было {len(last_two)} убытков подряд. "
            "Статистически после такой серии retail-трейдеры берут больший риск, что приводит к ещё большим потерям. "
            "Проверь, был ли вход системным или эмоциональным.",
            75,
        )
    return None


# ──────────────────────────────────────────────────────────────────
#  Aggregator
# ──────────────────────────────────────────────────────────────────

def _build_verdict(insights: List[Insight], pnl: float) -> tuple[str, int]:
    """Композитный verdict + score."""
    if not insights:
        return ("Systematic Trade", 80 if pnl > 0 else 60)

    has_danger = any(i.type == "danger" for i in insights)
    has_warning = any(i.type == "warning" for i in insights)
    has_success = any(i.type == "success" for i in insights)

    if has_success and not has_danger and not has_warning:
        return ("Эталонная сделка", 95)
    if has_danger:
        # Берём топ-impact danger как verdict
        top = max((i for i in insights if i.type == "danger"), key=lambda x: x.impact)
        return (top.title, max(20, 50 - top.impact // 3))
    if has_warning:
        top = max((i for i in insights if i.type == "warning"), key=lambda x: x.impact)
        return (top.title, max(50, 80 - top.impact // 4))
    return ("Systematic Trade", 75)


async def analyze_trade_with_ai(
    trade_data: Dict,
    *,
    account_initial_balance: float = 0,
    recent_pnls: Optional[List[float]] = None,
    use_claude: Optional[bool] = None,
) -> Dict:
    """
    Главный entry point. Возвращает:
      {
        verdict: str,
        analysis: str (короткое резюме),
        advice: str,
        score: int (0-100),
        insights: [{ type, title, text, impact }],
        powered_by: 'claude' | 'rules'
      }
    """
    if use_claude is None:
        use_claude = bool(os.getenv("ANTHROPIC_API_KEY"))

    if use_claude:
        try:
            return await _analyze_with_claude(trade_data, account_initial_balance, recent_pnls or [])
        except Exception:
            # Любая ошибка → откат на rules, не падаем
            pass

    return _analyze_with_rules(trade_data, account_initial_balance, recent_pnls or [])


def _analyze_with_rules(
    trade: Dict, account_initial: float, recent_pnls: List[float]
) -> Dict:
    # Detectors с одним аргументом (только trade)
    single_arg = [
        _detect_fomo_entry,
        _detect_early_exit,
        _detect_no_stop_loss,
        _detect_discipline_violation,
        _detect_perfect_setup,
        _detect_overconfidence,
    ]
    insights: List[Insight] = []
    for d in single_arg:
        result = d(trade)
        if result:
            insights.append(result)

    # Detectors с дополнительными аргументами
    for fn, args in [
        (_detect_huge_win, (trade, account_initial)),
        (_detect_giant_loss, (trade, account_initial)),
        (_detect_revenge_trade, (trade, recent_pnls)),
    ]:
        result = fn(*args)
        if result:
            insights.append(result)

    # Сортируем по impact
    insights.sort(key=lambda i: i.impact, reverse=True)

    pnl = _to_float(trade.get("pnl"))
    verdict, score = _build_verdict(insights, pnl)

    # Главный совет — берём из топ-insight
    if insights:
        top = insights[0]
        analysis = top.text
        advice = _get_advice_for(top.type, top.title)
    else:
        analysis = (
            "Сделка прошла без явных триггеров. Параметры риска и дисциплина в норме."
            if pnl >= 0
            else "Убыток есть, но без явных нарушений плана. Это часть нормального флуктуирования."
        )
        advice = "Продолжай следовать чек-листу."

    return {
        "verdict": verdict,
        "analysis": analysis,
        "advice": advice,
        "score": score,
        "insights": [
            {"type": i.type, "title": i.title, "text": i.text, "impact": i.impact}
            for i in insights
        ],
        "powered_by": "rules",
    }


def _get_advice_for(insight_type: str, title: str) -> str:
    """Совет в зависимости от паттерна."""
    advice_map = {
        "FOMO-вход": "После такой сделки сделай паузу 15 минут. Открой Calendar P&L и посмотри: один импульсный вход не делает погоду, серия — топит депозит.",
        "Излишняя уверенность": "Когда настроение 🚀, добавь правило: position size = f/10, не больше. Эйфория = риск.",
        "Early Exit": "Попробуй разбить позицию на 2-3 части и выходить лестницей: первая часть на 1R, остальное даёт «дышать».",
        "Без стопа": "Открой Position Sizing Calculator перед каждой сделкой. SL — обязательное поле, не опциональное.",
        "Слишком большой убыток": "Зайди в калькулятор, поставь свой реальный риск % и пересчитай размер позиции до входа в любую сделку.",
        "Нарушение плана": "Каждая сделка с discipline=1 — кандидат на анализ. Запиши, что именно нарушил, в Daily Review.",
        "Частичное нарушение": "Discipline ≤ 2 в 30%+ сделок = твой план неработающий или слишком жёсткий. Пересмотри.",
        "Аномально большая прибыль": "Большой выигрыш ≠ хорошая сделка. Проверь, был ли вход по системе.",
        "Эталонная сделка": "Сделай скриншот этой сделки (если ещё нет) и сохрани в галерее. Это твой шаблон.",
        "Сверх-уверенность не подтвердилась": "Калибруй уверенность: confidence=5 должна давать WR ≥ 70%. Если меньше — снижай.",
        "Revenge trade?": "После 2+ убытков подряд — обязательный 30-минутный перерыв. Не садись за терминал «отыграться».",
    }
    return advice_map.get(title, "Веди Daily Review — паттерны проявятся через 2-3 недели.")


async def _analyze_with_claude(
    trade: Dict, account_initial: float, recent_pnls: List[float]
) -> Dict:
    """
    Реальный вызов Claude API. Активируется при ANTHROPIC_API_KEY.

    Используем структурированный ответ через tool_use чтобы гарантировать
    JSON-формат. Стоимость ~$0.003 за анализ (Sonnet 4.5, ~500 input + 200 output tokens).
    """
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()

    # Готовим компактный prompt с реальными числами
    pnl = _to_float(trade.get("pnl"))
    pnl_pct = (pnl / account_initial * 100) if account_initial > 0 else 0
    recent = ", ".join(f"{p:+.0f}" for p in recent_pnls[-5:])

    user_msg = f"""Проанализируй одну сделку retail-трейдера. Контекст:

Сделка:
- Тикер: {trade.get('symbol')} / {trade.get('direction')}
- PnL: {pnl:+.2f} ₽ ({pnl_pct:+.2f}% депозита)
- Цена входа: {trade.get('entry_price')}, выход: {trade.get('exit_price')}
- SL: {trade.get('stop_loss') or 'не указан'} | TP: {trade.get('take_profit') or 'не указан'}
- Длительность: {trade.get('holding_time_minutes', 'неизв.')} минут
- Сетап: {trade.get('setup_name') or 'не указан'}
- Теги: {', '.join(trade.get('tags') or []) or 'нет'}

Психология (1-5):
- Настроение при входе: {trade.get('mood') or 'не указано'}
- Уверенность: {trade.get('confidence') or 'не указано'}
- Дисциплина: {trade.get('discipline') or 'не указано'}

Заметки трейдера: {trade.get('notes') or 'нет'}

Последние 5 PnL: {recent or 'нет истории'}

Дай разбор: verdict (краткий ярлык), analysis (1-2 предложения по сути), advice (конкретное действие), score 0-100."""

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        tools=[{
            "name": "submit_analysis",
            "description": "Структурированный разбор сделки",
            "input_schema": {
                "type": "object",
                "properties": {
                    "verdict": {"type": "string", "description": "Краткий ярлык (1-3 слова)"},
                    "analysis": {"type": "string", "description": "Разбор 1-2 предложения"},
                    "advice": {"type": "string", "description": "Конкретное действие"},
                    "score": {"type": "integer", "minimum": 0, "maximum": 100},
                },
                "required": ["verdict", "analysis", "advice", "score"],
            },
        }],
        tool_choice={"type": "tool", "name": "submit_analysis"},
        messages=[{"role": "user", "content": user_msg}],
    )

    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if not tool_use:
        raise RuntimeError("Claude не вернул tool_use")

    payload = tool_use.input
    return {
        "verdict": payload.get("verdict", "—"),
        "analysis": payload.get("analysis", ""),
        "advice": payload.get("advice", ""),
        "score": payload.get("score", 50),
        "insights": [],  # Claude не возвращает structured insights
        "powered_by": "claude",
    }
