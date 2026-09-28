"""Полный breakdown PnL для одного account_id — diagnostic.

Показывает откуда берётся каждая цифра в дашборде:
  - Реализованный PnL (Σ closed Trade.net_pnl) — что в Дневнике сделок
  - Нереализованный PnL (Σ Position.unrealized_pnl) — что на странице "Позиции"
  - Account-level adjustments ("Прочие") — orphan cash flows
  - Cash truth (last_portfolio_value − net_deposits) — broker ground truth
"""
from __future__ import annotations
import argparse
import sys

import database
import models
from sqlalchemy import func
from domain.pnl.cash_flow_classification import (
    CashFlowCategory,
    operation_types_in,
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--account-id", type=int, required=True)
    args = p.parse_args()
    aid = args.account_id

    s = database.SessionLocal()
    try:
        # === Block 1: closed Trade.net_pnl breakdown ===
        print("=" * 72)
        print("БЛОК 1: РЕАЛИЗОВАННЫЙ PnL (закрытые сделки в Дневнике)")
        print("=" * 72)
        closed_pnl = float(
            s.query(func.coalesce(func.sum(models.Trade.net_pnl), 0))
            .filter(models.Trade.account_id == aid, models.Trade.exit_at.isnot(None))
            .scalar() or 0
        )
        closed_body = float(
            s.query(func.coalesce(func.sum(models.Trade.pnl), 0))
            .filter(models.Trade.account_id == aid, models.Trade.exit_at.isnot(None))
            .scalar() or 0
        )
        closed_comm = float(
            s.query(func.coalesce(func.sum(func.abs(models.Trade.commission)), 0))
            .filter(models.Trade.account_id == aid, models.Trade.exit_at.isnot(None))
            .scalar() or 0
        )
        closed_vm = float(
            s.query(func.coalesce(func.sum(models.Trade.varmargin_attributed), 0))
            .filter(models.Trade.account_id == aid, models.Trade.exit_at.isnot(None))
            .scalar() or 0
        )
        closed_mf = float(
            s.query(func.coalesce(func.sum(models.Trade.margin_fee_attributed), 0))
            .filter(models.Trade.account_id == aid, models.Trade.exit_at.isnot(None))
            .scalar() or 0
        )
        closed_sf = float(
            s.query(func.coalesce(func.sum(models.Trade.service_fee_attributed), 0))
            .filter(models.Trade.account_id == aid, models.Trade.exit_at.isnot(None))
            .scalar() or 0
        )
        closed_other = float(
            s.query(func.coalesce(func.sum(models.Trade.other_fees_attributed), 0))
            .filter(models.Trade.account_id == aid, models.Trade.exit_at.isnot(None))
            .scalar() or 0
        )
        n_closed = s.query(func.count(models.Trade.id)).filter(
            models.Trade.account_id == aid, models.Trade.exit_at.isnot(None)
        ).scalar()

        print(f"  Кол-во закрытых сделок:               {n_closed:>15}")
        print(f"  Body P&L (разница цен × qty × pv):    {closed_body:>15,.2f} ₽")
        print(f"  − Комиссии брокера per-trade:         {-closed_comm:>15,.2f} ₽")
        print(f"  + Варм-маржа attributed (futures):    {closed_vm:>15,.2f} ₽")
        print(f"  + Маржинальные комиссии attributed:   {closed_mf:>15,.2f} ₽")
        print(f"  + Сервисные комиссии attributed:      {closed_sf:>15,.2f} ₽")
        print(f"  + Налоги/дивиденды/прочее attribut.:  {closed_other:>15,.2f} ₽")
        print(f"  {'─' * 60}")
        print(f"  Σ Trade.net_pnl (closed):             {closed_pnl:>15,.2f} ₽")
        print(f"  ↑ это число попадает в Equity curve + 'Реализ.' на дашборде")

        # === Block 2: open positions ===
        print()
        print("=" * 72)
        print("БЛОК 2: НЕРЕАЛИЗОВАННАЯ ПРИБЫЛЬ (открытые позиции на странице Позиции)")
        print("=" * 72)
        unrealized = float(
            s.query(func.coalesce(func.sum(models.PositionORM.unrealized_pnl), 0))
            .filter(models.PositionORM.account_id == aid)
            .scalar() or 0
        )
        positions = (
            s.query(models.PositionORM)
            .filter(
                models.PositionORM.account_id == aid,
                models.PositionORM.quantity != 0,
            )
            .all()
        )
        print(f"  Кол-во открытых позиций: {len(positions)}")
        for p2 in positions:
            instr = s.query(models.InstrumentORM).filter(
                models.InstrumentORM.uid == p2.instrument_uid
            ).first()
            ticker = instr.ticker if instr else (p2.instrument_uid or "")[:10]
            unr = float(p2.unrealized_pnl or 0)
            print(
                f"    {ticker:<12} ({p2.instrument_type:<8}) qty={float(p2.quantity):>7,.0f}  "
                f"unrealized = {unr:>12,.2f} ₽"
            )
        print(f"  {'─' * 60}")
        print(f"  Σ Position.unrealized_pnl:            {unrealized:>15,.2f} ₽")
        print(f"  ↑ это число на странице 'Позиции' + 'Нереализ.' на дашборде")

        # === Block 3: account-level adjustments ===
        print()
        print("=" * 72)
        print("БЛОК 3: ПРОЧИЕ (account_level_adjustments — что НЕ привязалось к сделкам)")
        print("=" * 72)

        def sum_cat(cat):
            types = tuple(operation_types_in(cat))
            if not types:
                return 0.0
            row = s.query(
                func.coalesce(func.sum(models.OperationORM.payment_units), 0),
                func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
            ).filter(
                models.OperationORM.account_id == aid,
                models.OperationORM.state == "executed",
                models.OperationORM.operation_type.in_(types),
            ).one()
            return float(row[0] or 0) + float(row[1] or 0) / 1e9

        raw_vm = sum_cat(CashFlowCategory.VARMARGIN)
        raw_attr = sum_cat(CashFlowCategory.ATTRIBUTABLE_FEE)
        raw_tax = sum_cat(CashFlowCategory.TAX)
        raw_income = sum_cat(CashFlowCategory.INCOME)
        raw_inctax = sum_cat(CashFlowCategory.INCOME_TAX)
        raw_broker = sum_cat(CashFlowCategory.BROKER_COMMISSION)

        attr_vm = float(
            s.query(func.coalesce(func.sum(models.Trade.varmargin_attributed), 0))
            .filter(models.Trade.account_id == aid).scalar() or 0
        )
        attr_mf = float(
            s.query(func.coalesce(func.sum(models.Trade.margin_fee_attributed), 0))
            .filter(models.Trade.account_id == aid).scalar() or 0
        )
        attr_sf = float(
            s.query(func.coalesce(func.sum(models.Trade.service_fee_attributed), 0))
            .filter(models.Trade.account_id == aid).scalar() or 0
        )
        attr_o = float(
            s.query(func.coalesce(func.sum(models.Trade.other_fees_attributed), 0))
            .filter(models.Trade.account_id == aid).scalar() or 0
        )
        sum_comm = float(
            s.query(func.coalesce(func.sum(models.Trade.commission), 0))
            .filter(
                models.Trade.account_id == aid,
                models.Trade.exit_at.isnot(None),
            ).scalar() or 0
        )

        # Phase 9: closed futures с Trade.pnl != 0 (body-formula) уже содержат
        # сумму varmargin от entry до exit. Вычитаем из raw_varmargin чтобы
        # не было double-count.
        closed_futures_body = float(
            s.query(func.coalesce(func.sum(models.Trade.pnl), 0))
            .filter(
                models.Trade.account_id == aid,
                models.Trade.exit_at.isnot(None),
                models.Trade.instrument_type_v2 == "futures",
                models.Trade.point_value.isnot(None),
            ).scalar() or 0
        )

        orphan_vm = raw_vm - attr_vm - closed_futures_body
        orphan_attr = raw_attr - (attr_mf + attr_sf)
        orphan_tax_inc = (raw_tax + raw_income + raw_inctax) - attr_o
        orphan_broker = raw_broker + sum_comm

        print(f"  Варм-маржа от MOEX:")
        print(f"    Σ всех varmargin ops в БД:          {raw_vm:>15,.2f} ₽")
        print(f"    − из них attributed к закрытым:     {attr_vm:>15,.2f} ₽")
        print(f"    = ORPHAN варм-маржа:                {orphan_vm:>15,.2f} ₽")
        print(f"      ↑ это варм-маржа в моменты когда не было active futures")
        print(f"        (типично: post-clearing settlement через 1-4 часа после")
        print(f"        exit_at — MOEX до-начисляет результат за день, а сделка")
        print(f"        уже закрыта). См. tools/audit_orphans_detail.py")
        print()
        print(f"  Маржинальные/сервисные комиссии:")
        print(f"    Σ всех attributable fees в БД:      {raw_attr:>15,.2f} ₽")
        print(f"    − attributed к сделкам:             {attr_mf + attr_sf:>15,.2f} ₽")
        print(f"    = ORPHAN fees:                      {orphan_attr:>15,.2f} ₽")
        print()
        print(f"  Налоги/дивиденды/купоны:")
        print(f"    Σ налогов (tax):                    {raw_tax:>15,.2f} ₽")
        print(f"    Σ доходов (dividends/coupons/exp):  {raw_income:>15,.2f} ₽")
        print(f"    Σ налогов на доходы:                {raw_inctax:>15,.2f} ₽")
        print(f"    − attributed к сделкам (other):     {attr_o:>15,.2f} ₽")
        print(f"    = ORPHAN tax/income:                {orphan_tax_inc:>15,.2f} ₽")
        print(f"      ↑ например, дивиденды пришли после закрытия позиции")
        print()
        print(f"  Broker commissions (раздельно от per-trade):")
        print(f"    Σ broker_fee ops (raw, signed):     {raw_broker:>15,.2f} ₽")
        print(f"    + Σ Trade.commission (closed, abs): {sum_comm:>15,.2f} ₽")
        print(f"    = ORPHAN broker_commission:         {orphan_broker:>15,.2f} ₽")
        print()
        total_orphan = orphan_vm + orphan_attr + orphan_tax_inc + orphan_broker
        print(f"  {'─' * 60}")
        print(f"  Σ account_level_adjustments:         {total_orphan:>15,.2f} ₽")
        print(f"  ↑ это число на дашборде в 'Прочие' (и причина расхождения")
        print(f"    между Equity curve и 'Общий PnL')")

        # === Block 4: net deposits ===
        print()
        print("=" * 72)
        print("БЛОК 4: ПОПОЛНЕНИЯ/ВЫВОДЫ + CASH TRUTH")
        print("=" * 72)
        net_dep = sum_cat(CashFlowCategory.NET_DEPOSIT)
        acc = s.get(models.Account, aid)
        portfolio = float(acc.last_portfolio_value or 0)
        cash_truth = portfolio - net_dep
        print(f"  Σ всех пополнений/выводов:            {net_dep:>15,.2f} ₽")
        print(f"  Текущая стоимость портфеля:           {portfolio:>15,.2f} ₽")
        print(f"  cash_truth = portfolio − deposits:    {cash_truth:>15,.2f} ₽")
        print(f"  ↑ это 'физическая правда' от брокера — что реально на счёте")

        # === FINAL ===
        print()
        print("=" * 72)
        print("ИТОГО: формула дашборда (без подгонки под брокера)")
        print("=" * 72)
        total = closed_pnl + unrealized + total_orphan
        print(f"  Блок 1: Реализованный PnL:           {closed_pnl:>15,.2f} ₽")
        print(f"  Блок 2: Нереализованная прибыль:     {unrealized:>15,.2f} ₽")
        print(f"  Блок 3: Прочие (orphan):             {total_orphan:>15,.2f} ₽")
        print(f"  {'─' * 60}")
        print(f"  ОБЩИЙ PnL (дашборд headline):        {total:>15,.2f} ₽")
        print()
        print(f"  Equity curve top label (Блок 1+2):   {closed_pnl + unrealized:>15,.2f} ₽")
        print(f"  ↑ график БЕЗ Прочих — поэтому расхождение с дашбордом")
        print()
        print(f"  Cash truth (Блок 4):                 {cash_truth:>15,.2f} ₽")
        print(f"  T-Bank app («Доход с учётом н/к»):       -248,552.57 ₽")
        print(f"  Diff с brокером:                     {total - (-248552.57):>15,.2f} ₽")
        pct = abs(total - (-248552.57)) / 248552.57 * 100
        print(f"  Diff %:                                       {pct:.2f}%")
        if pct < 1.0:
            print(f"\n  ✅ NATURAL MATCH (< 1%) — без подгонки")
        return 0
    finally:
        s.close()


if __name__ == "__main__":
    sys.exit(main())
