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
    tags: '',
    confidence: '5'
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
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fadeIn">
      <div className="cyber-card w-full max-w-md bg-[#0d0d0d] p-6 relative animate-scaleIn overflow-hidden">
        {/* Background glow */}
        <div className="absolute -top-32 -right-32 w-64 h-64 bg-accent/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-32 -left-32 w-64 h-64 bg-accent-secondary/10 rounded-full blur-3xl pointer-events-none" />
        
        <button onClick={onClose} className="absolute top-4 right-4 opacity-50 hover:opacity-100 hover:text-accent transition-colors z-10">
          <X size={20} />
        </button>
        
        <h2 className="text-xl font-bold mb-6 text-neon italic relative z-10">LOG NEW POSITION</h2>
        
        <form onSubmit={handleSubmit} className="space-y-4 relative z-10">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Symbol</label>
              <input 
                required
                className="input-cyber"
                placeholder="BTC/USDT"
                value={formData.symbol}
                onChange={e => setFormData({...formData, symbol: e.target.value.toUpperCase()})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Asset Name</label>
              <input 
                className="input-cyber"
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
                className="input-cyber"
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
                className="input-cyber"
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
                className="input-cyber"
                value={formData.entry_price}
                onChange={e => setFormData({...formData, entry_price: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Quantity</label>
              <input 
                required
                type="number" step="any"
                className="input-cyber"
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
                className="input-cyber"
                value={formData.leverage}
                onChange={e => setFormData({...formData, leverage: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Commission</label>
              <input 
                type="number" step="any"
                className="input-cyber"
                value={formData.commission}
                onChange={e => setFormData({...formData, commission: e.target.value})}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Setup Name</label>
              <input 
                className="input-cyber"
                placeholder="Breakout, Reversal..."
                value={formData.setup_name}
                onChange={e => setFormData({...formData, setup_name: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Timeframe</label>
              <select 
                className="input-cyber"
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
                className="input-cyber"
                value={formData.stop_loss}
                onChange={e => setFormData({...formData, stop_loss: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Risk Amount ($)</label>
              <input 
                type="number" step="any"
                className="input-cyber"
                value={formData.risk_amount}
                onChange={e => setFormData({...formData, risk_amount: e.target.value})}
              />
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Confidence (1-10)</label>
            <div className="flex items-center gap-2">
              <input 
                type="range"
                min="1"
                max="10"
                className="w-full accent-accent"
                value={formData.confidence}
                onChange={e => setFormData({...formData, confidence: e.target.value})}
              />
              <span className="font-mono text-accent w-6 text-center font-bold">{formData.confidence}</span>
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Notes / Strategy</label>
            <textarea 
              className="input-cyber h-20 resize-none"
              placeholder="Why are you entering this trade?"
              value={formData.notes}
              onChange={e => setFormData({...formData, notes: e.target.value})}
            />
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Tags (comma separated)</label>
            <input 
              className="input-cyber"
              placeholder="Trend, FOMO, Breakout"
              value={formData.tags}
              onChange={e => setFormData({...formData, tags: e.target.value})}
            />
          </div>

          <button 
            type="submit"
            className="btn-primary w-full py-3 text-center justify-center"
          >
            Initialize Position
          </button>
        </form>
      </div>
    </div>
  );
};
