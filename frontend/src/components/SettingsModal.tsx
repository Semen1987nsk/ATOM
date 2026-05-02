'use client';

import React, { useState } from 'react';
import { X, Settings, DollarSign, TrendingDown } from 'lucide-react';
import { useSettings, Currency, MAECalculationMethod } from '@/contexts/SettingsContext';
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

  if (!isOpen) return null;

  return (
    <SettingsModalContent
      key={`settings-${settings.currency}-${settings.maeCalculationMethod}`}
      onClose={onClose}
      initialCurrency={settings.currency}
      initialMaeMethod={settings.maeCalculationMethod}
      updateSettings={updateSettings}
      language={language}
    />
  );
};

interface SettingsModalContentProps {
  onClose: () => void;
  initialCurrency: Currency;
  initialMaeMethod: MAECalculationMethod;
  updateSettings: (newSettings: { currency: Currency; maeCalculationMethod: MAECalculationMethod }) => void;
  language: 'ru' | 'en';
}

const SettingsModalContent: React.FC<SettingsModalContentProps> = ({
  onClose,
  initialCurrency,
  initialMaeMethod,
  updateSettings,
  language,
}) => {
  const [currency, setCurrency] = useState<Currency>(initialCurrency);
  const [maeMethod, setMaeMethod] = useState<MAECalculationMethod>(initialMaeMethod);

  const handleSave = () => {
    updateSettings({
      currency: currency,
      maeCalculationMethod: maeMethod,
    });
    onClose();
  };

  const t = {
    ru: {
      title: 'Настройки',
      currency: 'Валюта',
      currencyHint: 'Валюта отображения',
      maeMethod: 'Расчёт MAE',
      maeMethodHint: 'От какой цены считать просадку',
      maeWeighted: 'Средневзвеш.',
      maeFirst: 'Первый вход',
      maeWeightedDesc: 'От средней цены всех входов',
      maeFirstDesc: 'От цены первой сделки',
      save: 'Сохранить',
      cancel: 'Отмена',
    },
    en: {
      title: 'Settings',
      currency: 'Currency',
      currencyHint: 'Display currency',
      maeMethod: 'MAE Calculation',
      maeMethodHint: 'Price basis for drawdown calculation',
      maeWeighted: 'Weighted Avg',
      maeFirst: 'First Entry',
      maeWeightedDesc: 'From average of all entries',
      maeFirstDesc: 'From first trade price',
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

          {/* MAE Calculation Method */}
          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1 flex items-center gap-1">
              <TrendingDown size={12} />
              {text.maeMethod}
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setMaeMethod('weighted_average')}
                className={`p-3 border text-center transition-colors ${
                  maeMethod === 'weighted_average' 
                    ? 'border-accent bg-accent/10 text-accent' 
                    : 'border-border hover:border-accent/50'
                }`}
              >
                <div className="text-sm font-bold">{text.maeWeighted}</div>
                <div className="text-[9px] opacity-50 mt-1">{text.maeWeightedDesc}</div>
              </button>
              <button
                type="button"
                onClick={() => setMaeMethod('first_entry')}
                className={`p-3 border text-center transition-colors ${
                  maeMethod === 'first_entry' 
                    ? 'border-accent bg-accent/10 text-accent' 
                    : 'border-border hover:border-accent/50'
                }`}
              >
                <div className="text-sm font-bold">{text.maeFirst}</div>
                <div className="text-[9px] opacity-50 mt-1">{text.maeFirstDesc}</div>
              </button>
            </div>
            <p className="text-[10px] opacity-40 mt-1">{text.maeMethodHint}</p>
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
