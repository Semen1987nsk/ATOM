'use client';

import { Activity } from 'lucide-react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import { useLanguage } from '@/i18n/LanguageContext';
import { useSettings } from '@/contexts/SettingsContext';

interface EquityDataPoint {
  date: string;
  balance: number;
}

interface EquityChartProps {
  data: EquityDataPoint[];
}

export function EquityChart({ data }: EquityChartProps) {
  const { t } = useLanguage();
  const { settings } = useSettings();

  return (
    <div className="cyber-card p-6 relative overflow-hidden group">
      {/* Background glow */}
      <div className="absolute top-0 right-0 w-64 h-64 bg-accent/5 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
      
      <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2 relative z-10">
        <Activity size={16} className="text-accent" />
        {t.charts.equityCurve}
        <span className="text-[10px] opacity-50 normal-case ml-1">(по сделкам)</span>
        <span className="ml-auto text-[10px] opacity-40">{data?.length || 0} {t.charts.dataPoints || 'points'}</span>
      </h2>
      <div className="h-[250px] w-full relative z-10">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data || []}>
            <defs>
              <linearGradient id="colorBalance" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#00ff9f" stopOpacity={0.4}/>
                <stop offset="50%" stopColor="#00ff9f" stopOpacity={0.15}/>
                <stop offset="100%" stopColor="#00ff9f" stopOpacity={0}/>
              </linearGradient>
              <linearGradient id="strokeGradient" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="#00ff9f" stopOpacity={0.5}/>
                <stop offset="50%" stopColor="#00ff9f" stopOpacity={1}/>
                <stop offset="100%" stopColor="#bc13fe" stopOpacity={0.8}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1a1a1a" vertical={false} />
            <XAxis 
              dataKey="date" 
              stroke="#333" 
              fontSize={10} 
              tickLine={false} 
              axisLine={false}
              tickFormatter={(str) => str.split(' ')[0]} 
            />
            <YAxis 
              stroke="#333" 
              fontSize={10} 
              tickLine={false} 
              axisLine={false}
              tickFormatter={(val) => `${settings.currencySymbol}${val}`}
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: 'rgba(13, 13, 13, 0.95)', 
                border: '1px solid rgba(0, 255, 159, 0.3)', 
                borderRadius: '8px',
                boxShadow: '0 0 20px rgba(0, 255, 159, 0.1)',
                backdropFilter: 'blur(10px)',
                fontSize: '12px' 
              }}
              itemStyle={{ color: '#00ff9f' }}
              labelStyle={{ color: '#888', marginBottom: '4px' }}
              cursor={{ stroke: 'rgba(0, 255, 159, 0.3)', strokeWidth: 1 }}
            />
            <Area 
              type="monotone" 
              dataKey="balance" 
              stroke="url(#strokeGradient)" 
              fillOpacity={1} 
              fill="url(#colorBalance)" 
              strokeWidth={2}
              dot={false}
              activeDot={{ 
                r: 6, 
                fill: '#00ff9f', 
                stroke: '#000', 
                strokeWidth: 2,
                style: { filter: 'drop-shadow(0 0 6px rgba(0, 255, 159, 0.8))' }
              }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
