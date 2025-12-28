'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export type Currency = 'USD' | 'EUR' | 'RUB' | 'USDT' | 'BTC';

export interface Settings {
  initialDeposit: number;
  currency: Currency;
  currencySymbol: string;
}

interface SettingsContextType {
  settings: Settings;
  updateSettings: (newSettings: Partial<Settings>) => void;
  formatCurrency: (amount: number) => string;
}

const currencySymbols: Record<Currency, string> = {
  USD: '$',
  EUR: '€',
  RUB: '₽',
  USDT: '₮',
  BTC: '₿',
};

const defaultSettings: Settings = {
  initialDeposit: 10000,
  currency: 'USD',
  currencySymbol: '$',
};

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const saved = localStorage.getItem('tradingSettings');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setSettings({
          ...defaultSettings,
          ...parsed,
          currencySymbol: currencySymbols[parsed.currency as Currency] || '$',
        });
      } catch {
        // Use defaults
      }
    }
  }, []);

  const updateSettings = (newSettings: Partial<Settings>) => {
    setSettings(prev => {
      const updated = {
        ...prev,
        ...newSettings,
        currencySymbol: newSettings.currency 
          ? currencySymbols[newSettings.currency] 
          : prev.currencySymbol,
      };
      localStorage.setItem('tradingSettings', JSON.stringify(updated));
      return updated;
    });
  };

  const formatCurrency = (amount: number): string => {
    const symbol = settings.currencySymbol;
    const formatted = Math.abs(amount).toLocaleString('ru-RU', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    
    if (settings.currency === 'BTC') {
      return `${amount < 0 ? '-' : ''}${formatted} ${symbol}`;
    }
    
    return `${amount < 0 ? '-' : ''}${symbol}${formatted}`;
  };

  if (!mounted) {
    return (
      <SettingsContext.Provider value={{ settings: defaultSettings, updateSettings, formatCurrency: (a) => `$${a.toFixed(2)}` }}>
        {children}
      </SettingsContext.Provider>
    );
  }

  return (
    <SettingsContext.Provider value={{ settings, updateSettings, formatCurrency }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (context === undefined) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
}
