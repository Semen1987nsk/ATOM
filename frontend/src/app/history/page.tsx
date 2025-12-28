'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Trash2, Zap, Download, Upload, Plus, Filter, Edit2 } from 'lucide-react';
import { AddTradeModal } from '@/components/AddTradeModal';
import { EditTradeModal } from '@/components/EditTradeModal';

interface Trade {
  id: number;
  symbol: string;
  asset_name?: string;
  asset_type?: string;
  direction: string;
  pnl: number | null;
  net_pnl?: number | null;
  commission?: number;
  swap?: number;
  leverage?: number;
  confidence?: number;
  entry_price: number;
  quantity: number;
  entry_at: string;
  exit_at?: string;
  setup_name?: string;
  timeframe?: string;
  notes?: string;
  stop_loss?: number;
  take_profit?: number;
  risk_amount?: number;
  news_event?: string;
  screenshot_url?: string;
  tags?: string[];
  ai_analysis?: {
    verdict: string;
    analysis: string;
    advice: string;
    score: number;
  };
}

export default function HistoryPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [filterDirection, setFilterDirection] = useState<'ALL' | 'LONG' | 'SHORT'>('ALL');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);

  const getApiUrl = (path: string) => {
    if (typeof window !== 'undefined' && window.location.hostname.includes('github.dev')) {
      const codespaceName = window.location.hostname.split('-3000')[0];
      return `https://${codespaceName}-8000.app.github.dev${path}`;
    }
    return `http://localhost:8000${path}`;
  };

  const fetchTrades = async () => {
    try {
      const res = await fetch(getApiUrl('/trades/'));
      const data = await res.json();
      setTrades(data.reverse());
    } catch (error) {
      console.error('Failed to fetch trades:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrades();
  }, []);

  const handleCloseTrade = async (tradeId: number) => {
    const exitPrice = prompt('Enter Exit Price:');
    if (!exitPrice) return;

    const exitReason = prompt('Enter Exit Reason (Strategy, Time, Panic, etc.):') || 'Manual';

    try {
      const response = await fetch(getApiUrl(`/trades/${tradeId}/close`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          exit_price: parseFloat(exitPrice),
          exit_at: new Date().toISOString(),
          exit_reason: exitReason,
          mae_price: parseFloat(exitPrice) * 0.98, // Mock MAE for now
          mfe_price: parseFloat(exitPrice) * 1.02  // Mock MFE for now
        }),
      });
      if (response.ok) {
        fetchTrades();
      }
    } catch (error) {
      console.error('Failed to close trade:', error);
    }
  };

  const handleEdit = (trade: Trade) => {
    setSelectedTrade(trade);
    setIsEditModalOpen(true);
  };

  const handleDelete = async (tradeId: number) => {
    if (!confirm('Are you sure you want to delete this trade?')) return;
    try {
      await fetch(getApiUrl(`/trades/${tradeId}`), { method: 'DELETE' });
      fetchTrades();
    } catch (error) {
      console.error('Delete failed:', error);
    }
  };

  const handleExport = async () => {
    window.open(getApiUrl('/trades/export'), '_blank');
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(getApiUrl('/trades/import'), {
        method: 'POST',
        body: formData,
      });
      if (response.ok) {
        fetchTrades();
      }
    } catch (error) {
      console.error('Import failed:', error);
    }
    e.target.value = '';
  };

  const allTags = Array.from(new Set(trades.flatMap(t => t.tags || [])));
  
  const filteredTrades = trades.filter(t => {
    const matchesTag = selectedTag ? t.tags?.includes(selectedTag) : true;
    const matchesDirection = filterDirection === 'ALL' ? true : t.direction.toUpperCase() === filterDirection;
    return matchesTag && matchesDirection;
  });

  if (loading) return <div className="p-8 font-mono text-accent animate-pulse">LOADING HISTORY...</div>;

  return (
    <main className="min-h-screen p-8 max-w-7xl mx-auto">
      <header className="mb-8 flex justify-between items-center">
        <div>
          <Link href="/" className="inline-flex items-center gap-2 text-accent hover:text-white transition-colors mb-2 font-mono text-xs uppercase tracking-widest">
            <ArrowLeft size={14} /> Return to Dashboard
          </Link>
          <h1 className="text-3xl font-black tracking-tighter italic">
            TRADE <span className="text-accent">HISTORY</span>
          </h1>
        </div>
        <div className="flex gap-4">
          <label className="flex items-center gap-2 bg-surface border border-border px-4 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest cursor-pointer">
            <input type="file" accept=".csv,.xlsx,.xls,.pdf" className="hidden" onChange={handleImport} />
            <Upload size={14} />
            Import
          </label>
          <button 
            onClick={handleExport}
            className="flex items-center gap-2 bg-surface border border-border px-4 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest"
          >
            <Download size={14} />
            Export
          </button>
          <button 
            onClick={() => setIsModalOpen(true)}
            className="bg-accent text-black px-6 py-2 font-bold text-xs uppercase tracking-widest hover:bg-white transition-colors flex items-center gap-2"
          >
            <Plus size={14} /> Log Position
          </button>
        </div>
      </header>

      <AddTradeModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        onSuccess={() => fetchTrades()} 
      />

      <EditTradeModal 
        isOpen={isEditModalOpen} 
        onClose={() => setIsEditModalOpen(false)} 
        onSuccess={() => fetchTrades()} 
        trade={selectedTrade}
      />

      <div className="cyber-card p-6">
        <div className="flex flex-wrap gap-4 mb-6 items-center">
          {/* Direction Filter */}
          <div className="flex items-center border border-border rounded-none overflow-hidden">
            <button 
              onClick={() => setFilterDirection('ALL')}
              className={`px-3 py-1 text-[10px] font-mono uppercase transition-colors ${filterDirection === 'ALL' ? 'bg-accent text-black font-bold' : 'hover:bg-white/5'}`}
            >
              All Sides
            </button>
            <div className="w-px h-full bg-border"></div>
            <button 
              onClick={() => setFilterDirection('LONG')}
              className={`px-3 py-1 text-[10px] font-mono uppercase transition-colors ${filterDirection === 'LONG' ? 'bg-green-500 text-black font-bold' : 'hover:bg-white/5 text-green-400'}`}
            >
              Long
            </button>
            <div className="w-px h-full bg-border"></div>
            <button 
              onClick={() => setFilterDirection('SHORT')}
              className={`px-3 py-1 text-[10px] font-mono uppercase transition-colors ${filterDirection === 'SHORT' ? 'bg-red-500 text-black font-bold' : 'hover:bg-white/5 text-red-400'}`}
            >
              Short
            </button>
          </div>

          <div className="w-px h-6 bg-border mx-2 hidden sm:block"></div>

          {/* Tag Filter */}
          <div className="flex gap-2 overflow-x-auto no-scrollbar max-w-full">
            <button 
              onClick={() => setSelectedTag(null)}
              className={`text-[10px] font-mono px-3 py-1 border whitespace-nowrap ${!selectedTag ? 'border-accent text-accent' : 'border-border opacity-50'}`}
            >
              ALL TAGS
            </button>
            {allTags.map(tag => (
              <button 
                key={tag}
                onClick={() => setSelectedTag(tag)}
                className={`text-[10px] font-mono px-3 py-1 border whitespace-nowrap ${selectedTag === tag ? 'border-accent text-accent' : 'border-border opacity-50'}`}
              >
                #{tag.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="text-[10px] font-mono uppercase opacity-50 border-b border-border">
                <th className="pb-2 pl-2">Date</th>
                <th className="pb-2">Date</th>
                <th className="pb-2">Symbol</th>
                <th className="pb-2">Side</th>
                <th className="pb-2">Price</th>
                <th className="pb-2">Qty</th>
                <th className="pb-2">Comm</th>
                <th className="pb-2">Swap</th>
                <th className="pb-2">PnL</th>
                <th className="pb-2">Net PnL</th>
                <th className="pb-2">Tags</th>
                <th className="pb-2 text-right pr-2">Actions</th>
              </tr>
            </thead>
            <tbody className="text-sm">
              {filteredTrades.map((trade) => (
                <tr key={trade.id} className="border-b border-border/50 hover:bg-white/5 transition-colors group">
                  <td colSpan={11} className="p-0 border-none">
                    <div className="flex flex-col w-full">
                      {/* Row 1: Entry */}
                      <div className="flex items-center py-2 px-2 border-b border-white/5 bg-white/[0.02]">
                        <div className="w-[10%] font-mono text-xs opacity-70">
                          {new Date(trade.entry_at).toLocaleDateString()} <span className="opacity-50 text-[10px]">{new Date(trade.entry_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                        </div>
                        <div className="w-[10%] font-bold">
                          {trade.symbol}
                        </div>
                        <div className="w-[8%]">
                          <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${trade.direction === 'long' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                            {trade.direction.toUpperCase()}
                          </span>
                        </div>
                        <div className="w-[10%] font-mono">{trade.entry_price.toLocaleString('ru-RU', { maximumFractionDigits: 4 })}</div>
                        <div className="w-[8%] font-mono">{trade.quantity}</div>
                        <div className="w-[8%] opacity-30">-</div>
                        <div className="w-[8%] opacity-30">-</div>
                        <div className="w-[10%] opacity-30">-</div>
                        <div className="w-[10%] opacity-30">-</div>
                        <div className="w-[10%]">
                           <div className="flex gap-1 flex-wrap">
                            {trade.tags?.map(tag => (
                              <span key={tag} className="text-[9px] font-mono border border-border px-1 opacity-50">
                                #{tag}
                              </span>
                            ))}
                          </div>
                        </div>
                        <div className="w-[8%] text-right">
                           <div className="flex justify-end gap-2">
                              <button 
                                onClick={() => handleEdit(trade)}
                                className="text-accent/50 hover:text-accent transition-colors p-1"
                              >
                                <Edit2 size={14} />
                              </button>
                              <button 
                                onClick={() => handleDelete(trade.id)}
                                className="text-red-500/50 hover:text-red-500 transition-colors p-1"
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                        </div>
                      </div>

                      {/* Row 2: Exit (if closed) */}
                      {trade.exit_at && (
                        <div className="flex items-center py-2 px-2 bg-white/[0.04]">
                          <div className="w-[10%] font-mono text-xs opacity-70 pl-4 border-l-2 border-accent/20">
                            {new Date(trade.exit_at).toLocaleDateString()} <span className="opacity-50 text-[10px]">{new Date(trade.exit_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                          </div>
                          <div className="w-[10%] opacity-50 text-[10px]">
                            EXIT
                          </div>
                          <div className="w-[8%]">
                             <span className={`text-[10px] font-mono px-2 py-0.5 rounded opacity-50 ${trade.direction === 'long' ? 'bg-red-500/10 text-red-400' : 'bg-green-500/10 text-green-400'}`}>
                              {trade.direction === 'long' ? 'SELL' : 'BUY'}
                            </span>
                          </div>
                          <div className="w-[10%] font-mono">{trade.exit_price?.toLocaleString('ru-RU', { maximumFractionDigits: 4 })}</div>
                          <div className="w-[8%] font-mono opacity-50">{trade.quantity}</div>
                          <div className="w-[8%] font-mono text-xs opacity-70 text-red-400/70">
                            -{trade.commission ? trade.commission.toFixed(2) : '0'}
                          </div>
                          <div className="w-[8%] font-mono text-xs opacity-70 text-red-400/70">
                            -{trade.swap ? trade.swap.toFixed(2) : '0'}
                          </div>
                          <div className="w-[10%] font-mono font-bold">
                            {trade.pnl !== null ? (
                              <span className={Number(trade.pnl) >= 0 ? 'text-green-400' : 'text-red-400'}>
                                {Number(trade.pnl) >= 0 ? '+' : ''}{Number(trade.pnl).toLocaleString('ru-RU', { style: 'currency', currency: 'RUB' })}
                              </span>
                            ) : '-'}
                          </div>
                          <div className="w-[10%] font-mono font-bold">
                            {trade.net_pnl !== null && trade.net_pnl !== undefined ? (
                              <span className={Number(trade.net_pnl) >= 0 ? 'text-green-400' : 'text-red-400'}>
                                {Number(trade.net_pnl) >= 0 ? '+' : ''}{Number(trade.net_pnl).toLocaleString('ru-RU', { style: 'currency', currency: 'RUB' })}
                              </span>
                            ) : '-'}
                          </div>
                          <div className="w-[10%]">
                             {trade.confidence && (
                               <span className="text-[9px] font-mono text-accent border border-accent/30 px-1 rounded">
                                 Conf: {trade.confidence}/10
                               </span>
                             )}
                          </div>
                          <div className="w-[8%]"></div>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
