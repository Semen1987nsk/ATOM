'use client';

import Link from 'next/link';
import { Activity, Plus, Lock, Trash2, Zap } from 'lucide-react';
import { useLanguage } from '@/i18n/LanguageContext';
import { useSettings } from '@/contexts/SettingsContext';

interface Trade {
  id: number;
  symbol: string;
  asset_name?: string;
  asset_type?: string;
  direction: string;
  pnl: number | null;
  commission?: number;
  entry_price: number;
  quantity: number;
  setup_name?: string;
  timeframe?: string;
  tags?: string[];
  ai_analysis?: {
    verdict: string;
    analysis: string;
    advice: string;
    score: number;
  };
}

interface RecentTradesCardProps {
  trades: Trade[];
  onOpenCloseModal: (trade: Trade) => void;
  onDelete: (tradeId: number) => void;
  onOpenAddModal: () => void;
}

export function RecentTradesCard({ 
  trades, 
  onOpenCloseModal, 
  onDelete, 
  onOpenAddModal 
}: RecentTradesCardProps) {
  const { t } = useLanguage();
  const { settings, formatCurrency } = useSettings();

  return (
    <div className="cyber-card p-6 relative overflow-hidden">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-sm font-mono uppercase flex items-center gap-2">
          <Activity size={16} className="text-accent" />
          {t.charts.recentTrades}
        </h2>
        <Link href="/history" className="text-[10px] font-mono text-accent hover:underline flex items-center gap-1 hover:gap-2 transition-all">
          {t.charts.viewAll}
          <span>→</span>
        </Link>
      </div>
      <div className="space-y-4">
        {trades.length === 0 ? (
          <div className="empty-state py-12">
            <div className="empty-state-icon">
              <Activity size={32} className="text-accent/50" />
            </div>
            <h3 className="text-lg font-bold mb-2">{t.charts.noTrades}</h3>
            <p className="text-sm opacity-50 mb-4">Начните торговать и данные появятся здесь</p>
            <button 
              onClick={onOpenAddModal}
              className="btn-primary text-xs"
            >
              <Plus size={14} className="inline mr-2" />
              {t.nav.logPosition}
            </button>
          </div>
        ) : (
          trades.slice(0, 5).map((trade, index) => (
            <div 
              key={trade.id} 
              className="border-b border-border pb-4 last:border-0 table-row-hover p-3 -mx-3 rounded-lg"
              style={{ animationDelay: `${index * 0.1}s` }}
            >
              <div className="flex justify-between items-center mb-2">
                <div className="flex items-center gap-3">
                  <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${trade.direction === 'long' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                    {trade.direction === 'long' ? t.trades.long : t.trades.short}
                  </span>
                  <div>
                    <span className="font-bold">{trade.symbol}</span>
                    {trade.asset_name && <span className="text-[10px] text-gray-500 ml-2">{trade.asset_name}</span>}
                    {trade.asset_type && <span className="text-[9px] border border-gray-700 rounded px-1 ml-2 text-gray-400">{trade.asset_type}</span>}
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    {trade.pnl !== null ? (
                      <span className={`block font-bold ${Number(trade.pnl) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {Number(trade.pnl) >= 0 ? '+' : ''}{formatCurrency(Number(trade.pnl))}
                      </span>
                    ) : (
                      <span className="text-[10px] text-accent">{t.trades.open}</span>
                    )}
                    {trade.commission && <div className="text-[9px] text-gray-500">{t.trades.commission}: {settings.currencySymbol}{trade.commission.toFixed(2)}</div>}
                  </div>
                  
                  {/* Close trade button for open trades */}
                  {trade.pnl === null && (
                    <button 
                      onClick={() => onOpenCloseModal(trade)}
                      className="text-yellow-500/50 hover:text-yellow-500 transition-colors p-1"
                      title={t.trades.closeTrade}
                    >
                      <Lock size={12} />
                    </button>
                  )}
                  
                  <button 
                    onClick={() => onDelete(trade.id)}
                    className="text-red-500/50 hover:text-red-500 transition-colors p-1"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
              
              <div className="flex flex-wrap gap-2 mb-2 items-center">
                {trade.setup_name && (
                  <span className="text-[10px] bg-blue-500/10 text-blue-400 px-1.5 py-0.5 rounded">
                    {t.trades.setup}: {trade.setup_name}
                  </span>
                )}
                {trade.timeframe && (
                  <span className="text-[10px] bg-purple-500/10 text-purple-400 px-1.5 py-0.5 rounded">
                    {t.trades.timeframe}: {trade.timeframe}
                  </span>
                )}
                {trade.tags && trade.tags.length > 0 && trade.tags.map(tag => (
                  <span key={tag} className="text-[9px] font-mono border border-border px-1.5 py-0.5 rounded text-muted">
                    #{tag.toUpperCase()}
                  </span>
                ))}
              </div>

              {trade.ai_analysis && (
                <div className="bg-white/5 p-3 rounded text-xs">
                  <div className="flex items-center gap-2 mb-1">
                    <Zap size={12} className="text-accent" />
                    <span className="font-bold uppercase text-accent">{trade.ai_analysis.verdict}</span>
                    <span className="opacity-40 ml-auto">{t.ai.score}: {trade.ai_analysis.score}/100</span>
                  </div>
                  <p className="opacity-70 mb-2">{trade.ai_analysis.analysis}</p>
                  <p className="text-accent-secondary italic">{trade.ai_analysis.advice}</p>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
