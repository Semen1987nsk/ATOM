"use client";
/**
 * AppShell — основной layout для авторизованных страниц.
 *
 * Структура (Stripe/Linear-style):
 *   ┌─ Sidebar 240px ─┬─ Header 56px ─────────────────┐
 *   │  Logo           │  ⌘K  search · 🔔 · 👤 user    │
 *   │  Acc switcher   ├───────────────────────────────┤
 *   │  + Add trade    │                               │
 *   │  ─ groups ─     │   children                    │
 *   │  ...            │                               │
 *   │  footer         │                               │
 *   └─────────────────┴───────────────────────────────┘
 *
 * Использование:
 *   export default function HistoryPage() {
 *     return (
 *       <AppShell>
 *         ...history content...
 *       </AppShell>
 *     );
 *   }
 *
 * Не нужен на /login, /register, гостевом лендинге — там свой layout.
 */
import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import { CommandPalette } from "./CommandPalette";
import ThemeToggle from "./ThemeToggle";
import { LanguageSwitcher } from "./LanguageSwitcher";
import {
  BarChart3,
  ListChecks,
  CalendarDays,
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
  Plus,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Bell,
  ChevronDown,
  LogOut,
  Sparkles,
  Wallet,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

// Логомарка «гистограмма-П»: три восходящих столбца (поли+стата), верхний —
// фирменный оранжевый с дата-точкой. currentColor наследует цвет текста (ink),
// поэтому знак виден на любой теме; оранжевый #E2521C фиксирован для консистентности
// бренда (гармонирует с ochre-акцентом приложения, в отличие от старого cyan).
function PolistataMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden="true" focusable="false">
      <rect x="6" y="28" width="9" height="14" rx="2.5" fill="currentColor" />
      <rect x="19.5" y="20" width="9" height="22" rx="2.5" fill="currentColor" />
      <rect x="33" y="10" width="9" height="32" rx="2.5" fill="#E2521C" />
      <circle cx="37.5" cy="10" r="3.4" fill="currentColor" />
    </svg>
  );
}

// ──────────────────────────────────────────────
//  Navigation config
// ──────────────────────────────────────────────

interface NavItem {
  label: string;
  href: string;
  icon: ReactNode;
  /** Если true — элемент пока без выделенного роута (ведёт на дашборд / модалку). */
  todo?: boolean;
  /** Бэйдж справа: число или точка-индикатор. */
  badge?: string | number;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    title: "Торговля",
    items: [
      { label: "Дашборд", href: "/", icon: <BarChart3 size={18} /> },
      { label: "Дневник сделок", href: "/history", icon: <ListChecks size={18} /> },
      { label: "Открытые позиции", href: "/positions", icon: <Wallet size={18} /> },
      { label: "Календарь P&L", href: "/analysis/calendar", icon: <CalendarDays size={18} /> },
    ],
  },
  {
    title: "Анализ",
    items: [
      { label: "AI-инсайты", href: "/analysis/insights", icon: <Sparkles size={18} /> },
      { label: "Сетапы", href: "/analysis/setups", icon: <Layers size={18} /> },
      { label: "MAE / MFE", href: "/analysis/mae-mfe", icon: <Target size={18} /> },
      { label: "Post-Exit", href: "/analysis/post-exit", icon: <Clock size={18} /> },
      { label: "По тегам", href: "/analysis/tags", icon: <PieChart size={18} /> },
    ],
  },
  {
    title: "Журнал",
    items: [
      { label: "Скриншоты", href: "/journal/screenshots", icon: <StickyNote size={18} /> },
      { label: "Daily Review", href: "/review", icon: <Layers size={18} /> },
      { label: "Импорт", href: "/", icon: <Upload size={18} />, todo: true },
    ],
  },
];

const FOOTER_ITEMS: NavItem[] = [
  { label: "Брокеры", href: "/profile?tab=brokers", icon: <Plug size={18} /> },
  { label: "Настройки", href: "/profile", icon: <Settings size={18} /> },
  { label: "Помощь", href: "/help", icon: <HelpCircle size={18} /> },
];

const SIDEBAR_STATE_KEY = "empirik:sidebar-collapsed";

// ──────────────────────────────────────────────
//  Component
// ──────────────────────────────────────────────

export interface AppShellProps {
  children: ReactNode;
  /** Заголовок страницы в хедере (опционально, для контекста). */
  pageTitle?: string;
  /** Right-side контролы хедера (period selector, sync indicator, etc.). */
  headerRight?: ReactNode;
  /** Callback на «+ Новая сделка» — обычно открывает AddTradeModal. */
  onAddTrade?: () => void;
  /** Callback на «Импорт» — обычно открывает ImportPreviewModal. */
  onImport?: () => void;
}

export function AppShell({ children, pageTitle, headerRight, onAddTrade, onImport }: AppShellProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  // Восстанавливаем collapsed-состояние из localStorage после mount.
  // SSR-safe: сначала рендерим в дефолтном виде, потом обновляем.
  useEffect(() => {
    setMounted(true);
    try {
      const saved = localStorage.getItem(SIDEBAR_STATE_KEY);
      if (saved === "true") setCollapsed(true);
    } catch {
      /* localStorage недоступен — игнорируем */
    }
  }, []);

  // Шина действий — Cmd+K палитра и глобальные хоткеи диспатчат сюда.
  // Единая точка для onAddTrade / onImport означает, что страницы не дублируют
  // одинаковые window.addEventListener — достаточно передать колбэк в AppShell.
  useEffect(() => {
    const onAdd = () => onAddTrade?.();
    const onImp = () => onImport?.();
    window.addEventListener("empirik:add-trade", onAdd);
    window.addEventListener("empirik:import-trades", onImp);
    return () => {
      window.removeEventListener("empirik:add-trade", onAdd);
      window.removeEventListener("empirik:import-trades", onImp);
    };
  }, [onAddTrade, onImport]);

  // Глобальный хоткей `N` — Новая сделка. Игнорируем, если фокус в input/textarea
  // или нажат модификатор (чтобы не конфликтовать с системными ⌘N / Ctrl+N).
  useEffect(() => {
    if (!onAddTrade) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key.toLowerCase() !== "n") return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) return;
      e.preventDefault();
      onAddTrade();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onAddTrade]);

  const toggleCollapsed = () => {
    setCollapsed((v) => {
      const next = !v;
      try {
        localStorage.setItem(SIDEBAR_STATE_KEY, String(next));
      } catch {
        /* noop */
      }
      return next;
    });
  };

  return (
    <div className="min-h-screen flex bg-[var(--background)]">
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 md:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden
        />
      )}

      <Sidebar
        collapsed={collapsed && mounted}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
        onToggleCollapse={toggleCollapsed}
        onAddTrade={onAddTrade}
      />

      {/* Main column */}
      <div
        className={clsx(
          "flex-1 flex flex-col min-w-0 transition-[margin] duration-200",
          // На десктопе оставляем место под фиксированный сайдбар.
          collapsed && mounted ? "md:ml-[64px]" : "md:ml-[240px]",
        )}
      >
        <Header
          pageTitle={pageTitle}
          right={headerRight}
          onOpenMobileSidebar={() => setMobileOpen(true)}
        />
        <main className="flex-1 min-w-0">{children}</main>
      </div>

      {/* Глобальное Cmd+K командное меню */}
      <CommandPalette />
    </div>
  );
}

// ──────────────────────────────────────────────
//  Sidebar
// ──────────────────────────────────────────────

function Sidebar({
  collapsed,
  mobileOpen,
  onCloseMobile,
  onToggleCollapse,
  onAddTrade,
}: {
  collapsed: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  onToggleCollapse: () => void;
  onAddTrade?: () => void;
}) {
  return (
    <aside
      className={clsx(
        "fixed top-0 left-0 z-40 h-screen flex flex-col",
        "bg-[var(--surface-1)] border-r border-[var(--border)]",
        "transition-[width,transform] duration-200",
        collapsed ? "w-[64px]" : "w-[240px]",
        // Mobile: hide off-canvas by default, slide-in when open
        "md:translate-x-0",
        mobileOpen ? "translate-x-0" : "-translate-x-full",
      )}
      aria-label="Главная навигация"
    >
      {/* Logo + (mobile close) */}
      <div className="flex items-center justify-between h-14 px-4 border-b border-[var(--border)]">
        <Link
          href="/"
          className="flex items-center gap-2 no-underline"
          onClick={onCloseMobile}
        >
          <PolistataMark className="h-6 w-auto shrink-0" />
          {collapsed ? (
            <span className="sr-only">Полистата</span>
          ) : (
            <span className="font-brand text-[19px]" style={{ fontWeight: 800, letterSpacing: "-0.01em" }}>
              Полистата
            </span>
          )}
        </Link>
        <button
          className="md:hidden btn-icon"
          onClick={onCloseMobile}
          aria-label="Закрыть меню"
        >
          <PanelLeftClose size={16} />
        </button>
      </div>

      {/* Account switcher + Primary CTA */}
      <div className={clsx("px-3 pt-3 pb-2 flex flex-col gap-2")}>
        {!collapsed && <AccountSwitcher />}
        <button
          type="button"
          onClick={onAddTrade}
          className={clsx(
            "btn-primary justify-center",
            collapsed ? "w-10 h-10 px-0" : "w-full",
          )}
          aria-label="Новая сделка"
          title="Новая сделка"
        >
          <Plus size={collapsed ? 18 : 16} />
          {!collapsed && <span>Новая сделка</span>}
        </button>
      </div>

      {/* Nav groups (scrollable) */}
      <nav className="flex-1 min-h-0 overflow-y-auto px-2 py-2 scrollbar-thin">
        {NAV_GROUPS.map((group) => (
          <NavGroupBlock
            key={group.title}
            group={group}
            collapsed={collapsed}
            onItemClick={onCloseMobile}
          />
        ))}
      </nav>

      {/* Footer items */}
      <div className="border-t border-[var(--border)] px-2 py-2 flex flex-col gap-0.5">
        {FOOTER_ITEMS.map((item) => (
          <SidebarItem
            key={item.href + item.label}
            item={item}
            collapsed={collapsed}
            onClick={onCloseMobile}
          />
        ))}

        {/* Collapse toggle (desktop only) */}
        <button
          type="button"
          onClick={onToggleCollapse}
          className={clsx(
            "hidden md:flex items-center gap-2.5 mt-1 px-2.5 py-2 rounded-[var(--radius-md)]",
            "text-[var(--text-tertiary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)]",
            "transition-colors text-[13px] font-medium",
            collapsed && "justify-center",
          )}
          aria-label={collapsed ? "Развернуть меню" : "Свернуть меню"}
          title={collapsed ? "Развернуть" : "Свернуть"}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          {!collapsed && <span>Свернуть</span>}
        </button>
      </div>
    </aside>
  );
}

function NavGroupBlock({
  group,
  collapsed,
  onItemClick,
}: {
  group: NavGroup;
  collapsed: boolean;
  onItemClick?: () => void;
}) {
  return (
    <div className="mb-3">
      {!collapsed && (
        <div className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
          {group.title}
        </div>
      )}
      <div className="flex flex-col gap-0.5">
        {group.items.map((item) => (
          <SidebarItem
            key={item.href + item.label}
            item={item}
            collapsed={collapsed}
            onClick={onItemClick}
          />
        ))}
      </div>
    </div>
  );
}

function SidebarItem({
  item,
  collapsed,
  onClick,
}: {
  item: NavItem;
  collapsed: boolean;
  onClick?: () => void;
}) {
  const pathname = usePathname();
  // Активность: точное совпадение пути ИЛИ префикс (не для корня "/").
  // Placeholder-элементы (todo) никогда не считаются активными — у них
  // href="/" в качестве заглушки, иначе на дашборде «активны» все «soon».
  const isActive =
    !item.todo && (
      pathname === item.href ||
      (item.href !== "/" && !item.href.includes("?") && pathname?.startsWith(item.href))
    );

  return (
    <Link
      href={item.href}
      onClick={onClick}
      className={clsx(
        "group relative flex items-center gap-2.5 px-2.5 py-2 rounded-[var(--radius-md)] no-underline",
        "transition-[background-color,color,box-shadow] duration-150 text-[14px] font-medium",
        isActive
          ? "bg-[var(--accent-soft)] text-[var(--accent-hover)] shadow-[inset_2px_0_0_var(--accent)]"
          : "text-[var(--text-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)]",
        item.todo && !isActive && "opacity-60",
        collapsed && "justify-center",
      )}
      title={collapsed ? item.label : undefined}
      aria-current={isActive ? "page" : undefined}
    >
      <span className={clsx("flex-shrink-0 transition-transform", isActive && "scale-105")}>
        {item.icon}
      </span>
      {!collapsed && (
        <>
          <span className="flex-1 truncate">{item.label}</span>
          {item.badge !== undefined && (
            <span
              className={clsx(
                "text-[11px] font-semibold px-1.5 py-0.5 rounded-[6px]",
                "bg-[var(--surface-2)] text-[var(--text-tertiary)]",
              )}
            >
              {item.badge}
            </span>
          )}
          {item.todo && (
            <span
              className="text-[10px] text-[var(--text-tertiary)] uppercase tracking-wider"
              title="В разработке"
            >
              soon
            </span>
          )}
        </>
      )}
    </Link>
  );
}

// ──────────────────────────────────────────────
//  Account Switcher
// ──────────────────────────────────────────────

interface AccountLite {
  id: number;
  name: string;
  currency: string;
  balance: number;
  initial_balance: number;
  is_active: boolean;
}

function AccountSwitcher() {
  // Реальный мульти-аккаунт (Phase 5).
  // Список тянем с /accounts/, активный = тот, у кого is_active=true.
  // Клик переключает через POST /accounts/{id}/activate, и мы перезагружаем
  // страницу — это самый простой способ инвалидировать все cached stats.
  const [open, setOpen] = useState(false);
  const [accounts, setAccounts] = useState<AccountLite[]>([]);
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();

  // Lazy fetch — только когда есть user
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    import("@/lib/apiClient").then(({ api }) =>
      api.get<AccountLite[]>("/accounts/")
        .then((data) => { if (!cancelled) setAccounts(data); })
        .catch(() => { if (!cancelled) setAccounts([]); })
        .finally(() => { if (!cancelled) setLoading(false); }),
    );
    return () => { cancelled = true; };
  }, [user]);

  const active = accounts.find((a) => a.is_active) || accounts[0];

  async function activate(id: number) {
    if (!id || (active && active.id === id)) {
      setOpen(false);
      return;
    }
    try {
      const { api } = await import("@/lib/apiClient");
      await api.post(`/accounts/${id}/activate`);
      // Перезагружаем страницу — все stat-данные пересчитаются под новым счётом
      if (typeof window !== "undefined") window.location.reload();
    } catch {
      setOpen(false);
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={clsx(
          "w-full flex items-center justify-between gap-2 px-2.5 py-2",
          "rounded-[var(--radius-md)] border border-[var(--border)]",
          "bg-[var(--surface-2)] hover:bg-[var(--surface-hover)]",
          "transition-colors text-[13px] text-left",
        )}
        aria-label="Переключить счёт"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <div className="min-w-0 flex-1">
          <div className="text-[10px] uppercase tracking-wider text-[var(--text-tertiary)] mb-0.5">
            Счёт {accounts.length > 1 && (
              <span className="text-[var(--accent)]">({accounts.length})</span>
            )}
          </div>
          <div className="font-medium truncate">
            {loading ? "Загрузка…" : active?.name || "Без счёта"}
          </div>
        </div>
        <ChevronDown
          size={14}
          className={clsx(
            "text-[var(--text-tertiary)] flex-shrink-0 transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div
            role="menu"
            className={clsx(
              "absolute left-0 right-0 mt-1 z-20",
              "rounded-[var(--radius-lg)] border border-[var(--border)]",
              "bg-[var(--surface-2)] shadow-[var(--shadow-lg)] py-1",
              "animate-scaleIn origin-top",
              "max-h-[60vh] overflow-y-auto",
            )}
          >
            <div className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wider text-[var(--text-tertiary)]">
              Мои счета
            </div>
            {accounts.length === 0 && !loading && (
              <div className="px-3 py-3 text-[12px] text-[var(--text-tertiary)]">
                Счетов пока нет
              </div>
            )}
            {accounts.map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => activate(a.id)}
                className={clsx(
                  "w-full flex items-center justify-between gap-2 px-3 py-2 text-[13px]",
                  a.is_active
                    ? "bg-[var(--accent-soft)] text-[var(--foreground)]"
                    : "hover:bg-[var(--surface-hover)]",
                )}
                role="menuitem"
              >
                <div className="min-w-0 flex-1 text-left">
                  <div className="font-medium truncate">{a.name}</div>
                  {a.initial_balance > 0 && (
                    <div className="text-[10px] text-[var(--text-tertiary)] tabular-nums">
                      {a.initial_balance.toLocaleString("ru-RU", { maximumFractionDigits: 0 })} {a.currency}
                    </div>
                  )}
                </div>
                {a.is_active && (
                  <span className="text-[10px] text-[var(--accent)] font-semibold flex-shrink-0">●</span>
                )}
              </button>
            ))}
            <div className="my-1 border-t border-[var(--border)]" />
            <Link
              href="/profile?tab=brokers"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3 py-2 text-[13px] text-[var(--text-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] no-underline"
              role="menuitem"
            >
              <Plug size={13} />
              Управление счетами
            </Link>
          </div>
        </>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────
//  Header
// ──────────────────────────────────────────────

function Header({
  pageTitle,
  right,
  onOpenMobileSidebar,
}: {
  pageTitle?: string;
  right?: ReactNode;
  onOpenMobileSidebar: () => void;
}) {
  const { user, logout } = useAuth();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);

  return (
    <header
      className={clsx(
        "sticky top-0 z-20 h-14 border-b border-[var(--border)]",
        "bg-[var(--background)]/85 backdrop-blur-md",
        "flex items-center gap-3 px-4 md:px-6",
      )}
    >
      {/* Mobile menu toggle */}
      <button
        type="button"
        className="md:hidden btn-icon"
        onClick={onOpenMobileSidebar}
        aria-label="Открыть меню"
      >
        <PanelLeftOpen size={16} />
      </button>

      {/* Page title (необязателен) */}
      {pageTitle && (
        <h1 className="hidden md:block text-base font-semibold truncate">{pageTitle}</h1>
      )}

      {/* Search — открывает Cmd+K командное меню */}
      <div className="flex-1 min-w-0 flex justify-center md:justify-start md:max-w-md md:ml-4">
        <button
          type="button"
          onClick={() => window.dispatchEvent(new CustomEvent("empirik:open-palette"))}
          className={clsx(
            "w-full max-w-[420px] flex items-center gap-2.5 px-3 py-1.5",
            "rounded-[var(--radius-md)] bg-[var(--surface-1)] border border-[var(--border)]",
            "text-[13px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:border-[var(--border-strong)]",
            "transition-colors",
          )}
          aria-label="Открыть командное меню (Cmd+K)"
          title="Командное меню (⌘K)"
        >
          <Search size={14} />
          <span className="flex-1 text-left">Поиск страницы, действия, тикера…</span>
          <kbd className="hidden sm:inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-[var(--surface-2)] border border-[var(--border)] text-[10px] font-mono">
            ⌘K
          </kbd>
        </button>
      </div>

      {/* Right slot for page-specific controls (period, sync, ...) */}
      {right && <div className="flex items-center gap-2">{right}</div>}

      {/* Notifications */}
      <div className="relative">
        <button
          type="button"
          onClick={() => setNotifOpen((v) => !v)}
          className="btn-icon relative"
          aria-label="Уведомления"
          aria-haspopup="menu"
          aria-expanded={notifOpen}
        >
          <Bell size={16} />
        </button>

        {notifOpen && (
          <>
            <div
              className="fixed inset-0 z-10"
              onClick={() => setNotifOpen(false)}
              aria-hidden
            />
            <div
              role="menu"
              className={clsx(
                "absolute right-0 mt-2 w-80 z-20",
                "rounded-[var(--radius-lg)] border border-[var(--border)]",
                "bg-[var(--surface-2)] shadow-[var(--shadow-lg)]",
                "animate-scaleIn origin-top-right",
              )}
            >
              <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
                <span className="text-[13px] font-semibold">Уведомления</span>
                <span className="text-[11px] text-[var(--text-tertiary)]">0 новых</span>
              </div>
              <div className="px-4 py-10 text-center">
                <div className="w-10 h-10 mx-auto mb-3 rounded-full bg-[var(--surface-1)] flex items-center justify-center text-[var(--text-tertiary)]">
                  <Bell size={16} />
                </div>
                <div className="text-[13px] text-[var(--text-secondary)] mb-1">
                  Пока тихо
                </div>
                <div className="text-[12px] text-[var(--text-tertiary)] leading-relaxed">
                  Здесь появятся алерты по сделкам, лимитам риска и обновлениям сервиса.
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* User menu */}
      <div className="relative">
        <button
          type="button"
          onClick={() => setUserMenuOpen((v) => !v)}
          className={clsx(
            "flex items-center gap-2 pl-1 pr-2 py-1 rounded-[var(--radius-pill)]",
            "border border-[var(--border)] hover:border-[var(--border-strong)]",
            "bg-[var(--surface-1)] hover:bg-[var(--surface-hover)]",
            "transition-colors text-[13px]",
          )}
          aria-haspopup="menu"
          aria-expanded={userMenuOpen}
        >
          <div
            className="w-7 h-7 rounded-full bg-[var(--accent-soft)] text-[var(--accent-hover)] flex items-center justify-center text-[12px] font-semibold"
            aria-hidden
          >
            {(user?.name || user?.email || "?").charAt(0).toUpperCase()}
          </div>
          <span className="hidden sm:inline max-w-[120px] truncate font-medium">
            {user?.name || user?.email?.split("@")[0] || "Гость"}
          </span>
          <ChevronDown size={12} className="text-[var(--text-tertiary)]" />
        </button>

        {userMenuOpen && (
          <>
            <div
              className="fixed inset-0 z-10"
              onClick={() => setUserMenuOpen(false)}
              aria-hidden
            />
            <div
              role="menu"
              className={clsx(
                "absolute right-0 mt-2 w-56 z-20",
                "rounded-[var(--radius-lg)] border border-[var(--border)]",
                "bg-[var(--surface-2)] shadow-[var(--shadow-lg)] py-1.5",
                "animate-scaleIn origin-top-right",
              )}
            >
              <div className="px-3 py-2 border-b border-[var(--border)]">
                <div className="text-[13px] font-semibold truncate">
                  {user?.name || "Без имени"}
                </div>
                <div className="text-[12px] text-[var(--text-tertiary)] truncate">
                  {user?.email}
                </div>
              </div>
              <Link
                href="/profile"
                onClick={() => setUserMenuOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-[13px] text-[var(--text-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] no-underline"
                role="menuitem"
              >
                <Settings size={14} /> Настройки профиля
              </Link>
              <Link
                href="/pricing"
                onClick={() => setUserMenuOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-[13px] text-[var(--text-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] no-underline"
                role="menuitem"
              >
                <Layers size={14} /> Тарифы
              </Link>

              {/* Тема + язык — Toggle/Switcher сами держат своё состояние,
                  поэтому просто кладём их рядом. Кликабельная зона осталась
                  в их собственных кнопках, но ряд выглядит как пункт меню. */}
              <div className="my-1 border-t border-[var(--border)]" />
              <div
                className="flex items-center justify-between gap-2 px-3 py-2 text-[13px] text-[var(--text-secondary)]"
                role="menuitem"
              >
                <span>Тема и язык</span>
                <div
                  className="flex items-center gap-1"
                  onClick={(e) => e.stopPropagation()}
                >
                  <ThemeToggle />
                  <LanguageSwitcher />
                </div>
              </div>

              <div className="my-1 border-t border-[var(--border)]" />
              <button
                type="button"
                onClick={() => {
                  setUserMenuOpen(false);
                  logout();
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-[13px] text-[var(--danger)] hover:bg-[var(--danger-soft)]"
                role="menuitem"
              >
                <LogOut size={14} /> Выйти
              </button>
            </div>
          </>
        )}
      </div>
    </header>
  );
}
