'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { AUTH_USER_CHANGED_EVENT } from '@/lib/userScopedStorage';

export type Currency = 'USD' | 'EUR' | 'RUB' | 'USDT' | 'BTC';
export type Theme = 'dark' | 'light';
export type MAECalculationMethod = 'weighted_average' | 'first_entry';
// Phase 11 (2026-05-17): отображение P&L — с комиссиями (net) или без (gross).
//   net    — реальный финансовый результат, как у брокера. Default.
//   gross  — только body P&L от движения цены, без commissions/fees/taxes.
export type PnLDisplayMode = 'net' | 'gross';

export interface Settings {
  currency: Currency;
  currencySymbol: string;
  theme: Theme;
  maeCalculationMethod: MAECalculationMethod;
  tradesStartDate: string | null; // ISO date string, null = all trades
  tradesStartTradeId: number | null; // ID конкретной сделки для начала отсчёта
  tradesStartTradeSymbol: string | null; // Символ сделки для отображения
  pnlDisplayMode: PnLDisplayMode;
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

// Theme — device-preference, не user-scoped: живёт в отдельном ключе вне
// tradingSettings, чтобы clearUserScopedState() (logout/смена юзера) её не стирал.
const THEME_DEVICE_KEY = 'empirik.theme';

// Полистата таргетится на трейдеров MOEX — все сделки приходят из Tinkoff API
// в рублях. Дефолтная валюта = RUB. USD/EUR/USDT/BTC доступны для тех
// кто торгует не на MOEX (опциональный override в настройках).
const defaultSettings: Settings = {
  currency: 'RUB',
  currencySymbol: '₽',
  theme: 'dark',
  maeCalculationMethod: 'weighted_average',
  tradesStartDate: null,
  tradesStartTradeId: null,
  tradesStartTradeSymbol: null,
  pnlDisplayMode: 'net',  // Phase 11: default net (matches broker, industry standard)
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
    let currency = parsed.currency as Currency | undefined;
    // Миграция: до этого дефолт был USD. У пользователей MOEX-трейдеров
    // в localStorage сохранилось 'USD', хотя они никогда явно его не
    // выбирали. Переключаем USD→RUB однократно. Если юзер реально торгует
    // в USD, он переключит обратно в настройках.
    if (currency === 'USD' && !parsed.currencyExplicitlyChosen) {
      currency = 'RUB';
    }
    return {
      ...defaultSettings,
      ...parsedWithoutLegacy,
      currency: currency || defaultSettings.currency,
      currencySymbol: currency ? currencySymbols[currency] || '₽' : defaultSettings.currencySymbol,
      theme: (typeof window !== 'undefined' && (localStorage.getItem(THEME_DEVICE_KEY) as Theme))
        || parsed.theme || defaultSettings.theme,
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

  // Cross-user leak guard: при смене владельца сессии (AuthProvider уже почистил
  // localStorage) перечитываем настройки — getInitialSettings вернёт дефолты,
  // и чужие tradesStartDate/tradesStartTradeSymbol (бейдж «С GLDRUBF») и пр.
  // мгновенно исчезают без перезагрузки.
  useEffect(() => {
    const onUserChanged = () => setSettings(getInitialSettings());
    window.addEventListener(AUTH_USER_CHANGED_EVENT, onUserChanged);
    return () => window.removeEventListener(AUTH_USER_CHANGED_EVENT, onUserChanged);
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
      try {
        localStorage.setItem('tradingSettings', JSON.stringify(updated));
        if (newSettings.theme) {
          localStorage.setItem(THEME_DEVICE_KEY, newSettings.theme);
        }
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
    const sign = amount < 0 ? '-' : '';
    // Русская типографика: ₽/¥ ставятся после числа, USD/EUR/£ — перед.
    // BTC/USDT/токены — после с пробелом.
    if (settings.currency === 'RUB' || settings.currency === 'BTC' || settings.currency === 'USDT') {
      return `${sign}${formatted} ${symbol}`;
    }
    return `${sign}${symbol}${formatted}`;
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
