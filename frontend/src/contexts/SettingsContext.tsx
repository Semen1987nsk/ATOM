'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export type Currency = 'USD' | 'EUR' | 'RUB' | 'USDT' | 'BTC';
export type Theme = 'dark' | 'light';

export interface Settings {
  initialDeposit: number;
  currency: Currency;
  currencySymbol: string;
  theme: Theme;
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
  initialDeposit: 10000,
  currency: 'USD',
  currencySymbol: '$',
  theme: 'dark',
};

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [mounted, setMounted] = useState(false);

  // Применяем тему к document
  useEffect(() => {
    if (mounted) {
      document.documentElement.setAttribute('data-theme', settings.theme);
    }
  }, [settings.theme, mounted]);

  useEffect(() => {
    setMounted(true);
    const saved = localStorage.getItem('tradingSettings');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        const theme = parsed.theme || 'dark';
        setSettings({
          ...defaultSettings,
          ...parsed,
          currencySymbol: currencySymbols[parsed.currency as Currency] || '$',
          theme,
        });
        // Применяем тему сразу при загрузке
        document.documentElement.setAttribute('data-theme', theme);
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

  if (!mounted) {
    return (
      <SettingsContext.Provider value={{ settings: defaultSettings, updateSettings, formatCurrency: (a) => `$${a.toFixed(2)}`, toggleTheme: () => {} }}>
        {children}
      </SettingsContext.Provider>
    );
  }

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
