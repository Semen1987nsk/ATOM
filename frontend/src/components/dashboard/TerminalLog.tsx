'use client';

import { useLanguage } from '@/i18n/LanguageContext';

interface LogEntry {
  msg: string;
  time: string;
}

interface TerminalLogProps {
  logs: LogEntry[];
}

export function TerminalLog({ logs }: TerminalLogProps) {
  const { t } = useLanguage();

  return (
    <div className="mt-8 cyber-card p-4 bg-black/50 border-t-2 border-accent/20 relative overflow-hidden">
      {/* Scan line animation */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent animate-pulse" />
      </div>
      
      <div className="flex items-center gap-2 mb-3 opacity-50">
        <div className="w-2 h-2 bg-accent rounded-full animate-pulse" />
        <span className="text-[10px] font-mono uppercase tracking-widest">{t.logs.title}</span>
        <span className="text-[9px] opacity-50 ml-auto font-mono">{logs.length} записей</span>
      </div>
      <div className="space-y-1 font-mono text-[10px] max-h-32 overflow-y-auto scrollbar-thin scrollbar-thumb-accent/20 scrollbar-track-transparent">
        {logs.map((log, i) => (
          <div 
            key={i} 
            className={`flex gap-4 py-0.5 ${i === 0 ? 'text-accent' : 'opacity-60'} hover:opacity-100 transition-opacity`}
          >
            <span className="opacity-30 shrink-0">[{log.time}]</span>
            <span className="flex-1">
              {i === 0 && <span className="text-accent mr-1">▸</span>}
              {log.msg}
            </span>
          </div>
        ))}
        {logs.length === 0 && (
          <div className="opacity-20 italic py-4 text-center">
            <span className="animate-pulse">_</span> Ожидание системных событий...
          </div>
        )}
      </div>
    </div>
  );
}
