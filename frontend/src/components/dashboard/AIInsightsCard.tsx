'use client';

import { AlertTriangle } from 'lucide-react';

interface AIInsightsCardProps {
  recommendations: string[];
  optimalF: number;
}

export function AIInsightsCard({ recommendations, optimalF }: AIInsightsCardProps) {
  return (
    <div className="cyber-card p-6 border-l-accent/30 relative overflow-hidden group">
      {/* Glow effect */}
      <div className="absolute -top-20 -right-20 w-40 h-40 bg-accent/10 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
      
      <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2 relative z-10">
        <AlertTriangle size={16} className="text-accent animate-pulse" />
        AI Insights
        <span className="ml-auto badge-accent text-[8px]">LIVE</span>
      </h2>
      <div className="space-y-4 relative z-10">
        {recommendations.map((rec, i) => (
          <div 
            key={i} 
            className="p-3 bg-accent/5 border-l-2 border-accent text-sm hover:bg-accent/10 transition-all duration-300 rounded-r-lg cursor-default"
            style={{ animationDelay: `${i * 0.1}s` }}
          >
            <span className="opacity-30 text-[10px] mr-2">0{i + 1}</span>
            {rec}
          </div>
        ))}
        <div className="p-3 bg-gradient-to-r from-blue-500/10 to-transparent border-l-2 border-blue-500 text-sm rounded-r-lg">
          <span className="text-blue-400 font-bold">Рекомендуемый риск:</span> 
          <span className="ml-2 text-blue-300 font-bold">{(optimalF * 10).toFixed(1)}%</span>
          <span className="text-[10px] opacity-40 ml-2">ультра-консервативный (f/10)</span>
        </div>
        <div className="mt-3 p-2 text-[10px] border border-white/5 rounded-lg space-y-2">
          <div className="font-mono uppercase opacity-60 mb-2">Варианты риска:</div>
          <div className="flex justify-between items-center">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-blue-500 ring-2 ring-blue-500/30"></span>
              <strong>Ультра-консерв. (f/10):</strong>
            </span>
            <span className="text-blue-400 font-bold">{(optimalF * 10).toFixed(1)}% ⭐</span>
          </div>
          <div className="flex justify-between items-center opacity-70">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-green-500"></span>
              Консервативный (f/4):
            </span>
            <span className="text-green-400">{(optimalF * 25).toFixed(1)}%</span>
          </div>
          <div className="flex justify-between items-center opacity-60">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-accent-secondary"></span>
              Умеренный (f/2):
            </span>
            <span className="text-accent-secondary">{(optimalF * 50).toFixed(1)}%</span>
          </div>
          <div className="flex justify-between items-center opacity-50">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-red-500"></span>
              Агрессивный (f):
            </span>
            <span className="text-red-400">{(optimalF * 100).toFixed(1)}%</span>
          </div>
          <div className="mt-2 pt-2 border-t border-white/5 space-y-1 opacity-60">
            <div className="text-blue-400/80">✓ f/10 — <strong>рекомендуется</strong>, минимальная просадка</div>
            <div className="text-green-400/80">✓ f/4 — стандартный выбор, умеренный риск</div>
            <div className="text-accent-secondary/80">✓ f/2 — опытные трейдеры, уверенные сетапы</div>
            <div className="text-red-400/80">⚠️ f — только конкурсы, разгон, «play money»</div>
          </div>
        </div>
      </div>
    </div>
  );
}
