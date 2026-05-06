'use client';

import { Activity } from 'lucide-react';
import { useLanguage } from '@/i18n/LanguageContext';

interface LogEntry {
  msg: string;
  time: string;
}

interface TerminalLogProps {
  logs: LogEntry[];
}

/**
 * Лента системных событий — компактная, без cyber-эффектов.
 * Mono-шрифт оставлен для outline времени и MS-точности — это
 * единственное место в UI, где монохром оправдан семантически (terminal log).
 */
export function TerminalLog({ logs }: TerminalLogProps) {
  const { t } = useLanguage();

  return (
    <div className="mt-8 cyber-card p-4">
      <div className="flex items-center gap-2 mb-3">
        <Activity size={14} className="text-[var(--accent)]" />
        <span className="text-[12px] font-medium text-[var(--text-secondary)]">
          {t.logs.title}
        </span>
        <span className="ml-auto text-[11px] text-[var(--text-tertiary)] tabular-nums">
          {logs.length} {logs.length === 1 ? 'запись' : 'записей'}
        </span>
      </div>

      <div className="font-mono text-[12px] max-h-40 overflow-y-auto scrollbar-thin">
        {logs.length === 0 ? (
          <div className="text-center py-4 text-[var(--text-tertiary)] italic">
            Нет системных событий
          </div>
        ) : (
          <ul className="flex flex-col gap-0.5 list-none p-0">
            {logs.map((log, i) => (
              <li
                key={i}
                className={`flex gap-3 py-0.5 px-1 rounded ${
                  i === 0
                    ? 'text-[var(--foreground)]'
                    : 'text-[var(--text-secondary)]'
                } hover:bg-[var(--surface-hover)]`}
              >
                <span className="text-[var(--text-tertiary)] flex-shrink-0 tabular-nums">
                  {log.time}
                </span>
                <span className="flex-1 break-words">{log.msg}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
