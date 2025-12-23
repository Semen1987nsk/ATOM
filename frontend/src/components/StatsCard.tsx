import React, { useState } from 'react';
import { Info } from 'lucide-react';

interface StatsCardProps {
  title: string;
  value: string | number;
  description?: string;
  trend?: 'up' | 'down';
  icon?: React.ReactNode;
  tooltipText?: string;
}

export const StatsCard: React.FC<StatsCardProps> = ({ title, value, description, trend, icon, tooltipText }) => {
  const [showInfo, setShowInfo] = useState(false);

  return (
    <div 
      className="cyber-card p-6 flex flex-col gap-2 relative overflow-hidden group"
      onMouseEnter={() => setShowInfo(true)}
      onMouseLeave={() => setShowInfo(false)}
    >
      <div className="flex justify-between items-start">
        <span className="text-xs font-mono uppercase tracking-wider opacity-60">{title}</span>
        <div className="flex gap-2 items-center">
          {tooltipText && (
            <Info 
              size={12} 
              className={`transition-opacity duration-300 ${showInfo ? 'opacity-100 text-accent' : 'opacity-0'}`} 
            />
          )}
          {icon && <div className="text-accent opacity-80">{icon}</div>}
        </div>
      </div>
      <div className="text-3xl font-bold tracking-tight text-neon">
        {value}
      </div>
      {description && (
        <div className={`text-xs ${trend === 'up' ? 'text-green-400' : trend === 'down' ? 'text-red-400' : 'opacity-40'}`}>
          {description}
        </div>
      )}

      {/* Cyberpunk Info Overlay */}
      <div className={`absolute inset-0 bg-[#050505]/95 backdrop-blur-md p-5 flex flex-col justify-center border border-accent/20 transition-all duration-300 ease-out ${showInfo ? 'translate-y-0 opacity-100' : 'translate-y-full opacity-0'}`}>
        <div className="text-accent font-bold mb-2 uppercase text-[10px] tracking-widest flex items-center gap-2">
          <Info size={10} /> System Reference
        </div>
        <p className="text-[11px] text-gray-300 leading-relaxed font-mono border-l-2 border-accent/50 pl-3">
          {tooltipText}
        </p>
      </div>
    </div>
  );
};
