'use client';

import React, { useState, useEffect } from 'react';
import { X, Settings, Wallet, DollarSign } from 'lucide-react';
import { useSettings, Currency } from '@/contexts/SettingsContext';
import { useLanguage } from '@/i18n/LanguageContext';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const currencies: { value: Currency; label: string; symbol: string }[] = [
  { value: 'USD', label: 'US Dollar', symbol: '$' },
  { value: 'EUR', label: 'Euro', symbol: '€' },
  { value: 'RUB', label: 'Russian Ruble', symbol: '₽' },
  { value: 'USDT', label: 'Tether USDT', symbol: '₮' },
  { value: 'BTC', label: 'Bitcoin', symbol: '₿' },
];

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
  const { settings, updateSettings } = useSettings();
  const { language } = useLanguage();
  const [deposit, setDeposit] = useState(settings.initialDeposit.toString());
  const [currency, setCurrency] = useState<Currency>(settings.currency);

  useEffect(() => {
    setDeposit(settings.initialDeposit.toString());
    setCurrency(settings.currency);
  }, [settings, isOpen]);

  if (!isOpen) return null;

  const handleSave = () => {
    const depositValue = parseFloat(deposit) || 10000;
    updateSettings({
      initialDeposit: depositValue,
      currency: currency,
    });
    onClose();
  };

  const t = {
    ru: {
      title: 'Настройки',
      deposit: 'Начальный депозит',
      depositHint: 'Размер вашего торгового капитала',
      currency: 'Валюта',
      currencyHint: 'Валюта отображения',
      save: 'Сохранить',
      cancel: 'Отмена',
    },
    en: {
      title: 'Settings',
      deposit: 'Initial Deposit',
      depositHint: 'Your trading capital size',
      currency: 'Currency',
      currencyHint: 'Display currency',
      save: 'Save',
      cancel: 'Cancel',
    },
  };

  const text = t[language];

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fadeIn">
      <div className="cyber-card w-full max-w-md bg-[#0d0d0d] p-6 relative animate-scaleIn overflow-hidden">
        {/* Background glow */}
        <div className="absolute -top-32 -right-32 w-64 h-64 bg-accent/10 rounded-full blur-3xl pointer-events-none" />
        
        <button onClick={onClose} className="absolute top-4 right-4 opacity-50 hover:opacity-100 hover:text-accent transition-colors z-10">
          <X size={20} />
        </button>
        
        <h2 className="text-xl font-bold mb-6 text-accent italic flex items-center gap-2 relative z-10">
          <Settings size={20} />
          {text.title}
        </h2>
        
        <div className="space-y-6 relative z-10">
          {/* Deposit */}
          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1 flex items-center gap-1">
              <Wallet size={12} />
              {text.deposit}
            </label>
            <input 
              type="number"
              min="0"
              step="100"
              className="input-cyber text-lg font-bold"
              placeholder="10000"
              value={deposit}
              onChange={e => setDeposit(e.target.value)}
            />
            <p className="text-[10px] opacity-40 mt-1">{text.depositHint}</p>
          </div>

          {/* Currency */}
          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1 flex items-center gap-1">
              <DollarSign size={12} />
              {text.currency}
            </label>
            <div className="grid grid-cols-5 gap-2">
              {currencies.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => setCurrency(c.value)}
                  className={`p-3 border text-center transition-colors ${
                    currency === c.value 
                      ? 'border-accent bg-accent/10 text-accent' 
                      : 'border-border hover:border-accent/50'
                  }`}
                >
                  <div className="text-lg font-bold">{c.symbol}</div>
                  <div className="text-[8px] opacity-50">{c.value}</div>
                </button>
              ))}
            </div>
            <p className="text-[10px] opacity-40 mt-1">{text.currencyHint}</p>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary flex-1 justify-center"
            >
              {text.cancel}
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="btn-primary flex-1 justify-center"
            >
              {text.save}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
