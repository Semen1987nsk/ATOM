'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { 
  Gauge, Search, ChevronDown, ChevronUp, Filter, 
  Star, AlertTriangle, 
  X, ArrowUpDown, Hash,
  Layers, RefreshCw, Calendar, List, Zap,
  Edit3
} from 'lucide-react';
import { useSettings } from '@/contexts/SettingsContext';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/apiClient';

interface GroupItem {
  name: string;
  asset_name?: string;
  asset_type?: string;
  trades_count: number;
  wins: number;
  win_rate: number;
  total_pnl: number;
  avg_mae: number;
  avg_mfe: number;
  avg_efficiency: number;
  edge_ratio: number;
  quality_score: number;
  mae_percentiles?: {
    p25: number;
    p50: number;
    p75: number;
    max: number;
  };
  mfe_percentiles?: {
    p25: number;
    p50: number;
    p75: number;
    max: number;
  };
  recommendations?: Array<{
    type: string;
    icon: string;
    text: string;
  }>;
}

interface AnalysisResponse {
  group_by: string;
  items?: GroupItem[];
  total_trades: number;
  trades_count?: number;
  total_groups?: number;
  filter_value?: string;
  avg_mae?: number;
  avg_mfe?: number;
  avg_efficiency?: number;
  edge_ratio?: number;
  quality_score?: number;
  wins?: number;
  losses?: number;
  win_rate?: number;
  total_pnl?: number;
  // Real performance metrics
  avg_win?: number;
  avg_loss?: number;
  real_rr?: number;
  profit_factor?: number;
  required_winrate?: number;
  recommendations?: Array<{type: string; icon: string; text: string}>;
  mae_percentiles?: {
    p25: number;
    p50: number;
    p75: number;
    max: number;
  };
  mfe_percentiles?: {
    p25: number;
    p50: number;
    p75: number;
    max: number;
  };
}

interface Setup {
  id: number;
  name: string;
}

interface TagInfo {
  tag: string;
  count: number;
  pnl: number;
  win_rate: number;
}

interface MAEMFEAnalysisPanelProps {
  onRecalculate?: () => void;
}

type GroupByType = 'tag' | 'setup';
type SortField = 'edge_ratio' | 'quality_score' | 'win_rate' | 'total_pnl' | 'trades_count' | 'avg_mae' | 'avg_mfe';
type PeriodType = 'all' | 'week' | 'month' | '3months' | 'year';

const LIMIT_PRESETS = ['all', '20', '50', '100', '200'] as const;

export function MAEMFEAnalysisPanel({ onRecalculate }: MAEMFEAnalysisPanelProps) {
  // Get global filter settings
  const { settings } = useSettings();
  const { user } = useAuth();
  const { tradesStartDate, tradesStartTradeId, tradesStartTradeSymbol, maeCalculationMethod } = settings;
  
  const [groupBy, setGroupBy] = useState<GroupByType>('tag');
  const [data, setData] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedItem, setSelectedItem] = useState<string | null>(null);
  const [selectedItemData, setSelectedItemData] = useState<AnalysisResponse | null>(null);
  const [isExpanded, setIsExpanded] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  
  // Available setups and tags for autocomplete
  const [availableSetups, setAvailableSetups] = useState<Setup[]>([]);
  const [availableTags, setAvailableTags] = useState<TagInfo[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  
  // Filters
  const [assetTypeFilter, setAssetTypeFilter] = useState<string | null>(null);
  const [directionFilter, setDirectionFilter] = useState<string | null>(null);
  const [tradesLimit, setTradesLimit] = useState<string>('all');
  const [customLimit, setCustomLimit] = useState<string>('');
  const [showCustomLimitInput, setShowCustomLimitInput] = useState(false);
  const [period, setPeriod] = useState<PeriodType>('all');
  const [showFilters, setShowFilters] = useState(false);
  
  // Sorting
  const [sortField, setSortField] = useState<SortField>('edge_ratio');
  const [sortAsc, setSortAsc] = useState(false);

  // Coverage stats
  const [coverageStats, setCoverageStats] = useState<{total: number; with_mae: number; pct: number} | null>(null);
  
  // Recalculation
  const [isRecalculating, setIsRecalculating] = useState(false);
  const [showRecalcOptions, setShowRecalcOptions] = useState(false);

  // Fetch available setups
  useEffect(() => {
    if (!user) return;
    const fetchSetups = async () => {
      try {
        const setups = await api.get<Setup[]>('/setups/');
        setAvailableSetups(setups);
      } catch (e) {
        console.error('Failed to fetch setups:', e);
      }
    };
    fetchSetups();
  }, [user]);

  // Fetch available tags
  useEffect(() => {
    if (!user) return;
    const fetchTags = async () => {
      try {
        const tags = await api.get<TagInfo[]>('/stats/tags/');
        setAvailableTags(tags);
      } catch (e) {
        console.error('Failed to fetch tags:', e);
      }
    };
    fetchTags();
  }, [user]);

  const fetchCoverage = useCallback(async () => {
    try {
      const stats = await api.get<{ total_closed: number; with_mae_mfe: number; coverage_pct: number }>('/trades/mae-mfe-stats');
      setCoverageStats({
        total: stats.total_closed,
        with_mae: stats.with_mae_mfe,
        pct: stats.coverage_pct
      });
    } catch (e) {
      console.error('Failed to fetch coverage:', e);
    }
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('group_by', groupBy);
      if (assetTypeFilter) params.append('asset_type', assetTypeFilter);
      if (directionFilter) params.append('direction', directionFilter);
      
      // Apply MAE calculation method from settings
      params.append('mae_method', maeCalculationMethod);
      
      // Apply limit (custom or preset)
      const effectiveLimit = tradesLimit !== 'all' ? tradesLimit : null;
      if (effectiveLimit) params.append('limit', effectiveLimit);
      
      if (period !== 'all') params.append('period', period);
      
      // Apply global start_trade_id filter
      if (tradesStartTradeId) {
        params.append('start_trade_id', tradesStartTradeId.toString());
      }
      
      const res = await api.get<AnalysisResponse>('/stats/mae-mfe-analysis', { params: Object.fromEntries(params) });
      setData(res);
    } catch (e) {
      console.error('Failed to fetch MAE/MFE analysis:', e);
    } finally {
      setLoading(false);
    }
  }, [groupBy, assetTypeFilter, directionFilter, tradesLimit, period, tradesStartTradeId, maeCalculationMethod]);

  const fetchItemDetails = useCallback(async (itemName: string) => {
    try {
      const params = new URLSearchParams();
      params.append('group_by', groupBy);
      params.append('filter_value', itemName);
      
      // Apply MAE calculation method from settings
      params.append('mae_method', maeCalculationMethod);
      
      const effectiveLimit = tradesLimit !== 'all' ? tradesLimit : null;
      if (effectiveLimit) params.append('limit', effectiveLimit);
      
      if (period !== 'all') params.append('period', period);
      
      // Apply global start_trade_id filter
      if (tradesStartTradeId) {
        params.append('start_trade_id', tradesStartTradeId.toString());
      }
      
      const res = await api.get<AnalysisResponse>('/stats/mae-mfe-analysis', { params: Object.fromEntries(params) });
      setSelectedItemData(res);
    } catch (e) {
      console.error('Failed to fetch item details:', e);
    }
  }, [groupBy, maeCalculationMethod, tradesLimit, period, tradesStartTradeId]);

  useEffect(() => {
    if (!user) return;
    fetchData();
    fetchCoverage();
  }, [user, fetchData, fetchCoverage]);

  useEffect(() => {
    if (selectedItem) {
      fetchItemDetails(selectedItem);
    } else {
      setSelectedItemData(null);
    }
  }, [selectedItem, fetchItemDetails]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  // Filter suggestions based on group type
  // Note: Show all tags including system ones for autocomplete
  const filteredSuggestions = groupBy === 'tag' 
    ? availableTags.filter(t => t.tag.toLowerCase().includes(searchQuery.toLowerCase()))
    : availableSetups.filter(s => s.name.toLowerCase().includes(searchQuery.toLowerCase()));

  const sortedItems = data?.items
    ?.filter(item => !searchQuery || 
      item.name.toLowerCase().includes(searchQuery.toLowerCase())
    )
    ?.sort((a, b) => {
      const aVal = (a as any)[sortField] || 0;
      const bVal = (b as any)[sortField] || 0;
      return sortAsc ? aVal - bVal : bVal - aVal;
    }) || [];

  const getQualityColor = (score: number) => {
    if (score >= 70) return 'text-green-400';
    if (score >= 50) return 'text-yellow-400';
    if (score >= 30) return 'text-orange-400';
    return 'text-red-400';
  };

  const getEdgeColor = (edge: number) => {
    if (edge >= 2) return 'text-green-400';
    if (edge >= 1.5) return 'text-cyan-400';
    if (edge >= 1) return 'text-yellow-400';
    return 'text-red-400';
  };

  const formatPnl = (pnl: number) => {
    const formatted = Math.abs(pnl).toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    return pnl >= 0 ? `+₽${formatted}` : `-₽${formatted}`;
  };

  const getGroupIcon = () => {
    switch (groupBy) {
      case 'tag': return <Hash size={16} className="text-purple-400" />;
      case 'setup': return <Layers size={16} className="text-emerald-400" />;
    }
  };

  const getGroupLabel = () => {
    switch (groupBy) {
      case 'tag': return 'Теги (Стратегии)';
      case 'setup': return 'Сетапы';
    }
  };

  const handleRecalculate = async (forceAll: boolean = false) => {
    setIsRecalculating(true);
    setShowRecalcOptions(false);
    try {
      await api.post('/trades/calculate-mae-mfe', { params: { force_all: forceAll } });
      await fetchData();
      await fetchCoverage();
      onRecalculate?.();
    } catch (e) {
      console.error('Failed to recalculate:', e);
    } finally {
      setIsRecalculating(false);
    }
  };

  const handleSelectSuggestion = (name: string) => {
    setSearchQuery(name);
    setShowSuggestions(false);
  };

  const handleSetCustomLimit = () => {
    const num = parseInt(customLimit, 10);
    if (num > 0) {
      setTradesLimit(customLimit);
      setShowCustomLimitInput(false);
    }
  };

  const getPeriodLabel = (p: PeriodType) => {
    switch (p) {
      case 'all': return 'Всё время';
      case 'week': return 'Неделя';
      case 'month': return 'Месяц';
      case '3months': return '3 мес.';
      case 'year': return 'Год';
    }
  };

  const getLimitLabel = (l: string) => {
    if (l === 'all') return 'Все сделки';
    return `Последние ${l}`;
  };

  // Format global filter display
  const getGlobalFilterLabel = () => {
    if (tradesStartDate && tradesStartTradeId) {
      const date = new Date(tradesStartDate);
      const dateStr = date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
      if (tradesStartTradeSymbol) {
        return `С ${tradesStartTradeSymbol} (${dateStr})`;
      }
      return `С ${dateStr}`;
    }
    return null;
  };

  const globalFilterLabel = getGlobalFilterLabel();

  return (
    <div className="cyber-card overflow-hidden relative">
      {/* Background gradient */}
      <div className="absolute -top-20 -right-20 w-40 h-40 bg-gradient-to-br from-purple-500/10 via-emerald-500/10 to-cyan-500/10 rounded-full blur-3xl pointer-events-none" />
      
      {/* Header */}
      <div className="p-6 pb-4 relative z-10">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <Gauge size={20} className="text-purple-400" />
            MAE/MFE Анализ
            {globalFilterLabel && (
              <span className="text-xs bg-purple-500/20 text-purple-400 px-2 py-0.5 rounded-full">
                📅 {globalFilterLabel}
              </span>
            )}
          </h2>
          <div className="flex items-center gap-2">
            {coverageStats && (
              <span className="text-xs text-slate-400">
                {coverageStats.with_mae}/{coverageStats.total} ({coverageStats.pct}%)
              </span>
            )}
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="text-slate-400 hover:text-white transition-colors"
            >
              {isExpanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
            </button>
          </div>
        </div>

        {/* Group By Tabs - Only Tags and Setups */}
        <div className="flex gap-1 p-1 bg-slate-800/50 rounded-lg mb-4">
          <button
            onClick={() => { setGroupBy('tag'); setSelectedItem(null); setSearchQuery(''); }}
            className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-sm font-medium transition-all ${
              groupBy === 'tag' 
                ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30' 
                : 'text-slate-400 hover:text-white hover:bg-white/5'
            }`}
          >
            <Hash size={14} />
            Теги (Стратегии)
          </button>
          <button
            onClick={() => { setGroupBy('setup'); setSelectedItem(null); setSearchQuery(''); }}
            className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-sm font-medium transition-all ${
              groupBy === 'setup' 
                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' 
                : 'text-slate-400 hover:text-white hover:bg-white/5'
            }`}
          >
            <Layers size={14} />
            Сетапы
          </button>
        </div>

        {/* Quick Filters Row */}
        <div className="flex flex-wrap gap-2 mb-4">
          {/* Trades Limit with Custom Input */}
          <div className="flex items-center gap-1 bg-slate-800/50 rounded-lg p-1">
            <List size={14} className="text-slate-400 ml-2" />
            {LIMIT_PRESETS.map(l => (
              <button
                key={l}
                onClick={() => { setTradesLimit(l); setShowCustomLimitInput(false); }}
                className={`px-2 py-1 rounded text-xs font-medium transition-all ${
                  tradesLimit === l && !showCustomLimitInput
                    ? 'bg-cyan-500/20 text-cyan-400'
                    : 'text-slate-500 hover:text-white'
                }`}
              >
                {l === 'all' ? 'Все' : l}
              </button>
            ))}
            {/* Custom input toggle */}
            {showCustomLimitInput ? (
              <div className="flex items-center gap-1">
                <input
                  type="number"
                  value={customLimit}
                  onChange={(e) => setCustomLimit(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSetCustomLimit()}
                  placeholder="N"
                  className="w-14 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-xs text-center focus:border-cyan-500 outline-none"
                  autoFocus
                />
                <button
                  onClick={handleSetCustomLimit}
                  className="px-2 py-1 bg-cyan-500/20 text-cyan-400 rounded text-xs hover:bg-cyan-500/30"
                >
                  ✓
                </button>
                <button
                  onClick={() => setShowCustomLimitInput(false)}
                  className="px-1 py-1 text-slate-500 hover:text-white text-xs"
                >
                  ✕
                </button>
              </div>
            ) : (
              <button
                onClick={() => { setShowCustomLimitInput(true); setCustomLimit(''); }}
                className={`px-2 py-1 rounded text-xs font-medium transition-all flex items-center gap-1 ${
                  !LIMIT_PRESETS.includes(tradesLimit as any)
                    ? 'bg-cyan-500/20 text-cyan-400'
                    : 'text-slate-500 hover:text-white'
                }`}
                title="Ввести своё число"
              >
                <Edit3 size={10} />
                {!LIMIT_PRESETS.includes(tradesLimit as any) ? tradesLimit : '...'}
              </button>
            )}
          </div>
          
          {/* Period Filter */}
          <div className="flex items-center gap-1 bg-slate-800/50 rounded-lg p-1">
            <Calendar size={14} className="text-slate-400 ml-2" />
            {(['all', 'week', 'month', '3months', 'year'] as PeriodType[]).map(p => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-2 py-1 rounded text-xs font-medium transition-all ${
                  period === p
                    ? 'bg-purple-500/20 text-purple-400'
                    : 'text-slate-500 hover:text-white'
                }`}
              >
                {getPeriodLabel(p)}
              </button>
            ))}
          </div>
        </div>

        {/* Summary Stats */}
        {data && data.items && data.items.length > 0 && (
          <div className="grid grid-cols-4 gap-2 mb-4">
            <div className="bg-white/5 rounded-lg p-2 text-center">
              <div className="text-[9px] uppercase opacity-50">Групп</div>
              <div className="text-lg font-bold">{data.total_groups || data.items.length}</div>
            </div>
            <div className="bg-white/5 rounded-lg p-2 text-center">
              <div className="text-[9px] uppercase opacity-50">Сделок</div>
              <div className="text-lg font-bold">{data.total_trades}</div>
            </div>
            <div className="bg-green-500/10 rounded-lg p-2 text-center">
              <div className="text-[9px] uppercase opacity-50">Edge ≥1.5</div>
              <div className="text-lg font-bold text-green-400">
                {data.items.filter(i => i.edge_ratio >= 1.5).length}
              </div>
            </div>
            <div className="bg-red-500/10 rounded-lg p-2 text-center">
              <div className="text-[9px] uppercase opacity-50">Edge &lt;1</div>
              <div className="text-lg font-bold text-red-400">
                {data.items.filter(i => i.edge_ratio < 1).length}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="px-6 pb-6 space-y-4 relative z-10">
          {/* Search and Actions */}
          <div className="flex gap-2">
            {/* Search with Autocomplete */}
            <div className="flex-1 relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                ref={searchInputRef}
                type="text"
                placeholder={`Поиск ${groupBy === 'tag' ? 'тега' : 'сетапа'}...`}
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setShowSuggestions(true);
                }}
                onFocus={() => {
                  // Show suggestions on focus even if empty
                  setShowSuggestions(true);
                }}
                onBlur={() => {
                  // Delay to allow click on suggestion
                  setTimeout(() => setShowSuggestions(false), 200);
                }}
                className="w-full bg-slate-800/50 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm focus:border-purple-500 outline-none"
              />
              
              {/* Suggestions Dropdown */}
              {showSuggestions && filteredSuggestions.length > 0 && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-lg z-50 max-h-48 overflow-y-auto">
                  {groupBy === 'tag' ? (
                    // Tag suggestions
                    (filteredSuggestions as TagInfo[]).map(tag => (
                      <button
                        key={tag.tag}
                        onClick={() => handleSelectSuggestion(tag.tag)}
                        className="w-full text-left px-3 py-2 text-sm hover:bg-purple-500/20 transition-colors flex items-center justify-between"
                      >
                        <div className="flex items-center gap-2">
                          <Hash size={12} className="text-purple-400" />
                          <span>{tag.tag}</span>
                        </div>
                        <span className="text-[10px] text-slate-500">{tag.count} сд.</span>
                      </button>
                    ))
                  ) : (
                    // Setup suggestions
                    (filteredSuggestions as Setup[]).map(setup => (
                      <button
                        key={setup.id}
                        onClick={() => handleSelectSuggestion(setup.name)}
                        className="w-full text-left px-3 py-2 text-sm hover:bg-purple-500/20 transition-colors flex items-center gap-2"
                      >
                        <Layers size={12} className="text-emerald-400" />
                        {setup.name}
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
            
            {/* More Filters Button */}
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`px-3 py-2 rounded-lg border transition-colors ${
                showFilters || assetTypeFilter || directionFilter
                  ? 'bg-purple-500/20 border-purple-500 text-purple-400'
                  : 'bg-slate-800/50 border-slate-700 text-slate-400'
              }`}
              title="Дополнительные фильтры"
            >
              <Filter size={16} />
            </button>
            
            {/* Recalculate Button with Options */}
            <div className="relative">
              <button
                onClick={() => setShowRecalcOptions(!showRecalcOptions)}
                disabled={isRecalculating}
                className={`px-3 py-2 rounded-lg border transition-colors flex items-center gap-2 ${
                  isRecalculating
                    ? 'bg-purple-500/30 border-purple-500 text-purple-400'
                    : 'bg-slate-800/50 border-slate-700 text-slate-400 hover:text-white hover:border-purple-500'
                }`}
                title="Пересчитать MAE/MFE"
              >
                <RefreshCw size={16} className={isRecalculating ? 'animate-spin' : ''} />
                {!isRecalculating && <span className="text-sm hidden sm:inline">Пересчёт</span>}
              </button>
              
              {/* Recalc Options Dropdown */}
              {showRecalcOptions && !isRecalculating && (
                <div className="absolute top-full right-0 mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-lg z-50 min-w-[200px]">
                  <button
                    onClick={() => handleRecalculate(false)}
                    className="w-full text-left px-4 py-3 text-sm hover:bg-purple-500/20 transition-colors flex items-center gap-3 border-b border-slate-700"
                  >
                    <Zap size={16} className="text-cyan-400" />
                    <div>
                      <div className="font-medium">Только новые</div>
                      <div className="text-[10px] text-slate-500">Сделки без MAE/MFE</div>
                    </div>
                  </button>
                  <button
                    onClick={() => handleRecalculate(true)}
                    className="w-full text-left px-4 py-3 text-sm hover:bg-purple-500/20 transition-colors flex items-center gap-3"
                  >
                    <RefreshCw size={16} className="text-orange-400" />
                    <div>
                      <div className="font-medium">Все сделки</div>
                      <div className="text-[10px] text-slate-500">Полный пересчёт</div>
                    </div>
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Additional Filter Panel */}
          {showFilters && (
            <div className="flex flex-wrap gap-4 p-3 bg-slate-800/30 rounded-lg">
              <div>
                <label className="text-[10px] uppercase opacity-50 block mb-1">Тип актива</label>
                <select
                  value={assetTypeFilter || ''}
                  onChange={(e) => setAssetTypeFilter(e.target.value || null)}
                  className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm"
                >
                  <option value="">Все</option>
                  <option value="Stock">Акции</option>
                  <option value="Futures">Фьючерсы</option>
                  <option value="Bond">Облигации</option>
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase opacity-50 block mb-1">Направление</label>
                <select
                  value={directionFilter || ''}
                  onChange={(e) => setDirectionFilter(e.target.value || null)}
                  className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm"
                >
                  <option value="">Все</option>
                  <option value="long">LONG</option>
                  <option value="short">SHORT</option>
                </select>
              </div>
              {(assetTypeFilter || directionFilter) && (
                <button
                  onClick={() => { setAssetTypeFilter(null); setDirectionFilter(null); }}
                  className="text-red-400 hover:text-red-300 text-xs self-end pb-1"
                >
                  Сбросить
                </button>
              )}
            </div>
          )}

          {/* Loading */}
          {loading && (
            <div className="flex justify-center py-8">
              <RefreshCw className="w-6 h-6 animate-spin text-purple-400" />
            </div>
          )}

          {/* Items Table */}
          {!loading && sortedItems.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-2 px-2 font-medium text-slate-400">
                      {getGroupIcon()}
                      <span className="ml-2">{getGroupLabel()}</span>
                    </th>
                    <th 
                      className="text-right py-2 px-2 font-medium text-slate-400 cursor-pointer hover:text-white"
                      onClick={() => handleSort('edge_ratio')}
                    >
                      <span className="flex items-center justify-end gap-1">
                        Edge <ArrowUpDown size={12} className={sortField === 'edge_ratio' ? 'text-purple-400' : ''} />
                      </span>
                    </th>
                    <th 
                      className="text-right py-2 px-2 font-medium text-slate-400 cursor-pointer hover:text-white"
                      onClick={() => handleSort('avg_mae')}
                    >
                      <span className="flex items-center justify-end gap-1">
                        MAE <ArrowUpDown size={12} className={sortField === 'avg_mae' ? 'text-purple-400' : ''} />
                      </span>
                    </th>
                    <th 
                      className="text-right py-2 px-2 font-medium text-slate-400 cursor-pointer hover:text-white"
                      onClick={() => handleSort('avg_mfe')}
                    >
                      <span className="flex items-center justify-end gap-1">
                        MFE <ArrowUpDown size={12} className={sortField === 'avg_mfe' ? 'text-purple-400' : ''} />
                      </span>
                    </th>
                    <th 
                      className="text-right py-2 px-2 font-medium text-slate-400 cursor-pointer hover:text-white"
                      onClick={() => handleSort('win_rate')}
                    >
                      <span className="flex items-center justify-end gap-1">
                        WR <ArrowUpDown size={12} className={sortField === 'win_rate' ? 'text-purple-400' : ''} />
                      </span>
                    </th>
                    <th 
                      className="text-right py-2 px-2 font-medium text-slate-400 cursor-pointer hover:text-white"
                      onClick={() => handleSort('total_pnl')}
                    >
                      <span className="flex items-center justify-end gap-1">
                        PnL <ArrowUpDown size={12} className={sortField === 'total_pnl' ? 'text-purple-400' : ''} />
                      </span>
                    </th>
                    <th 
                      className="text-right py-2 px-2 font-medium text-slate-400 cursor-pointer hover:text-white"
                      onClick={() => handleSort('quality_score')}
                    >
                      <span className="flex items-center justify-end gap-1">
                        Score <ArrowUpDown size={12} className={sortField === 'quality_score' ? 'text-purple-400' : ''} />
                      </span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedItems.map((item) => (
                    <tr 
                      key={item.name}
                      onClick={() => setSelectedItem(selectedItem === item.name ? null : item.name)}
                      className={`border-b border-slate-800 cursor-pointer transition-colors ${
                        selectedItem === item.name 
                          ? 'bg-purple-500/10' 
                          : 'hover:bg-white/5'
                      }`}
                    >
                      <td className="py-2 px-2">
                        <div className="flex items-center gap-2">
                          {groupBy === 'tag' && <Hash size={12} className="text-purple-400" />}
                          {groupBy === 'setup' && <Layers size={12} className="text-emerald-400" />}
                          <span className="font-medium">{item.name}</span>
                          <span className="text-[10px] text-slate-500">{item.trades_count} сд.</span>
                        </div>
                      </td>
                      <td className={`text-right py-2 px-2 font-bold ${getEdgeColor(item.edge_ratio)}`}>
                        {item.edge_ratio?.toFixed(2)}x
                      </td>
                      <td className="text-right py-2 px-2 text-red-400">
                        {item.avg_mae?.toFixed(1)}%
                      </td>
                      <td className="text-right py-2 px-2 text-green-400">
                        {item.avg_mfe?.toFixed(1)}%
                      </td>
                      <td className="text-right py-2 px-2">
                        {item.win_rate}%
                      </td>
                      <td className={`text-right py-2 px-2 font-medium ${item.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatPnl(item.total_pnl)}
                      </td>
                      <td className="text-right py-2 px-2">
                        <div className={`inline-flex items-center gap-1 ${getQualityColor(item.quality_score)}`}>
                          {item.quality_score >= 70 && <Star size={12} />}
                          {item.quality_score < 30 && <AlertTriangle size={12} />}
                          {item.quality_score}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* No Data */}
          {!loading && sortedItems.length === 0 && (
            <div className="text-center py-8 opacity-50">
              {searchQuery 
                ? 'Ничего не найдено' 
                : coverageStats && coverageStats.with_mae === 0 
                  ? (
                    <div className="space-y-3">
                      <p>Нет данных MAE/MFE</p>
                      <button
                        onClick={() => handleRecalculate(false)}
                        disabled={isRecalculating}
                        className="px-4 py-2 bg-purple-500 hover:bg-purple-600 rounded-lg text-white text-sm transition-colors inline-flex items-center gap-2"
                      >
                        {isRecalculating ? (
                          <RefreshCw size={16} className="animate-spin" />
                        ) : (
                          <Zap size={16} />
                        )}
                        Рассчитать MAE/MFE
                      </button>
                    </div>
                  )
                  : 'Нет данных для выбранной группировки'
              }
            </div>
          )}
        </div>
      )}

      {/* Selected Item Details Modal - Using React Portal for proper overlay */}
      {selectedItem && selectedItemData && typeof document !== 'undefined' && createPortal(
        <div 
          className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
          style={{ zIndex: 99999 }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setSelectedItem(null);
          }}
        >
          <div className="bg-[#0a0a0a] border border-slate-700 rounded-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl" onClick={(e) => e.stopPropagation()}>
            {/* Modal Header */}
            <div className="p-6 border-b border-slate-700 flex items-center justify-between sticky top-0 bg-[#0a0a0a] z-10">
              <div className="flex items-center gap-3">
                {getGroupIcon()}
                <div>
                  <h3 className="text-xl font-bold">{selectedItem}</h3>
                  <p className="text-sm text-slate-400">
                    {selectedItemData.total_trades} сделок • {getGroupLabel()}
                    {tradesLimit !== 'all' && ` • ${getLimitLabel(tradesLimit)}`}
                    {period !== 'all' && ` • ${getPeriodLabel(period)}`}
                    {globalFilterLabel && ` • ${globalFilterLabel}`}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedItem(null)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X size={24} />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 space-y-6">
              {/* Main Metrics */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-white/5 rounded-lg p-4 text-center">
                  <div className="text-[10px] uppercase opacity-50 mb-1">Edge Ratio</div>
                  <div className={`text-2xl font-bold ${getEdgeColor(selectedItemData.edge_ratio || 0)}`}>
                    {(selectedItemData.edge_ratio || 0).toFixed(2)}x
                  </div>
                </div>
                <div className="bg-red-500/10 rounded-lg p-4 text-center">
                  <div className="text-[10px] uppercase opacity-50 mb-1">Ср. MAE</div>
                  <div className="text-2xl font-bold text-red-400">
                    {(selectedItemData.avg_mae || 0).toFixed(2)}%
                  </div>
                </div>
                <div className="bg-green-500/10 rounded-lg p-4 text-center">
                  <div className="text-[10px] uppercase opacity-50 mb-1">Ср. MFE</div>
                  <div className="text-2xl font-bold text-green-400">
                    {(selectedItemData.avg_mfe || 0).toFixed(2)}%
                  </div>
                </div>
                <div className="bg-cyan-500/10 rounded-lg p-4 text-center">
                  <div className="text-[10px] uppercase opacity-50 mb-1">Эффективность</div>
                  <div className="text-2xl font-bold text-cyan-400">
                    {(selectedItemData.avg_efficiency || 0).toFixed(0)}%
                  </div>
                </div>
              </div>

              {/* Method indicator */}
              <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg px-3 py-2 text-xs">
                <span className="text-purple-400 font-medium">Метод расчёта MAE/MFE:</span>{' '}
                <span className="text-white">{maeCalculationMethod === 'first_entry' ? 'От первой цены входа' : 'От средневзвешенной цены'}</span>
              </div>

              {/* Trade Stats */}
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-white/5 rounded-lg p-3">
                  <div className="text-[10px] uppercase opacity-50 mb-1">Сделок</div>
                  <div className="text-lg font-bold">{selectedItemData.trades_count || 0}</div>
                  <div className="text-xs opacity-50">
                    {selectedItemData.wins || 0} побед / {selectedItemData.losses || ((selectedItemData.trades_count || 0) - (selectedItemData.wins || 0))} убытков
                  </div>
                </div>
                <div className="bg-white/5 rounded-lg p-3">
                  <div className="text-[10px] uppercase opacity-50 mb-1">Винрейт</div>
                  <div className="text-lg font-bold">{selectedItemData.win_rate || 0}%</div>
                </div>
                <div className="bg-white/5 rounded-lg p-3">
                  <div className="text-[10px] uppercase opacity-50 mb-1">Общий PnL</div>
                  <div className={`text-lg font-bold ${(selectedItemData.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatPnl(selectedItemData.total_pnl || 0)}
                  </div>
                </div>
              </div>

              {/* Real Performance Metrics */}
              {(selectedItemData.real_rr || selectedItemData.profit_factor) && (
                <div className="bg-gradient-to-r from-blue-500/10 to-purple-500/10 border border-blue-500/30 rounded-lg p-4">
                  <div className="text-xs font-bold text-blue-400 mb-3">📊 РЕАЛЬНЫЕ ПОКАЗАТЕЛИ</div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div>
                      <div className="text-[10px] opacity-50">Реальный R:R</div>
                      <div className="font-bold">{(selectedItemData.real_rr || 0).toFixed(2)}:1</div>
                    </div>
                    <div>
                      <div className="text-[10px] opacity-50">Profit Factor</div>
                      <div className={`font-bold ${(selectedItemData.profit_factor || 0) >= 1.5 ? 'text-green-400' : (selectedItemData.profit_factor || 0) >= 1 ? 'text-yellow-400' : 'text-red-400'}`}>
                        {(selectedItemData.profit_factor || 0).toFixed(2)}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] opacity-50">Ср. победа</div>
                      <div className="font-bold text-green-400">+{(selectedItemData.avg_win || 0).toLocaleString('ru-RU', {maximumFractionDigits: 0})}₽</div>
                    </div>
                    <div>
                      <div className="text-[10px] opacity-50">Ср. убыток</div>
                      <div className="font-bold text-red-400">-{(selectedItemData.avg_loss || 0).toLocaleString('ru-RU', {maximumFractionDigits: 0})}₽</div>
                    </div>
                  </div>
                  <div className="mt-2 text-[10px] opacity-60">
                    Мин. винрейт для безубытка: {(selectedItemData.required_winrate || 0).toFixed(0)}% | Ваш: {selectedItemData.win_rate || 0}%
                    {(selectedItemData.win_rate || 0) >= (selectedItemData.required_winrate || 100) ? ' ✅' : ' ⚠️'}
                  </div>
                </div>
              )}

              {/* MAE/MFE Percentiles Distribution */}
              <div className="grid md:grid-cols-2 gap-4">
                {/* MAE Distribution */}
                <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-3 h-3 rounded-full bg-red-500" />
                    <h4 className="text-sm font-bold text-red-400">MAE Распределение</h4>
                  </div>
                  <p className="text-[10px] text-slate-400 mb-3">Максимальный убыток во время сделки</p>
                  
                  {selectedItemData.mae_percentiles ? (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-slate-500 w-8">p25</span>
                          <div className="h-2 bg-red-500/30 rounded" style={{ width: `${Math.min(100, selectedItemData.mae_percentiles.p25 * 10)}px` }} />
                        </div>
                        <span className="text-sm font-medium text-red-400">{selectedItemData.mae_percentiles.p25}%</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-slate-500 w-8">p50</span>
                          <div className="h-2 bg-red-500/50 rounded" style={{ width: `${Math.min(100, selectedItemData.mae_percentiles.p50 * 10)}px` }} />
                        </div>
                        <span className="text-sm font-bold text-red-400">{selectedItemData.mae_percentiles.p50}%</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-slate-500 w-8">p75</span>
                          <div className="h-2 bg-red-500/70 rounded" style={{ width: `${Math.min(100, selectedItemData.mae_percentiles.p75 * 10)}px` }} />
                        </div>
                        <span className="text-sm font-medium text-red-400">{selectedItemData.mae_percentiles.p75}%</span>
                      </div>
                      <div className="flex items-center justify-between pt-1 border-t border-slate-700">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-slate-500 w-8">max</span>
                          <div className="h-2 bg-red-500 rounded" style={{ width: `${Math.min(100, selectedItemData.mae_percentiles.max * 10)}px` }} />
                        </div>
                        <span className="text-sm font-medium text-red-500">{selectedItemData.mae_percentiles.max}%</span>
                      </div>
                    </div>
                  ) : (
                    <div className="text-slate-500 text-sm">Нет данных</div>
                  )}
                  
                  {/* MAE Interpretation */}
                  {selectedItemData.mae_percentiles && (
                    <div className="mt-3 pt-3 border-t border-red-500/20 text-[11px] text-slate-400">
                      <p>📊 <strong>Медиана (p50):</strong> {selectedItemData.mae_percentiles.p50}% — половина сделок уходила в минус не более чем на {selectedItemData.mae_percentiles.p50}%</p>
                      <p className="mt-1">🎯 <strong>Рекомендуемый стоп:</strong> {selectedItemData.mae_percentiles.p75}% (p75) — покрывает 75% сделок</p>
                    </div>
                  )}
                </div>

                {/* MFE Distribution */}
                <div className="bg-green-500/5 border border-green-500/20 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-3 h-3 rounded-full bg-green-500" />
                    <h4 className="text-sm font-bold text-green-400">MFE Распределение</h4>
                  </div>
                  <p className="text-[10px] text-slate-400 mb-3">Максимальная прибыль во время сделки</p>
                  
                  {selectedItemData.mfe_percentiles ? (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-slate-500 w-8">p25</span>
                          <div className="h-2 bg-green-500/30 rounded" style={{ width: `${Math.min(100, selectedItemData.mfe_percentiles.p25 * 10)}px` }} />
                        </div>
                        <span className="text-sm font-medium text-green-400">{selectedItemData.mfe_percentiles.p25}%</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-slate-500 w-8">p50</span>
                          <div className="h-2 bg-green-500/50 rounded" style={{ width: `${Math.min(100, selectedItemData.mfe_percentiles.p50 * 10)}px` }} />
                        </div>
                        <span className="text-sm font-bold text-green-400">{selectedItemData.mfe_percentiles.p50}%</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-slate-500 w-8">p75</span>
                          <div className="h-2 bg-green-500/70 rounded" style={{ width: `${Math.min(100, selectedItemData.mfe_percentiles.p75 * 10)}px` }} />
                        </div>
                        <span className="text-sm font-medium text-green-400">{selectedItemData.mfe_percentiles.p75}%</span>
                      </div>
                      <div className="flex items-center justify-between pt-1 border-t border-slate-700">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-slate-500 w-8">max</span>
                          <div className="h-2 bg-green-500 rounded" style={{ width: `${Math.min(100, selectedItemData.mfe_percentiles.max * 10)}px` }} />
                        </div>
                        <span className="text-sm font-medium text-green-500">{selectedItemData.mfe_percentiles.max}%</span>
                      </div>
                    </div>
                  ) : (
                    <div className="text-slate-500 text-sm">Нет данных</div>
                  )}
                  
                  {/* MFE Interpretation */}
                  {selectedItemData.mfe_percentiles && (
                    <div className="mt-3 pt-3 border-t border-green-500/20 text-[11px] text-slate-400">
                      <p>📊 <strong>Медиана (p50):</strong> {selectedItemData.mfe_percentiles.p50}% — половина сделок достигала прибыли минимум {selectedItemData.mfe_percentiles.p50}%</p>
                      <p className="mt-1">🎯 <strong>Рекомендуемый тейк:</strong> {selectedItemData.mfe_percentiles.p25}% (p25) — достижимо в 75% сделок</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Stop-Loss & Take-Profit Recommendations */}
              {selectedItemData.mae_percentiles && selectedItemData.mfe_percentiles && (
                <div className="bg-gradient-to-r from-purple-500/10 to-cyan-500/10 border border-purple-500/20 rounded-lg p-4">
                  <h4 className="text-sm font-bold flex items-center gap-2 mb-3">
                    <Gauge size={16} className="text-purple-400" />
                    Рекомендации по управлению позицией
                  </h4>
                  
                  <div className="grid md:grid-cols-2 gap-4">
                    {/* Stop-Loss Recommendation */}
                    <div className="bg-black/20 rounded-lg p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-slate-400">📉 Стоп-лосс</span>
                        <span className="text-lg font-bold text-red-400">{selectedItemData.mae_percentiles.p75}%</span>
                      </div>
                      <p className="text-[10px] text-slate-500 leading-relaxed">
                        <strong>Обоснование:</strong> 75% ваших сделок не уходили ниже {selectedItemData.mae_percentiles.p75}%. 
                        Стоп на этом уровне защитит от аномальных движений, сохраняя большинство позиций.
                        {selectedItemData.mae_percentiles.p50 < selectedItemData.mae_percentiles.p75 * 0.5 && (
                          <span className="block mt-1 text-yellow-400">
                            ⚠️ Есть разрыв между медианой ({selectedItemData.mae_percentiles.p50}%) и p75 — возможны редкие глубокие просадки.
                          </span>
                        )}
                      </p>
                    </div>
                    
                    {/* Take-Profit Recommendation */}
                    <div className="bg-black/20 rounded-lg p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-slate-400">📈 Тейк-профит</span>
                        <span className="text-lg font-bold text-green-400">{selectedItemData.mfe_percentiles.p25}%</span>
                      </div>
                      <p className="text-[10px] text-slate-500 leading-relaxed">
                        <strong>Обоснование:</strong> 75% ваших сделок достигали прибыли минимум {selectedItemData.mfe_percentiles.p25}%. 
                        Консервативный тейк на этом уровне увеличит реализованную прибыль.
                        {selectedItemData.mfe_percentiles.p50 > selectedItemData.mfe_percentiles.p25 * 1.5 && (
                          <span className="block mt-1 text-cyan-400">
                            💡 Потенциал роста: медиана MFE ({selectedItemData.mfe_percentiles.p50}%) выше — рассмотрите trailing stop.
                          </span>
                        )}
                      </p>
                    </div>
                  </div>
                  
                  {/* Risk/Reward Analysis */}
                  <div className="mt-3 pt-3 border-t border-purple-500/20">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-400">Рекомендуемый R:R (тейк/стоп)</span>
                      <span className={`text-lg font-bold ${
                        (selectedItemData.mfe_percentiles.p25 / selectedItemData.mae_percentiles.p75) >= 1 
                          ? 'text-green-400' 
                          : 'text-yellow-400'
                      }`}>
                        {(selectedItemData.mfe_percentiles.p25 / selectedItemData.mae_percentiles.p75).toFixed(2)}:1
                      </span>
                    </div>
                    <p className="text-[10px] text-slate-500 mt-1">
                      {(selectedItemData.mfe_percentiles.p25 / selectedItemData.mae_percentiles.p75) >= 1.5 
                        ? '✅ Отличное соотношение риск/прибыль. Стратегия имеет математическое преимущество.'
                        : (selectedItemData.mfe_percentiles.p25 / selectedItemData.mae_percentiles.p75) >= 1
                          ? '⚠️ Приемлемое соотношение. При высоком винрейте стратегия прибыльна.'
                          : '❌ Низкое R:R. Требуется высокий винрейт (>60%) для прибыльности.'
                      }
                    </p>
                  </div>
                </div>
              )}

              {/* Recommendations */}
              {selectedItemData.recommendations && selectedItemData.recommendations.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-sm font-bold flex items-center gap-2">
                    <Star className="text-yellow-400" size={16} />
                    Рекомендации для стратегии
                  </h4>
                  {selectedItemData.recommendations.map((rec, idx) => (
                    <div 
                      key={idx}
                      className={`p-3 rounded-lg text-sm flex items-start gap-2 ${
                        rec.type === 'success' ? 'bg-green-500/10 text-green-400' :
                        rec.type === 'warning' ? 'bg-yellow-500/10 text-yellow-400' :
                        rec.type === 'danger' ? 'bg-red-500/10 text-red-400' :
                        rec.type === 'insight' ? 'bg-purple-500/10 text-purple-400' :
                        'bg-white/5'
                      }`}
                    >
                      <span>{rec.icon}</span>
                      <span>{rec.text}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Quality Score */}
              <div className="bg-white/5 rounded-lg p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-[10px] uppercase opacity-50 mb-1">Рейтинг стратегии</div>
                    <div className="text-xs opacity-60">
                      На основе Edge Ratio, Win Rate и MAE
                    </div>
                  </div>
                  <div className={`text-4xl font-bold ${getQualityColor(selectedItemData.quality_score || 0)}`}>
                    {selectedItemData.quality_score || 0}
                    <span className="text-lg opacity-50">/100</span>
                  </div>
                </div>
                <div className="mt-3 h-2 bg-slate-800 rounded-full overflow-hidden">
                  <div 
                    className={`h-full transition-all ${
                      (selectedItemData.quality_score || 0) >= 70 ? 'bg-green-500' :
                      (selectedItemData.quality_score || 0) >= 50 ? 'bg-yellow-500' :
                      (selectedItemData.quality_score || 0) >= 30 ? 'bg-orange-500' :
                      'bg-red-500'
                    }`}
                    style={{ width: `${selectedItemData.quality_score || 0}%` }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
