'use client';

import React, { createContext, useContext, useState, ReactNode } from 'react';
import ru from './locales/ru.json';
import en from './locales/en.json';

type Language = 'ru' | 'en';
type Translations = typeof ru;

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: Translations;
  toggleLanguage: () => void;
}

const translations: Record<Language, Translations> = { ru, en };

function getInitialLanguage(): Language {
  if (typeof window === 'undefined') {
    return 'ru';
  }

  const saved = localStorage.getItem('language');
  return saved === 'en' || saved === 'ru' ? saved : 'ru';
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(getInitialLanguage);

  const setLanguage = (lang: Language) => {
    setLanguageState(lang);
    localStorage.setItem('language', lang);
  };

  const toggleLanguage = () => {
    const newLang = language === 'ru' ? 'en' : 'ru';
    setLanguage(newLang);
  };

  const value: LanguageContextType = {
    language,
    setLanguage,
    t: translations[language],
    toggleLanguage,
  };

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (context === undefined) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
}

// Helper function for string interpolation
export function interpolate(template: string, values: Record<string, string | number>): string {
  return template.replace(/{(\w+)}/g, (_, key) => String(values[key] ?? `{${key}}`));
}
