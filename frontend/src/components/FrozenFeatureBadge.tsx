'use client';

/**
 * FrozenFeatureBadge — единый бейдж для «замороженных» Pro-фич на Free+.
 *
 * Эталон: .business/product/feature-canon/04-downgrade-experience.md
 * Решение: ADR-0005 (Reverse-Trial)
 *
 * Использование:
 *   <FrozenFeatureBadge tooltip="MAE/MFE для новых сделок доступно на Pro" />
 *
 * Соответствие DS:
 *   - Цвет: var(--info) #3b82f6 (60% opacity)
 *   - Иконка: <Snowflake size={12} /> из lucide-react (НЕ эмодзи 🧊)
 *   - Радиус: var(--radius-sm) 6px
 *   - Без glow / pulse / scale-анимаций
 */

import { ReactNode } from 'react';
import { Snowflake } from 'lucide-react';

interface FrozenFeatureBadgeProps {
  /** Tooltip-текст при наведении. По умолчанию — стандартный для DS. */
  tooltip?: string;
  /** Лейбл. По умолчанию — «Pro». */
  label?: string;
  /** Дополнительные классы для позиционирования (например absolute top-3 right-3). */
  className?: string;
}

export function FrozenFeatureBadge({
  tooltip = 'Эта фича доступна на Pro. Твой архив за trial — навсегда сохранён',
  label = 'Pro',
  className = '',
}: FrozenFeatureBadgeProps) {
  return (
    <span
      title={tooltip}
      className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium uppercase tracking-wide select-none ${className}`}
      style={{
        backgroundColor: 'rgba(59, 130, 246, 0.12)',
        color: 'rgba(59, 130, 246, 0.85)',
        border: '1px solid rgba(59, 130, 246, 0.25)',
      }}
    >
      <Snowflake size={12} aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}

/**
 * FrozenFeatureCTA — текстовая inline-кнопка-ссылка под замороженным виджетом.
 *
 *   [Возобновить → Pro 399₽]
 *
 * Соответствие DS: text-link стиль, без фоновой заливки.
 * UTM: добавляет ?from=frozen-<feature> для аналитики какой триггер чаще конвертит.
 */
interface FrozenFeatureCTAProps {
  children: ReactNode;
  /** Идентификатор виджета для UTM (например 'ai-insights', 'sync-tinkoff'). */
  feature: string;
  className?: string;
}

export function FrozenFeatureCTA({ children, feature, className = '' }: FrozenFeatureCTAProps) {
  return (
    <a
      href={`/pricing?from=frozen-${feature}`}
      className={`inline-flex items-center gap-1 text-sm hover:underline transition-colors ${className}`}
      style={{ color: 'var(--accent)' }}
    >
      {children}
    </a>
  );
}
