'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Trash2, Zap, Download, Upload, Plus, Filter, Edit2, ChevronDown, ChevronRight, Lock } from 'lucide-react';
import { AddTradeModal } from '@/components/AddTradeModal';
import { EditTradeModal } from '@/components/EditTradeModal';
import CloseTradeModal from '@/components/CloseTradeModal';
import { TradeHistorySkeleton } from '@/components/Skeleton';

interface Trade {
  id: number;
  symbol: string;
  asset_name?: string;
  asset_type?: string;
  direction: string;
  pnl: number | null;
  net_pnl?: number | null;
  commission?: number;
  entry_commission?: number;
  exit_commission?: number;
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
  exit_reason?: string;
  isAddition?: boolean;
}

export default function HistoryPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [filterDirection, setFilterDirection] = useState<'ALL' | 'LONG' | 'SHORT'>('ALL');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isCloseModalOpen, setIsCloseModalOpen] = useState(false);
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const [selectedTradeToClose, setSelectedTradeToClose] = useState<Trade | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [unrealizedData, setUnrealizedData] = useState<{[key: number]: {pnl: number, price: number}}>({});

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

  const fetchUnrealizedPnL = async () => {
    try {
        const res = await fetch(getApiUrl('/trades/unrealized-pnl'));
        if (res.ok) {
            const data = await res.json();
            const map: any = {};
            data.forEach((item: any) => {
                map[item.trade_id] = { pnl: item.unrealized_pnl, price: item.current_price };
            });
            setUnrealizedData(map);
        }
    } catch (e) {
        console.error(e);
    }
  };

  useEffect(() => {
    fetchTrades();
    fetchUnrealizedPnL();
    const interval = setInterval(fetchUnrealizedPnL, 10000); // 10 sec
    return () => clearInterval(interval);
  }, []);

  const openCloseModal = (trade: Trade) => {
    setSelectedTradeToClose(trade);
    setIsCloseModalOpen(true);
  };

  const handleCloseTradeConfirm = async (exitPrice: number, exitReason: string) => {
    if (!selectedTradeToClose) return;
    
    try {
      const response = await fetch(getApiUrl(`/trades/${selectedTradeToClose.id}/close`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          exit_price: exitPrice,
          exit_at: new Date().toISOString(),
          exit_reason: exitReason,
          mae_price: exitPrice * 0.98,
          mfe_price: exitPrice * 1.02
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

  // Logic to detect additions (averaging/pyramiding)
  const enrichedTrades = trades.map(trade => {
    // We assume 'trades' is sorted Newest First (as per fetchTrades).
    // To check if 'trade' is an addition, we look for OLDER trades (which are AFTER it in the array)
    // that overlap with it.
    // Actually, it's safer to look at the whole list.
    
    const isAddition = trades.some(other => 
      other.id !== trade.id && // Not self
      other.symbol === trade.symbol && // Same symbol
      other.direction === trade.direction && // Same direction
      new Date(other.entry_at).getTime() < new Date(trade.entry_at).getTime() && // Other started BEFORE this one
      (other.exit_at ? new Date(other.exit_at).getTime() > new Date(trade.entry_at).getTime() : true) // Other ended AFTER this one started (or is still open)
    );
    
    return { ...trade, isAddition };
  });
  
  const filteredTrades = enrichedTrades.filter(t => {
    const matchesTag = selectedTag ? t.tags?.includes(selectedTag) : true;
    const matchesDirection = filterDirection === 'ALL' ? true : t.direction.toUpperCase() === filterDirection;
    return matchesTag && matchesDirection;
  });

  // Grouping Logic
  const groups: { [key: string]: Trade[] } = {};
  filteredTrades.forEach(trade => {
    const key = trade.exit_at 
      ? `${trade.symbol}-${trade.direction}-${trade.exit_at}`
      : `${trade.symbol}-${trade.direction}-OPEN`;
      
    if (!groups[key]) groups[key] = [];
    groups[key].push(trade);
  });

  const sortedGroupKeys = Object.keys(groups).sort((a, b) => {
    const groupA = groups[a];
    const groupB = groups[b];
    const getDate = (t: Trade) => new Date(t.exit_at || t.entry_at).getTime();
    const maxDateA = Math.max(...groupA.map(getDate));
    const maxDateB = Math.max(...groupB.map(getDate));
    return maxDateB - maxDateA;
  });

  const toggleGroup = (key: string) => {
    const newSet = new Set(expandedGroups);
    if (newSet.has(key)) newSet.delete(key);
    else newSet.add(key);
    setExpandedGroups(newSet);
  };

  if (loading) return <TradeHistorySkeleton />;

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

      <CloseTradeModal
        isOpen={isCloseModalOpen}
        onClose={() => {
          setIsCloseModalOpen(false);
          setSelectedTradeToClose(null);
        }}
        onConfirm={handleCloseTradeConfirm}
        tradeTicker={selectedTradeToClose?.symbol}
        tradeDirection={selectedTradeToClose?.direction}
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
                <th className="pb-2 pl-2">Дата</th>
                <th className="pb-2">Тикер</th>
                <th className="pb-2">Название</th>
                <th className="pb-2">Тип</th>
                <th className="pb-2">Стор.</th>
                <th className="pb-2">Сетап</th>
                <th className="pb-2">Событие</th>
                <th className="pb-2">Причина</th>
                <th className="pb-2">Увер.</th>
                <th className="pb-2">Цена</th>
                <th className="pb-2">Кол-во</th>
                <th className="pb-2">Комис.</th>
                <th className="pb-2">Своп</th>
                <th className="pb-2">PnL</th>
                <th className="pb-2">Чист. PnL</th>
                <th className="pb-2">Теги</th>
                <th className="pb-2 text-right pr-2">Действия</th>
              </tr>
            </thead>
            <tbody className="text-sm">
              {sortedGroupKeys.map((key) => {
                const groupTrades = groups[key];
                // Sort trades within group by entry time (Oldest first)
                const sortedTrades = [...groupTrades].sort((a, b) => new Date(a.entry_at).getTime() - new Date(b.entry_at).getTime());
                const isGroup = groupTrades.length > 1;
                const isExpanded = expandedGroups.has(key);
                
                // Summary Stats for Group
                const firstTrade = sortedTrades[0];
                const totalQty = groupTrades.reduce((sum, t) => sum + t.quantity, 0);
                const totalPnl = groupTrades.reduce((sum, t) => sum + (t.pnl || 0), 0);
                const totalNetPnl = groupTrades.reduce((sum, t) => sum + (t.net_pnl || 0), 0);
                const totalCommission = groupTrades.reduce((sum, t) => sum + (t.commission || 0), 0);
                const totalSwap = groupTrades.reduce((sum, t) => sum + (t.swap || 0), 0);
                const avgEntryPrice = groupTrades.reduce((sum, t) => sum + (t.entry_price * t.quantity), 0) / totalQty;
                const isClosed = groupTrades.every(t => t.exit_at);
                
                const totalUnrealizedPnl = groupTrades.reduce((sum, t) => {
                    if (!t.exit_at && unrealizedData[t.id]) {
                        return sum + unrealizedData[t.id].pnl;
                    }
                    return sum;
                }, 0);
                
                // Render Logic for a Single Trade (used for both single groups and expanded items)
                const renderTrade = (trade: Trade, isChild = false) => (
                  <div className={`flex flex-col w-full ${isChild ? 'border-l-2 border-accent/20 pl-2' : ''}`}>
                    {/* Row 1: Entry */}
                    <div className={`flex items-center py-2 px-2 border-b border-white/5 ${isChild ? 'bg-transparent' : 'bg-white/[0.02]'}`}>
                      <div className="w-[8%] font-mono text-xs opacity-70 flex items-center gap-2">
                        {!isChild && isGroup && (
                           <button onClick={(e) => { e.stopPropagation(); toggleGroup(key); }} className="text-accent hover:text-white">
                              {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                           </button>
                        )}
                        <div>
                          {new Date(trade.entry_at).toLocaleDateString()} <span className="opacity-50 text-[10px]">{new Date(trade.entry_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                        </div>
                      </div>
                      <div className="w-[6%] font-bold">
                        {trade.symbol}
                      </div>
                      <div className="w-[8%] font-mono text-[10px] truncate opacity-70" title={trade.asset_name || ''}>
                        {trade.asset_name || '-'}
                      </div>
                      <div className="w-[5%] font-mono text-[10px] truncate opacity-70" title={trade.asset_type || ''}>
                        {trade.asset_type || '-'}
                      </div>
                      <div className="w-[4%]">
                        <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${trade.direction === 'long' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                          {trade.isAddition ? 'ДОБАВКА' : (trade.direction === 'long' ? 'LONG' : 'SHORT')}
                        </span>
                      </div>
                      <div className="w-[6%] font-mono text-xs truncate" title={trade.setup_name || ''}>
                        {trade.setup_name || '-'}
                      </div>
                      <div className="w-[6%] font-mono text-xs truncate opacity-70" title={trade.news_event || ''}>
                        {trade.news_event || '-'}
                      </div>
                      <div className="w-[6%] font-mono text-xs truncate opacity-70" title={trade.exit_reason || ''}>
                        -
                      </div>
                      <div className="w-[3%] font-mono text-xs text-center">
                        {trade.confidence ? (
                          <span className={`px-1.5 py-0.5 rounded ${
                            trade.confidence >= 8 ? 'bg-green-500/20 text-green-400' :
                            trade.confidence >= 5 ? 'bg-yellow-500/20 text-yellow-400' :
                            'bg-red-500/20 text-red-400'
                          }`}>
                            {trade.confidence}
                          </span>
                        ) : '-'}
                      </div>
                      <div className="w-[7%] font-mono">{trade.entry_price.toLocaleString('ru-RU', { maximumFractionDigits: 4 })}</div>
                      <div className="w-[5%] font-mono">{trade.quantity}</div>
                      <div className="w-[5%] font-mono text-xs opacity-70 text-red-400/70">
                        {trade.entry_commission ? `-${Number(trade.entry_commission).toFixed(2)}` : '-'}
                      </div>
                      <div className="w-[5%] opacity-30">-</div>
                      <div className="w-[7%]">
                        {!trade.exit_at ? (
                            unrealizedData[trade.id] ? (
                                <span className={`font-mono font-bold text-xs ${unrealizedData[trade.id].pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {unrealizedData[trade.id].pnl >= 0 ? '+' : ''}
                                    {unrealizedData[trade.id].pnl.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB' })}
                                    <span className="block text-[9px] opacity-50 text-white">
                                        {unrealizedData[trade.id].price.toLocaleString('ru-RU')}
                                    </span>
                                </span>
                            ) : (
                                <span className="text-[9px] font-bold bg-accent/20 text-accent px-1.5 py-0.5 rounded animate-pulse">
                                  В РАБОТЕ
                                </span>
                            )
                        ) : (
                          <span className="opacity-30">-</span>
                        )}
                      </div>
                      <div className="w-[7%] opacity-30">-</div>
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
                            {/* Close button for open trades */}
                            {!trade.exit_at && (
                              <button 
                                onClick={(e) => { e.stopPropagation(); openCloseModal(trade); }}
                                className="text-yellow-500/50 hover:text-yellow-500 transition-colors p-1"
                                title="Закрыть сделку"
                              >
                                <Lock size={14} />
                              </button>
                            )}
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
                      <div className={`flex items-center py-2 px-2 ${isChild ? 'bg-white/[0.02]' : 'bg-white/[0.04]'}`}>
                        <div className="w-[8%] font-mono text-xs opacity-70 pl-4 border-l-2 border-accent/20">
                          {new Date(trade.exit_at).toLocaleDateString()} <span className="opacity-50 text-[10px]">{new Date(trade.exit_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                        </div>
                        <div className="w-[6%] font-bold opacity-50">
                          {trade.symbol}
                        </div>
                        <div className="w-[8%] font-mono text-[10px] truncate opacity-50" title={trade.asset_name || ''}>
                          {trade.asset_name || '-'}
                        </div>
                        <div className="w-[5%] font-mono text-[10px] truncate opacity-50" title={trade.asset_type || ''}>
                          {trade.asset_type || '-'}
                        </div>
                        <div className="w-[4%]">
                           <span className={`text-[10px] font-mono px-2 py-0.5 rounded opacity-50 ${trade.direction === 'long' ? 'bg-red-500/10 text-red-400' : 'bg-green-500/10 text-green-400'}`}>
                            {trade.direction === 'long' ? 'ПРОДАЖА' : 'ПОКУПКА'}
                          </span>
                        </div>
                        <div className="w-[6%] opacity-30">-</div>
                        <div className="w-[6%] opacity-30">-</div>
                        <div className="w-[6%] font-mono text-xs truncate opacity-70" title={trade.exit_reason || ''}>
                          {trade.exit_reason || '-'}
                        </div>
                        <div className="w-[3%] opacity-30">-</div>
                        <div className="w-[7%] font-mono">{trade.exit_price?.toLocaleString('ru-RU', { maximumFractionDigits: 4 })}</div>
                        <div className="w-[5%] font-mono opacity-50">{trade.quantity}</div>
                        <div className="w-[5%] font-mono text-xs opacity-70 text-red-400/70">
                          {trade.exit_commission ? `-${Number(trade.exit_commission).toFixed(2)}` : '-'}
                        </div>
                        <div className="w-[5%] font-mono text-xs opacity-70 text-red-400/70">
                          -{trade.swap ? trade.swap.toFixed(2) : '0'}
                        </div>
                        <div className="w-[7%] font-mono font-bold">
                          {trade.pnl !== null ? (
                            <span className={Number(trade.pnl) >= 0 ? 'text-green-400' : 'text-red-400'}>
                              {Number(trade.pnl) >= 0 ? '+' : ''}{Number(trade.pnl).toLocaleString('ru-RU', { style: 'currency', currency: 'RUB' })}
                            </span>
                          ) : '-'}
                        </div>
                        <div className="w-[7%] font-mono font-bold">
                          {trade.net_pnl !== null && trade.net_pnl !== undefined ? (
                            <span className={Number(trade.net_pnl) >= 0 ? 'text-green-400' : 'text-red-400'}>
                              {Number(trade.net_pnl) >= 0 ? '+' : ''}{Number(trade.net_pnl).toLocaleString('ru-RU', { style: 'currency', currency: 'RUB' })}
                            </span>
                          ) : '-'}
                        </div>
                        <div className="w-[10%]"></div>
                        <div className="w-[8%]"></div>
                      </div>
                    )}
                  </div>
                );

                if (!isGroup) {
                  return (
                    <tr key={key} className="border-b border-border/50 hover:bg-white/5 transition-colors group">
                      <td colSpan={17} className="p-0 border-none">
                        {renderTrade(firstTrade)}
                      </td>
                    </tr>
                  );
                }

                return (
                  <>
                    {/* Summary Row for Group */}
                    <tr 
                      key={key} 
                      className="border-b border-border/50 hover:bg-white/5 transition-colors cursor-pointer bg-white/[0.02]"
                      onClick={() => toggleGroup(key)}
                    >
                      <td colSpan={17} className="p-0 border-none">
                        <div className="flex items-center py-3 px-2">
                          <div className="w-[8%] font-mono text-xs opacity-70 flex items-center gap-2">
                             <button className="text-accent hover:text-white">
                                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                             </button>
                             <div>
                                {isClosed && firstTrade.exit_at ? (
                                    <>
                                       {new Date(firstTrade.exit_at).toLocaleDateString()} 
                                       <span className="opacity-50 text-[10px] ml-1">{new Date(firstTrade.exit_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                                    </>
                                ) : (
                                    <span className="text-accent animate-pulse">OPEN</span>
                                )}
                             </div>
                          </div>
                          <div className="w-[6%] font-bold text-accent">{firstTrade.symbol}</div>
                          <div className="w-[8%] font-mono text-[10px] truncate opacity-70">{firstTrade.asset_name || '-'}</div>
                          <div className="w-[5%] font-mono text-[10px] truncate opacity-70">{firstTrade.asset_type || '-'}</div>
                          <div className="w-[4%]">
                            <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${firstTrade.direction === 'long' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                              {firstTrade.direction === 'long' ? 'LONG' : 'SHORT'}
                            </span>
                          </div>
                          <div className="w-[6%] font-mono text-xs opacity-50">Mixed</div>
                          <div className="w-[6%] font-mono text-xs opacity-50">-</div>
                          <div className="w-[6%] font-mono text-xs opacity-50">-</div>
                          <div className="w-[3%] opacity-50">-</div>
                          <div className="w-[7%] font-mono text-yellow-400">{avgEntryPrice.toLocaleString('ru-RU', { maximumFractionDigits: 4 })}</div>
                          <div className="w-[5%] font-mono font-bold">{totalQty}</div>
                          <div className="w-[5%] font-mono text-xs opacity-70 text-red-400/70">
                            {totalCommission ? `-${totalCommission.toFixed(2)}` : '-'}
                          </div>
                          <div className="w-[5%] font-mono text-xs opacity-70 text-red-400/70">
                            {totalSwap ? `-${totalSwap.toFixed(2)}` : '-'}
                          </div>
                          <div className="w-[7%] font-mono font-bold text-lg">
                            {isClosed ? (
                              <span className={totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                                {totalPnl >= 0 ? '+' : ''}{totalPnl.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB' })}
                              </span>
                            ) : (
                               totalUnrealizedPnl !== 0 ? (
                                  <span className={`text-sm ${totalUnrealizedPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {totalUnrealizedPnl >= 0 ? '+' : ''}{totalUnrealizedPnl.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB' })}
                                    <span className="block text-[9px] opacity-50 text-accent">OPEN</span>
                                  </span>
                               ) : (
                                   <span className="text-[9px] font-bold bg-accent/20 text-accent px-1.5 py-0.5 rounded animate-pulse">
                                      В РАБОТЕ
                                   </span>
                               )
                            )}
                          </div>
                          <div className="w-[7%] font-mono font-bold">
                            {isClosed ? (
                              <span className={totalNetPnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                                {totalNetPnl >= 0 ? '+' : ''}{totalNetPnl.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB' })}
                              </span>
                            ) : '-'}
                          </div>
                          <div className="w-[10%]"></div>
                          <div className="w-[8%]"></div>
                        </div>
                      </td>
                    </tr>
                    
                    {/* Expanded Children */}
                    {isExpanded && sortedTrades.map(trade => (
                      <tr key={trade.id} className="border-b border-border/30 bg-black/20">
                        <td colSpan={17} className="p-0 border-none pl-8">
                          {renderTrade(trade, true)}
                        </td>
                      </tr>
                    ))}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
