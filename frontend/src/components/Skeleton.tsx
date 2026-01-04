"use client";

interface SkeletonProps {
  className?: string;
  style?: React.CSSProperties;
}

export function Skeleton({ className = "", style }: SkeletonProps) {
  return (
    <div 
      className={`skeleton-shimmer bg-white/5 rounded ${className}`}
      style={style}
    />
  );
}

// Skeleton для карточки статистики
export function StatsCardSkeleton() {
  return (
    <div className="cyber-card p-4 space-y-3 relative overflow-hidden">
      {/* Glow effect */}
      <div className="absolute -top-10 -right-10 w-20 h-20 bg-accent/5 rounded-full blur-2xl" />
      
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-8 w-8 rounded-lg" />
      </div>
      <Skeleton className="h-10 w-32" />
      <div className="flex items-center gap-2">
        <Skeleton className="h-3 w-3 rounded-full" />
        <Skeleton className="h-3 w-20" />
      </div>
    </div>
  );
}

// Skeleton для строки таблицы
export function TableRowSkeleton({ columns = 8 }: { columns?: number }) {
  return (
    <tr className="border-b border-border/50">
      {Array.from({ length: columns }).map((_, i) => (
        <td key={i} className="p-3">
          <Skeleton className="h-4 w-full" style={{ animationDelay: `${i * 0.05}s` }} />
        </td>
      ))}
    </tr>
  );
}

// Skeleton для таблицы истории сделок
export function TradeHistorySkeleton() {
  return (
    <div className="cyber-card p-6 space-y-4">
      {/* Filter bar skeleton */}
      <div className="flex gap-4 mb-6">
        <Skeleton className="h-10 w-32" />
        <Skeleton className="h-10 w-32" />
        <Skeleton className="h-10 w-24" />
      </div>
      
      {/* Table skeleton */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              {Array.from({ length: 10 }).map((_, i) => (
                <th key={i} className="p-3">
                  <Skeleton className="h-4 w-16" style={{ animationDelay: `${i * 0.03}s` }} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 8 }).map((_, i) => (
              <TableRowSkeleton key={i} columns={10} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Skeleton для дашборда
export function DashboardSkeleton() {
  return (
    <div className="p-8 space-y-8 bg-gradient-mesh min-h-screen">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div className="space-y-2">
          <Skeleton className="h-10 w-48" />
          <Skeleton className="h-4 w-32" />
        </div>
        <div className="flex gap-3">
          <Skeleton className="h-10 w-24" />
          <Skeleton className="h-10 w-32" />
        </div>
      </div>
      
      {/* Stats Cards - Staggered */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} style={{ animationDelay: `${i * 0.1}s` }} className="opacity-0 animate-[fadeIn_0.4s_ease-out_forwards]">
            <StatsCardSkeleton />
          </div>
        ))}
      </div>
      
      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartSkeleton />
        <ChartSkeleton />
      </div>
      
      {/* Trade list */}
      <div className="cyber-card p-6">
        <div className="flex items-center justify-between mb-6">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-8 w-24" />
        </div>
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div 
              key={i} 
              className="flex items-center gap-4 p-4 border border-border/30 rounded-lg"
              style={{ animationDelay: `${i * 0.1}s` }}
            >
              <Skeleton className="h-10 w-10 rounded-lg" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-3 w-32" />
              </div>
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-8 w-8 rounded" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// Skeleton для чартов
export function ChartSkeleton({ height = "h-64" }: { height?: string }) {
  return (
    <div className={`cyber-card p-6 ${height} relative overflow-hidden`}>
      {/* Subtle glow */}
      <div className="absolute top-0 right-0 w-32 h-32 bg-accent/5 rounded-full blur-3xl" />
      
      <div className="flex justify-between items-center mb-6">
        <div className="space-y-1">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-3 w-20" />
        </div>
        <Skeleton className="h-8 w-24 rounded-lg" />
      </div>
      
      <div className="relative h-[calc(100%-60px)]">
        {/* Grid lines */}
        <div className="absolute inset-0 flex flex-col justify-between">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-px w-full bg-white/5" style={{ animationDelay: `${i * 0.1}s` }} />
          ))}
        </div>
        
        {/* Animated chart line simulation */}
        <svg className="absolute inset-0 w-full h-full" preserveAspectRatio="none">
          <defs>
            <linearGradient id="chartGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="rgba(0, 255, 159, 0.2)" />
              <stop offset="50%" stopColor="rgba(0, 255, 159, 0.4)" />
              <stop offset="100%" stopColor="rgba(0, 255, 159, 0.2)" />
            </linearGradient>
          </defs>
          <path 
            d="M0,80 Q50,60 100,70 T200,50 T300,65 T400,40 T500,55" 
            fill="none" 
            stroke="url(#chartGradient)" 
            strokeWidth="2"
            className="opacity-30"
          />
        </svg>
        
        {/* Bars */}
        <div className="absolute bottom-0 left-0 right-0 h-3/4 flex items-end gap-2 justify-around">
          {Array.from({ length: 12 }).map((_, i) => (
            <div 
              key={i} 
              className="flex-1 skeleton-shimmer rounded-t"
              style={{ 
                height: `${30 + Math.random() * 60}%`,
                animationDelay: `${i * 0.05}s`
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// Empty State Component
interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="empty-state py-16">
      {icon && (
        <div className="empty-state-icon">
          {icon}
        </div>
      )}
      <h3 className="text-xl font-bold mb-2 text-foreground">{title}</h3>
      <p className="text-sm opacity-60 max-w-md mb-6">{description}</p>
      {action}
    </div>
  );
}
