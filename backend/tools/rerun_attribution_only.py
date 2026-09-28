"""Запустить ТОЛЬКО _stage_attribute_fees для account_id без full re-sync.

Это нужно после изменений в fee_attribution.py / cash_flow_classification.py
чтобы переcчитать Trade.varmargin_attributed/margin_fee_attributed/...
без хождения в Tinkoff API.

Usage:
    python -X utf8 -m tools.rerun_attribution_only --account-id 4
"""
from __future__ import annotations
import argparse
import sys

import database


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--account-id", type=int, required=True)
    args = p.parse_args()

    from application.sync.pipeline import SyncPipeline

    # Build minimal pipeline instance — нам нужны только _stage_attribute_fees,
    # все остальные dependencies можно опустить.
    pipeline = SyncPipeline.__new__(SyncPipeline)
    pipeline._account_id = args.account_id
    pipeline._session_factory = database.SessionLocal

    pipeline._stage_attribute_fees()

    # Helper для конверсии ORM → domain используется внутри. Подцепляем методы
    # которые stage может вызвать.
    print(f"Attribution stage re-run для account_id={args.account_id} — done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
