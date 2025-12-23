import React from 'react';

interface StatsCardProps {
  title: string;
  value: string | number;
  description?: string;
  trend?: 'up' | 'down';
  icon?: React.ReactNode;
}

export const StatsCard: React.FC<StatsCardProps> = ({ title, value, description, trend, icon }) => {
  return (
    <div className="cyber-card p-6 flex flex-col gap-2">
      <div className="flex justify-between items-start">
        <span className="text-xs font-mono uppercase tracking-wider opacity-60">{title}</span>
        {icon && <div className="text-accent opacity-80">{icon}</div>}
      </div>
      <div className="text-3xl font-bold tracking-tight text-neon">
        {value}
      </div>
      {description && (
        <div className={`text-xs ${trend === 'up' ? 'text-green-400' : trend === 'down' ? 'text-red-400' : 'opacity-40'}`}>
          {description}
        </div>
      )}
    </div>
  );
};
