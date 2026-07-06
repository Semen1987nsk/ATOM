"use client";
/**
 * CommandPalette — глобальное командное меню (⌘K / Ctrl+K).
 *
 * Что внутри:
 * 1. Навигация — мгновенный переход на любую страницу sidebar.
 * 2. Действия — открыть модалку (Add trade, Import, Settings, ...).
 * 3. Поиск по тикерам / тегам / заметкам — Phase 5+, сейчас placeholder.
 *
 * Open: ⌘K / Ctrl+K из любого места приложения.
 * Close: Esc или клик за пределами.
 *
 * Использует библиотеку `cmdk` (от Vercel) — даёт fuzzy-search,
 * keyboard-navigation, ARIA accessibility из коробки.
 */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import {
  BarChart3,
  ListChecks,
  CalendarDays,
  Briefcase,
  PieChart,
  Target,
  Clock,
  Brain,
  StickyNote,
  Layers,
  Upload,
  Plug,
  Settings,
  HelpCircle,
  FileText,
  Wallet,
  Plus,
  Search,
  Moon,
  Sun,
  LogOut,
  type LucideIcon,
} from "lucide-react";

import { useAuth } from "@/contexts/AuthContext";

// ──────────────────────────────────────────────
//  Items registry
// ──────────────────────────────────────────────

interface CommandItem {
  id: string;
  label: string;
  Icon: LucideIcon;
  /** Группа в палитре. */
  group: "Навигация" | "Действия" | "Аккаунт";
  /** Альтернативные ключевые слова (для fuzzy-search). */
  keywords?: string[];
  /** Горячая клавиша (визуальный hint справа). */
  shortcut?: string;
  /** Что произойдёт при выборе. */
  onSelect: (ctx: CommandContext) => void;
}

interface CommandContext {
  router: ReturnType<typeof useRouter>;
  closePalette: () => void;
  toggleTheme: () => void;
  logout: () => void;
}

export const ITEMS: CommandItem[] = [
  // ── Навигация ──
  { id: "nav.dashboard", label: "Дашборд", Icon: BarChart3, group: "Навигация", keywords: ["главная", "home"], onSelect: ({ router }) => router.push("/") },
  { id: "nav.trades", label: "Дневник сделок", Icon: ListChecks, group: "Навигация", keywords: ["сделки", "журнал", "history"], onSelect: ({ router }) => router.push("/history") },
  { id: "nav.calendar", label: "Календарь P&L", Icon: CalendarDays, group: "Навигация", keywords: ["heatmap", "месяц"], onSelect: ({ router }) => router.push("/analysis/calendar") },
  { id: "nav.insights", label: "AI-инсайты", Icon: Brain, group: "Навигация", keywords: ["ai", "рекомендации", "инсайты"], onSelect: ({ router }) => router.push("/analysis/insights") },
  { id: "nav.maemfe", label: "MAE / MFE анализ", Icon: Target, group: "Навигация", keywords: ["excursion", "стоп", "тейк"], onSelect: ({ router }) => router.push("/analysis/mae-mfe") },
  { id: "nav.postexit", label: "Post-Exit анализ", Icon: Clock, group: "Навигация", keywords: ["упущенная", "early exit"], onSelect: ({ router }) => router.push("/analysis/post-exit") },
  { id: "nav.tags", label: "По тегам", Icon: PieChart, group: "Навигация", keywords: ["теги", "статистика"], onSelect: ({ router }) => router.push("/analysis/tags") },
  { id: "nav.setups", label: "Сетапы", Icon: Layers, group: "Навигация", keywords: ["стратегии", "паттерны"], onSelect: ({ router }) => router.push("/analysis/setups") },
  { id: "nav.import", label: "Импорт сделок", Icon: Upload, group: "Навигация", keywords: ["загрузить", "csv"], onSelect: ({ closePalette }) => { closePalette(); window.dispatchEvent(new CustomEvent("empirik:import-trades")); } },
  { id: "nav.brokers", label: "Брокеры", Icon: Plug, group: "Навигация", keywords: ["tinkoff", "подключить"], onSelect: ({ router }) => router.push("/profile?tab=brokers") },
  { id: "nav.manual", label: "Руководство", Icon: FileText, group: "Навигация", keywords: ["docs", "help"], onSelect: ({ router }) => router.push("/manual") },
  { id: "nav.blog", label: "Блог", Icon: FileText, group: "Навигация", onSelect: ({ router }) => router.push("/blog") },
  { id: "nav.pricing", label: "Тарифы", Icon: Wallet, group: "Навигация", keywords: ["цены", "оплата"], onSelect: ({ router }) => router.push("/pricing") },
  { id: "nav.help", label: "Помощь", Icon: HelpCircle, group: "Навигация", keywords: ["faq", "support"], onSelect: ({ router }) => router.push("/help") },

  // ── Действия ──
  {
    id: "action.add",
    label: "Новая сделка",
    Icon: Plus,
    group: "Действия",
    keywords: ["добавить", "создать", "trade"],
    shortcut: "N",
    onSelect: ({ closePalette }) => {
      closePalette();
      // Хук-эвент — Home/History страницы слушают и открывают AddTradeModal
      window.dispatchEvent(new CustomEvent("empirik:add-trade"));
    },
  },
  {
    id: "action.import",
    label: "Импорт отчёта брокера",
    Icon: Upload,
    group: "Действия",
    keywords: ["загрузить", "csv", "excel"],
    onSelect: ({ closePalette }) => {
      closePalette();
      window.dispatchEvent(new CustomEvent("empirik:import-trades"));
    },
  },
  {
    id: "action.theme",
    label: "Переключить тему (light / dark)",
    Icon: Moon,
    group: "Действия",
    keywords: ["dark", "light", "светлая", "тёмная"],
    onSelect: ({ toggleTheme, closePalette }) => {
      toggleTheme();
      closePalette();
    },
  },

  // ── Аккаунт ──
  { id: "acc.profile", label: "Профиль", Icon: Settings, group: "Аккаунт", onSelect: ({ router }) => router.push("/profile") },
  {
    id: "acc.logout",
    label: "Выйти из аккаунта",
    Icon: LogOut,
    group: "Аккаунт",
    keywords: ["logout", "exit"],
    onSelect: ({ logout, closePalette }) => {
      closePalette();
      logout();
    },
  },
];

// ──────────────────────────────────────────────
//  Component
// ──────────────────────────────────────────────

export function CommandPalette() {
  const router = useRouter();
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  // Hotkeys: ⌘K (mac) / Ctrl+K (win/linux) — toggle palette globally.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Внешний триггер из header search-кнопки.
  useEffect(() => {
    const handler = () => setOpen(true);
    window.addEventListener("empirik:open-palette", handler);
    return () => window.removeEventListener("empirik:open-palette", handler);
  }, []);

  // Body scroll lock пока палитра открыта.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  const closePalette = useCallback(() => setOpen(false), []);

  const toggleTheme = useCallback(() => {
    if (typeof document === "undefined") return;
    const root = document.documentElement;
    const current = root.getAttribute("data-theme");
    root.setAttribute("data-theme", current === "light" ? "dark" : "light");
  }, []);

  if (!open) return null;

  // Группируем для рендера.
  const groups = Array.from(new Set(ITEMS.map((i) => i.group)));

  const ctx: CommandContext = { router, closePalette, toggleTheme, logout };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] px-4 animate-fadeIn"
      onClick={closePalette}
    >
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" aria-hidden />
      <div
        className="relative w-full max-w-[640px] bg-[var(--surface-2)] border border-[var(--border-strong)] rounded-[var(--radius-xl)] shadow-[var(--shadow-xl)] overflow-hidden animate-scaleIn"
        onClick={(e) => e.stopPropagation()}
      >
        <Command
          label="Командное меню"
          shouldFilter
          className="flex flex-col"
        >
          <div className="flex items-center gap-2.5 px-4 py-3 border-b border-[var(--border)]">
            <Search size={16} className="text-[var(--text-tertiary)] flex-shrink-0" />
            <Command.Input
              autoFocus
              value={query}
              onValueChange={setQuery}
              placeholder="Найти страницу, действие, тикер…"
              className="flex-1 bg-transparent border-none outline-none text-[15px] text-[var(--foreground)] placeholder:text-[var(--text-tertiary)]"
            />
            <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 rounded bg-[var(--surface-3)] text-[10px] font-mono text-[var(--text-tertiary)]">
              ESC
            </kbd>
          </div>

          <Command.List className="max-h-[420px] overflow-y-auto scrollbar-thin py-2">
            <Command.Empty className="px-4 py-8 text-center text-[13px] text-[var(--text-tertiary)]">
              Ничего не нашлось. Попробуй другое слово.
            </Command.Empty>

            {groups.map((group) => (
              <Command.Group
                key={group}
                heading={group}
                className="px-2 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-[var(--text-tertiary)]"
              >
                {ITEMS.filter((i) => i.group === group).map((item) => {
                  const { Icon } = item;
                  return (
                    <Command.Item
                      key={item.id}
                      value={`${item.label} ${item.keywords?.join(" ") || ""}`}
                      onSelect={() => item.onSelect(ctx)}
                      className="flex items-center gap-2.5 px-2.5 py-2 rounded-[var(--radius-md)] text-[14px] text-[var(--text-secondary)] cursor-pointer data-[selected=true]:bg-[var(--accent-soft)] data-[selected=true]:text-[var(--foreground)] hover:bg-[var(--surface-hover)]"
                    >
                      <Icon size={16} className="flex-shrink-0 opacity-80" />
                      <span className="flex-1">{item.label}</span>
                      {item.shortcut && (
                        <kbd className="px-1.5 py-0.5 rounded bg-[var(--surface-3)] text-[10px] font-mono text-[var(--text-tertiary)]">
                          {item.shortcut}
                        </kbd>
                      )}
                    </Command.Item>
                  );
                })}
              </Command.Group>
            ))}
          </Command.List>

          {/* Footer hints */}
          <div className="flex items-center gap-3 px-4 py-2 border-t border-[var(--border)] text-[11px] text-[var(--text-tertiary)]">
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 rounded bg-[var(--surface-3)] font-mono">↑↓</kbd>
              навигация
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 rounded bg-[var(--surface-3)] font-mono">↵</kbd>
              выбрать
            </span>
            <span className="flex items-center gap-1 ml-auto">
              <kbd className="px-1.5 py-0.5 rounded bg-[var(--surface-3)] font-mono">⌘K</kbd>
              открыть откуда угодно
            </span>
          </div>
        </Command>
      </div>
    </div>
  );
}
