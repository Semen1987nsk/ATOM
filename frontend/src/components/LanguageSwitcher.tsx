'use client';

import { useLanguage } from '@/i18n/LanguageContext';
import { Globe } from 'lucide-react';

export function LanguageSwitcher() {
  const { language, toggleLanguage, t } = useLanguage();

  return (
    <button
      onClick={toggleLanguage}
      className="btn-secondary p-2.5"
      title={t.language.switch}
    >
      <Globe size={14} />
      <span className="hidden sm:inline">{language === 'ru' ? 'RU' : 'EN'}</span>
    </button>
  );
}
