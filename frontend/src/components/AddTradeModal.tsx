'use client';

import React, { useState } from 'react';
import { X } from 'lucide-react';

interface AddTradeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const AddTradeModal: React.FC<AddTradeModalProps> = ({ isOpen, onClose, onSuccess }) => {
  const [formData, setFormData] = useState({
    symbol: '',
    asset_name: '',
    asset_type: 'Stock',
    direction: 'long',
    entry_price: '',
    quantity: '',
    leverage: '1',
    commission: '',
    entry_at: new Date().toISOString().slice(0, 16),
    stop_loss: '',
    take_profit: '',
    risk_amount: '',
    setup_name: '',
    timeframe: '1D',
    news_event: '',
    screenshot_url: '',
    notes: '',
    tags: ''
  });

  if (!isOpen) return null;

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
      const response = await fetch(getApiUrl('/trades/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formData,
          account_id: 1, // Hardcoded for MVP
          entry_price: parseFloat(formData.entry_price),
          quantity: parseFloat(formData.quantity),
          leverage: formData.leverage ? parseFloat(formData.leverage) : 1.0,
          commission: formData.commission ? parseFloat(formData.commission) : 0,
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
      console.error('Failed to add trade:', error);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="cyber-card w-full max-w-md bg-[#0d0d0d] p-6 relative">
        <button onClick={onClose} className="absolute top-4 right-4 opacity-50 hover:opacity-100">
          <X size={20} />
        </button>
        
        <h2 className="text-xl font-bold mb-6 text-neon italic">LOG NEW POSITION</h2>
        
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

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Stop Loss</label>
              <input 
                type="number" step="any"
                className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
                value={formData.stop_loss}
                onChange={e => setFormData({...formData, stop_loss: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Risk Amount ($)</label>
              <input 
                type="number" step="any"
                className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
                value={formData.risk_amount}
                onChange={e => setFormData({...formData, risk_amount: e.target.value})}
              />
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Notes / Strategy</label>
            <textarea 
              className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none h-20"
              placeholder="Why are you entering this trade?"
              value={formData.notes}
              onChange={e => setFormData({...formData, notes: e.target.value})}
            />
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Tags (comma separated)</label>
            <input 
              className="w-full bg-black border border-border p-2 text-sm focus:border-accent outline-none"
              placeholder="Trend, FOMO, Breakout"
              value={formData.tags}
              onChange={e => setFormData({...formData, tags: e.target.value})}
            />
          </div>

          <button 
            type="submit"
            className="w-full bg-accent text-black font-bold py-3 hover:bg-white transition-colors uppercase tracking-widest text-xs"
          >
            Initialize Position
          </button>
        </form>
      </div>
    </div>
  );
};
