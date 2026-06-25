/**
 * Phase 13 (2026-05-17): hook для filter state + localStorage persistence.
 */
import { useEffect, useState } from 'react';
import { JournalFilters, DEFAULT_JOURNAL_FILTERS } from './types';

const STORAGE_KEY = 'empirik_journal_filters_v1';

function loadFromStorage(): JournalFilters {
  if (typeof window === 'undefined') return DEFAULT_JOURNAL_FILTERS;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_JOURNAL_FILTERS;
    const parsed = JSON.parse(raw) as Partial<JournalFilters>;
    // Merge с defaults — защита от schema drift (новые поля наследуют default).
    return { ...DEFAULT_JOURNAL_FILTERS, ...parsed };
  } catch {
    return DEFAULT_JOURNAL_FILTERS;
  }
}

function persistToStorage(filters: JournalFilters) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filters));
  } catch {
    // localStorage quota / private mode — silent
  }
}

export function useJournalFilters() {
  const [filters, setFilters] = useState<JournalFilters>(() => loadFromStorage());

  useEffect(() => {
    persistToStorage(filters);
  }, [filters]);

  // Cross-user leak guard: при смене владельца сессии (localStorage уже почищен
  // AuthProvider) сбрасываем фильтры журнала к дефолтам — чужой search/setupId
  // не должен утечь новому пользователю на том же устройстве.
  useEffect(() => {
    const onUserChanged = () => setFilters(DEFAULT_JOURNAL_FILTERS);
    window.addEventListener('auth:user-changed', onUserChanged);
    return () => window.removeEventListener('auth:user-changed', onUserChanged);
  }, []);

  const update = (patch: Partial<JournalFilters>) =>
    setFilters((f) => ({ ...f, ...patch }));

  const reset = () =>
    setFilters((f) => ({ ...DEFAULT_JOURNAL_FILTERS, visibleLimit: f.visibleLimit }));

  return { filters, update, reset };
}
