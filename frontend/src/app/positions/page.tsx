'use client';

/**
 * Открытые позиции — текущий портфель пользователя с unrealized PnL.
 *
 * Данные берём из локальной БД через GET /positions (не дёргаем Tinkoff API
 * на каждый рендер — это синхронизирует pipeline). Это даёт мгновенный
 * отклик и не упирается в rate-limit брокера.
 *
 * Update flow: кнопка «Обновить» вызывает sync для активного broker connection
 * (POST /broker/connections/{id}/sync), после чего повторно тянем /positions.
 */

import { useEffect, useState, useCallback, Fragment } from 'react';
import Link from 'next/link';
import { RefreshCw, Briefcase, TrendingUp, TrendingDown, Plug, ChevronDown, ChevronRight } from 'lucide-react';
import { AppShell } from '@/components/AppShell';
import { api, ApiError } from '@/lib/apiClient';
import { useToast } from '@/contexts/ToastContext';
import {
  joinPositionsTrades,
  type EnrichedPosition,
  type PositionTrade,
  type PositionResponse,
} from './joinPositionsTrades';
import { OpenPositionExpand } from './OpenPositionExpand';
import { parseApiDate } from '@/lib/dateUtils';
import { EditTradeModal, type EditableTrade } from '@/components/EditTradeModal';

/**
 * Форматирует сумму в валюте позиции из ответа API (rub/usd/eur/...).
 * Не используем глобальный `useSettings.formatCurrency` — у пользователя
 * там может быть выставлен USD, тогда как реальная валюта инструмента
 * приходит с бэка вместе с позицией (для MOEX всегда RUB).
 */
const CURRENCY_SYMBOLS: Record<string, string> = {
  rub: '₽',
  usd: '$',
  eur: '€',
  gbp: '£',
  cny: '¥',
  hkd: 'HK$',
};

/**
 * Нормализация «технических» кодов от Tinkoff API к ISO 4217.
 * - `pt`, `point`, `points` — это «пункты» цены фьючерса, не валюта.
 *   Реальные деньги (PnL, варм-маржа) у фьючерсов MOEX в рублях.
 * - `rur` — старый код RUB, давно deprecated.
 * - Пустая строка / unknown — также fallback на RUB (MOEX-only сервис).
 */
const normalizeCurrency = (raw: string | null | undefined): string => {
  const code = (raw || '').toLowerCase().replace(/\./g, '').trim();
  if (!code) return 'rub';
  if (['pt', 'point', 'points', 'пт'].includes(code)) return 'rub';
  if (code === 'rur') return 'rub';
  return code;
};

const formatMoney = (amount: number, currency: string = 'rub'): string => {
  const code = normalizeCurrency(currency);
  const symbol = CURRENCY_SYMBOLS[code] || code.toUpperCase();
  const formatted = Math.abs(amount).toLocaleString('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const sign = amount < 0 ? '-' : '';
  // Рубль и валютные коды без однобуквенных символов ставим после числа,
  // доллар/евро — перед (международная конвенция).
  if (code === 'usd' || code === 'eur' || code === 'gbp') {
    return `${sign}${symbol}${formatted}`;
  }
  return `${sign}${formatted} ${symbol}`;
};

interface SyncStatusConnection {
  id: number;
  broker: string;
  broker_account_id: string;
  is_syncing?: boolean;
}

interface SyncStatus {
  has_connections: boolean;
  connections: SyncStatusConnection[];
}

type SortKey = 'ticker' | 'pnl' | 'quantity';

/**
 * Дружелюбные ярлыки типа инструмента — показываем когда справочник ещё
 * не подтянул ticker/name для конкретного UID (новая серия фьючерсов /
 * экзотика). Лучше «Фьючерс • b4df2961» чем голый UUID.
 */
const INSTRUMENT_TYPE_LABELS: Record<string, string> = {
  futures: 'Фьючерс',
  share: 'Акция',
  bond: 'Облигация',
  etf: 'ETF',
  option: 'Опцион',
  currency: 'Валюта',
};

const formatInstrumentTypeLabel = (type: string): string =>
  INSTRUMENT_TYPE_LABELS[type?.toLowerCase()] || type || 'Инструмент';

/**
 * Если backend не успел подтянуть ticker — показываем читаемый fallback:
 * «Фьючерс • b4df2961» вместо «b4df2961-035a-4dcd-8372-9af0db10d2c9».
 * 8 символов UUID хватает для уникальности в рамках портфеля, а тип
 * сразу даёт пользователю понять что это за инструмент.
 */
const displayTicker = (p: PositionResponse): string => {
  if (p.ticker) return p.ticker;
  const short = p.instrument_uid.slice(0, 8);
  return `${formatInstrumentTypeLabel(p.instrument_type)} • ${short}`;
};

export default function PositionsPage() {
  const toast = useToast();
  const [enriched, setEnriched] = useState<EnrichedPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [activeConnectionId, setActiveConnectionId] = useState<number | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>('pnl');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [editingTrade, setEditingTrade] = useState<EditableTrade | null>(null);

  const fetchPositions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [snap, openPos] = await Promise.all([
        api.get<PositionResponse[]>('/positions'),
        api.get<PositionTrade[]>('/trades/positions?status=open').catch(() => [] as PositionTrade[]),
      ]);
      setEnriched(joinPositionsTrades(snap, openPos));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Не удалось загрузить позиции';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchActiveConnection = useCallback(async () => {
    try {
      const status = await api.get<SyncStatus>('/broker/sync-status');
      const first = status.connections?.[0];
      setActiveConnectionId(first?.id ?? null);
    } catch {
      setActiveConnectionId(null);
    }
  }, []);

  useEffect(() => {
    fetchPositions();
    fetchActiveConnection();
  }, [fetchPositions, fetchActiveConnection]);

  const handleSync = useCallback(async () => {
    if (!activeConnectionId) return;
    setSyncing(true);
    try {
      await api.post(`/broker/connections/${activeConnectionId}/sync`, {});
      await fetchPositions();
    } catch (err: unknown) {
      // Ошибка вторичного действия — через тост, чтобы не затирать таблицу (S3-21).
      toast.error(err instanceof ApiError ? err.toUserMessage() : 'Ошибка синхронизации');
    } finally {
      setSyncing(false);
    }
  }, [activeConnectionId, fetchPositions, toast]);

  // Сортировка локально на клиенте, ~7 позиций — это бесплатно.
  const sorted = [...enriched].sort((a, b) => {
    const sign = sortDir === 'asc' ? 1 : -1;
    if (sortKey === 'ticker') {
      return sign * (a.ticker || a.instrument_uid).localeCompare(b.ticker || b.instrument_uid);
    }
    if (sortKey === 'quantity') {
      return sign * (a.quantity - b.quantity);
    }
    // pnl
    const pa = a.unrealized_pnl ? parseFloat(a.unrealized_pnl) : 0;
    const pb = b.unrealized_pnl ? parseFloat(b.unrealized_pnl) : 0;
    return sign * (pa - pb);
  });

  const setSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const totalUnrealized = enriched.reduce(
    (sum, p) => sum + (p.unrealized_pnl ? parseFloat(p.unrealized_pnl) : 0),
    0,
  );
  // Валюта портфеля для совокупного PnL. Для MOEX все позиции в RUB —
  // берём с первой позиции, fallback на 'rub'.
  const portfolioCurrency = enriched[0]?.currency || 'rub';

  return (
    <>
    <AppShell pageTitle="Открытые позиции">
      <div className="p-6 md:p-8 max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold tracking-tight mb-1">Открытые позиции</h1>
            <p className="text-sm text-[var(--text-secondary)]">
              Текущий портфель с unrealized PnL по mark-to-market
            </p>
          </div>
          <button
            onClick={handleSync}
            disabled={!activeConnectionId || syncing}
            className="btn-secondary inline-flex items-center gap-2"
            title={
              activeConnectionId
                ? 'Запустить синхронизацию с брокером'
                : 'Сначала подключите брокера'
            }
          >
            <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} />
            {syncing ? 'Синхронизация…' : 'Обновить'}
          </button>
        </div>

        {/* Summary card */}
        {!loading && enriched.length > 0 && (
          <div className="mb-6 rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface)] p-5">
            <div className="flex flex-wrap items-center gap-6">
              <div>
                <div className="text-[12px] text-[var(--text-tertiary)] uppercase tracking-wider mb-1">
                  Позиций
                </div>
                <div className="text-2xl font-bold">{enriched.length}</div>
              </div>
              <div>
                <div className="text-[12px] text-[var(--text-tertiary)] uppercase tracking-wider mb-1">
                  Совокупный unrealized PnL
                </div>
                <div
                  className={`text-2xl font-bold font-mono ${
                    totalUnrealized >= 0 ? 'text-green-400' : 'text-red-400'
                  }`}
                >
                  {totalUnrealized >= 0 ? '+' : ''}
                  {formatMoney(totalUnrealized, portfolioCurrency)}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Loading state */}
        {loading && (
          <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface)] p-12 text-center">
            <RefreshCw className="mx-auto animate-spin text-[var(--text-secondary)]" size={32} />
            <p className="mt-3 text-sm text-[var(--text-secondary)]">Загружаем позиции…</p>
          </div>
        )}

        {/* Error state */}
        {error && !loading && (
          <div className="rounded-[var(--radius-xl)] border border-red-500/30 bg-red-500/5 p-5 text-sm text-red-400">
            Ошибка: {error}
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && enriched.length === 0 && (
          <div className="rounded-[var(--radius-xl)] border border-[var(--accent)]/30 bg-gradient-to-r from-[var(--accent-soft)] to-transparent p-8 text-center">
            <Briefcase className="mx-auto text-[var(--accent)]" size={40} />
            <h3 className="mt-4 text-lg font-semibold">Нет открытых позиций</h3>
            <p className="mt-2 text-sm text-[var(--text-secondary)] max-w-md mx-auto">
              {activeConnectionId
                ? 'Совершите сделку через брокера и нажмите «Обновить» — позиции появятся здесь.'
                : 'Подключите Тинькофф через API, чтобы увидеть свои открытые позиции с unrealized PnL.'}
            </p>
            {!activeConnectionId && (
              <Link
                href="/profile?tab=brokers"
                className="btn-primary mt-5 inline-flex items-center gap-2"
              >
                <Plug size={14} />
                Подключить брокера
              </Link>
            )}
          </div>
        )}

        {/* Table */}
        {!loading && !error && enriched.length > 0 && (
          <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-hover)] text-[var(--text-secondary)]">
                <tr>
                  <th className="px-2 py-3 w-8" aria-label="Expand"></th>
                  <th
                    onClick={() => setSort('ticker')}
                    className="px-4 py-3 text-left font-medium cursor-pointer hover:text-[var(--foreground)]"
                  >
                    Тикер
                  </th>
                  <th className="px-4 py-3 text-left font-medium">Название</th>
                  <th className="px-4 py-3 text-left font-medium">Тип</th>
                  <th
                    onClick={() => setSort('quantity')}
                    className="px-4 py-3 text-right font-medium cursor-pointer hover:text-[var(--foreground)]"
                  >
                    Кол-во
                  </th>
                  <th className="px-4 py-3 text-right font-medium">Ср. цена входа</th>
                  <th className="px-4 py-3 text-right font-medium">Текущая цена</th>
                  <th
                    onClick={() => setSort('pnl')}
                    className="px-4 py-3 text-right font-medium cursor-pointer hover:text-[var(--foreground)]"
                  >
                    Unrealized PnL
                  </th>
                  <th className="px-4 py-3 text-right font-medium">%</th>
                  <th className="px-4 py-3 text-right font-medium">Цена от</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((p) => {
                  const pnl = p.unrealized_pnl ? parseFloat(p.unrealized_pnl) : null;
                  const pct = p.unrealized_pnl_percent;
                  const isLong = p.quantity > 0;
                  const isExpanded = expanded.has(p.instrument_uid);
                  const toggleExpand = () => {
                    setExpanded((prev) => {
                      const next = new Set(prev);
                      if (next.has(p.instrument_uid)) next.delete(p.instrument_uid);
                      else next.add(p.instrument_uid);
                      return next;
                    });
                  };
                  return (
                    <Fragment key={p.instrument_uid}>
                      <tr
                        className="border-t border-[var(--border)] hover:bg-[var(--surface-hover)] cursor-pointer"
                        onClick={toggleExpand}
                      >
                        <td className="px-2 py-3 align-middle">
                          <button
                            className="text-[var(--text-secondary)] hover:text-[var(--foreground)]"
                            aria-label={isExpanded ? 'Свернуть' : 'Развернуть'}
                            onClick={(e) => { e.stopPropagation(); toggleExpand(); }}
                          >
                            {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                          </button>
                        </td>
                        <td className="px-4 py-3 font-mono font-semibold">
                          <span title={p.instrument_uid}>{displayTicker(p)}</span>
                        </td>
                        <td className="px-4 py-3 text-[var(--text-secondary)] max-w-xs truncate">
                          {p.name || (p.ticker ? '—' : 'Справочник обновится при следующей синхронизации')}
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-[11px] uppercase tracking-wider text-[var(--text-tertiary)]">
                            {p.instrument_type}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-mono">
                          <span className={isLong ? 'text-green-400' : 'text-red-400'}>
                            {isLong ? '+' : ''}
                            {p.quantity.toLocaleString('ru-RU')}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-mono">
                          {parseFloat(p.avg_entry_price).toLocaleString('ru-RU', {
                            maximumFractionDigits: 4,
                          })}
                        </td>
                        <td className="px-4 py-3 text-right font-mono">
                          {p.current_price
                            ? parseFloat(p.current_price).toLocaleString('ru-RU', {
                                maximumFractionDigits: 4,
                              })
                            : '—'}
                        </td>
                        <td className="px-4 py-3 text-right font-mono font-bold">
                          {pnl !== null ? (
                            <span className={pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                              {pnl >= 0 ? '+' : ''}
                              {formatMoney(pnl, p.currency)}
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="px-4 py-3 text-right font-mono">
                          {pct !== null && pct !== undefined ? (
                            <span
                              className={`inline-flex items-center gap-1 ${
                                pct >= 0 ? 'text-green-400' : 'text-red-400'
                              }`}
                            >
                              {pct >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                              {pct >= 0 ? '+' : ''}
                              {pct.toFixed(2)}%
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="px-4 py-3 text-right text-[11px] text-[var(--text-tertiary)]">
                          {p.last_priced_at
                            ? parseApiDate(p.last_priced_at).toLocaleString('ru-RU', {
                                hour: '2-digit',
                                minute: '2-digit',
                                day: '2-digit',
                                month: '2-digit',
                              })
                            : '—'}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr className="bg-[var(--surface-hover)]/40 border-t border-[var(--border)]">
                          <td colSpan={10} className="px-4 py-3">
                            <OpenPositionExpand
                              executions={p.open_executions}
                              onEdit={async (executionId) => {
                                try {
                                  const full = await api.get<EditableTrade>(`/trades/${executionId}`);
                                  setEditingTrade(full);
                                } catch (err: unknown) {
                                  // Вторичное действие — тост, таблица остаётся (S3-21).
                                  toast.error(err instanceof ApiError ? err.toUserMessage() : 'Не удалось загрузить сделку');
                                }
                              }}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
    {editingTrade !== null && (
      <EditTradeModal
        isOpen={true}
        trade={editingTrade}
        onClose={() => setEditingTrade(null)}
        onSuccess={() => {
          setEditingTrade(null);
          fetchPositions();
        }}
      />
    )}
    </>
  );
}
