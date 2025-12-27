'use client';

import { useEffect, useState } from 'react';
import { StatsCard } from '@/components/StatsCard';
import { AddTradeModal } from '@/components/AddTradeModal';
import Link from 'next/link';
import { Activity, TrendingUp, Target, Zap, AlertTriangle, Plus, Lock, Download, Upload, Trash2, BookOpen, GitGraph, History } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';

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

interface DashboardData {
  total_pnl: number;
  win_rate: number;
  total_trades: number;
  profitable_trades: number;
  optimal_f: number;
  sqn: {
    sqn: number;
    rating: string;
  };
  z_score: {
    z_score: number;
    verdict: string;
    description: string;
  };
  profit_factor: number;
  r_expectancy: number;
  recovery_factor: number;
  ahpr: number;
  mae_mfe_analysis: {
    avg_mae_ratio: number;
    avg_mfe_ratio: number;
    recommendations: string[];
  };
  equity_curve: { date: string; balance: number }[];
  tag_stats: { tag: string; pnl: number; win_rate: number; count: number }[];
}

export default function Home() {
  const [stats, setStats] = useState<DashboardData | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [logs, setLogs] = useState<{msg: string, time: string}[]>([]);
  const [mounted, setMounted] = useState(false);

  const getApiUrl = (path: string) => {
    if (typeof window !== 'undefined' && window.location.hostname.includes('github.dev')) {
      const codespaceName = window.location.hostname.split('-3000')[0];
      return `https://${codespaceName}-8000.app.github.dev${path}`;
    }
    return `http://localhost:8000${path}`;
  };

  const addLog = (msg: string) => {
    const time = new Date().toLocaleTimeString();
    setLogs(prev => [{msg, time}, ...prev].slice(0, 5));
  };

  const fetchData = async () => {
    try {
      const [statsRes, tradesRes] = await Promise.all([
        fetch(getApiUrl('/stats/')),
        fetch(getApiUrl('/trades/'))
      ]);
      const statsData = await statsRes.json();
      const tradesData = await tradesRes.json();
      setStats(statsData);
      setTrades(tradesData.reverse());
      addLog('System data synchronized');
    } catch (error) {
      console.error('Failed to fetch data:', error);
      addLog('ERROR: Sync failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setMounted(true);
    fetchData();
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
        fetchData();
        addLog(`Position closed: ${tradeId}`);
      }
    } catch (error) {
      console.error('Failed to close trade:', error);
      addLog('ERROR: Close failed');
    }
  };

  const handleExport = async () => {
    try {
      window.open(getApiUrl('/trades/export'), '_blank');
      addLog('Exporting CSV data...');
    } catch (error) {
      console.error('Export failed:', error);
      addLog('ERROR: Export failed');
    }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      addLog('Uploading trade data...');
      const response = await fetch(getApiUrl('/trades/import'), {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const result = await response.json();
        addLog(result.message);
        fetchData();
      } else {
        const err = await response.json();
        addLog(`ERROR: ${err.detail}`);
      }
    } catch (error) {
      console.error('Import failed:', error);
      addLog('ERROR: Import failed');
    }
    // Reset input
    e.target.value = '';
  };

  const handleDelete = async (tradeId: number) => {
    if (!confirm('Are you sure you want to delete this trade?')) return;
    try {
      await fetch(getApiUrl(`/trades/${tradeId}`), { method: 'DELETE' });
      fetchData();
      addLog(`Trade ${tradeId} purged from database`);
    } catch (error) {
      console.error('Delete failed:', error);
      addLog('ERROR: Purge failed');
    }
  };

  if (!mounted) return null;
  if (loading) return <div className="p-8 font-mono text-accent animate-pulse">INITIALIZING SYSTEM...</div>;

  const allTags = Array.from(new Set(trades.flatMap(t => t.tags || [])));
  const filteredTrades = selectedTag 
    ? trades.filter(t => t.tags?.includes(selectedTag)) 
    : trades;

  return (
    <main className="min-h-screen p-8 max-w-7xl mx-auto">
      <header className="mb-12 flex justify-between items-start">
        <div>
          <h1 className="text-4xl font-black tracking-tighter mb-2 italic">
            Set<span className="text-accent">Up</span>
          </h1>
          <p className="text-xs font-mono opacity-50 uppercase tracking-[0.2em]">
            AI-Powered Trading Intelligence System v1.0.4
          </p>
        </div>
        <div className="flex gap-4">
          <Link 
            href="/history"
            className="flex items-center gap-2 bg-surface border border-border px-4 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest text-accent"
          >
            <History size={14} />
            Trade History
          </Link>
          <Link 
            href="/manual"
            className="flex items-center gap-2 bg-surface border border-border px-4 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest text-accent"
          >
            <BookOpen size={14} />
            System Manual
          </Link>
          <label className="flex items-center gap-2 bg-surface border border-border px-4 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest cursor-pointer">
            <input type="file" accept=".csv,.xlsx,.xls,.pdf" className="hidden" onChange={handleImport} />
            <Upload size={14} />
            Import Data
          </label>
          <button 
            onClick={handleExport}
            className="flex items-center gap-2 bg-surface border border-border px-4 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest"
          >
            <Download size={14} />
            Export CSV
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
        onSuccess={() => {
          fetchData();
          addLog('New position initialized');
        }} 
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatsCard 
          title="Total PnL" 
          value={`$${Number(stats?.total_pnl || 0).toFixed(2)}`} 
          description="Net profit after commissions"
          trend={stats?.total_pnl && stats.total_pnl > 0 ? 'up' : 'down'}
          icon={<TrendingUp size={18} />}
          tooltipText="Чистая прибыль или убыток по всем закрытым сделкам с учетом комиссий. Основной показатель финансового результата."
        />
        <StatsCard 
          title="Win Rate" 
          value={`${stats?.win_rate.toFixed(1)}%`} 
          description={`${stats?.profitable_trades} of ${stats?.total_trades} trades`}
          icon={<Target size={18} />}
          tooltipText="Процент прибыльных сделок. Формула: (Кол-во прибыльных / Общее кол-во) * 100. Для трендовых стратегий норма 30-40%, для скальпинга >50%."
        />
        <StatsCard 
          title="Optimal f" 
          value={stats?.optimal_f || 0} 
          description="Vince's risk model"
          icon={<Zap size={18} />}
          tooltipText="Модель Ральфа Винса. Показывает оптимальную долю капитала для риска в одной сделке, чтобы максимизировать геометрический рост депозита."
        />
        <StatsCard 
          title="System Quality (SQN)" 
          value={stats?.sqn?.sqn || 0} 
          description={stats?.sqn?.rating || "Calculating..."}
          icon={<Activity size={18} />}
          tooltipText="System Quality Number (Ван Тарп). Оценивает качество системы. SQN = (Ожидание / Станд.Откл) * корень(N). >2.0 — хорошо, >3.0 — отлично."
        />
        <StatsCard 
          title="Z-Score (Serial)" 
          value={stats?.z_score?.z_score || 0} 
          description={stats?.z_score?.verdict || "Calculating..."}
          icon={<GitGraph size={18} />}
          tooltipText={stats?.z_score?.description || "Z-Score показывает зависимость между сделками. > 1.96: Пила (чередование). < -1.96: Серии (тренды). Около 0: Случайность."}
        />
        <StatsCard 
          title="Profit Factor" 
          value={stats?.profit_factor || 0} 
          description="Gross Profit / Gross Loss"
          icon={<TrendingUp size={18} />}
          tooltipText="Отношение общей прибыли к общему убытку. > 1.5 — хорошо, > 2.0 — отлично. Если < 1.0 — система убыточна."
        />
        <StatsCard 
          title="R-Expectancy" 
          value={`${stats?.r_expectancy || 0}R`} 
          description="Avg Return per 1R Risk"
          icon={<Target size={18} />}
          tooltipText="Матожидание в R (рисках). Показывает, сколько вы зарабатываете на каждый доллар риска. 0.5R означает $50 прибыли на $100 риска."
        />
        <StatsCard 
          title="Recovery Factor" 
          value={stats?.recovery_factor || 0} 
          description="Net Profit / Max Drawdown"
          icon={<Activity size={18} />}
          tooltipText="Фактор восстановления. Показывает, насколько быстро система выходит из просадок. Чем выше, тем лучше. > 3.0 — отличная устойчивость."
        />
        <StatsCard 
          title="AHPR" 
          value={stats?.ahpr || 0} 
          description="Avg Holding Period Return"
          icon={<TrendingUp size={18} />}
          tooltipText="Средняя доходность за период удержания (Geometric Mean). Если 1.05, то +5% за сделку. Ключ к сложному проценту."
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <div className="cyber-card p-6">
            <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2">
              <Activity size={16} className="text-accent" />
              Equity Curve
            </h2>
            <div className="h-[250px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={stats?.equity_curve || []}>
                  <defs>
                    <linearGradient id="colorBalance" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#00ff9f" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#00ff9f" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1a1a1a" vertical={false} />
                  <XAxis 
                    dataKey="date" 
                    stroke="#444" 
                    fontSize={10} 
                    tickLine={false} 
                    axisLine={false}
                    tickFormatter={(str) => str.split(' ')[0]} 
                  />
                  <YAxis 
                    stroke="#444" 
                    fontSize={10} 
                    tickLine={false} 
                    axisLine={false}
                    tickFormatter={(val) => `$${val}`}
                  />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0d0d0d', border: '1px solid #1a1a1a', fontSize: '12px' }}
                    itemStyle={{ color: '#00ff9f' }}
                  />
                  <Area 
                    type="monotone" 
                    dataKey="balance" 
                    stroke="#00ff9f" 
                    fillOpacity={1} 
                    fill="url(#colorBalance)" 
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="cyber-card p-6">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-sm font-mono uppercase flex items-center gap-2">
                <Activity size={16} className="text-accent" />
                Recent Trades & AI Analysis
              </h2>
              <Link href="/history" className="text-[10px] font-mono text-accent hover:underline">
                VIEW ALL
              </Link>
            </div>
            <div className="space-y-4">
              {filteredTrades.length === 0 ? (
                <div className="text-center py-8 opacity-30 font-mono">NO TRADES MATCHING FILTER</div>
              ) : (
                filteredTrades.slice(0, 5).map((trade) => ( // Show only last 5 trades
                  <div key={trade.id} className="border-b border-border pb-4 last:border-0">
                    <div className="flex justify-between items-center mb-2">
                      <div className="flex items-center gap-3">
                        <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${trade.direction === 'long' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                          {trade.direction.toUpperCase()}
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
                              {Number(trade.pnl) >= 0 ? '+' : ''}{Number(trade.pnl).toFixed(2)}
                            </span>
                          ) : (
                            <span className="text-[10px] text-accent">OPEN</span>
                          )}
                          {trade.commission && <div className="text-[9px] text-gray-500">Comm: {trade.commission.toFixed(2)}</div>}
                        </div>
                        
                        <button 
                          onClick={() => handleDelete(trade.id)}
                          className="text-red-500/50 hover:text-red-500 transition-colors p-1"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                    
                    <div className="flex flex-wrap gap-2 mb-2 items-center">
                      {trade.setup_name && (
                         <span className="text-[10px] bg-blue-500/10 text-blue-400 px-1.5 py-0.5 rounded">
                           Setup: {trade.setup_name}
                         </span>
                      )}
                      {trade.timeframe && (
                         <span className="text-[10px] bg-purple-500/10 text-purple-400 px-1.5 py-0.5 rounded">
                           TF: {trade.timeframe}
                         </span>
                      )}
                      {trade.tags && trade.tags.length > 0 && trade.tags.map(tag => (
                          <span key={tag} className="text-[9px] font-mono border border-border px-1.5 opacity-50">
                            #{tag.toUpperCase()}
                          </span>
                        ))}
                    </div>

                    {trade.ai_analysis && (
                      <div className="bg-white/5 p-3 rounded text-xs">
                        <div className="flex items-center gap-2 mb-1">
                          <Zap size={12} className="text-accent" />
                          <span className="font-bold uppercase text-accent">{trade.ai_analysis.verdict}</span>
                          <span className="opacity-40 ml-auto">Score: {trade.ai_analysis.score}/100</span>
                        </div>
                        <p className="opacity-70 mb-2">{trade.ai_analysis.analysis}</p>
                        <p className="text-accent-secondary italic">Advice: {trade.ai_analysis.advice}</p>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="cyber-card p-6 border-l-accent/30">
            <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2">
              <AlertTriangle size={16} className="text-accent" />
              AI Insights
            </h2>
            <div className="space-y-4">
              {stats?.mae_mfe_analysis?.recommendations.map((rec, i) => (
                <div key={i} className="p-3 bg-accent/5 border-l-2 border-accent text-sm">
                  {rec}
                </div>
              ))}
              <div className="p-3 bg-accent-secondary/5 border-l-2 border-accent-secondary text-sm opacity-80">
                Optimal f suggests risking {((stats?.optimal_f || 0) * 10).toFixed(1)}% per trade for maximum growth.
              </div>
            </div>
          </div>

          <div className="cyber-card p-6 border-l-accent-secondary/30">
            <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2">
              <Target size={16} className="text-accent-secondary" />
              Tag Performance
            </h2>
            <div className="space-y-3">
              {stats?.tag_stats.length === 0 ? (
                <div className="text-center py-4 opacity-30 font-mono text-[10px]">NO TAG DATA</div>
              ) : (
                stats?.tag_stats.map((item) => (
                  <div key={item.tag} className="flex justify-between items-center border-b border-border pb-2 last:border-0">
                    <div>
                      <div className="text-[10px] font-mono text-accent-secondary uppercase">#{item.tag}</div>
                      <div className="text-[9px] opacity-40">{item.count} trades</div>
                    </div>
                    <div className="text-right">
                      <div className={`text-xs font-bold ${Number(item.pnl) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {Number(item.pnl) >= 0 ? '+' : ''}{Number(item.pnl).toFixed(2)}
                      </div>
                      <div className="text-[9px] opacity-60">{item.win_rate}% WR</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Terminal Log */}
      <div className="mt-8 cyber-card p-4 bg-black/50 border-t-2 border-accent/20">
        <div className="flex items-center gap-2 mb-2 opacity-50">
          <div className="w-2 h-2 bg-accent rounded-full animate-pulse" />
          <span className="text-[10px] font-mono uppercase tracking-widest">System Terminal Log</span>
        </div>
        <div className="space-y-1">
          {logs.map((log, i) => (
            <div key={i} className="font-mono text-[10px] flex gap-4">
              <span className="opacity-30">[{log.time}]</span>
              <span className={i === 0 ? 'text-accent' : 'opacity-60'}>
                {i === 0 ? '> ' : '  '}{log.msg}
              </span>
            </div>
          ))}
          {logs.length === 0 && (
            <div className="font-mono text-[10px] opacity-20 italic">Waiting for system events...</div>
          )}
        </div>
      </div>
    </main>
  );
}
