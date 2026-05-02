'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export type Currency = 'USD' | 'EUR' | 'RUB' | 'USDT' | 'BTC';
export type Theme = 'dark' | 'light';
export type MAECalculationMethod = 'weighted_average' | 'first_entry';

export interface Settings {
  currency: Currency;
  currencySymbol: string;
  theme: Theme;
  maeCalculationMethod: MAECalculationMethod;
  tradesStartDate: string | null; // ISO date string, null = all trades
  tradesStartTradeId: number | null; // ID конкретной сделки для начала отсчёта
  tradesStartTradeSymbol: string | null; // Символ сделки для отображения
}

interface SettingsContextType {
  settings: Settings;
  updateSettings: (newSettings: Partial<Settings>) => void;
  formatCurrency: (amount: number) => string;
  toggleTheme: () => void;
}

const currencySymbols: Record<Currency, string> = {
  USD: '$',
  EUR: '€',
  RUB: '₽',
  USDT: '₮',
  BTC: '₿',
};

const defaultSettings: Settings = {
  currency: 'USD',
  currencySymbol: '$',
  theme: 'dark',
  maeCalculationMethod: 'weighted_average',
  tradesStartDate: null,
  tradesStartTradeId: null,
  tradesStartTradeSymbol: null,
};

function getInitialSettings(): Settings {
  if (typeof window === 'undefined') {
    return defaultSettings;
  }

  const saved = localStorage.getItem('tradingSettings');
  if (!saved) {
    return defaultSettings;
  }

  try {
    const parsed = JSON.parse(saved);
    const { initialDeposit: _legacyInitialDeposit, ...parsedWithoutLegacy } = parsed;
    const currency = parsed.currency as Currency | undefined;
    return {
      ...defaultSettings,
      ...parsedWithoutLegacy,
      currencySymbol: currency ? currencySymbols[currency] || '$' : defaultSettings.currencySymbol,
      theme: parsed.theme || defaultSettings.theme,
    };
  } catch {
    return defaultSettings;
  }
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(getInitialSettings);

  // Применяем тему к document
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', settings.theme);
  }, [settings.theme]);

  const updateSettings = (newSettings: Partial<Settings>) => {
    setSettings(prev => {
      const updated = {
        ...prev,
        ...newSettings,
        currencySymbol: newSettings.currency 
          ? currencySymbols[newSettings.currency] 
          : prev.currencySymbol,
      };
      try {
        localStorage.setItem('tradingSettings', JSON.stringify(updated));
      } catch (e) {
        console.error('Failed to persist settings to localStorage:', e);
      }
      return updated;
    });
  };

  const toggleTheme = () => {
    const newTheme: Theme = settings.theme === 'dark' ? 'light' : 'dark';
    updateSettings({ theme: newTheme });
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

  return (
    <SettingsContext.Provider value={{ settings, updateSettings, formatCurrency, toggleTheme }}>
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
