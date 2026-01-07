'use client';

import { useState, useEffect, useRef } from 'react';
import { Gauge, RefreshCw, Calculator } from 'lucide-react';

interface MAEMFEAnalysis {
  avg_mae_pct: number;
  avg_mfe_pct: number;
  avg_efficiency: number;
  trades_analyzed: number;
}

interface MAEMFECardProps {
  analysis: MAEMFEAnalysis | undefined;
  onRecalculate?: () => void;
  getApiUrl: (path: string) => string;
}

export function MAEMFECard({ analysis, onRecalculate, getApiUrl }: MAEMFECardProps) {
  const [calculating, setCalculating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressText, setProgressText] = useState('');
  const [result, setResult] = useState<{ updated: number; failed: number } | null>(null);
  const progressInterval = useRef<NodeJS.Timeout | null>(null);
  
  const avgMAE = analysis?.avg_mae_pct || 0;
  const avgMFE = analysis?.avg_mfe_pct || 0;
  const avgEfficiency = analysis?.avg_efficiency || 0;
  const tradesAnalyzed = analysis?.trades_analyzed || 0;

  // Очистка интервала при размонтировании
  useEffect(() => {
    return () => {
      if (progressInterval.current) {
        clearInterval(progressInterval.current);
      }
    };
  }, []);

  const handleCalculateMAEMFE = async () => {
    setCalculating(true);
    setResult(null);
    setProgress(0);
    setProgressText('Запрос исторических данных MOEX...');
    
    // Симуляция прогресса для лучшего UX
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
      const response = await fetch(getApiUrl('/trades/calculate-mae-mfe'), {
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

  return (
    <div className="cyber-card p-6 border-l-cyan-500/30 relative overflow-hidden group">
      <div className="absolute -top-20 -left-20 w-40 h-40 bg-cyan-500/10 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
      
      <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2 relative z-10">
        <Gauge size={16} className="text-cyan-400" />
        MAE/MFE Анализ
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
        
        {/* Интерпретация */}
        <div className="p-3 bg-white/5 rounded-lg space-y-2 text-[11px]">
          <div className="font-mono uppercase opacity-60 text-[10px] mb-2">Интерпретация</div>
          {tradesAnalyzed === 0 ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-muted-foreground">
                <span className="w-1.5 h-1.5 rounded-full bg-gray-500"></span>
                Нет данных для анализа. Добавьте сделки с MAE/MFE метриками.
              </div>
              
              {/* Прогресс бар */}
              {calculating && (
                <div className="space-y-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-300">{progressText}</span>
                    <span className="text-cyan-400 font-medium">{Math.round(progress)}%</span>
                  </div>
                  <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
                    <div 
                      className="bg-gradient-to-r from-cyan-500 to-teal-500 h-full rounded-full transition-all duration-300 ease-out"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
              )}
              
              {!calculating && (
                <button
                  onClick={handleCalculateMAEMFE}
                  disabled={calculating}
                  className="w-full px-4 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded-lg text-cyan-400 text-xs font-medium flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
                >
                  <Calculator size={14} />
                  Рассчитать MAE/MFE из истории MOEX
                </button>
              )}
              
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
          ) : (
            <>
              {avgMAE < 1 && (
                <div className="flex items-center gap-2 text-green-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span>
                  Отличные точки входа! Средняя просадка менее 1%
                </div>
              )}
              {avgMAE >= 1 && avgMAE < 3 && (
                <div className="flex items-center gap-2 text-yellow-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-yellow-500"></span>
                  Нормальные входы. Просадка в пределах нормы
                </div>
              )}
              {avgMAE >= 3 && (
                <div className="flex items-center gap-2 text-red-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-500"></span>
                  Высокий MAE. Рассмотрите улучшение точек входа
                </div>
              )}
              
              {avgEfficiency < 50 && (
                <div className="flex items-center gap-2 text-yellow-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-yellow-500"></span>
                  Низкая эффективность. Вы забираете менее половины движения
                </div>
              )}
              {avgEfficiency >= 50 && avgEfficiency < 80 && (
                <div className="flex items-center gap-2 text-cyan-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-500"></span>
                  Хорошая эффективность закрытия позиций
                </div>
              )}
              {avgEfficiency >= 80 && (
                <div className="flex items-center gap-2 text-green-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span>
                  Отличная эффективность! Вы улавливаете большую часть движения
                </div>
              )}
              
              {avgMFE > avgMAE * 1.5 && (
                <div className="flex items-center gap-2 text-green-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span>
                  MFE превышает MAE в {(avgMFE / (avgMAE || 1)).toFixed(1)}x — положительное соотношение
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
