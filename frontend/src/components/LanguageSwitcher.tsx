'use client';

import { useLanguage } from '@/i18n/LanguageContext';
import { Globe } from 'lucide-react';

export function LanguageSwitcher() {
  const { language, toggleLanguage, t } = useLanguage();

  return (
    <button
      onClick={toggleLanguage}
      className="flex items-center gap-2 bg-surface border border-border px-3 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest"
      title={t.language.switch}
    >
      <Globe size={14} />
      <span className="hidden sm:inline">{language === 'ru' ? 'RU' : 'EN'}</span>
    </button>
  );
}
