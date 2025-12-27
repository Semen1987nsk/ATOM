'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Trash2, Zap, Download, Upload, Plus, Filter } from 'lucide-react';
import { AddTradeModal } from '@/components/AddTradeModal';

interface Trade {
  id: number;
  symbol: string;
  asset_name?: string;
  asset_type?: string;
  direction: string;
  pnl: number | null;
  commission?: number;
  leverage?: number;
  entry_price: number;
  quantity: number;
  entry_at: string;
  exit_at?: string;
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

export default function HistoryPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [filterDirection, setFilterDirection] = useState<'ALL' | 'LONG' | 'SHORT'>('ALL');
  const [isModalOpen, setIsModalOpen] = useState(false);

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
                <th className="pb-2">Symbol</th>
                <th className="pb-2">Type</th>
                <th className="pb-2">Side</th>
                <th className="pb-2">Setup</th>
                <th className="pb-2">TF</th>
                <th className="pb-2">Entry</th>
                <th className="pb-2">Qty</th>
                <th className="pb-2">PnL</th>
                <th className="pb-2">Comm</th>
                <th className="pb-2">Tags</th>
                <th className="pb-2 text-right pr-2">Actions</th>
              </tr>
            </thead>
            <tbody className="text-sm">
              {filteredTrades.map((trade) => (
                <tr key={trade.id} className="border-b border-border/50 hover:bg-white/5 transition-colors">
                  <td className="py-3 pl-2 font-mono text-xs opacity-70">
                    {new Date(trade.entry_at).toLocaleDateString()} <span className="opacity-50 text-[10px]">{new Date(trade.entry_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                  </td>
                  <td className="py-3 font-bold">
                    {trade.symbol}
                    {trade.asset_name && <div className="text-[9px] font-normal opacity-50">{trade.asset_name}</div>}
                  </td>
                  <td className="py-3 text-xs opacity-70">{trade.asset_type || '-'}</td>
                  <td className="py-3">
                    <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${trade.direction === 'long' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                      {trade.direction.toUpperCase()}
                    </span>
                  </td>
                  <td className="py-3 text-xs">{trade.setup_name || '-'}</td>
                  <td className="py-3 text-xs font-mono">{trade.timeframe || '-'}</td>
                  <td className="py-3 font-mono">{trade.entry_price.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}</td>
                  <td className="py-3 font-mono">{trade.quantity}</td>
                  <td className="py-3 font-mono font-bold">
                    {trade.pnl !== null ? (
                      <span className={Number(trade.pnl) >= 0 ? 'text-green-400' : 'text-red-400'}>
                        {Number(trade.pnl) >= 0 ? '+' : ''}{Number(trade.pnl).toLocaleString('ru-RU', { style: 'currency', currency: 'RUB' })}
                      </span>
                    ) : (
                      <span className="opacity-30">-</span>
                    )}
                  </td>
                  <td className="py-3 font-mono text-xs opacity-70">
                    {trade.commission ? trade.commission.toFixed(2) : '-'}
                  </td>
                  <td className="py-3">
                    <div className="flex gap-1 flex-wrap">
                      {trade.tags?.map(tag => (
                        <span key={tag} className="text-[9px] font-mono border border-border px-1 opacity-50">
                          #{tag}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="py-3 text-right pr-2">
                    <div className="flex justify-end gap-2">
                      {trade.pnl === null && (
                        <button 
                          onClick={() => handleCloseTrade(trade.id)}
                          className="text-[10px] font-mono border border-accent text-accent px-2 py-1 hover:bg-accent hover:text-black transition-colors"
                        >
                          CLOSE
                        </button>
                      )}
                      <button 
                        onClick={() => handleDelete(trade.id)}
                        className="text-red-500/50 hover:text-red-500 transition-colors p-1"
                      >
                        <Trash2 size={14} />
                      </button>
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
