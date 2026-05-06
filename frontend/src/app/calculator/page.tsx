"use client";
/**
 * /calculator — Position Sizing Calculator.
 *
 * Решает первую задачу трейдера КАЖДЫЙ ДЕНЬ: «сколько лотов брать в этой сделке».
 *
 * Inputs:
 *   - Депозит (RUB) — берётся из stats.period_start_balance, можно перебить
 *   - Риск на сделку (% от депозита) — preset f/10 / f/4 / f/2 / Kelly (на основе Optimal F юзера)
 *   - Цена входа
 *   - Цена стопа
 *   - Тип инструмента (Stock — целое кол-во, Futures — в лотах со spec)
 *   - Опционально: Take Profit для расчёта R/R
 *
 * Outputs:
 *   - Position size (qty)
 *   - Risk RUB
 *   - Reward RUB и R/R (если TP)
 *   - Stop distance %
 *   - Notional value
 *   - Кнопка «Создать сделку с этими параметрами»
 */
import { useEffect, useMemo, useState } from "react";
import { Briefcase, Calculator, ArrowRight, Sparkles, Wallet } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AnalysisPageHeader } from "@/components/analysis/AnalysisPageHeader";
import { DashboardSkeleton } from "@/components/Skeleton";
import { api } from "@/lib/apiClient";
import { useAuth } from "@/contexts/AuthContext";
import { useSettings } from "@/contexts/SettingsContext";

interface DashboardStatsLite {
  period_start_balance?: number | null;
  current_balance?: number | null;
  optimal_f?: number;
}

type Direction = "long" | "short";
type AssetType = "stock" | "futures" | "crypto" | "forex";

export default function CalculatorPage() {
  const { user, isLoading: authLoading } = useAuth();
  const { formatCurrency } = useSettings();
  const [stats, setStats] = useState<DashboardStatsLite | null>(null);

  useEffect(() => {
    if (!user) return;
    api.get<DashboardStatsLite>("/stats/").then(setStats).catch(() => setStats(null));
  }, [user]);

  // Inputs
  const [deposit, setDeposit] = useState<string>("");
  const [riskPct, setRiskPct] = useState<string>("2");
  const [entryPrice, setEntryPrice] = useState<string>("");
  const [stopPrice, setStopPrice] = useState<string>("");
  const [takeProfit, setTakeProfit] = useState<string>("");
  const [direction, setDirection] = useState<Direction>("long");
  const [assetType, setAssetType] = useState<AssetType>("stock");
  // Лот-спецификация для фьючерсов (point value × lot multiplier).
  // Для Si это 1 ₽/пункт, для RTS — ~12.5 ₽, для BR — ~$0.01 × USD/RUB.
  const [pointValue, setPointValue] = useState<string>("1");

  // При первой загрузке stats — заполняем deposit
  useEffect(() => {
    if (deposit === "" && stats?.current_balance) {
      setDeposit(String(Math.round(stats.current_balance)));
    }
  }, [stats, deposit]);

  const optimalF = stats?.optimal_f || null;

  const presets = useMemo(() => {
    const presetList: Array<{ label: string; pct: number; tone: string; hint: string }> = [
      { label: "0.5%", pct: 0.5, tone: "success", hint: "Микро-риск, для агрессивной серии" },
      { label: "1%", pct: 1, tone: "success", hint: "Консервативно, выживаешь долго" },
      { label: "2%", pct: 2, tone: "neutral", hint: "Классика для retail" },
      { label: "3%", pct: 3, tone: "warning", hint: "Уже агрессивно" },
      { label: "5%", pct: 5, tone: "danger", hint: "Очень агрессивно" },
    ];
    if (optimalF && optimalF > 0) {
      // Прибавляем калиброванные на персональный Optimal F
      presetList.push({
        label: `f/10 (${(optimalF / 10 * 100).toFixed(1)}%)`,
        pct: optimalF / 10 * 100,
        tone: "accent",
        hint: "Рекомендуемый — десятая часть Optimal F",
      });
      presetList.push({
        label: `f/4 (${(optimalF / 4 * 100).toFixed(1)}%)`,
        pct: optimalF / 4 * 100,
        tone: "accent",
        hint: "Полу-Kelly, агрессивнее",
      });
    }
    return presetList;
  }, [optimalF]);

  const calc = useMemo(() => {
    const dep = parseFloat(deposit);
    const risk = parseFloat(riskPct);
    const entry = parseFloat(entryPrice);
    const stop = parseFloat(stopPrice);
    const tp = parseFloat(takeProfit);
    const pv = parseFloat(pointValue) || 1;

    if (!dep || !risk || !entry || !stop) return null;

    const stopDistance = direction === "long" ? entry - stop : stop - entry;
    if (stopDistance <= 0) {
      return { error: direction === "long"
        ? "Стоп должен быть НИЖЕ цены входа для лонга."
        : "Стоп должен быть ВЫШЕ цены входа для шорта." };
    }

    const stopDistancePct = (stopDistance / entry) * 100;
    const riskRub = dep * (risk / 100);

    let qty: number;
    let notional: number;
    if (assetType === "futures") {
      // Для фьючерсов риск на 1 лот = stopDistance × pointValue
      const riskPerLot = stopDistance * pv;
      qty = riskPerLot > 0 ? Math.floor(riskRub / riskPerLot) : 0;
      notional = qty * entry * pv;
    } else {
      // Для акций/крипты/форекса риск на 1 единицу = stopDistance в валюте
      const riskPerUnit = stopDistance;
      qty = riskPerUnit > 0 ? Math.floor(riskRub / riskPerUnit) : 0;
      notional = qty * entry;
    }

    const actualRisk = assetType === "futures" ? qty * stopDistance * pv : qty * stopDistance;

    let reward: number | null = null;
    let rrRatio: number | null = null;
    if (tp && tp > 0) {
      const rewardDistance = direction === "long" ? tp - entry : entry - tp;
      if (rewardDistance > 0) {
        reward = assetType === "futures" ? qty * rewardDistance * pv : qty * rewardDistance;
        rrRatio = rewardDistance / stopDistance;
      }
    }

    return {
      qty,
      notional,
      actualRisk,
      stopDistance,
      stopDistancePct,
      reward,
      rrRatio,
      // Что % депозита будет в позиции (не риск, а размер)
      notionalPctOfDeposit: (notional / dep) * 100,
    };
  }, [deposit, riskPct, entryPrice, stopPrice, takeProfit, direction, assetType, pointValue]);

  if (authLoading) return <DashboardSkeleton />;

  return (
    <AppShell pageTitle="Калькулятор позиции">
      <div className="p-6 md:p-8 max-w-5xl mx-auto">
        <AnalysisPageHeader
          title="Калькулятор позиции"
          subtitle="Сколько лотов брать в сделке, чтобы рискнуть ровно тем, что готов потерять."
          Icon={Calculator}
          accentColor="indigo"
        />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* INPUTS */}
          <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-5 md:p-6">
            <h3 className="text-[14px] font-semibold mb-4 flex items-center gap-2">
              <Wallet size={14} className="text-[var(--accent)]" />
              Параметры сделки
            </h3>

            <div className="space-y-4">
              <Row label="Депозит, ₽">
                <input
                  type="number"
                  value={deposit}
                  onChange={(e) => setDeposit(e.target.value)}
                  className="input-cyber w-full text-right tabular-nums"
                  placeholder="100000"
                />
              </Row>

              <div>
                <Row label="Риск на сделку, %">
                  <input
                    type="number"
                    step="0.1"
                    value={riskPct}
                    onChange={(e) => setRiskPct(e.target.value)}
                    className="input-cyber w-full text-right tabular-nums"
                  />
                </Row>
                {/* Presets */}
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {presets.map((p) => (
                    <button
                      key={p.label}
                      onClick={() => setRiskPct(p.pct.toFixed(2))}
                      className={`text-[11px] px-2 py-1 rounded-[var(--radius-pill)] border transition-colors ${
                        Math.abs(parseFloat(riskPct) - p.pct) < 0.01
                          ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                          : "border-[var(--border)] hover:border-[var(--border-strong)] text-[var(--text-secondary)]"
                      }`}
                      title={p.hint}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
                {optimalF && (
                  <div className="mt-2 text-[11px] text-[var(--text-tertiary)] flex items-center gap-1.5">
                    <Sparkles size={11} className="text-[var(--accent)]" />
                    Твой Optimal F = {(optimalF * 100).toFixed(1)}%. Рекомендуется f/10 = {(optimalF * 10).toFixed(1)}%.
                  </div>
                )}
              </div>

              <Row label="Направление">
                <div className="flex gap-2">
                  <DirBtn active={direction === "long"} onClick={() => setDirection("long")} tone="success">LONG</DirBtn>
                  <DirBtn active={direction === "short"} onClick={() => setDirection("short")} tone="danger">SHORT</DirBtn>
                </div>
              </Row>

              <Row label="Тип актива">
                <select
                  value={assetType}
                  onChange={(e) => setAssetType(e.target.value as AssetType)}
                  className="input-cyber w-full"
                >
                  <option value="stock">Акция</option>
                  <option value="futures">Фьючерс</option>
                  <option value="crypto">Криптовалюта</option>
                  <option value="forex">Forex</option>
                </select>
              </Row>

              {assetType === "futures" && (
                <Row label="Стоимость пункта, ₽">
                  <input
                    type="number"
                    step="0.01"
                    value={pointValue}
                    onChange={(e) => setPointValue(e.target.value)}
                    className="input-cyber w-full text-right tabular-nums"
                    placeholder="1 для Si, ~12.5 для RTS"
                  />
                </Row>
              )}

              <div className="border-t border-[var(--border)] pt-4 space-y-4">
                <Row label="Цена входа">
                  <input
                    type="number"
                    step="0.01"
                    value={entryPrice}
                    onChange={(e) => setEntryPrice(e.target.value)}
                    className="input-cyber w-full text-right tabular-nums"
                  />
                </Row>
                <Row label="Стоп-лосс">
                  <input
                    type="number"
                    step="0.01"
                    value={stopPrice}
                    onChange={(e) => setStopPrice(e.target.value)}
                    className="input-cyber w-full text-right tabular-nums"
                  />
                </Row>
                <Row label="Take-profit (опц.)">
                  <input
                    type="number"
                    step="0.01"
                    value={takeProfit}
                    onChange={(e) => setTakeProfit(e.target.value)}
                    className="input-cyber w-full text-right tabular-nums"
                  />
                </Row>
              </div>
            </div>
          </div>

          {/* OUTPUTS */}
          <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-5 md:p-6">
            <h3 className="text-[14px] font-semibold mb-4 flex items-center gap-2">
              <Briefcase size={14} className="text-[var(--accent)]" />
              Результат
            </h3>

            {!calc ? (
              <div className="text-[13px] text-[var(--text-tertiary)] py-12 text-center">
                Заполните депозит, риск %, цену входа и стоп — увидите расчёт.
              </div>
            ) : "error" in calc ? (
              <div className="rounded-[var(--radius-md)] border border-[var(--danger)] bg-[var(--danger-soft)] p-3 text-[13px] text-[var(--danger)]">
                {calc.error}
              </div>
            ) : (
              <div className="space-y-3">
                <BigStat
                  label="Размер позиции"
                  value={`${calc.qty.toLocaleString("ru-RU")} ${assetType === "futures" ? "контр." : "шт."}`}
                  tone="accent"
                />
                <div className="grid grid-cols-2 gap-3">
                  <SmallStat
                    label="Реальный риск"
                    value={`${formatCurrency(calc.actualRisk)}`}
                    sub={`${((calc.actualRisk / parseFloat(deposit)) * 100).toFixed(2)}% депозита`}
                  />
                  <SmallStat
                    label="Стоп от входа"
                    value={`${calc.stopDistancePct.toFixed(2)}%`}
                    sub={`${calc.stopDistance.toFixed(2)} пунктов`}
                  />
                  <SmallStat
                    label="Notional value"
                    value={formatCurrency(calc.notional)}
                    sub={`${calc.notionalPctOfDeposit.toFixed(0)}% депозита`}
                  />
                  {calc.reward !== null && calc.rrRatio !== null && (
                    <SmallStat
                      label="Потенц. прибыль"
                      value={formatCurrency(calc.reward)}
                      sub={`R/R = ${calc.rrRatio.toFixed(2)}`}
                      tone="success"
                    />
                  )}
                </div>

                {calc.rrRatio !== null && (
                  <div
                    className={`rounded-[var(--radius-md)] border p-3 text-[12px] ${
                      calc.rrRatio >= 2
                        ? "border-[var(--success)]/30 bg-[var(--success-soft)] text-[var(--success)]"
                        : calc.rrRatio >= 1
                        ? "border-[var(--warning)]/30 bg-[var(--warning-soft)] text-[var(--warning)]"
                        : "border-[var(--danger)]/30 bg-[var(--danger-soft)] text-[var(--danger)]"
                    }`}
                  >
                    {calc.rrRatio >= 2
                      ? `R/R ${calc.rrRatio.toFixed(2)} — отлично. Можешь проигрывать каждую вторую и быть в плюсе.`
                      : calc.rrRatio >= 1
                      ? `R/R ${calc.rrRatio.toFixed(2)} — приемлемо, но нужен win rate > 50%.`
                      : `R/R ${calc.rrRatio.toFixed(2)} — низко. Тейк ближе стопа = нужен очень высокий win rate.`}
                  </div>
                )}

                <button
                  onClick={() => {
                    // Передаём параметры в AddTradeModal через events
                    if (typeof window === "undefined") return;
                    window.dispatchEvent(
                      new CustomEvent("eqio:add-trade", {
                        detail: {
                          entry_price: parseFloat(entryPrice),
                          stop_loss: parseFloat(stopPrice),
                          take_profit: takeProfit ? parseFloat(takeProfit) : undefined,
                          quantity: calc.qty,
                          direction,
                          risk_amount: calc.actualRisk,
                        },
                      }),
                    );
                  }}
                  className="btn-primary w-full justify-center mt-2"
                >
                  Создать сделку с этими параметрами
                  <ArrowRight size={14} />
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Educational footer */}
        <div className="mt-6 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4 text-[12px] text-[var(--text-secondary)]">
          <div className="font-semibold mb-2 text-[var(--foreground)]">Как читать расчёт</div>
          <ul className="space-y-1.5 list-disc pl-5">
            <li><strong>Размер позиции</strong> — округлено вниз, чтобы не превысить риск.</li>
            <li><strong>Риск на сделку 2%</strong> — классика. При 50 убыточных подряд (мало вероятно) теряешь 64% — пережить можно.</li>
            <li><strong>R/R ≥ 2</strong> — даже при WR 40% стратегия плюсовая. Меньше — нужен высокий WR.</li>
            <li><strong>Optimal F (от Vince)</strong> — теоретически оптимальный % на основе твоей истории. Реально брать <em>десятую часть</em> (f/10) — даёт защиту от ruin.</li>
          </ul>
        </div>
      </div>
    </AppShell>
  );
}

// ──────────────────────────────────────────────────────────────────
//  Sub-components
// ──────────────────────────────────────────────────────────────────

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[12px] font-medium text-[var(--text-secondary)] mb-1.5 block">{label}</span>
      {children}
    </label>
  );
}

function DirBtn({
  children,
  active,
  onClick,
  tone,
}: {
  children: React.ReactNode;
  active: boolean;
  onClick: () => void;
  tone: "success" | "danger";
}) {
  const activeBg = tone === "success" ? "bg-[var(--success-soft)] text-[var(--success)] border-[var(--success)]/40" : "bg-[var(--danger-soft)] text-[var(--danger)] border-[var(--danger)]/40";
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 px-4 py-2 rounded-[var(--radius-md)] border text-[13px] font-semibold transition-colors ${
        active ? activeBg : "border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--border-strong)]"
      }`}
    >
      {children}
    </button>
  );
}

function BigStat({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "accent" }) {
  return (
    <div className={`rounded-[var(--radius-lg)] p-4 ${tone === "accent" ? "bg-[var(--accent-soft)]" : "bg-[var(--surface-2)]"}`}>
      <div className={`text-[11px] font-medium ${tone === "accent" ? "text-[var(--accent)]" : "text-[var(--text-tertiary)]"} uppercase tracking-wider mb-1`}>
        {label}
      </div>
      <div className={`text-[28px] font-bold tracking-tight tabular-nums ${tone === "accent" ? "text-[var(--accent-hover)]" : ""}`}>
        {value}
      </div>
    </div>
  );
}

function SmallStat({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "neutral" | "success";
}) {
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--border)] p-3">
      <div className="text-[11px] text-[var(--text-tertiary)] mb-0.5">{label}</div>
      <div className={`text-[16px] font-semibold tabular-nums ${tone === "success" ? "text-[var(--success)]" : ""}`}>
        {value}
      </div>
      {sub && <div className="text-[11px] text-[var(--text-tertiary)] mt-0.5">{sub}</div>}
    </div>
  );
}
