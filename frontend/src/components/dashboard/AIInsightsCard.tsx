'use client';

import { AlertTriangle, CheckCircle, Info, Lightbulb, Brain } from 'lucide-react';

type Recommendation = string | { type: string; icon: string; text: string };

interface AIInsightsCardProps {
  recommendations: Recommendation[];
  optimalF: number;
}

export function AIInsightsCard({ recommendations, optimalF }: AIInsightsCardProps) {
  const getRecText = (rec: Recommendation): string =>
    typeof rec === 'string' ? rec : rec.text || '';

  // Цвет акцентной полосы слева — по типу рекомендации
  const getBorderClass = (rec: Recommendation): string => {
    if (typeof rec === 'string') return 'border-l-[var(--accent)]';
    switch (rec.type) {
      case 'success': return 'border-l-[var(--success)]';
      case 'warning': return 'border-l-[var(--warning)]';
      case 'danger': return 'border-l-[var(--danger)]';
      case 'insight': return 'border-l-[var(--accent)]';
      default: return 'border-l-[var(--accent)]';
    }
  };

  const getRecIcon = (rec: Recommendation) => {
    if (typeof rec === 'string') return null;
    switch (rec.type) {
      case 'success': return <CheckCircle size={13} className="text-[var(--success)]" />;
      case 'warning': return <AlertTriangle size={13} className="text-[var(--warning)]" />;
      case 'danger':  return <AlertTriangle size={13} className="text-[var(--danger)]" />;
      case 'insight': return <Lightbulb size={13} className="text-[var(--accent)]" />;
      default:        return <Info size={13} className="text-[var(--text-tertiary)]" />;
    }
  };

  // Варианты риска по Optimal F
  const riskTiers = [
    { key: 'f10', label: 'Ультра-консерв. (f/10)', value: optimalF * 10, color: 'var(--accent)', recommended: true },
    { key: 'f4',  label: 'Консервативный (f/4)',   value: optimalF * 25, color: 'var(--success)' },
    { key: 'f2',  label: 'Умеренный (f/2)',        value: optimalF * 50, color: 'var(--accent-secondary)' },
    { key: 'f',   label: 'Агрессивный (f)',        value: optimalF * 100, color: 'var(--danger)' },
  ];

  return (
    <div className="cyber-card p-6 flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-[var(--radius-md)] bg-[var(--accent-soft)] text-[var(--accent)] flex items-center justify-center">
          <Brain size={16} />
        </div>
        <h3 className="text-base font-semibold flex-1">AI-инсайты</h3>
        <span className="badge badge-accent">live</span>
      </div>

      {/* Recommendations */}
      <div className="flex flex-col gap-2">
        {recommendations.map((rec, i) => (
          <div
            key={i}
            className={`flex items-start gap-2.5 px-3 py-2.5 rounded-[var(--radius-md)] bg-[var(--surface-2)] border-l-2 ${getBorderClass(rec)} text-[13px] leading-relaxed`}
          >
            {getRecIcon(rec) && <span className="flex-shrink-0 mt-0.5">{getRecIcon(rec)}</span>}
            <span>{getRecText(rec)}</span>
          </div>
        ))}
      </div>

      {/* Recommended risk highlight */}
      <div className="px-4 py-3 rounded-[var(--radius-md)] bg-[var(--accent-soft)] border border-[var(--accent)]/30">
        <div className="flex items-baseline justify-between gap-3 flex-wrap">
          <span className="text-[13px] font-medium text-[var(--accent-hover)]">
            Рекомендуемый риск
          </span>
          <span className="text-2xl font-bold tabular-nums text-[var(--foreground)]">
            {(optimalF * 10).toFixed(1)}%
          </span>
        </div>
        <div className="text-[11px] text-[var(--text-tertiary)] mt-0.5">
          Ультра-консервативный (f/10) — по Ральфу Винсу
        </div>
      </div>

      {/* Risk tiers comparison */}
      <div className="flex flex-col gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-1">
          Варианты риска
        </div>
        {riskTiers.map((tier) => (
          <div
            key={tier.key}
            className={`flex items-center justify-between gap-3 text-[13px] ${
              tier.recommended ? 'text-[var(--foreground)]' : 'text-[var(--text-secondary)]'
            }`}
          >
            <span className="flex items-center gap-2 min-w-0">
              <span
                className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                style={{ background: tier.color }}
              />
              <span className="truncate">{tier.label}</span>
              {tier.recommended && (
                <span className="text-[10px] text-[var(--accent)]">⭐</span>
              )}
            </span>
            <span className="font-medium tabular-nums" style={{ color: tier.color }}>
              {tier.value.toFixed(1)}%
            </span>
          </div>
        ))}
      </div>

      {/* Hints */}
      <div className="text-[11px] text-[var(--text-tertiary)] leading-relaxed pt-2 border-t border-[var(--border)]">
        <strong className="text-[var(--text-secondary)]">f/10</strong> — рекомендуется, минимальная просадка ·{' '}
        <strong className="text-[var(--text-secondary)]">f/4</strong> — стандартный выбор ·{' '}
        <strong className="text-[var(--text-secondary)]">f/2</strong> — для опытных ·{' '}
        <strong className="text-[var(--text-secondary)]">f</strong> — только разгон / «play money»
      </div>
    </div>
  );
}
