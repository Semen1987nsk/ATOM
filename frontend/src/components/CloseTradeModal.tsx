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
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-[#1e1e1e] rounded-lg shadow-xl w-full max-w-md border border-gray-700">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-gray-700">
            <h3 className="text-lg font-semibold text-white">
              Закрыть сделку
            </h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          
          {/* Content */}
          <form onSubmit={handleSubmit} className="p-4 space-y-4">
            {/* Trade Info */}
            {tradeTicker && (
              <div className="bg-gray-800 rounded-lg p-3 flex items-center gap-3">
                <span className={`px-2 py-1 rounded text-xs font-bold ${
                  tradeDirection === "LONG" 
                    ? "bg-green-500/20 text-green-400" 
                    : "bg-red-500/20 text-red-400"
                }`}>
                  {tradeDirection}
                </span>
                <span className="text-white font-medium">{tradeTicker}</span>
              </div>
            )}

            {/* Exit Price */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
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
                className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                autoFocus
              />
            </div>

            {/* Exit Reason */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Причина выхода *
              </label>
              <div className="grid grid-cols-4 gap-2 mb-2">
                {EXIT_REASONS.map((reason) => (
                  <button
                    key={reason}
                    type="button"
                    onClick={() => setExitReason(reason)}
                    className={`px-2 py-1.5 text-xs rounded-lg transition-colors ${
                      exitReason === reason
                        ? "bg-blue-600 text-white"
                        : "bg-gray-800 text-gray-300 hover:bg-gray-700"
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
                  className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              )}
            </div>

            {/* Error */}
            {error && (
              <p className="text-red-400 text-sm">{error}</p>
            )}

            {/* Actions */}
            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
              >
                Отмена
              </button>
              <button
                type="submit"
                className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
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
