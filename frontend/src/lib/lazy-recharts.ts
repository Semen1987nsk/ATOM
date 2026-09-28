/**
 * Lazy-загрузка recharts — chart-engine ~85KB gzip живёт в отдельном чанке.
 *
 * Стратегия: container'ы (Chart-компоненты + ResponsiveContainer) идут через
 * next/dynamic (ssr: false), вспомогательные компоненты (XAxis, Tooltip, Line, ...)
 * — прямой re-export, чтобы tree-shake мог их выпилить когда чарт не используется
 * на странице. Прямой re-export СЧИТЫВАЕТСЯ webpack'ом — но т.к. контейнер всегда
 * рядом и тащит engine, второй импорт effectively бесплатен.
 *
 * FE-09 Sprint 5 Batch 5.
 */
import dynamic from 'next/dynamic';

// Entry-points (контейнеры) — lazy. ssr: false т.к. ResizeObserver/DOM нужны клиенту.
export const LineChart = dynamic(
  () => import('recharts').then((m) => ({ default: m.LineChart })),
  { ssr: false },
);

export const BarChart = dynamic(
  () => import('recharts').then((m) => ({ default: m.BarChart })),
  { ssr: false },
);

export const AreaChart = dynamic(
  () => import('recharts').then((m) => ({ default: m.AreaChart })),
  { ssr: false },
);

export const ComposedChart = dynamic(
  () => import('recharts').then((m) => ({ default: m.ComposedChart })),
  { ssr: false },
);

export const PieChart = dynamic(
  () => import('recharts').then((m) => ({ default: m.PieChart })),
  { ssr: false },
);

export const ResponsiveContainer = dynamic(
  () => import('recharts').then((m) => ({ default: m.ResponsiveContainer })),
  { ssr: false },
);

// Вспомогательные — прямой re-export. Они НЕ загружают chart-engine сами,
// и tree-shaking webpack'а оставит только нужные в финальном чанке.
export {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Line,
  Bar,
  Area,
  Pie,
  Cell,
  ReferenceLine,
  ReferenceArea,
  ReferenceDot,
} from 'recharts';
