'use client';

import { Gauge } from 'lucide-react';

interface MAEMFEAnalysis {
  avg_mae_pct: number;
  avg_mfe_pct: number;
  avg_efficiency: number;
  trades_analyzed: number;
}

interface MAEMFECardProps {
  analysis: MAEMFEAnalysis | undefined;
}

export function MAEMFECard({ analysis }: MAEMFECardProps) {
  const avgMAE = analysis?.avg_mae_pct || 0;
  const avgMFE = analysis?.avg_mfe_pct || 0;
  const avgEfficiency = analysis?.avg_efficiency || 0;
  const tradesAnalyzed = analysis?.trades_analyzed || 0;

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
            <div className="flex items-center gap-2 text-muted-foreground">
              <span className="w-1.5 h-1.5 rounded-full bg-gray-500"></span>
              Нет данных для анализа. Добавьте сделки с MAE/MFE метриками.
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
