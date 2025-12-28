'use client';

import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';

interface EditTradeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  trade: any; // Using any for simplicity, but should be Trade interface
}

export const EditTradeModal: React.FC<EditTradeModalProps> = ({ isOpen, onClose, onSuccess, trade }) => {
  const [formData, setFormData] = useState({
    symbol: '',
    asset_name: '',
    asset_type: 'Stock',
    direction: 'long',
    entry_price: '',
    quantity: '',
    leverage: '1',
    commission: '',
    swap: '',
    entry_at: '',
    stop_loss: '',
    take_profit: '',
    risk_amount: '',
    setup_name: '',
    timeframe: '1D',
    news_event: '',
    screenshot_url: '',
    notes: '',
    tags: '',
    exit_reason: '',
    confidence: ''
  });

  useEffect(() => {
    if (trade) {
      setFormData({
        symbol: trade.symbol || '',
        asset_name: trade.asset_name || '',
        asset_type: trade.asset_type || 'Stock',
        direction: trade.direction || 'long',
        entry_price: trade.entry_price?.toString() || '',
        quantity: trade.quantity?.toString() || '',
        leverage: trade.leverage?.toString() || '1',
        commission: trade.commission?.toString() || '',
        swap: trade.swap?.toString() || '',
        entry_at: trade.entry_at ? new Date(trade.entry_at).toISOString().slice(0, 16) : '',
        stop_loss: trade.stop_loss?.toString() || '',
        take_profit: trade.take_profit?.toString() || '',
        risk_amount: trade.risk_amount?.toString() || '',
        setup_name: trade.setup_name || '',
        timeframe: trade.timeframe || '1D',
        news_event: trade.news_event || '',
        screenshot_url: trade.screenshot_url || '',
        notes: trade.notes || '',
        tags: trade.tags ? trade.tags.join(', ') : '',
        exit_reason: trade.exit_reason || '',
        confidence: trade.confidence?.toString() || ''
      });
    }
  }, [trade]);

  if (!isOpen || !trade) return null;

  const getApiUrl = (path: string) => {
    if (typeof window !== 'undefined' && window.location.hostname.includes('github.dev')) {
      const codespaceName = window.location.hostname.split('-3000')[0];
      return `https://${codespaceName}-8000.app.github.dev${path}`;
    }
    return `http://localhost:8000${path}`;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const response = await fetch(getApiUrl(`/trades/${trade.id}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formData,
          entry_price: parseFloat(formData.entry_price),
          quantity: parseFloat(formData.quantity),
          leverage: formData.leverage ? parseFloat(formData.leverage) : 1.0,
          commission: formData.commission ? parseFloat(formData.commission) : 0,
          swap: formData.swap ? parseFloat(formData.swap) : 0,
          stop_loss: formData.stop_loss ? parseFloat(formData.stop_loss) : null,
          take_profit: formData.take_profit ? parseFloat(formData.take_profit) : null,
          risk_amount: formData.risk_amount ? parseFloat(formData.risk_amount) : null,
          entry_at: new Date(formData.entry_at).toISOString(),
          tags: formData.tags.split(',').map(t => t.trim()).filter(t => t !== '')
        }),
      });

      if (response.ok) {
        onSuccess();
        onClose();
      }
    } catch (error) {
      console.error('Failed to update trade:', error);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="cyber-card w-full max-w-md bg-[#0d0d0d] p-6 relative max-h-[90vh] overflow-y-auto">
        <button onClick={onClose} className="absolute top-4 right-4 opacity-50 hover:opacity-100">
          <X size={20} />
        </button>
        
        <h2 className="text-xl font-bold mb-6 text-neon italic">EDIT POSITION #{trade.id}</h2>
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Symbol</label>
              <input 
                required
                className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
                placeholder="BTC/USDT"
                value={formData.symbol}
                onChange={e => setFormData({...formData, symbol: e.target.value.toUpperCase()})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Asset Name</label>
              <input 
                className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
                placeholder="Bitcoin"
                value={formData.asset_name}
                onChange={e => setFormData({...formData, asset_name: e.target.value})}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Type</label>
              <select 
                className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
                value={formData.asset_type}
                onChange={e => setFormData({...formData, asset_type: e.target.value})}
              >
                <option value="Stock">Stock</option>
                <option value="Futures">Futures</option>
                <option value="Bond">Bond</option>
                <option value="Crypto">Crypto</option>
                <option value="Forex">Forex</option>
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Direction</label>
              <select 
                className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
                value={formData.direction}
                onChange={e => setFormData({...formData, direction: e.target.value})}
              >
                <option value="long">LONG</option>
                <option value="short">SHORT</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Entry Price</label>
              <input 
                required
                type="number" step="any"
                className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
                value={formData.entry_price}
                onChange={e => setFormData({...formData, entry_price: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Quantity</label>
              <input 
                required
                type="number" step="any"
                className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
                value={formData.quantity}
                onChange={e => setFormData({...formData, quantity: e.target.value})}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Leverage</label>
              <input 
                type="number" step="any"
                className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
                value={formData.leverage}
                onChange={e => setFormData({...formData, leverage: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Commission</label>
              <input 
                type="number" step="any"
                className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
                value={formData.commission}
                onChange={e => setFormData({...formData, commission: e.target.value})}
              />
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Swap / Rollover</label>
            <input 
              type="number" step="any"
              className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
              value={formData.swap}
              onChange={e => setFormData({...formData, swap: e.target.value})}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Setup Name</label>
              <input 
                className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
                placeholder="Breakout, Reversal..."
                value={formData.setup_name}
                onChange={e => setFormData({...formData, setup_name: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Timeframe</label>
              <select 
                className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
                value={formData.timeframe}
                onChange={e => setFormData({...formData, timeframe: e.target.value})}
              >
                <option value="1m">1m</option>
                <option value="5m">5m</option>
                <option value="15m">15m</option>
                <option value="1H">1H</option>
                <option value="4H">4H</option>
                <option value="1D">1D</option>
                <option value="1W">1W</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Exit Reason</label>
            <select 
              className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
              value={formData.exit_reason}
              onChange={e => setFormData({...formData, exit_reason: e.target.value})}
            >
              <option value="">- Select Reason -</option>
              <option value="Manual">Manual (Ручной)</option>
              <option value="Stop Loss">Stop Loss</option>
              <option value="Take Profit">Take Profit</option>
              <option value="Strategy">Strategy Signal</option>
              <option value="Time">Time Exit</option>
              <option value="Panic">Panic</option>
            </select>
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Entry Date</label>
            <input 
              type="datetime-local"
              className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
              value={formData.entry_at}
              onChange={e => setFormData({...formData, entry_at: e.target.value})}
            />
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Confidence (1-10)</label>
            <div className="flex items-center gap-2">
              <input 
                type="range"
                min="1"
                max="10"
                className="w-full accent-accent"
                value={formData.confidence || '5'}
                onChange={e => setFormData({...formData, confidence: e.target.value})}
              />
              <span className="font-mono text-accent w-6 text-center">{formData.confidence || '-'}</span>
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Notes</label>
            <textarea 
              className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none h-20"
              placeholder="Trade logic, emotions..."
              value={formData.notes}
              onChange={e => setFormData({...formData, notes: e.target.value})}
            />
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Tags (comma separated)</label>
            <input 
              className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
              placeholder="FOMO, NEWS, TREND"
              value={formData.tags}
              onChange={e => setFormData({...formData, tags: e.target.value})}
            />
          </div>

          <button 
            type="submit"
            className="w-full bg-accent text-black font-bold py-3 uppercase tracking-widest hover:bg-white transition-colors"
          >
            Update Trade
          </button>
        </form>
      </div>
    </div>
  );
};
