'use client';

import React from 'react';
import Image from 'next/image';
import { Trash2, Edit2, ChevronDown, ChevronRight, Lock, Loader2, BarChart2, StickyNote, ImageIcon } from 'lucide-react';
import { getApiUrl } from '@/lib/apiClient';
import { AssetTypeIcon } from './AssetTypeIcon';
import type { Trade } from './types';
import { formatHoldingTime } from './types';

interface TradeRowProps {
  trade: Trade;
  isExpanded: boolean;
  unrealized?: { pnl: number; price: number };
  visibleColumnsSize: number;
  isColumnVisible: (id: string) => boolean;
  isCalculatingMAE: boolean;
  onToggleExpand: (tradeId: number) => void;
  onOpenClose: (trade: Trade) => void;
  onEdit: (trade: Trade) => void;
  onDelete: (tradeId: number) => void;
  onCalculateMAE: (tradeIds: number[]) => void;
}

export function TradeRow({
  trade,
  isExpanded,
  unrealized,
  visibleColumnsSize,
  isColumnVisible,
  isCalculatingMAE,
  onToggleExpand,
  onOpenClose,
  onEdit,
  onDelete,
  onCalculateMAE,
}: TradeRowProps) {
  const hasDetails = trade.setup_name || trade.news_event || trade.notes || trade.entry_reason || trade.tags?.length || trade.operations?.length || trade.mood || trade.discipline || trade.screenshot_url || trade.setup;
  const pnlValue = trade.net_pnl ?? trade.pnl;

  return (
    <React.Fragment>
      {/* Компактная строка */}
      <tr
        className={`border-b border-border/30 hover:bg-white/5 transition-colors ${hasDetails ? 'cursor-pointer' : ''}`}
        onClick={() => hasDetails && onToggleExpand(trade.id)}
      >
        {/* Expand Icon */}
        <td className="py-2 pl-2">
          {hasDetails && (
            <button className="text-accent/50 hover:text-accent">
              {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>
          )}
        </td>

        {/* Дата */}
        {isColumnVisible('date') && (
          <td className="py-2 font-mono text-xs">
            <div className="flex flex-col gap-1 leading-tight">
              <div>
                <span className="text-[9px] uppercase tracking-wide text-slate-500 mr-1">ВХ</span>
                <span>{new Date(trade.entry_at).toLocaleDateString('ru-RU', {day: '2-digit', month: '2-digit', year: '2-digit'})}</span>
                <span className="text-slate-500 ml-1 text-[10px]">
                  {new Date(trade.entry_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                </span>
              </div>
              <div>
                <span className="text-[9px] uppercase tracking-wide text-slate-500 mr-1">ВЫХ</span>
                {trade.exit_at ? (
                  <>
                    <span>{new Date(trade.exit_at).toLocaleDateString('ru-RU', {day: '2-digit', month: '2-digit', year: '2-digit'})}</span>
                    <span className="text-slate-500 ml-1 text-[10px]">
                      {new Date(trade.exit_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                    </span>
                  </>
                ) : (
                  <span className="text-accent/80">ОТКРЫТА</span>
                )}
              </div>
            </div>
          </td>
        )}

        {/* Тикер (с иконкой типа актива) */}
        {isColumnVisible('ticker') && (
          <td className="py-2">
            <div className="flex items-center gap-1.5">
              <AssetTypeIcon type={trade.instrument_type_v2 || trade.asset_type} />
              <span className="font-bold font-mono">{trade.symbol}</span>
            </div>
          </td>
        )}

        {/* Название */}
        {isColumnVisible('name') && (
          <td className="py-2 text-xs text-slate-300 max-w-44">
            {trade.asset_name ? (
              <span className="truncate block" title={trade.asset_name}>
                {trade.asset_name}
              </span>
            ) : (
              <span className="text-slate-600">—</span>
            )}
          </td>
        )}

        {/* Сторона */}
        {isColumnVisible('direction') && (
          <td className="py-2">
            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
              trade.direction === 'long' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
            }`}>
              {trade.isAddition ? '+ ДОБ.' : (trade.direction === 'long' ? 'ЛОНГ' : 'ШОРТ')}
            </span>
          </td>
        )}

        {/* Кол-во */}
        {isColumnVisible('quantity') && (
          <td className="py-2 font-mono text-xs">
            {trade.quantity.toLocaleString('ru-RU')}
          </td>
        )}

        {/* Вход */}
        {isColumnVisible('entry') && (
          <td className="py-2 font-mono text-xs">
            {trade.entry_price.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}
          </td>
        )}

        {/* Выход */}
        {isColumnVisible('exit') && (
          <td className="py-2 font-mono text-xs">
            {trade.exit_price
              ? trade.exit_price.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
              : <span className="text-slate-500">—</span>
            }
          </td>
        )}

        {/* Таймфрейм */}
        {isColumnVisible('timeframe') && (
          <td className="py-2 text-center">
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
              {trade.timeframe || '—'}
            </span>
          </td>
        )}

        {/* Комиссия */}
        {isColumnVisible('commission') && (
          <td className="py-2 font-mono text-xs text-red-400">
            {(trade.commission || 0) > 0 ? `-${Number(trade.commission).toFixed(0)}` : '—'}
          </td>
        )}

        {/* Своп */}
        {isColumnVisible('swap') && (
          <td className="py-2 font-mono text-xs text-red-400">
            {(trade.swap || 0) > 0 ? `-${Number(trade.swap).toFixed(0)}` : '—'}
          </td>
        )}

        {/* Уверенность */}
        {isColumnVisible('confidence') && (
          <td className="py-2 text-center">
            {trade.confidence ? (
              <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                trade.confidence >= 8 ? 'bg-green-500/20 text-green-400' :
                trade.confidence >= 5 ? 'bg-yellow-500/20 text-yellow-400' :
                'bg-red-500/20 text-red-400'
              }`}>{trade.confidence}</span>
            ) : '—'}
          </td>
        )}

        {/* Риск */}
        {isColumnVisible('risk') && (
          <td className="py-2 font-mono text-xs">
            {trade.risk_amount ? `${trade.risk_amount.toLocaleString('ru-RU')} ₽` : '—'}
          </td>
        )}

        {/* R-Multiple */}
        {isColumnVisible('rMultiple') && (
          <td className="py-2 font-mono text-xs">
            {trade.r_multiple ? (
              <span className={trade.r_multiple >= 1 ? 'text-green-400' : trade.r_multiple < 0 ? 'text-red-400' : ''}>
                {trade.r_multiple.toFixed(1)}R
              </span>
            ) : '—'}
          </td>
        )}

        {/* PnL */}
        {isColumnVisible('pnl') && (() => {
          // Источник процента в порядке приоритета:
          // 1. trade.pnl_pct с бэка (учитывает direction + комиссии,
          //    знак всегда совпадает с trade.pnl — single source of truth).
          // 2. Для открытой позиции (unrealized) считаем локально
          //    от текущей цены с учётом direction.
          // 3. Fallback для legacy-сделок без pnl_pct: формула
          //    через цены входа/выхода.
          let pnlPercent = 0;
          if (unrealized?.price && trade.entry_price > 0) {
            const isLong = trade.direction.toLowerCase() === 'long';
            pnlPercent = isLong
              ? ((unrealized.price - trade.entry_price) / trade.entry_price * 100)
              : ((trade.entry_price - unrealized.price) / trade.entry_price * 100);
          } else if (trade.pnl_pct !== null && trade.pnl_pct !== undefined) {
            pnlPercent = trade.pnl_pct;
          } else if (trade.exit_price && trade.entry_price > 0) {
            const isLong = trade.direction.toLowerCase() === 'long';
            pnlPercent = isLong
              ? ((trade.exit_price - trade.entry_price) / trade.entry_price * 100)
              : ((trade.entry_price - trade.exit_price) / trade.entry_price * 100);
          }

          return (
            <td className="py-2 font-mono font-bold">
              {unrealized ? (
                <div className="flex flex-col">
                  <span className={unrealized.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                    {unrealized.pnl >= 0 ? '+' : ''}{unrealized.pnl.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽
                  </span>
                  <span className={`text-[10px] ${pnlPercent >= 0 ? 'text-green-400/60' : 'text-red-400/60'}`}>
                    {pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%
                  </span>
                </div>
              ) : pnlValue !== null && pnlValue !== undefined ? (
                <div className="flex flex-col">
                  <span className={Number(pnlValue) >= 0 ? 'text-green-400' : 'text-red-400'}>
                    {Number(pnlValue) >= 0 ? '+' : ''}{Number(pnlValue).toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽
                  </span>
                  <span className={`text-[10px] ${pnlPercent >= 0 ? 'text-green-400/60' : 'text-red-400/60'}`}>
                    {pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%
                  </span>
                </div>
              ) : (
                <span className="text-slate-500">—</span>
              )}
            </td>
          );
        })()}

        {/* Holding (продолжительность сделки) */}
        {isColumnVisible('holding') && (
          <td className="py-2 font-mono text-xs text-slate-300">
            {trade.exit_at ? (
              formatHoldingTime(trade.holding_time_minutes)
            ) : (
              <span className="text-[10px] font-bold bg-accent/20 text-accent px-1.5 py-0.5 rounded">
                OPEN
              </span>
            )}
          </td>
        )}

        {/* Сетап */}
        {isColumnVisible('setup') && (
          <td className="py-2 text-xs max-w-24">
            {trade.setup ? (
              <div className="flex items-center gap-1 truncate">
                <span style={{ color: trade.setup.color }}>{trade.setup.icon}</span>
                <span className="truncate" style={{ color: trade.setup.color }}>{trade.setup.name}</span>
              </div>
            ) : (
              <span className="text-slate-400 truncate block">{trade.setup_name || '—'}</span>
            )}
          </td>
        )}

        {/* Note indicator */}
        {isColumnVisible('note') && (
          <td className="py-2 text-center">
            <div className="flex items-center justify-center gap-1">
              {trade.notes && (
                <StickyNote
                  size={12}
                  className="text-amber-400/70"
                  aria-label="Есть заметка"
                />
              )}
              {trade.screenshot_url && (
                <ImageIcon
                  size={12}
                  className="text-blue-400/70"
                  aria-label="Есть скриншот"
                />
              )}
              {!trade.notes && !trade.screenshot_url && (
                <span className="text-slate-700">—</span>
              )}
            </div>
          </td>
        )}

        {/* Статус (legacy, hidden by default) */}
        {isColumnVisible('status') && (
          <td className="py-2">
            {trade.exit_at ? (
              <span className="text-[10px] font-mono text-slate-400">
                {formatHoldingTime(trade.holding_time_minutes)}
              </span>
            ) : (
              <span className="text-[10px] font-bold bg-accent/20 text-accent px-1.5 py-0.5 rounded animate-pulse">
                OPEN
              </span>
            )}
          </td>
        )}

        {/* Теги */}
        {isColumnVisible('tags') && (
          <td className="py-2">
            <div className="flex gap-0.5 flex-wrap">
              {trade.tags?.slice(0, 2).map(tag => (
                <span key={tag} className="text-[9px] font-mono border border-accent/30 px-1 rounded text-accent">
                  #{tag}
                </span>
              ))}
              {(trade.tags?.length || 0) > 2 && (
                <span className="text-[9px] text-slate-500">+{(trade.tags?.length || 0) - 2}</span>
              )}
            </div>
          </td>
        )}

        {/* Плечо */}
        {isColumnVisible('leverage') && (
          <td className="py-2 font-mono text-xs text-center">
            {trade.leverage ? `${trade.leverage}x` : '—'}
          </td>
        )}

        {/* Действия */}
        <td className="py-2 pr-2">
          <div className="flex justify-end gap-1">
            {!trade.exit_at && (
              <button
                onClick={(e) => { e.stopPropagation(); onOpenClose(trade); }}
                className="text-yellow-500/50 hover:text-yellow-500 p-1"
                title="Закрыть"
              >
                <Lock size={14} />
              </button>
            )}
            <button
              onClick={(e) => { e.stopPropagation(); onEdit(trade); }}
              className="text-accent/50 hover:text-accent p-1"
            >
              <Edit2 size={14} />
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(trade.id); }}
              className="text-red-500/50 hover:text-red-500 p-1"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </td>
      </tr>

      {/* Развёрнутые детали */}
      {isExpanded && (
        <tr className="bg-slate-800/30 border-b border-border/30">
          <td colSpan={visibleColumnsSize + 2} className="p-4">
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 text-xs">
              {/* Сетап */}
              <div>
                <span className="text-slate-500 block mb-1">Сетап</span>
                {trade.setup ? (
                  <span className="font-medium flex items-center gap-1" style={{ color: trade.setup.color }}>
                    {trade.setup.icon} {trade.setup.name}
                  </span>
                ) : (
                  <span className="font-medium">{trade.setup_name || '-'}</span>
                )}
              </div>
              <div>
                <span className="text-slate-500 block mb-1">Событие</span>
                <span className="font-medium">{trade.news_event || '-'}</span>
              </div>

              {/* Психо-метрики */}
              <div>
                <span className="text-slate-500 block mb-1">Настроение</span>
                {trade.mood ? (
                  <span className="text-lg">{['😤', '😟', '😐', '😊', '🚀'][trade.mood - 1]}</span>
                ) : '-'}
              </div>
              <div>
                <span className="text-slate-500 block mb-1">Уверенность</span>
                {trade.confidence ? (
                  <span className={`px-1.5 py-0.5 rounded font-medium ${
                    trade.confidence >= 4 ? 'bg-green-500/20 text-green-400' :
                    trade.confidence >= 3 ? 'bg-yellow-500/20 text-yellow-400' :
                    'bg-red-500/20 text-red-400'
                  }`}>{trade.confidence}/5</span>
                ) : '-'}
              </div>
              <div>
                <span className="text-slate-500 block mb-1">Дисциплина</span>
                {trade.discipline ? (
                  <span className={`px-1.5 py-0.5 rounded font-medium ${
                    trade.discipline >= 4 ? 'bg-green-500/20 text-green-400' :
                    trade.discipline >= 3 ? 'bg-yellow-500/20 text-yellow-400' :
                    'bg-red-500/20 text-red-400'
                  }`}>{['Нарушил', 'Частично', 'Нейтр.', 'Следовал', 'Идеально'][trade.discipline - 1]}</span>
                ) : '-'}
              </div>
              <div>
                <span className="text-slate-500 block mb-1">Комиссия</span>
                <span className="font-medium text-red-400">
                  {(trade.commission || 0) > 0 ? `-${Number(trade.commission).toFixed(2)} ₽` : '-'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block mb-1">Своп</span>
                <span className="font-medium text-red-400">
                  {(trade.swap || 0) > 0 ? `-${Number(trade.swap).toFixed(2)} ₽` : '-'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block mb-1">Время в сделке</span>
                <span className="font-medium text-cyan-400">
                  {trade.holding_time_minutes ? formatHoldingTime(trade.holding_time_minutes) : '-'}
                </span>
              </div>

              {/* Вторая строка */}
              <div>
                <span className="text-slate-500 block mb-1">SL</span>
                <span className="font-mono">{trade.stop_loss?.toLocaleString('ru-RU') || '-'}</span>
              </div>
              <div>
                <span className="text-slate-500 block mb-1">TP</span>
                <span className="font-mono">{trade.take_profit?.toLocaleString('ru-RU') || '-'}</span>
              </div>
              <div>
                <span className="text-slate-500 block mb-1">Риск</span>
                <span className="font-mono">{trade.risk_amount ? `${trade.risk_amount.toLocaleString('ru-RU')} ₽` : '-'}</span>
              </div>
              <div>
                <span className="text-slate-500 block mb-1">R-Multiple</span>
                <span className={`font-mono font-bold ${
                  trade.r_multiple && trade.r_multiple >= 1 ? 'text-green-400' :
                  trade.r_multiple && trade.r_multiple < 0 ? 'text-red-400' : ''
                }`}>
                  {trade.r_multiple ? `${trade.r_multiple.toFixed(2)}R` : '-'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block mb-1">Причина выхода</span>
                <span className="font-medium">{trade.exit_reason || '-'}</span>
              </div>
              <div>
                <span className="text-slate-500 block mb-1">Плечо</span>
                <span className="font-mono">{trade.leverage ? `${trade.leverage}x` : '-'}</span>
              </div>

              {/* MAE/MFE Анализ */}
              {trade.exit_at && (trade.mae_price || trade.mfe_price) && (
                <div className="col-span-full border border-accent/20 rounded-lg p-3 bg-accent/5">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-accent font-bold text-sm">📊 MAE/MFE Анализ</span>
                    {!trade.mae_price && !trade.mfe_price && (
                      <span className="text-slate-500 text-[10px]">(нет данных)</span>
                    )}
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {/* MAE */}
                    <div>
                      <span className="text-slate-500 block mb-1 text-[10px]">MAE (худшая цена)</span>
                      <span className="font-mono text-red-400">
                        {trade.mae_price ? trade.mae_price.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) : '—'}
                      </span>
                      {trade.mae_price && trade.entry_price && (
                        <span className="text-red-400/70 text-[10px] ml-1">
                          ({trade.direction === 'long'
                            ? `-${(((trade.entry_price - trade.mae_price) / trade.entry_price) * 100).toFixed(2)}%`
                            : `-${(((trade.mae_price - trade.entry_price) / trade.entry_price) * 100).toFixed(2)}%`
                          })
                        </span>
                      )}
                    </div>

                    {/* MFE */}
                    <div>
                      <span className="text-slate-500 block mb-1 text-[10px]">MFE (лучшая цена)</span>
                      <span className="font-mono text-green-400">
                        {trade.mfe_price ? trade.mfe_price.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) : '—'}
                      </span>
                      {trade.mfe_price && trade.entry_price && (
                        <span className="text-green-400/70 text-[10px] ml-1">
                          (+{trade.direction === 'long'
                            ? (((trade.mfe_price - trade.entry_price) / trade.entry_price) * 100).toFixed(2)
                            : (((trade.entry_price - trade.mfe_price) / trade.entry_price) * 100).toFixed(2)
                          }%)
                        </span>
                      )}
                    </div>

                    {/* Edge Ratio */}
                    {trade.mae_price && trade.mfe_price && trade.entry_price && (
                      <div>
                        <span className="text-slate-500 block mb-1 text-[10px]">Edge Ratio (MFE/MAE)</span>
                        {(() => {
                          const maeMove = trade.direction === 'long'
                            ? trade.entry_price - trade.mae_price
                            : trade.mae_price - trade.entry_price;
                          const mfeMove = trade.direction === 'long'
                            ? trade.mfe_price - trade.entry_price
                            : trade.entry_price - trade.mfe_price;
                          const edgeRatio = maeMove > 0 ? mfeMove / maeMove : 0;
                          return (
                            <span className={`font-mono font-bold ${edgeRatio >= 2 ? 'text-green-400' : edgeRatio >= 1 ? 'text-yellow-400' : 'text-red-400'}`}>
                              {edgeRatio.toFixed(2)}
                            </span>
                          );
                        })()}
                        <span className="text-slate-500 text-[10px] ml-1">
                          ({'>'}2 = отлично)
                        </span>
                      </div>
                    )}

                    {/* Capture Ratio */}
                    {trade.mfe_price && trade.entry_price && trade.exit_price && (
                      <div>
                        <span className="text-slate-500 block mb-1 text-[10px]">Capture (захват MFE)</span>
                        {(() => {
                          const maxProfit = trade.direction === 'long'
                            ? (trade.mfe_price - trade.entry_price) * trade.quantity
                            : (trade.entry_price - trade.mfe_price) * trade.quantity;
                          const actualProfit = trade.pnl || 0;
                          const captureRatio = maxProfit > 0 ? (actualProfit / maxProfit) * 100 : 0;
                          return (
                            <span className={`font-mono font-bold ${captureRatio >= 70 ? 'text-green-400' : captureRatio >= 40 ? 'text-yellow-400' : 'text-red-400'}`}>
                              {captureRatio.toFixed(0)}%
                            </span>
                          );
                        })()}
                        <span className="text-slate-500 text-[10px] ml-1">
                          (сколько взяли от макс.)
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Visual representation */}
                  {trade.mae_price && trade.mfe_price && trade.entry_price && trade.exit_price && (
                    <div className="mt-3 pt-3 border-t border-slate-700/50">
                      <div className="flex items-center gap-2 text-[10px]">
                        <span className="text-red-400">MAE {trade.mae_price.toLocaleString('ru-RU')}</span>
                        <div className="flex-1 h-2 bg-slate-700 rounded-full relative overflow-hidden">
                          {(() => {
                            const min = Math.min(trade.mae_price, trade.entry_price, trade.exit_price);
                            const max = Math.max(trade.mfe_price, trade.entry_price, trade.exit_price);
                            const range = max - min;
                            const entryPos = ((trade.entry_price - min) / range) * 100;
                            const exitPos = ((trade.exit_price - min) / range) * 100;
                            const maePos = ((trade.mae_price - min) / range) * 100;
                            const mfePos = ((trade.mfe_price - min) / range) * 100;

                            return (
                              <>
                                {/* MAE to MFE range */}
                                <div
                                  className="absolute h-full bg-gradient-to-r from-red-500/30 via-slate-600 to-green-500/30"
                                  style={{ left: `${maePos}%`, width: `${mfePos - maePos}%` }}
                                />
                                {/* Entry marker */}
                                <div
                                  className="absolute w-1 h-full bg-white"
                                  style={{ left: `${entryPos}%` }}
                                  title={`Вход: ${trade.entry_price}`}
                                />
                                {/* Exit marker */}
                                <div
                                  className="absolute w-1 h-full bg-accent"
                                  style={{ left: `${exitPos}%` }}
                                  title={`Выход: ${trade.exit_price}`}
                                />
                              </>
                            );
                          })()}
                        </div>
                        <span className="text-green-400">MFE {trade.mfe_price.toLocaleString('ru-RU')}</span>
                      </div>
                      <div className="flex justify-between text-[9px] text-slate-500 mt-1">
                        <span>⬜ Вход: {trade.entry_price.toLocaleString('ru-RU')}</span>
                        <span>🟩 Выход: {trade.exit_price.toLocaleString('ru-RU')}</span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Нет данных MAE/MFE - показываем кнопку расчёта */}
              {trade.exit_at && !trade.mae_price && !trade.mfe_price && (
                <div className="col-span-full border border-slate-700 rounded-lg p-3 bg-slate-800/30">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-slate-400 text-sm">📊 MAE/MFE Анализ</span>
                      <p className="text-slate-500 text-[10px] mt-1">Нет данных о ценовом диапазоне во время сделки</p>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onCalculateMAE([trade.id]);
                      }}
                      disabled={isCalculatingMAE}
                      className="flex items-center gap-1 px-3 py-1.5 bg-accent/20 hover:bg-accent/30 text-accent rounded text-xs transition-colors disabled:opacity-50"
                    >
                      {isCalculatingMAE ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <BarChart2 size={12} />
                      )}
                      Рассчитать
                    </button>
                  </div>
                </div>
              )}

              {/* Теги на всю ширину */}
              {trade.tags && trade.tags.length > 0 && (
                <div className="col-span-full">
                  <span className="text-slate-500 block mb-1">Теги</span>
                  <div className="flex gap-1 flex-wrap">
                    {trade.tags.map(tag => (
                      <span key={tag} className="text-[10px] font-mono border border-accent/30 px-2 py-0.5 rounded text-accent">
                        #{tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Логика входа */}
              {trade.entry_reason && (
                <div className="col-span-full">
                  <span className="text-slate-500 block mb-1">Логика входа</span>
                  <span className="font-medium">{trade.entry_reason}</span>
                </div>
              )}

              {/* Скриншот */}
              {trade.screenshot_url && (
                <div className="col-span-full">
                  <span className="text-slate-500 block mb-1">📷 Скриншот графика</span>
                  <a
                    href={getApiUrl(trade.screenshot_url)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block"
                  >
                    <Image
                      src={getApiUrl(trade.screenshot_url)}
                      alt="Скриншот сделки"
                      width={640}
                      height={160}
                      className="max-w-md h-40 object-cover rounded-lg border border-border hover:border-accent transition-colors cursor-pointer"
                    />
                  </a>
                </div>
              )}

              {/* Заметки */}
              {trade.notes && (
                <div className="col-span-full">
                  <span className="text-slate-500 block mb-1">📝 Заметки</span>
                  <p className="text-slate-300 whitespace-pre-wrap bg-slate-800/50 p-2 rounded-lg">{trade.notes}</p>
                </div>
              )}

              {/* Операции */}
              {trade.operations && trade.operations.length > 0 && (
                <div className="col-span-full">
                  <span className="text-slate-500 block mb-2">Операции ({trade.operations.length})</span>
                  <div className="overflow-x-auto">
                    <table className="w-full text-[10px]">
                      <thead>
                        <tr className="text-slate-500">
                          <th className="text-left py-1">Дата</th>
                          <th className="text-left py-1">Тип</th>
                          <th className="text-right py-1">Цена</th>
                          <th className="text-right py-1">Кол-во</th>
                          <th className="text-right py-1">Комиссия</th>
                        </tr>
                      </thead>
                      <tbody>
                        {trade.operations.map((op, idx) => (
                          <tr key={idx} className="border-t border-slate-700/50">
                            <td className="py-1 font-mono">{op.date} {op.time}</td>
                            <td className="py-1">
                              <span className={`px-1 rounded ${op.type === 'entry' ? 'bg-blue-500/20 text-blue-400' : 'bg-orange-500/20 text-orange-400'}`}>
                                {op.type === 'entry' ? 'ВХОД' : (op.note === 'partial_close' ? 'ЧАСТИЧ. ВЫХОД' : 'ВЫХОД')}
                              </span>
                            </td>
                            <td className="py-1 text-right font-mono">{op.price?.toLocaleString('ru-RU')}</td>
                            <td className="py-1 text-right font-mono">{op.qty?.toLocaleString('ru-RU')}</td>
                            <td className="py-1 text-right font-mono text-red-400">
                              {op.commission ? `-${op.commission.toFixed(2)}` : '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </React.Fragment>
  );
}
