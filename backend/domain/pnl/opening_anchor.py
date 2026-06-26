"""Opening-balance anchor decision (ADR-0010, amends ADR-0008). Pure — no I/O.

При неполной истории депозитов брокерского счёта стартовое финансирование вне
окна sync. candidate = portfolio − net_deposits − journal восстанавливает
опорную базу. Гейтим тремя deposit-НЕзависимыми проверками, чтобы не спрятать
реальный баг расчёта журнала (pv×1000 и т.п.). См. spec §3.2.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# G1 — минимально осмысленный якорь (₽). <= → журнал ≥ кассы, восстанавливать нечего.
ANCHOR_MIN = Decimal("1")
# G2 — допуск телескопирования фьючерсного body против фактической варм-маржи.
TELESCOPE_TOL_PCT = Decimal("0.25")
# G2 отключается на счёте без фьючерсов (|varmargin_net| < этого).
VARMARGIN_FLOOR = Decimal("1")
# G3 — потолок правдоподобия: якорь не больше N× крупнейшей buy-операции.
ANCHOR_MAX_FACTOR = Decimal("50")


@dataclass(frozen=True)
class AnchorDecision:
    should_anchor: bool
    value: Decimal       # округлённый якорь (0 если не якорим)
    source: str          # 'inferred_anchor' | 'inferred_blocked' | 'inferred_skipped' | 'complete'
    reason: str


def compute_candidate_anchor(
    *, portfolio_value: Decimal, net_deposits: Decimal, journal_pnl: Decimal
) -> Decimal:
    """Пропущенный стартовый депозит = касса − депозиты − журнал (spec §3.1)."""
    return portfolio_value - net_deposits - journal_pnl


def telescope_residual(
    *, body_closed: Decimal, varmargin_net: Decimal, open_settled: Decimal
) -> Decimal:
    """|body закрытых фьючерсов − (нетто варм-маржа − осевшая ВМ открытых)| (spec §3.2 G2)."""
    return abs(body_closed - (varmargin_net - open_settled))


def decide_anchor(
    *,
    incomplete_history: bool,
    portfolio_value: Decimal,
    net_deposits: Decimal,
    journal_pnl: Decimal,
    body_closed: Decimal,
    varmargin_net: Decimal,
    open_settled: Decimal,
    gross_buy_peak: Decimal,
) -> AnchorDecision:
    if not incomplete_history:
        return AnchorDecision(False, Decimal("0"), "complete", "first op is a deposit")

    candidate = compute_candidate_anchor(
        portfolio_value=portfolio_value,
        net_deposits=net_deposits,
        journal_pnl=journal_pnl,
    )

    # G1 — знак.
    # source='inferred_skipped' (НЕ 'complete'): история всё ещё неполная,
    # реальный стартовый капитал не появился — кандидат лишь временно просел
    # ≤1 ₽ (напр. убыточный счёт восстанавливается к безубытку). 'complete'
    # снял бы service-заморозку и обнулил бы уже поставленный якорь. См. ADR-0010 §5.
    if candidate <= ANCHOR_MIN:
        return AnchorDecision(
            False, Decimal("0"), "inferred_skipped", "candidate<=min; nothing to restore"
        )

    # G2 — телескоп фьючерсов (только если на счёте есть варм-маржа).
    if abs(varmargin_net) >= VARMARGIN_FLOOR:
        residual = telescope_residual(
            body_closed=body_closed, varmargin_net=varmargin_net, open_settled=open_settled
        )
        if residual > TELESCOPE_TOL_PCT * abs(varmargin_net):
            return AnchorDecision(
                False, Decimal("0"), "inferred_blocked",
                f"telescope gate failed: residual={residual} > tol",
            )

    # G3 — потолок правдоподобия.
    if candidate > ANCHOR_MAX_FACTOR * abs(gross_buy_peak):
        return AnchorDecision(
            False, Decimal("0"), "inferred_blocked",
            f"candidate={candidate} exceeds {ANCHOR_MAX_FACTOR}x buy peak",
        )

    return AnchorDecision(
        True, candidate.quantize(Decimal("0.01")), "inferred_anchor", "anchored"
    )
