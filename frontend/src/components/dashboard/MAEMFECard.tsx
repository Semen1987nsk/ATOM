'use client';

import { useState, useEffect, useRef } from 'react';
import { Gauge, RefreshCw, Calculator, ExternalLink, ChevronDown, ChevronUp, Target, TrendingUp, TrendingDown, AlertTriangle, CheckCircle, Info, Lightbulb, DollarSign } from 'lucide-react';
import Link from 'next/link';
import { api } from '@/lib/apiClient';

interface MAEMFEAnalysis {
  avg_mae_pct: number;
  avg_mfe_pct: number;
  avg_efficiency: number;
  avg_edge_ratio?: number;
  trades_analyzed: number;
  
  // Детальная статистика
  mae_percentiles?: {
    p10: number;
    p25: number;
    p50: number;
    p75: number;
    p90: number;
    max: number;
  };
  mfe_percentiles?: {
    p10: number;
    p25: number;
    p50: number;
    p75: number;
    p90: number;
    max: number;
  };
  winners_vs_losers?: {
    winners: {
      count: number;
      avg_mae: number;
      avg_mfe: number;
      avg_efficiency: number;
    };
    losers: {
      count: number;
      avg_mae: number;
      avg_mfe: number;
      avg_efficiency: number;
    };
  };
  
  // Качество
  entry_quality_score?: number;
  exit_quality_score?: number;
  
  // Оптимизация стопов
  optimal_stop_pct?: number;
  trades_above_optimal_stop?: number;
  
  // Упущенная прибыль
  total_profit_left_on_table?: number;
  avg_profit_left_on_table?: number;
  
  // Рекомендации
  recommendations?: Array<{
    type: 'success' | 'warning' | 'danger' | 'info' | 'insight';
    icon: string;
    text: string;
  }>;
}

interface MAEMFECardProps {
  analysis: MAEMFEAnalysis | undefined;
  onRecalculate?: () => void;
  getApiUrl: (path: string) => string;
}

interface MAEMFEStats {
  total_closed: number;
  with_mae_mfe: number;
  without_mae_mfe: number;
  coverage_pct: number;
}

export function MAEMFECard({ analysis, onRecalculate, getApiUrl }: MAEMFECardProps) {
  const [calculating, setCalculating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressText, setProgressText] = useState('');
  const [result, setResult] = useState<{ updated: number; failed: number } | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [stats, setStats] = useState<MAEMFEStats | null>(null);
  const progressInterval = useRef<NodeJS.Timeout | null>(null);
  
  const avgMAE = analysis?.avg_mae_pct || 0;
  const avgMFE = analysis?.avg_mfe_pct || 0;
  const avgEfficiency = analysis?.avg_efficiency || 0;
  const avgEdgeRatio = analysis?.avg_edge_ratio || 0;
  const tradesAnalyzed = analysis?.trades_analyzed || 0;

  // Загружаем статистику MAE/MFE
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await api.get<MAEMFEStats>('/trades/mae-mfe-stats');
        setStats(data);
      } catch (e) {
        console.error('Failed to fetch MAE/MFE stats:', e);
      }
    };
    fetchStats();
  }, [tradesAnalyzed]);

  // Очистка интервала при размонтировании
  useEffect(() => {
    return () => {
      if (progressInterval.current) {
        clearInterval(progressInterval.current);
      }
    };
  }, []);

  const handleCalculateMAEMFE = async (forceAll: boolean = false) => {
    setCalculating(true);
    setResult(null);
    setProgress(0);
    setProgressText(forceAll ? 'Пересчёт всех сделок...' : 'Расчёт новых сделок...');
    
    let currentProgress = 0;
    progressInterval.current = setInterval(() => {
      currentProgress += Math.random() * 8 + 2;
      if (currentProgress > 90) currentProgress = 90;
      setProgress(currentProgress);
      
      if (currentProgress < 30) {
        setProgressText('Загрузка свечей с MOEX...');
      } else if (currentProgress < 60) {
        setProgressText('Расчёт MAE для сделок...');
      } else if (currentProgress < 85) {
        setProgressText('Расчёт MFE для сделок...');
      } else {
        setProgressText('Сохранение результатов...');
      }
    }, 300);
    
    try {
      const url = forceAll 
        ? getApiUrl('/trades/calculate-mae-mfe?force_all=true')
        : getApiUrl('/trades/calculate-mae-mfe');
        
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      
      if (progressInterval.current) {
        clearInterval(progressInterval.current);
      }
      
      setProgress(100);
      setProgressText('Готово!');
      
      const data = await response.json();
      setResult({ updated: data.updated, failed: data.failed });
      
      // Обновляем статистику
      try {
        const statsData = await api.get<MAEMFEStats>('/trades/mae-mfe-stats');
        setStats(statsData);
      } catch { /* ignore */ }
      
      if (data.updated > 0 && onRecalculate) {
        setTimeout(() => onRecalculate(), 500);
      }
    } catch (error) {
      console.error('Failed to calculate MAE/MFE:', error);
      setResult({ updated: 0, failed: -1 });
      setProgressText('Ошибка!');
    } finally {
      if (progressInterval.current) {
        clearInterval(progressInterval.current);
      }
      setTimeout(() => {
        setCalculating(false);
        setProgress(0);
      }, 1500);
    }
  };

  const getRecommendationIcon = (type: string) => {
    switch (type) {
      case 'success': return <CheckCircle size={14} className="text-green-400" />;
      case 'warning': return <AlertTriangle size={14} className="text-yellow-400" />;
      case 'danger': return <AlertTriangle size={14} className="text-red-400" />;
      case 'insight': return <Lightbulb size={14} className="text-cyan-400" />;
      default: return <Info size={14} className="text-slate-400" />;
    }
  };

  const getQualityColor = (score: number) => {
    if (score >= 70) return 'text-green-400';
    if (score >= 40) return 'text-yellow-400';
    return 'text-red-400';
  };

  const getQualityBg = (score: number) => {
    if (score >= 70) return 'bg-green-500/20 border-green-500/30';
    if (score >= 40) return 'bg-yellow-500/20 border-yellow-500/30';
    return 'bg-red-500/20 border-red-500/30';
  };

  return (
    <div className="cyber-card p-6 border-l-cyan-500/30 relative overflow-hidden group">
      <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2 relative z-10">
        <Gauge size={16} className="text-cyan-400" />
        <Link 
          href="/manual#mae-mfe" 
          className="hover:text-accent transition-colors flex items-center gap-1"
          title="Открыть в руководстве"
        >
          MAE/MFE Анализ
          <ExternalLink size={10} className="opacity-0 group-hover:opacity-60" />
        </Link>
        <span className="ml-auto text-[10px] opacity-40">{tradesAnalyzed} сделок</span>
      </h2>
      
      <div className="space-y-4 relative z-10">
        {/* Основные метрики */}
        <div className="grid grid-cols-3 gap-3">
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-center">
            <div className="text-[10px] opacity-60 uppercase mb-1">MAE (просадка)</div>
            <div className="text-2xl font-bold text-red-400">{avgMAE.toFixed(2)}%</div>
            <div className="text-[9px] opacity-40">против позиции</div>
          </div>
          <div className="p-3 bg-green-500/10 border border-green-500/20 rounded-lg text-center">
            <div className="text-[10px] opacity-60 uppercase mb-1">MFE (прибыль)</div>
            <div className="text-2xl font-bold text-green-400">{avgMFE.toFixed(2)}%</div>
            <div className="text-[9px] opacity-40">в нашу сторону</div>
          </div>
          <div className="p-3 bg-cyan-500/10 border border-cyan-500/20 rounded-lg text-center">
            <div className="text-[10px] opacity-60 uppercase mb-1">Эффективность</div>
            <div className="text-2xl font-bold text-cyan-400">{avgEfficiency.toFixed(0)}%</div>
            <div className="text-[9px] opacity-40">от MFE забираем</div>
          </div>
        </div>
        
        {/* Edge Ratio */}
        {avgEdgeRatio > 0 && (
          <div className="p-3 bg-white/5 rounded-lg flex items-center justify-between">
            <div>
              <div className="text-[10px] opacity-60 uppercase mb-1">Edge Ratio (MFE/MAE)</div>
              <div className="text-xs opacity-60">Потенциал прибыли vs риск</div>
            </div>
            <div className={`text-2xl font-bold ${avgEdgeRatio >= 2 ? 'text-green-400' : avgEdgeRatio >= 1 ? 'text-yellow-400' : 'text-red-400'}`}>
              {avgEdgeRatio.toFixed(2)}x
            </div>
          </div>
        )}
        
        {/* Визуальная шкала MAE vs MFE */}
        <div className="p-3 bg-white/5 rounded-lg">
          <div className="text-[10px] opacity-60 uppercase mb-2">Соотношение MAE / MFE</div>
          <div className="relative h-6 bg-white/5 rounded-full overflow-hidden">
            <div 
              className="absolute left-0 top-0 h-full bg-gradient-to-r from-red-500/60 to-red-500/30 rounded-l-full"
              style={{ width: `${Math.min(50, avgMAE / (avgMAE + (avgMFE || 1)) * 100)}%` }}
            />
            <div 
              className="absolute right-0 top-0 h-full bg-gradient-to-l from-green-500/60 to-green-500/30 rounded-r-full"
              style={{ width: `${Math.min(50, avgMFE / (avgMAE + (avgMFE || 1)) * 100)}%` }}
            />
            <div className="absolute inset-0 flex items-center justify-center text-[10px] font-mono">
              <span className="text-red-400 mr-2">−{avgMAE.toFixed(1)}%</span>
              <span className="text-white/40">|</span>
              <span className="text-green-400 ml-2">+{avgMFE.toFixed(1)}%</span>
            </div>
          </div>
        </div>
        
        {/* Кнопка раскрытия */}
        {tradesAnalyzed > 0 && (
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="w-full p-2 bg-white/5 hover:bg-white/10 rounded-lg flex items-center justify-between text-xs transition-colors"
          >
            <span className="opacity-60">Подробный анализ</span>
            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        )}
        
        {/* Развёрнутая информация */}
        {isExpanded && analysis && (
          <div className="space-y-4 pt-2 border-t border-white/10">
            
            {/* Качество входов и выходов */}
            <div className="grid grid-cols-2 gap-3">
              <div className={`p-3 border rounded-lg ${getQualityBg(analysis.entry_quality_score || 0)}`}>
                <div className="flex items-center gap-2 mb-2">
                  <Target size={14} />
                  <span className="text-[10px] opacity-60 uppercase">Качество входов</span>
                </div>
                <div className={`text-3xl font-bold ${getQualityColor(analysis.entry_quality_score || 0)}`}>
                  {analysis.entry_quality_score || 0}
                  <span className="text-lg opacity-60">/100</span>
                </div>
                <div className="text-[9px] opacity-50 mt-1">
                  {(analysis.entry_quality_score || 0) >= 70 ? 'Отличные точки входа' : 
                   (analysis.entry_quality_score || 0) >= 40 ? 'Требует улучшения' : 'Плохие входы'}
                </div>
              </div>
              
              <div className={`p-3 border rounded-lg ${getQualityBg(analysis.exit_quality_score || 0)}`}>
                <div className="flex items-center gap-2 mb-2">
                  <TrendingUp size={14} />
                  <span className="text-[10px] opacity-60 uppercase">Качество выходов</span>
                </div>
                <div className={`text-3xl font-bold ${getQualityColor(analysis.exit_quality_score || 0)}`}>
                  {analysis.exit_quality_score || 0}
                  <span className="text-lg opacity-60">/100</span>
                </div>
                <div className="text-[9px] opacity-50 mt-1">
                  {(analysis.exit_quality_score || 0) >= 70 ? 'Забираете прибыль' : 
                   (analysis.exit_quality_score || 0) >= 40 ? 'Выходите рано' : 'Много упускаете'}
                </div>
              </div>
            </div>
            
            {/* Percentiles */}
            {analysis.mae_percentiles && analysis.mfe_percentiles && (
              <div className="p-3 bg-white/5 rounded-lg">
                <div className="text-[10px] opacity-60 uppercase mb-3">Распределение (перцентили)</div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-[10px] text-red-400 mb-2 flex items-center gap-1">
                      <TrendingDown size={12} /> MAE (просадка)
                    </div>
                    <div className="space-y-1 text-[10px] font-mono">
                      <div className="flex justify-between">
                        <span className="opacity-40">10%:</span>
                        <span>{analysis.mae_percentiles.p10}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="opacity-40">Медиана:</span>
                        <span>{analysis.mae_percentiles.p50}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="opacity-40">90%:</span>
                        <span>{analysis.mae_percentiles.p90}%</span>
                      </div>
                      <div className="flex justify-between text-red-400">
                        <span className="opacity-60">Макс:</span>
                        <span>{analysis.mae_percentiles.max}%</span>
                      </div>
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-green-400 mb-2 flex items-center gap-1">
                      <TrendingUp size={12} /> MFE (потенциал)
                    </div>
                    <div className="space-y-1 text-[10px] font-mono">
                      <div className="flex justify-between">
                        <span className="opacity-40">10%:</span>
                        <span>{analysis.mfe_percentiles.p10}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="opacity-40">Медиана:</span>
                        <span>{analysis.mfe_percentiles.p50}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="opacity-40">90%:</span>
                        <span>{analysis.mfe_percentiles.p90}%</span>
                      </div>
                      <div className="flex justify-between text-green-400">
                        <span className="opacity-60">Макс:</span>
                        <span>{analysis.mfe_percentiles.max}%</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
            
            {/* Winners vs Losers */}
            {analysis.winners_vs_losers && (
              <div className="p-3 bg-white/5 rounded-lg">
                <div className="text-[10px] opacity-60 uppercase mb-3">Выигрышные vs Проигрышные сделки</div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-2 bg-green-500/10 rounded border border-green-500/20">
                    <div className="text-[10px] text-green-400 mb-2 font-medium">
                      ✓ Выигрышные ({analysis.winners_vs_losers.winners.count})
                    </div>
                    <div className="space-y-1 text-[10px] font-mono">
                      <div className="flex justify-between">
                        <span className="opacity-60">MAE:</span>
                        <span>{analysis.winners_vs_losers.winners.avg_mae}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="opacity-60">MFE:</span>
                        <span>{analysis.winners_vs_losers.winners.avg_mfe}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="opacity-60">Эфф.:</span>
                        <span>{analysis.winners_vs_losers.winners.avg_efficiency}%</span>
                      </div>
                    </div>
                  </div>
                  <div className="p-2 bg-red-500/10 rounded border border-red-500/20">
                    <div className="text-[10px] text-red-400 mb-2 font-medium">
                      ✕ Проигрышные ({analysis.winners_vs_losers.losers.count})
                    </div>
                    <div className="space-y-1 text-[10px] font-mono">
                      <div className="flex justify-between">
                        <span className="opacity-60">MAE:</span>
                        <span>{analysis.winners_vs_losers.losers.avg_mae}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="opacity-60">MFE:</span>
                        <span>{analysis.winners_vs_losers.losers.avg_mfe}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="opacity-60">Эфф.:</span>
                        <span>{analysis.winners_vs_losers.losers.avg_efficiency}%</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
            
            {/* Stop Loss Optimization */}
            {analysis.optimal_stop_pct !== undefined && (
              <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                <div className="flex items-center gap-2 mb-2">
                  <Target size={14} className="text-amber-400" />
                  <span className="text-[10px] opacity-60 uppercase">Оптимизация стоп-лосса</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-bold text-amber-400">{analysis.optimal_stop_pct}%</span>
                  <span className="text-[10px] opacity-60">рекомендуемый стоп</span>
                </div>
                <div className="text-[10px] opacity-50 mt-1">
                  75% ваших сделок не пробивали этот уровень. 
                  {analysis.trades_above_optimal_stop && analysis.trades_above_optimal_stop > 0 && (
                    <span className="text-amber-400"> {analysis.trades_above_optimal_stop} сделок могли быть закрыты раньше.</span>
                  )}
                </div>
              </div>
            )}
            
            {/* Profit Left on Table */}
            {analysis.total_profit_left_on_table !== undefined && analysis.total_profit_left_on_table > 0 && (
              <div className="p-3 bg-purple-500/10 border border-purple-500/20 rounded-lg">
                <div className="flex items-center gap-2 mb-2">
                  <DollarSign size={14} className="text-purple-400" />
                  <span className="text-[10px] opacity-60 uppercase">Упущенная прибыль</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-bold text-purple-400">
                    {analysis.total_profit_left_on_table.toLocaleString('ru-RU')} ₽
                  </span>
                  <span className="text-[10px] opacity-60">всего</span>
                </div>
                <div className="text-[10px] opacity-50 mt-1">
                  В среднем {analysis.avg_profit_left_on_table?.toLocaleString('ru-RU')} ₽ на сделку — разница между MFE и реальным выходом.
                </div>
              </div>
            )}
            
            {/* Recommendations */}
            {analysis.recommendations && analysis.recommendations.length > 0 && (
              <div className="p-3 bg-white/5 rounded-lg space-y-2">
                <div className="text-[10px] opacity-60 uppercase mb-2">Рекомендации</div>
                {analysis.recommendations.map((rec, idx) => (
                  <div key={idx} className="flex items-start gap-2 text-[11px]">
                    {getRecommendationIcon(rec.type)}
                    <span className={
                      rec.type === 'success' ? 'text-green-400' :
                      rec.type === 'warning' ? 'text-yellow-400' :
                      rec.type === 'danger' ? 'text-red-400' :
                      rec.type === 'insight' ? 'text-cyan-400' : 'text-slate-400'
                    }>{rec.text}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        
        {/* Секция расчёта MAE/MFE - всегда показываем */}
        <div className="p-3 bg-white/5 rounded-lg space-y-3 text-[11px]">
          {/* Статистика покрытия */}
          {stats && stats.total_closed > 0 && (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${stats.coverage_pct === 100 ? 'bg-green-400' : stats.coverage_pct > 0 ? 'bg-yellow-400' : 'bg-gray-500'}`} />
                <span className="opacity-60">
                  MAE/MFE: {stats.with_mae_mfe} из {stats.total_closed} сделок
                </span>
              </div>
              <span className={`font-mono text-xs ${stats.coverage_pct === 100 ? 'text-green-400' : 'text-yellow-400'}`}>
                {stats.coverage_pct}%
              </span>
            </div>
          )}
          
          {tradesAnalyzed === 0 && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <span className="w-1.5 h-1.5 rounded-full bg-gray-500"></span>
              Нет данных для анализа. Рассчитайте MAE/MFE.
            </div>
          )}
          
          {/* Прогресс-бар */}
          {calculating && (
            <div className="space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-[var(--text-secondary)]">{progressText}</span>
                <span className="text-[var(--accent)] font-medium num">{Math.round(progress)}%</span>
              </div>
              <div className="w-full bg-[var(--surface-2)] rounded-[var(--radius-xs)] h-1.5 overflow-hidden">
                <div
                  className="bg-[var(--accent)] h-full rounded-[var(--radius-xs)] transition-all duration-300 ease-out"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}
          
          {/* Кнопки расчёта */}
          {!calculating && (
            <div className="flex gap-2">
              {/* Кнопка "Только новые" - показываем если есть сделки без MAE/MFE */}
              {stats && stats.without_mae_mfe > 0 && (
                <button
                  onClick={() => handleCalculateMAEMFE(false)}
                  disabled={calculating}
                  className="flex-1 px-3 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded-lg text-cyan-400 text-xs font-medium flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
                >
                  <Calculator size={14} />
                  Новые ({stats.without_mae_mfe})
                </button>
              )}
              
              {/* Кнопка "Все сделки" - всегда если есть закрытые сделки */}
              {stats && stats.total_closed > 0 && (
                <button
                  onClick={() => handleCalculateMAEMFE(true)}
                  disabled={calculating}
                  className={`${stats.without_mae_mfe > 0 ? 'flex-1' : 'w-full'} px-3 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-white/60 hover:text-white/80 text-xs font-medium flex items-center justify-center gap-2 transition-colors disabled:opacity-50`}
                >
                  <RefreshCw size={14} />
                  {stats.without_mae_mfe > 0 ? `Все (${stats.total_closed})` : `Пересчитать (${stats.total_closed})`}
                </button>
              )}
              
              {/* Если нет сделок вообще */}
              {(!stats || stats.total_closed === 0) && (
                <div className="w-full text-center opacity-40 py-2">
                  Нет закрытых сделок
                </div>
              )}
            </div>
          )}
          
          {/* Результат */}
          {result && !calculating && (
            <div className={`text-xs p-2 rounded ${result.failed === -1 ? 'bg-red-500/20 text-red-400' : result.updated > 0 ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
              {result.failed === -1 
                ? 'Ошибка при расчёте' 
                : result.updated > 0 
                  ? `✓ Обновлено ${result.updated} сделок` 
                  : 'Нет сделок для обновления или данные недоступны'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
