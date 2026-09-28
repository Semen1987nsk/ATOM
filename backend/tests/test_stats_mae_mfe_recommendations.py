"""S3-01: _generate_strategy_recommendations не должен падать при profit_factor=None."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routers.stats import _generate_strategy_recommendations  # noqa: E402


def _base_analysis(**over):
    a = {
        "edge_ratio": 1.2,
        "avg_mae": 1.0,
        "avg_mfe": 2.0,
        "avg_efficiency": 50.0,
        "win_rate": 100.0,
        "quality_score": 60,
        "trades_count": 2,
        "real_rr": 0.0,          # нет убытков → real_rr=0 (guard на :1541 не сработает)
        "profit_factor": None,   # MATH-05: PF undefined при отсутствии лузеров
        "required_winrate": 100.0,
        "avg_win": 500.0,
        "avg_loss": 0.0,
        "total_pnl": 1000.0,     # is_profitable=True → ветка :1580 активна
        "mae_percentiles": {"p25": 0.5, "p50": 1.0, "p75": 1.5, "max": 2.0},
        "mfe_percentiles": {"p25": 1.0, "p50": 2.0, "p75": 3.0, "max": 4.0},
    }
    a.update(over)
    return a


def test_profitable_all_winners_no_type_error():
    # До фикса: TypeError '>=' NoneType/float на :1580 → 500.
    recs = _generate_strategy_recommendations(_base_analysis())
    assert isinstance(recs, list)
    assert any(r.get("type") in {"success", "info", "warning"} for r in recs)


def test_real_rr_positive_with_none_pf():
    # Ветка :1546 тоже не должна падать, когда real_rr>0, но PF=None.
    recs = _generate_strategy_recommendations(_base_analysis(real_rr=1.5, profit_factor=None))
    assert isinstance(recs, list)
