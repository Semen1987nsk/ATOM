'use client';

import { Settings, X, Eye, EyeOff } from 'lucide-react';
import { ALL_COLUMNS } from './types';

interface ColumnSettingsProps {
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
  visibleColumns: Set<string>;
  toggleColumn: (columnId: string) => void;
  resetColumns: () => void;
}

export function ColumnSettings({
  isOpen,
  onToggle,
  onClose,
  visibleColumns,
  toggleColumn,
  resetColumns,
}: ColumnSettingsProps) {
  const isColumnVisible = (columnId: string) => visibleColumns.has(columnId);

  return (
    <div className="relative">
      <button
        onClick={onToggle}
        className={`p-2 rounded-lg border transition-all cursor-pointer ${
          isOpen
            ? 'border-accent bg-accent/20 text-accent'
            : 'border-border hover:border-accent/50 text-slate-400 hover:text-accent'
        }`}
        title="Настройки колонок"
      >
        <Settings size={18} />
      </button>

      {/* Column Settings Panel */}
      {isOpen && (
        <div className="absolute right-0 top-12 z-50 bg-slate-900 border border-border rounded-xl shadow-2xl p-4 w-72">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-bold text-white flex items-center gap-2">
              <Settings size={16} className="text-accent" />
              Колонки таблицы
            </h3>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-white"
            >
              <X size={18} />
            </button>
          </div>

          <div className="space-y-1 max-h-80 overflow-y-auto">
            {ALL_COLUMNS.map(col => (
              <button
                key={col.id}
                onClick={() => toggleColumn(col.id)}
                className={`w-full flex items-center justify-between p-2 rounded-lg transition-all ${
                  isColumnVisible(col.id)
                    ? 'bg-accent/20 text-accent'
                    : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800'
                }`}
              >
                <span className="text-sm">{col.label}</span>
                {isColumnVisible(col.id) ? (
                  <Eye size={16} className="text-accent" />
                ) : (
                  <EyeOff size={16} className="text-slate-500" />
                )}
              </button>
            ))}
          </div>

          <div className="mt-4 pt-4 border-t border-border flex justify-between items-center">
            <span className="text-xs text-slate-500">
              {visibleColumns.size} из {ALL_COLUMNS.length} колонок
            </span>
            <button
              onClick={resetColumns}
              className="text-xs text-accent hover:underline"
            >
              Сбросить
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
