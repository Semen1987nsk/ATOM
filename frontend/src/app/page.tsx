'use client';

import { useEffect, useState } from 'react';
import { StatsCard } from '@/components/StatsCard';
import { Activity, TrendingUp, Target, Zap, AlertTriangle } from 'lucide-react';

interface DashboardData {
  total_pnl: number;
  win_rate: number;
  total_trades: number;
  profitable_trades: number;
  optimal_f: number;
  mae_mfe_analysis: {
    avg_mae_ratio: number;
    avg_mfe_ratio: number;
    recommendations: string[];
  };
}

export default function Home() {
  const [stats, setStats] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await fetch('http://localhost:8000/stats/');
        const data = await response.json();
        setStats(data);
      } catch (error) {
        console.error('Failed to fetch stats:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
  }, []);

  if (loading) return <div className="p-8 font-mono text-accent animate-pulse">INITIALIZING SYSTEM...</div>;

  return (
    <main className="min-h-screen p-8 max-w-7xl mx-auto">
      <header className="mb-12">
        <h1 className="text-4xl font-black tracking-tighter mb-2 italic">
          ATOM <span className="text-accent">TERMINAL</span>
        </h1>
        <p className="text-xs font-mono opacity-50 uppercase tracking-[0.2em]">
          AI-Powered Trading Intelligence System v1.0.4
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatsCard 
          title="Total PnL" 
          value={`$${stats?.total_pnl.toFixed(2)}`} 
          description="Net profit after commissions"
          trend={stats?.total_pnl && stats.total_pnl > 0 ? 'up' : 'down'}
          icon={<TrendingUp size={18} />}
        />
        <StatsCard 
          title="Win Rate" 
          value={`${stats?.win_rate.toFixed(1)}%`} 
          description={`${stats?.profitable_trades} of ${stats?.total_trades} trades`}
          icon={<Target size={18} />}
        />
        <StatsCard 
          title="Optimal f" 
          value={stats?.optimal_f || 0} 
          description="Recommended risk unit"
          icon={<Zap size={18} />}
        />
        <StatsCard 
          title="Efficiency" 
          value={stats?.mae_mfe_analysis?.avg_mfe_ratio || 0} 
          description="Avg MFE / Risk ratio"
          icon={<Activity size={18} />}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 cyber-card p-6">
          <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2">
            <Activity size={16} className="text-accent" />
            Performance Analytics
          </h2>
          <div className="h-[300px] flex items-center justify-center border border-dashed border-border opacity-30">
            [ Equity Curve Chart Placeholder ]
          </div>
        </div>

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
      </div>
    </main>
  );
}
