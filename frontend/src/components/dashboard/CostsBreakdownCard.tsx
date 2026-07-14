"use client";

/**
 * CostsBreakdownCard — отдельная плитка дашборда для расходов с разбивкой.
 *
 * Visual goal: одна большая сумма + 4 строки разбивки (брокер/маржа/сервис/налоги)
 * + явный hint снизу что «уже включены в Общий PnL» — это убирает перцептивный
 * двойной учёт. Расчёт P&L это число НЕ ПРИБАВЛЯЕТ — оно visualisation only.
 */
import { Info, Receipt } from "lucide-react";

interface Breakdown {
  broker_commission?: number;
  margin_fees?: number;
  service_fees?: number;
  taxes?: number;
}

interface Props {
  total: number;
  breakdown: Breakdown;
  formatCurrency: (n: number) => string;
}

export function CostsBreakdownCard({ total, breakdown, formatCurrency }: Props) {
  const rows: Array<{ label: string; value: number | undefined }> = [
    { label: "Брокер", value: breakdown.broker_commission },
    { label: "Маржа",  value: breakdown.margin_fees },
    { label: "Сервис", value: breakdown.service_fees },
    { label: "Налоги", value: breakdown.taxes },
  ];

  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-5 flex flex-col">
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <h3 className="text-[13px] font-medium text-[var(--text-secondary)]">Расходы</h3>
        <Receipt size={18} className="text-[var(--text-tertiary)]" />
      </div>

      {/* Big number */}
      <div className="text-[22px] font-semibold tabular-nums text-[var(--danger)] mb-4">
        {formatCurrency(total)}
      </div>

      {/* Breakdown rows */}
      <div className="space-y-1.5 border-t border-[var(--border)] pt-3 flex-1">
        {rows.map(({ label, value }) =>
          !value || Math.abs(value) < 1 ? null : (
            <div key={label} className="flex justify-between text-[13px]">
              <span className="text-[var(--text-secondary)]">{label}</span>
              <span className="tabular-nums font-medium">{formatCurrency(value)}</span>
            </div>
          ),
        )}
      </div>

      {/* Hint */}
      <div className="mt-3 pt-3 border-t border-[var(--border)] flex items-center gap-1.5 text-[11px] text-[var(--text-tertiary)]">
        <Info size={12} />
        <span>Уже включены в Общий PnL</span>
      </div>
    </div>
  );
}
