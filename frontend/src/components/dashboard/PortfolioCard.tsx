'use client';

import { useState, useEffect, useCallback } from 'react';
import { 
  Wallet, TrendingUp, TrendingDown, RefreshCw, 
  PieChart, DollarSign, BarChart3, AlertCircle,
  ChevronDown, ChevronUp, Settings, Calendar
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/apiClient';

interface Portfolio {
  success: boolean;
  total_balance: number;
  cash: number;
  stocks_value: number;
  bonds_value: number;
  etf_value: number;
  futures_value: number;
  unrealized_pnl: number;
  initial_balance: number | null;
  roi_percent: number | null;
  positions: Position[];
  updated_at: string;
}

interface Position {
  ticker: string;
  name: string;
  quantity: number;
  average_price: number;
  current_price: number;
  unrealized_pnl: number;
  instrument_type: string;
}

interface BalanceHistoryMetrics {
  start_balance: number;
  current_balance: number;
  peak_balance: number;
  roi_percent: number;
  max_drawdown_percent: number;
  volatility_percent: number;
  profit_factor: number | string;
  trading_days: number;
  profitable_days: number;
  losing_days: number;
}

interface BalanceHistory {
  snapshots: Array<{
    date: string;
    balance: number;
    cash: number;
    stocks_value: number;
    futures_value: number;
    unrealized_pnl: number;
  }>;
  metrics: BalanceHistoryMetrics | null;
}

interface PortfolioCardProps {
}

export default function PortfolioCard({}: PortfolioCardProps) {
  const { user } = useAuth();
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [history, setHistory] = useState<BalanceHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [showPositions, setShowPositions] = useState(false);
  const [editingInitial, setEditingInitial] = useState(false);
  const [initialBalanceInput, setInitialBalanceInput] = useState('');
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [isCalculating, setIsCalculating] = useState(false);

  const calculateNetDepositOnDate = async (date: string) => {
    setIsCalculating(true);
    try {
      const data = await api.get<{ net_deposit: number }>('/broker/net-deposit', { params: { date } });
      setInitialBalanceInput(data.net_deposit.toString());
      setShowDatePicker(false);
    } catch (e) {
      console.error('Failed to calculate net deposit', e);
    } finally {
      setIsCalculating(false);
    }
  };

  const fetchPortfolio = useCallback(async () => {
    if (!user) { setLoading(false); return; }
    try {
      const [portfolioData, historyData] = await Promise.all([
        api.get<Portfolio>('/broker/portfolio'),
        api.get<BalanceHistory>('/broker/balance-history', { params: { days: 30 } })
      ]);
      
      setPortfolio(portfolioData);
      if (portfolioData.initial_balance) {
        setInitialBalanceInput(portfolioData.initial_balance.toString());
      }
      
      setHistory(historyData);
      
      setError(null);
    } catch (e) {
      setError('Не удалось загрузить портфель');
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    fetchPortfolio();
    if (!user) return;
    const interval = setInterval(fetchPortfolio, 60000); // Обновляем каждую минуту
    return () => clearInterval(interval);
  }, [fetchPortfolio, user]);

  const saveInitialBalance = async () => {
    const value = parseFloat(initialBalanceInput);
    if (isNaN(value) || value <= 0) return;
    
    try {
      await api.post('/broker/set-initial-balance', { params: { initial_balance: value } });
      setEditingInitial(false);
      fetchPortfolio();
    } catch (e) {
      console.error('Failed to save initial balance', e);
    }
  };

  const formatMoney = (value: number) => {
    return new Intl.NumberFormat('ru-RU', {
      style: 'currency',
      currency: 'RUB',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value);
  };

  const formatPercent = (value: number) => {
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(2)}%`;
  };

  if (loading) {
    return (
      <div className="card p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-emerald-500/20 rounded-lg">
            <Wallet className="w-5 h-5 text-emerald-400" />
          </div>
          <h3 className="text-lg font-semibold">Портфель</h3>
        </div>
        <div className="animate-pulse space-y-3">
          <div className="h-8 bg-slate-700 rounded w-1/2"></div>
          <div className="h-4 bg-slate-700 rounded w-3/4"></div>
        </div>
      </div>
    );
  }

  if (error || !portfolio) {
    return (
      <div className="card p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-slate-700 rounded-lg">
            <Wallet className="w-5 h-5 text-slate-400" />
          </div>
          <h3 className="text-lg font-semibold">Портфель</h3>
        </div>
        <div className="flex items-center gap-2 text-slate-400">
          <AlertCircle className="w-4 h-4" />
          <span className="text-sm">{error || 'Подключите брокера'}</span>
        </div>
      </div>
    );
  }

  const metrics = history?.metrics;
  const pnlColor = portfolio.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400';
  const roiColor = (portfolio.roi_percent || 0) >= 0 ? 'text-emerald-400' : 'text-red-400';

  return (
    <div className="card overflow-hidden">
      {/* Header */}
      <div className="p-6 pb-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-gradient-to-br from-emerald-500/20 to-cyan-500/20 rounded-lg">
              <Wallet className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold">Портфель</h3>
              <p className="text-xs text-slate-500">
                Обновлено: {new Date(portfolio.updated_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
              </p>
            </div>
          </div>
          <button 
            onClick={fetchPortfolio}
            className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
            title="Обновить"
          >
            <RefreshCw className="w-4 h-4 text-slate-400" />
          </button>
        </div>

        {/* Main Balance */}
        <div className="mb-4">
          <div className="text-3xl font-bold text-white mb-1">
            {formatMoney(portfolio.total_balance)}
          </div>
          <div className={`flex items-center gap-2 ${pnlColor}`}>
            {portfolio.unrealized_pnl >= 0 ? (
              <TrendingUp className="w-4 h-4" />
            ) : (
              <TrendingDown className="w-4 h-4" />
            )}
            <span className="font-medium">
              {formatMoney(portfolio.unrealized_pnl)} нереализ.
            </span>
          </div>
        </div>

        {/* Asset Breakdown */}
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="flex items-center gap-2 text-slate-400 text-xs mb-1">
              <DollarSign className="w-3 h-3" />
              Валюта
            </div>
            <div className="font-semibold">{formatMoney(portfolio.cash)}</div>
          </div>
          <div 
            className="bg-slate-800/50 rounded-lg p-3 cursor-pointer hover:bg-slate-700/50 transition-colors relative group"
            onClick={() => {
              setExpanded(true);
              setShowPositions(true);
              // Небольшая задержка чтобы успел раскрыться список
              setTimeout(() => {
                document.getElementById('portfolio-positions')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
              }, 100);
            }}
          >
            <div className="flex items-center justify-between gap-2 text-slate-400 text-xs mb-1">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-3 h-3" />
                Позиции
              </div>
              <ChevronDown className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
            <div className="font-semibold">
              {portfolio.futures_value > 0 
                ? formatMoney(portfolio.futures_value)
                : formatMoney(portfolio.total_balance - portfolio.cash)
              }
            </div>
          </div>
        </div>

        {/* Net Deposits (Чистые вложения) */}
        <div className="bg-slate-800/50 rounded-lg p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1">
              <span className="text-slate-400 text-sm">Чистые вложения</span>
              <span className="text-slate-600 text-[10px]" title="Сумма пополнений минус выводы">(депозиты − выводы)</span>
            </div>
            <button 
              onClick={() => setEditingInitial(!editingInitial)}
              className="text-slate-500 hover:text-slate-300 transition-colors"
            >
              <Settings className="w-3 h-3" />
            </button>
          </div>
          
          {editingInitial ? (
            <div className="flex flex-col gap-2 w-full relative">
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={initialBalanceInput}
                  onChange={(e) => setInitialBalanceInput(e.target.value)}
                  className="flex-1 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm min-w-0"
                  placeholder="Сумма"
                />
                <button 
                  onClick={() => setShowDatePicker(!showDatePicker)}
                  className={`p-1.5 bg-slate-700 hover:bg-slate-600 rounded text-slate-300 ${showDatePicker ? 'text-accent' : ''}`}
                  title="Рассчитать на дату"
                >
                  <Calendar className="w-4 h-4" />
                </button>
                <button 
                  onClick={saveInitialBalance}
                  className="px-2 py-1 bg-accent text-white rounded text-sm whitespace-nowrap"
                >
                  OK
                </button>
              </div>
              
              {showDatePicker && (
                <div className="flex flex-col gap-3 animate-in fade-in slide-in-from-top-1 p-3 bg-slate-800 rounded border border-slate-700 absolute top-full left-0 z-20 w-full shadow-xl mt-1">
                  {/* Quick Date Presets */}
                  <div className="flex flex-wrap gap-1">
                    {[
                      { label: 'Сегодня', days: 0 },
                      { label: 'Неделя', days: 7 },
                      { label: 'Месяц', days: 30 },
                      { label: '3 мес.', days: 90 },
                      { label: 'Год', days: 365 },
                    ].map((preset) => (
                      <button
                        key={preset.label}
                        onClick={() => {
                          const date = new Date();
                          date.setDate(date.getDate() - preset.days);
                          calculateNetDepositOnDate(date.toISOString().split('T')[0]);
                        }}
                        className="px-2 py-1 text-[10px] bg-slate-700 hover:bg-slate-600 text-slate-300 rounded transition-colors"
                        disabled={isCalculating}
                      >
                        {preset.label}
                      </button>
                    ))}
                  </div>
                  
                  {/* Custom Date */}
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400 whitespace-nowrap">Или дата:</span>
                    <input
                      type="date"
                      id="net-deposit-date-picker"
                      className="bg-slate-900 border border-slate-600 rounded px-2 py-1 text-xs text-white flex-1 outline-none focus:border-accent"
                      style={{ colorScheme: 'dark' }}
                    />
                    <button
                      onClick={() => {
                        const dateInput = document.getElementById('net-deposit-date-picker') as HTMLInputElement;
                        if (dateInput?.value) calculateNetDepositOnDate(dateInput.value);
                      }}
                      className="px-2 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs transition-colors flex items-center justify-center min-w-[24px]"
                      disabled={isCalculating}
                    >
                      {isCalculating ? <RefreshCw className="w-3 h-3 animate-spin" /> : '✓'}
                    </button>
                  </div>
                  
                  <p className="text-[10px] text-slate-500">
                    Расчёт: пополнения − выводы + PnL сделок − комиссии
                  </p>
                </div>
              )}
            </div>
          ) : portfolio.initial_balance ? (
            <div className="flex items-center justify-between">
              <span className="font-semibold">{formatMoney(portfolio.initial_balance)}</span>
              {portfolio.roi_percent !== null && (
                <span className={`font-bold ${roiColor}`}>
                  {formatPercent(portfolio.roi_percent)} ROI
                </span>
              )}
            </div>
          ) : (
            <button
              onClick={() => setEditingInitial(true)}
              className="text-accent text-sm hover:underline"
            >
              Указать чистые вложения →
            </button>
          )}
        </div>
      </div>

      {/* Expandable Section */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-6 py-3 bg-slate-800/30 hover:bg-slate-800/50 transition-colors flex items-center justify-between text-sm"
      >
        <span className="text-slate-400">
          {expanded ? 'Скрыть детали' : 'Показать метрики'}
        </span>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-slate-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-slate-400" />
        )}
      </button>

      {expanded && (
        <div className="p-6 pt-4 border-t border-slate-700/50">
          {/* Metrics Grid */}
          {metrics && (
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div className="bg-slate-800/50 rounded-lg p-3">
                <div className="text-slate-400 text-xs mb-1">Max Drawdown</div>
                <div className="font-semibold text-red-400">
                  -{metrics.max_drawdown_percent}%
                </div>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-3">
                <div className="text-slate-400 text-xs mb-1">Волатильность</div>
                <div className="font-semibold text-amber-400">
                  {metrics.volatility_percent}%
                </div>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-3">
                <div className="text-slate-400 text-xs mb-1">Profit Factor</div>
                <div className="font-semibold text-cyan-400">
                  {metrics.profit_factor}
                </div>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-3">
                <div className="text-slate-400 text-xs mb-1">Дней торговли</div>
                <div className="font-semibold">
                  <span className="text-emerald-400">{metrics.profitable_days}</span>
                  <span className="text-slate-500"> / </span>
                  <span className="text-red-400">{metrics.losing_days}</span>
                </div>
              </div>
            </div>
          )}

          {/* Asset Pie */}
          <div className="mb-4">
            <div className="text-sm text-slate-400 mb-2">Структура портфеля</div>
            <div className="flex gap-2 flex-wrap">
              {portfolio.stocks_value > 0 && (
                <span className="px-2 py-1 bg-blue-500/20 text-blue-400 rounded text-xs">
                  Акции: {formatMoney(portfolio.stocks_value)}
                </span>
              )}
              {portfolio.futures_value > 0 && (
                <span className="px-2 py-1 bg-purple-500/20 text-purple-400 rounded text-xs">
                  Фьючерсы: {formatMoney(portfolio.futures_value)}
                </span>
              )}
              {portfolio.bonds_value > 0 && (
                <span className="px-2 py-1 bg-amber-500/20 text-amber-400 rounded text-xs">
                  Облигации: {formatMoney(portfolio.bonds_value)}
                </span>
              )}
              {portfolio.etf_value > 0 && (
                <span className="px-2 py-1 bg-cyan-500/20 text-cyan-400 rounded text-xs">
                  ETF: {formatMoney(portfolio.etf_value)}
                </span>
              )}
            </div>
          </div>

          {/* Positions */}
          {portfolio.positions.length > 0 && (
            <div id="portfolio-positions">
              <button
                onClick={() => setShowPositions(!showPositions)}
                className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors mb-2 w-full"
              >
                <PieChart className="w-4 h-4" />
                Открытые позиции ({portfolio.positions.length})
                {showPositions ? <ChevronUp className="w-3 h-3 ml-auto" /> : <ChevronDown className="w-3 h-3 ml-auto" />}
              </button>
              
              {showPositions && (
                <div className="space-y-2 max-h-60 overflow-y-auto pr-1 custom-scrollbar">
                  {portfolio.positions.map((pos, idx) => (
                    <div key={idx} className="flex items-center justify-between bg-slate-800/30 hover:bg-slate-800/50 transition-colors rounded px-3 py-2 text-sm">
                      <div>
                        <div className="font-medium flex items-center gap-2">
                          {pos.ticker}
                          <span className={`text-[10px] px-1.5 py-0.5 rounded ${pos.quantity > 0 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                            {pos.quantity > 0 ? 'L' : 'S'}
                          </span>
                        </div>
                        <div className="text-xs text-slate-500 mt-0.5">{pos.name}</div>
                        <div className="text-xs text-slate-500">
                           {pos.quantity} шт × {formatMoney(pos.average_price)}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={`font-medium ${pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {pos.unrealized_pnl >= 0 ? '+' : ''}{formatMoney(pos.unrealized_pnl)}
                        </div>
                        <div className="text-xs text-slate-500 mt-0.5">
                          {formatMoney(pos.current_price)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
