"use client";

import { useState, useEffect } from "react";

interface CloseTradeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (exitPrice: number, exitReason: string) => void;
  tradeTicker?: string;
  tradeDirection?: string;
}

const EXIT_REASONS = [
  "Strategy",
  "Target",
  "Stop-loss",
  "Trailing stop",
  "Time",
  "Panic",
  "Manual",
  "Other"
];

export default function CloseTradeModal({
  isOpen,
  onClose,
  onConfirm,
  tradeTicker,
  tradeDirection
}: CloseTradeModalProps) {
  const [exitPrice, setExitPrice] = useState("");
  const [exitReason, setExitReason] = useState("Strategy");
  const [customReason, setCustomReason] = useState("");
  const [error, setError] = useState("");

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      setExitPrice("");
      setExitReason("Strategy");
      setCustomReason("");
      setError("");
    }
  }, [isOpen]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    const price = parseFloat(exitPrice);
    if (isNaN(price) || price <= 0) {
      setError("Введите корректную цену выхода");
      return;
    }

    const reason = exitReason === "Other" ? customReason : exitReason;
    if (!reason.trim()) {
      setError("Укажите причину выхода");
      return;
    }

    onConfirm(price, reason);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto animate-fadeIn">
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black/80 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative cyber-card bg-[#0d0d0d] w-full max-w-md animate-scaleIn overflow-hidden">
          {/* Background glow */}
          <div className="absolute -top-32 -right-32 w-64 h-64 bg-accent/10 rounded-full blur-3xl pointer-events-none" />
          
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-border relative z-10">
            <h3 className="text-lg font-bold text-white italic">
              Закрыть <span className="text-accent">сделку</span>
            </h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-accent transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          
          {/* Content */}
          <form onSubmit={handleSubmit} className="p-4 space-y-4 relative z-10">
            {/* Trade Info */}
            {tradeTicker && (
              <div className="bg-surface rounded-lg p-3 flex items-center gap-3 border border-border">
                <span className={`px-2 py-1 rounded text-xs font-bold ${
                  tradeDirection === "LONG" 
                    ? "bg-green-500/20 text-green-400" 
                    : "bg-red-500/20 text-red-400"
                }`}>
                  {tradeDirection}
                </span>
                <span className="text-white font-bold">{tradeTicker}</span>
              </div>
            )}

            {/* Exit Price */}
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-2">
                Цена выхода *
              </label>
              <input
                type="number"
                step="0.01"
                value={exitPrice}
                onChange={(e) => {
                  setExitPrice(e.target.value);
                  setError("");
                }}
                placeholder="0.00"
                className="input-cyber"
                autoFocus
              />
            </div>

            {/* Exit Reason */}
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-2">
                Причина выхода *
              </label>
              <div className="grid grid-cols-4 gap-2 mb-2">
                {EXIT_REASONS.map((reason) => (
                  <button
                    key={reason}
                    type="button"
                    onClick={() => setExitReason(reason)}
                    className={`px-2 py-1.5 text-xs rounded-lg transition-all duration-200 font-mono ${
                      exitReason === reason
                        ? "bg-accent text-black font-bold shadow-[0_0_10px_rgba(0,255,159,0.3)]"
                        : "bg-surface border border-border text-gray-300 hover:border-accent/50"
                    }`}
                  >
                    {reason}
                  </button>
                ))}
              </div>
              
              {exitReason === "Other" && (
                <input
                  type="text"
                  value={customReason}
                  onChange={(e) => setCustomReason(e.target.value)}
                  placeholder="Укажите причину..."
                  className="input-cyber mt-2"
                />
              )}
            </div>

            {/* Error */}
            {error && (
              <p className="text-red-400 text-sm flex items-center gap-2">
                <span className="w-1 h-1 bg-red-400 rounded-full animate-pulse" />
                {error}
              </p>
            )}

            {/* Actions */}
            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="btn-secondary flex-1 justify-center"
              >
                Отмена
              </button>
              <button
                type="submit"
                className="btn-primary flex-1 justify-center"
              >
                Закрыть сделку
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
