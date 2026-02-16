'use client';

import { useState, useEffect, useCallback } from 'react';
import { TrendingUp, Calendar, ChevronDown } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/apiClient';

interface BalanceSnapshot {
  date: string;
  balance: number;
  cash: number;
  stocks_value: number;
  futures_value: number;
  unrealized_pnl: number;
}

interface EquityCurveCardProps {
}

export default function EquityCurveCard({}: EquityCurveCardProps) {
  const { user } = useAuth();
  const [snapshots, setSnapshots] = useState<BalanceSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState(30);
  const [showPeriodMenu, setShowPeriodMenu] = useState(false);

  const fetchHistory = useCallback(async () => {
    if (!user) { setLoading(false); return; }
    try {
      const data = await api.get<{ snapshots: BalanceSnapshot[] }>('/broker/balance-history', { params: { days: period } });
      setSnapshots(data.snapshots || []);
    } catch (e) {
      console.error('Failed to fetch balance history', e);
    } finally {
      setLoading(false);
    }
  }, [user, period]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const formatMoney = (value: number) => {
    if (value >= 1000000) {
      return `${(value / 1000000).toFixed(1)}M`;
    }
    if (value >= 1000) {
      return `${(value / 1000).toFixed(0)}K`;
    }
    return value.toFixed(0);
  };

  const periodOptions = [
    { value: 7, label: '7 дней' },
    { value: 14, label: '14 дней' },
    { value: 30, label: '30 дней' },
    { value: 90, label: '3 месяца' },
    { value: 180, label: '6 месяцев' },
    { value: 365, label: '1 год' }
  ];

  if (loading) {
    return (
      <div className="card p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-cyan-500/20 rounded-lg">
            <TrendingUp className="w-5 h-5 text-cyan-400" />
          </div>
          <h3 className="text-lg font-semibold">Баланс счёта</h3>
        </div>
        <div className="animate-pulse">
          <div className="h-32 bg-slate-700 rounded"></div>
        </div>
      </div>
    );
  }

  if (snapshots.length < 2) {
    return (
      <div className="card p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-slate-700 rounded-lg">
            <TrendingUp className="w-5 h-5 text-slate-400" />
          </div>
          <h3 className="text-lg font-semibold">Баланс счёта</h3>
        </div>
        <div className="text-center py-8 text-slate-400">
          <Calendar className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">Недостаточно данных</p>
          <p className="text-xs text-slate-500 mt-1">
            График появится после нескольких дней торговли
          </p>
        </div>
      </div>
    );
  }

  // Calculate chart data
  const balances = snapshots.map(s => s.balance);
  const minBalance = Math.min(...balances);
  const maxBalance = Math.max(...balances);
  const range = maxBalance - minBalance || 1;
  const padding = range * 0.1;

  const chartMin = minBalance - padding;
  const chartMax = maxBalance + padding;
  const chartRange = chartMax - chartMin;

  // Generate SVG path
  const width = 100;
  const height = 100;
  
  const points = snapshots.map((s, i) => {
    const x = (i / (snapshots.length - 1)) * width;
    const y = height - ((s.balance - chartMin) / chartRange) * height;
    return `${x},${y}`;
  });

  const linePath = `M ${points.join(' L ')}`;
  const areaPath = `${linePath} L ${width},${height} L 0,${height} Z`;

  // Calculate change
  const firstBalance = snapshots[0].balance;
  const lastBalance = snapshots[snapshots.length - 1].balance;
  const change = lastBalance - firstBalance;
  const changePercent = ((change / firstBalance) * 100).toFixed(2);
  const isPositive = change >= 0;

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-gradient-to-br from-cyan-500/20 to-blue-500/20 rounded-lg">
            <TrendingUp className="w-5 h-5 text-cyan-400" />
          </div>
          <div>
            <h3 className="text-lg font-semibold">Баланс счёта</h3>
            <p className="text-xs text-slate-500">{snapshots.length} точек данных</p>
          </div>
        </div>
        
        {/* Period Selector */}
        <div className="relative">
          <button
            onClick={() => setShowPeriodMenu(!showPeriodMenu)}
            className="flex items-center gap-1 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm transition-colors"
          >
            {periodOptions.find(p => p.value === period)?.label}
            <ChevronDown className="w-4 h-4" />
          </button>
          
          {showPeriodMenu && (
            <>
              <div 
                className="fixed inset-0 z-10" 
                onClick={() => setShowPeriodMenu(false)}
              />
              <div className="absolute right-0 top-full mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-20 overflow-hidden">
                {periodOptions.map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => {
                      setPeriod(opt.value);
                      setShowPeriodMenu(false);
                    }}
                    className={`w-full px-4 py-2 text-left text-sm hover:bg-slate-700 transition-colors ${
                      period === opt.value ? 'text-accent' : 'text-slate-300'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Change Summary */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-2xl font-bold">
            {new Intl.NumberFormat('ru-RU', {
              style: 'currency',
              currency: 'RUB',
              minimumFractionDigits: 0,
              maximumFractionDigits: 0
            }).format(lastBalance)}
          </div>
          <div className={`text-sm ${isPositive ? 'text-emerald-400' : 'text-red-400'}`}>
            {isPositive ? '+' : ''}{new Intl.NumberFormat('ru-RU', {
              style: 'currency',
              currency: 'RUB',
              minimumFractionDigits: 0,
              maximumFractionDigits: 0
            }).format(change)} ({isPositive ? '+' : ''}{changePercent}%)
          </div>
        </div>
        <div className="text-right text-sm text-slate-400">
          <div>{new Date(snapshots[0].date).toLocaleDateString('ru-RU')}</div>
          <div>→ {new Date(snapshots[snapshots.length - 1].date).toLocaleDateString('ru-RU')}</div>
        </div>
      </div>

      {/* Chart */}
      <div className="relative h-40">
        <svg 
          viewBox={`0 0 ${width} ${height}`} 
          preserveAspectRatio="none"
          className="w-full h-full"
        >
          {/* Gradient */}
          <defs>
            <linearGradient id="equityGradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop 
                offset="0%" 
                stopColor={isPositive ? '#10b981' : '#ef4444'} 
                stopOpacity="0.3" 
              />
              <stop 
                offset="100%" 
                stopColor={isPositive ? '#10b981' : '#ef4444'} 
                stopOpacity="0.05" 
              />
            </linearGradient>
          </defs>
          
          {/* Grid lines */}
          <line x1="0" y1="25" x2="100" y2="25" stroke="#334155" strokeWidth="0.5" strokeDasharray="2" />
          <line x1="0" y1="50" x2="100" y2="50" stroke="#334155" strokeWidth="0.5" strokeDasharray="2" />
          <line x1="0" y1="75" x2="100" y2="75" stroke="#334155" strokeWidth="0.5" strokeDasharray="2" />
          
          {/* Area */}
          <path d={areaPath} fill="url(#equityGradient)" />
          
          {/* Line */}
          <path 
            d={linePath} 
            fill="none" 
            stroke={isPositive ? '#10b981' : '#ef4444'} 
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          
          {/* End point */}
          <circle 
            cx={width} 
            cy={height - ((lastBalance - chartMin) / chartRange) * height}
            r="3"
            fill={isPositive ? '#10b981' : '#ef4444'}
          />
        </svg>

        {/* Y-axis labels */}
        <div className="absolute left-0 top-0 bottom-0 flex flex-col justify-between text-xs text-slate-500 -translate-x-1">
          <span>{formatMoney(chartMax)}</span>
          <span>{formatMoney((chartMax + chartMin) / 2)}</span>
          <span>{formatMoney(chartMin)}</span>
        </div>
      </div>

      {/* X-axis labels */}
      <div className="flex justify-between mt-2 text-xs text-slate-500">
        <span>{new Date(snapshots[0].date).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' })}</span>
        {snapshots.length > 2 && (
          <span>
            {new Date(snapshots[Math.floor(snapshots.length / 2)].date).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' })}
          </span>
        )}
        <span>{new Date(snapshots[snapshots.length - 1].date).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' })}</span>
      </div>
    </div>
  );
}
