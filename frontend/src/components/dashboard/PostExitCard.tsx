'use client';

import { useState, useEffect, useRef } from 'react';
import { Clock, AlertTriangle, CheckCircle, Eye, X, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';
import Link from 'next/link';
import { api } from '@/lib/apiClient';

interface PeriodStats {
  label: string;
  early_count: number;
  good_count: number;
  neutral_count: number;
  total: number;
  avg_continuation_pct: number;
  max_continuation_pct: number;
  avg_missed_pct: number;
}

interface EarlyExit {
  trade_id: number;
  symbol: string;
  direction: string;
  exit_date: string;
  pnl: number;
  period: string;
  missed_pct: number;
  exit_price: number;
  max_price_after: number;
  min_price_after: number;
  final_price: number;
}

interface PostExitAnalysis {
  processed: number;
  updated: number;
  failed: number;
  summary: {
    early_exits: number;
    good_exits: number;
    total_analyzed: number;
    avg_missed_profit_pct: number;
    early_exit_tendency: boolean;
  } | null;
  period_stats: Record<string, PeriodStats>;
  top_early_exits: EarlyExit[];
}

interface TradePostExit {
  id: number;
  symbol: string;
  direction: string;
  entry_at: string;
  exit_at: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  net_pnl: number;
  has_early_exit: boolean;
  max_missed_pct: number;
  worst_period: string | null;
  analysis: Record<string, unknown>;
}

interface PostExitCardProps {
  tradesCount: number;
  onRecalculate?: () => void;
}

export function PostExitCard({ tradesCount, onRecalculate }: PostExitCardProps) {
  const [calculating, setCalculating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressText, setProgressText] = useState('');
  const [result, setResult] = useState<PostExitAnalysis | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [showTradesList, setShowTradesList] = useState(false);
  const [tradesList, setTradesList] = useState<TradePostExit[]>([]);
  const [selectedTrade, setSelectedTrade] = useState<TradePostExit | null>(null);
  const [selectedTimeframe, setSelectedTimeframe] = useState<string>('1H');
  const [loadingTrades, setLoadingTrades] = useState(false);
  const [tradesError, setTradesError] = useState<string | null>(null);
  const progressInterval = useRef<NodeJS.Timeout | null>(null);
  const cleanupTimeout = useRef<NodeJS.Timeout | null>(null);

  const timeframes = [
    { value: '1m', label: '1 мин', periods: '15м, 1ч, 4ч' },
    { value: '5m', label: '5 мин', periods: '15м, 1ч, 4ч' },
    { value: '15m', label: '15 мин', periods: '1ч, 4ч, 1д' },
    { value: '30m', label: '30 мин', periods: '1ч, 4ч, 1д' },
    { value: '1H', label: '1 час', periods: '4ч, 1д, 1н' },
    { value: '4H', label: '4 часа', periods: '1д, 1н, 1м' },
    { value: '1D', label: '1 день', periods: '1н, 1м, 3м' },
    { value: '1W', label: '1 неделя', periods: '1м, 3м, 6м' },
  ];

  useEffect(() => {
    return () => {
      if (progressInterval.current) {
        clearInterval(progressInterval.current);
      }
      if (cleanupTimeout.current) {
        clearTimeout(cleanupTimeout.current);
      }
    };
  }, []);

  const handleCalculate = async () => {
    setCalculating(true);
    setResult(null);
    setProgress(0);
    setProgressText('Запрос исторических данных...');
    
    let currentProgress = 0;
    progressInterval.current = setInterval(() => {
      currentProgress += Math.random() * 6 + 2;
      if (currentProgress > 90) currentProgress = 90;
      setProgress(currentProgress);
      
      if (currentProgress < 25) {
        setProgressText('Загрузка свечей после закрытия...');
      } else if (currentProgress < 50) {
        setProgressText('Анализ краткосрочных периодов...');
      } else if (currentProgress < 75) {
        setProgressText('Анализ долгосрочных периодов...');
      } else {
        setProgressText('Расчёт упущенной прибыли...');
      }
    }, 400);
    
    try {
      const data = await api.post<PostExitAnalysis>(`/trades/calculate-post-exit`, {
        params: { recalculate: true, timeframe: selectedTimeframe }
      });
      
      if (progressInterval.current) {
        clearInterval(progressInterval.current);
      }
      
      setProgress(100);
      setProgressText('Готово!');
      
      setResult(data);
      
      if (data.updated > 0 && onRecalculate) {
        setTimeout(() => onRecalculate(), 500);
      }
    } catch (error) {
      console.error('Failed to calculate post-exit:', error);
      setProgressText('Ошибка!');
    } finally {
      if (progressInterval.current) {
        clearInterval(progressInterval.current);
      }
      cleanupTimeout.current = setTimeout(() => {
        setCalculating(false);
        setProgress(0);
      }, 1500);
    }
  };

  const loadTradesList = async () => {
    setLoadingTrades(true);
    setTradesError(null);
    setShowTradesList(true); // Сначала открываем модал со спиннером
    
    try {
      const data = await api.get<{ trades: TradePostExit[] }>('/trades/post-exit/list', { params: { limit: 100 } });
      setTradesList(data.trades || []);
      
      if (!data.trades || data.trades.length === 0) {
        setTradesError('Нет сделок с post-exit анализом. Сначала запустите анализ.');
      }
    } catch (error) {
      console.error('Failed to load trades list:', error);
      setTradesError(error instanceof Error ? error.message : 'Ошибка загрузки данных');
    } finally {
      setLoadingTrades(false);
    }
  };

  const formatPrice = (value: number) => {
    if (!value) return '-';
    return value.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  return (
    <div className="cyber-card p-6 border-l-purple-500/30 relative overflow-hidden group">
      <div className="absolute -top-20 -left-20 w-40 h-40 bg-purple-500/10 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
      
      <h2 className="text-sm font-mono uppercase mb-4 flex items-center gap-2 relative z-10">
        <Clock size={16} className="text-purple-400" />
        <Link 
          href="/manual#post-exit" 
          className="hover:text-accent transition-colors flex items-center gap-1"
          title="Открыть в руководстве"
        >
        Post-Exit Анализ
          <ExternalLink size={10} className="opacity-0 group-hover:opacity-60" />
        </Link>
        <span className="ml-auto text-xs text-slate-400">Качество выходов</span>
      </h2>
      
      <div className="space-y-4 relative z-10">
        {/* Результаты с конкретными цифрами */}
        {result && result.summary && (
          <div className="space-y-4">
            {/* Главные метрики */}
            <div className="grid grid-cols-3 gap-3">
              <div className="p-3 bg-white/10 rounded-lg text-center">
                <div className="text-2xl font-bold text-yellow-400">{result.summary.early_exits}</div>
                <div className="text-xs text-slate-400">Ранних выходов</div>
              </div>
              <div className="p-3 bg-white/10 rounded-lg text-center">
                <div className="text-2xl font-bold text-green-400">{result.summary.good_exits}</div>
                <div className="text-xs text-slate-400">Хороших</div>
              </div>
              <div className="p-3 bg-white/10 rounded-lg text-center">
                <div className={`text-2xl font-bold ${result.summary.avg_missed_profit_pct > 1 ? 'text-red-400' : 'text-slate-300'}`}>
                  +{result.summary.avg_missed_profit_pct.toFixed(1)}%
                </div>
                <div className="text-xs text-slate-400">Ср. упущено</div>
              </div>
            </div>
            
            {/* Прогресс-бар раннего закрытия */}
            <div className="p-3 bg-white/10 rounded-lg">
              <div className="flex justify-between text-xs mb-1">
                <span className="text-yellow-400">Ранние выходы</span>
                <span className="text-green-400">Хорошие выходы</span>
              </div>
              <div className="h-3 bg-slate-700 rounded-full overflow-hidden flex">
                <div 
                  className="bg-yellow-500 h-full"
                  style={{ width: `${(result.summary.early_exits / (result.summary.early_exits + result.summary.good_exits + 0.01)) * 100}%` }}
                />
                <div 
                  className="bg-green-500 h-full"
                  style={{ width: `${(result.summary.good_exits / (result.summary.early_exits + result.summary.good_exits + 0.01)) * 100}%` }}
                />
              </div>
            </div>
            
            {/* Статистика по периодам */}
            {result.period_stats && Object.keys(result.period_stats).length > 0 && (
              <div className="p-3 bg-white/10 rounded-lg">
                <button 
                  onClick={() => setShowDetails(!showDetails)}
                  className="w-full flex items-center justify-between text-xs uppercase text-slate-300 hover:text-white"
                >
                  <span>📊 Статистика по периодам</span>
                  {showDetails ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>
                
                {showDetails && (
                  <div className="mt-3 space-y-2">
                    <div className="grid grid-cols-5 gap-2 text-xs text-slate-400 uppercase border-b border-white/20 pb-1">
                      <div>Период</div>
                      <div className="text-center">Ранние</div>
                      <div className="text-center">Хорошие</div>
                      <div className="text-right">Ср. упущено</div>
                      <div className="text-right">Макс</div>
                    </div>
                    {Object.entries(result.period_stats)
                      .sort((a, b) => parseFloat(a[0]) - parseFloat(b[0]))
                      .map(([key, stats]) => (
                        <div key={key} className="grid grid-cols-5 gap-2 text-sm py-2 border-b border-white/10">
                          <div className="text-purple-400 font-semibold">{stats.label}</div>
                          <div className="text-center text-yellow-400 font-medium">{stats.early_count}</div>
                          <div className="text-center text-green-400 font-medium">{stats.good_count}</div>
                          <div className={`text-right font-medium ${stats.avg_continuation_pct > 1 ? 'text-red-400' : 'text-slate-300'}`}>
                            {stats.early_count > 0 ? `+${stats.avg_continuation_pct.toFixed(1)}%` : '-'}
                          </div>
                          <div className={`text-right font-medium ${stats.max_continuation_pct > 3 ? 'text-red-500' : 'text-slate-300'}`}>
                            {stats.max_continuation_pct > 0 ? `+${stats.max_continuation_pct.toFixed(1)}%` : '-'}
                          </div>
                        </div>
                      ))}
                  </div>
                )}
              </div>
            )}
            
            {/* Топ худших ранних выходов */}
            {result.top_early_exits && result.top_early_exits.length > 0 && (
              <div className="p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                <div className="text-xs uppercase mb-3 flex items-center gap-2 text-yellow-400 font-medium">
                  <AlertTriangle size={14} />
                  Топ ранних выходов (упущенная прибыль)
                </div>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {result.top_early_exits.slice(0, 5).map((exit, idx) => (
                    <div key={idx} className="flex items-center justify-between text-sm py-2 border-b border-white/10">
                      <div className="flex items-center gap-2">
                        <span className="text-slate-400">{exit.exit_date}</span>
                        <span className="font-semibold text-white">{exit.symbol}</span>
                        <span className={`font-medium ${exit.direction === 'LONG' ? 'text-green-400' : 'text-red-400'}`}>
                          {exit.direction}
                        </span>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-red-400 font-bold">+{exit.missed_pct.toFixed(2)}%</span>
                        <span className="text-xs text-slate-400">{exit.period}</span>
                      </div>
                    </div>
                  ))}
                </div>
                
                {result.top_early_exits.length > 5 && (
                  <button 
                    onClick={loadTradesList}
                    className="mt-2 text-sm text-purple-400 hover:text-purple-300 flex items-center gap-1 font-medium"
                  >
                    <Eye size={14} />
                    Смотреть все {result.summary?.total_analyzed} сделок
                  </button>
                )}
              </div>
            )}
            
            {/* Предупреждение */}
            {result.summary.early_exit_tendency && (
              <div className="flex items-start gap-2 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-sm text-yellow-400">
                <AlertTriangle size={18} className="flex-shrink-0 mt-0.5" />
                <div>
                  <div className="font-semibold mb-1">Тенденция к раннему закрытию!</div>
                  <div className="text-xs text-yellow-300">
                    В среднем вы оставляете на столе {result.summary.avg_missed_profit_pct.toFixed(2)}% прибыли.
                    Рассмотрите использование trailing stop или частичное закрытие позиций.
                  </div>
                </div>
              </div>
            )}
            
            {!result.summary.early_exit_tendency && result.summary.good_exits > result.summary.early_exits && (
              <div className="flex items-center gap-2 p-2 bg-green-500/10 border border-green-500/20 rounded text-xs text-green-400">
                <CheckCircle size={14} />
                Хорошее время выхода из сделок!
              </div>
            )}
          </div>
        )}
        
        {/* Прогресс бар */}
        {calculating && (
          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-slate-300">{progressText}</span>
              <span className="text-purple-400 font-medium">{Math.round(progress)}%</span>
            </div>
            <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
              <div 
                className="bg-gradient-to-r from-purple-500 to-pink-500 h-full rounded-full transition-all duration-300 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}
        
        {/* Выбор таймфрейма */}
        {!calculating && (
          <div className="p-3 bg-white/10 rounded-lg space-y-2">
            <div className="text-xs text-slate-400 uppercase">Ваш таймфрейм торговли:</div>
            <div className="grid grid-cols-4 gap-1">
              {timeframes.map((tf) => (
                <button
                  key={tf.value}
                  onClick={() => setSelectedTimeframe(tf.value)}
                  className={`px-2 py-2 rounded text-xs font-medium transition-colors ${
                    selectedTimeframe === tf.value
                      ? 'bg-purple-500/30 border border-purple-500/50 text-purple-300'
                      : 'bg-white/10 border border-white/20 text-slate-300 hover:bg-white/15'
                  }`}
                >
                  {tf.label}
                </button>
              ))}
            </div>
            <div className="text-xs text-slate-400 mt-1">
              Периоды анализа: <span className="text-purple-400 font-medium">{timeframes.find(t => t.value === selectedTimeframe)?.periods}</span>
            </div>
          </div>
        )}
        
        {/* Кнопки */}
        {!calculating && (
          <div className="flex gap-2">
            <button
              onClick={handleCalculate}
              disabled={tradesCount === 0}
              className="flex-1 px-4 py-2.5 bg-purple-500/20 hover:bg-purple-500/30 border border-purple-500/30 rounded-lg text-purple-400 text-sm font-medium flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
            >
              <Clock size={16} />
              Анализировать ({selectedTimeframe})
            </button>
            
            <button
              onClick={loadTradesList}
              disabled={tradesCount === 0}
              className="px-4 py-2.5 bg-slate-500/20 hover:bg-slate-500/30 border border-slate-500/30 rounded-lg text-slate-300 text-sm font-medium flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
              title="Смотреть все сделки"
            >
              <Eye size={16} />
              Все сделки
            </button>
          </div>
        )}
        
        {result && !calculating && (
          <div className="text-xs text-center text-slate-500">
            Проанализировано {result.updated} из {result.processed} сделок
          </div>
        )}
      </div>
      
      {/* Модальное окно со списком сделок */}
      {showTradesList && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl max-w-4xl w-full max-h-[80vh] overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <h3 className="text-lg font-medium">Post-Exit анализ по сделкам</h3>
              <button onClick={() => { setShowTradesList(false); setSelectedTrade(null); }} className="text-slate-400 hover:text-white">
                <X size={20} />
              </button>
            </div>
            
            <div className="p-4 overflow-auto max-h-[calc(80vh-120px)]">
              {/* Loading state */}
              {loadingTrades && (
                <div className="flex flex-col items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-10 w-10 border-2 border-purple-500 border-t-transparent mb-4"></div>
                  <div className="text-slate-400">Загрузка сделок...</div>
                </div>
              )}
              
              {/* Error state */}
              {!loadingTrades && tradesError && (
                <div className="flex flex-col items-center justify-center py-12">
                  <AlertTriangle size={40} className="text-yellow-500 mb-4" />
                  <div className="text-slate-400 text-center">{tradesError}</div>
                  <button 
                    onClick={loadTradesList}
                    className="mt-4 px-4 py-2 bg-purple-500/20 hover:bg-purple-500/30 rounded-lg text-purple-400 text-sm"
                  >
                    Попробовать снова
                  </button>
                </div>
              )}
              
              {/* Content */}
              {!loadingTrades && !tradesError && selectedTrade ? (
                // Детальный просмотр одной сделки
                <div className="space-y-4">
                  <button 
                    onClick={() => setSelectedTrade(null)}
                    className="text-sm text-purple-400 hover:text-purple-300 flex items-center gap-1 font-medium"
                  >
                    ← Назад к списку
                  </button>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div className="p-4 bg-white/10 rounded-lg">
                      <div className="text-xs text-slate-400 uppercase mb-1">Инструмент</div>
                      <div className="text-2xl font-bold text-white">{selectedTrade.symbol}</div>
                      <div className={`text-base font-semibold ${selectedTrade.direction === 'LONG' ? 'text-green-400' : 'text-red-400'}`}>
                        {selectedTrade.direction}
                      </div>
                    </div>
                    <div className="p-4 bg-white/10 rounded-lg">
                      <div className="text-xs text-slate-400 uppercase mb-1">P&L</div>
                      <div className={`text-2xl font-bold ${(selectedTrade.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {selectedTrade.pnl?.toLocaleString('ru-RU')} ₽
                      </div>
                      {(selectedTrade.pnl || 0) < 0 ? (
                        <div className="text-red-400 text-base font-semibold">
                          {selectedTrade.has_early_exit 
                            ? `Можно было спасти ${selectedTrade.max_missed_pct}%` 
                            : 'Убыток неизбежен'}
                        </div>
                      ) : (
                        <div className={`text-base font-semibold ${selectedTrade.has_early_exit ? 'text-yellow-400' : 'text-green-400'}`}>
                          {selectedTrade.has_early_exit ? `Упущено +${selectedTrade.max_missed_pct}%` : 'Хороший выход'}
                        </div>
                      )}
                    </div>
                  </div>
                  
                  <div className="p-4 bg-white/10 rounded-lg">
                    <div className="text-xs text-slate-400 uppercase mb-3">Детали по периодам</div>
                    {(() => {
                      const periods = (selectedTrade.analysis as { periods?: Record<string, { available?: boolean; label?: string; max_price?: number; min_price?: number; final_price?: number; continuation_move_pct?: number; exit_quality?: string; message?: string }> })?.periods;
                      if (!periods) return <div className="text-slate-400 text-sm">Нет данных анализа</div>;
                      
                      const availablePeriods = Object.entries(periods).filter(([, p]) => p.available);
                      const unavailablePeriods = Object.entries(periods).filter(([, p]) => !p.available);
                      
                      if (availablePeriods.length === 0) {
                        return (
                          <div className="space-y-2">
                            <div className="text-yellow-400 text-sm flex items-center gap-2 mb-3">
                              <AlertTriangle size={16} />
                              Нет торговых данных для анализа
                            </div>
                            {unavailablePeriods.map(([key, period]) => (
                              <div key={key} className="text-slate-400 text-xs py-1 border-b border-white/5">
                                <span className="text-purple-400">{period.label || key}:</span> {period.message || 'Нет данных'}
                              </div>
                            ))}
                          </div>
                        );
                      }
                      
                      return (
                        <>
                          <div className="grid grid-cols-5 gap-3 text-xs text-slate-400 uppercase border-b border-white/20 pb-2 mb-2">
                            <div>Период</div>
                            <div>Макс цена</div>
                            <div>Мин цена</div>
                            <div>Итог цена</div>
                            <div>Оценка</div>
                          </div>
                          {availablePeriods.map(([key, period]) => (
                            <div key={key} className="grid grid-cols-5 gap-3 text-sm py-3 border-b border-white/10">
                              <div className="text-purple-400 font-semibold">{period.label || key}</div>
                              <div className="text-white">{formatPrice(period.max_price || 0)}</div>
                              <div className="text-white">{formatPrice(period.min_price || 0)}</div>
                              <div className="text-white">{formatPrice(period.final_price || 0)}</div>
                              <div className={
                                `font-semibold ${period.exit_quality === 'early' ? 'text-yellow-400' :
                                period.exit_quality === 'good' ? 'text-green-400' : 'text-slate-300'}`
                              }>
                                {period.exit_quality === 'early' && `+${period.continuation_move_pct}%`}
                                {period.exit_quality === 'good' && '✓ Хорошо'}
                                {period.exit_quality === 'neutral' && 'Нейтрально'}
                              </div>
                            </div>
                          ))}
                        </>
                      );
                    })()}
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div className="p-3 bg-white/10 rounded-lg">
                      <span className="text-slate-400">Вход:</span> <span className="text-white font-medium">{formatPrice(selectedTrade.entry_price)}</span> <span className="text-slate-400">@</span> <span className="text-white">{selectedTrade.entry_at?.split('T')[0]}</span>
                    </div>
                    <div className="p-3 bg-white/10 rounded-lg">
                      <span className="text-slate-400">Выход:</span> <span className="text-white font-medium">{formatPrice(selectedTrade.exit_price)}</span> <span className="text-slate-400">@</span> <span className="text-white">{selectedTrade.exit_at?.split('T')[0]}</span>
                    </div>
                  </div>
                </div>
              ) : !loadingTrades && !tradesError && (
                // Список сделок
                <div className="space-y-2">
                  <div className="grid grid-cols-6 gap-3 text-xs text-slate-400 uppercase border-b border-white/20 pb-2 sticky top-0 bg-slate-900 font-medium">
                    <div>Дата</div>
                    <div>Инструмент</div>
                    <div>Направление</div>
                    <div>P&L</div>
                    <div>Упущено</div>
                    <div></div>
                  </div>
                  
                  {tradesList.map((trade) => (
                    <div 
                      key={trade.id} 
                      className="grid grid-cols-6 gap-3 text-sm py-3 border-b border-white/10 hover:bg-white/10 cursor-pointer rounded transition-colors"
                      onClick={() => setSelectedTrade(trade)}
                    >
                      <div className="text-slate-300">{trade.exit_at?.split('T')[0]}</div>
                      <div className="font-semibold text-white">{trade.symbol}</div>
                      <div className={`font-medium ${trade.direction === 'LONG' ? 'text-green-400' : 'text-red-400'}`}>
                        {trade.direction}
                      </div>
                      <div className={`font-medium ${(trade.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {trade.pnl?.toLocaleString('ru-RU')} ₽
                      </div>
                      <div className={`font-semibold ${
                        (trade.pnl || 0) < 0 
                          ? (trade.has_early_exit ? 'text-orange-400' : 'text-red-400')
                          : (trade.has_early_exit ? 'text-yellow-400' : 'text-green-400')
                      }`}>
                        {(trade.pnl || 0) < 0 
                          ? (trade.has_early_exit ? `↓${trade.max_missed_pct}%` : '✗')
                          : (trade.has_early_exit ? `+${trade.max_missed_pct}%` : '✓')
                        }
                      </div>
                      <div className="text-right">
                        <Eye size={16} className="inline text-slate-400 hover:text-purple-400" />
                      </div>
                    </div>
                  ))}
                  
                  {tradesList.length === 0 && (
                    <div className="text-center py-8 text-slate-400 text-sm">
                      Нет сделок с post-exit анализом. Сначала запустите анализ.
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
