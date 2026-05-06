"use client";
/**
 * TanStack Query provider — оборачивает приложение в layout.tsx.
 *
 * QueryClient создаём через useState, чтобы он был стабильным per-mount
 * и не пересоздавался на каждый render (важно для дедупликации и кеша).
 *
 * Дефолты подобраны под трейдинговый дневник:
 * - staleTime 30s: статистика считается дорого; не дёргаем backend на каждый focus
 * - retry: 1 раз для GET (network blip), 0 для mutations (двойная отправка = баг)
 * - refetchOnWindowFocus: false — у нас нет «живого» рынка в /stats, focus-refetch шумит
 */
import { useState } from "react";
import {
  QueryClient,
  QueryClientProvider,
  type DefaultOptions,
} from "@tanstack/react-query";

const defaultOptions: DefaultOptions = {
  queries: {
    staleTime: 30 * 1000,
    gcTime: 5 * 60 * 1000,
    retry: 1,
    refetchOnWindowFocus: false,
  },
  mutations: {
    retry: 0,
  },
};

export function QueryProvider({ children }: { children: React.ReactNode }) {
  // useState — гарантирует ОДИН клиент на mount (а не новый на каждый render).
  const [client] = useState(() => new QueryClient({ defaultOptions }));

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
