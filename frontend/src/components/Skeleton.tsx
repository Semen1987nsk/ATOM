"use client";

interface SkeletonProps {
  className?: string;
  style?: React.CSSProperties;
}

export function Skeleton({ className = "", style }: SkeletonProps) {
  return (
    <div 
      className={`animate-pulse bg-gray-700/50 rounded ${className}`}
      style={style}
    />
  );
}

// Skeleton для карточки статистики
export function StatsCardSkeleton() {
  return (
    <div className="cyber-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-5 w-5 rounded-full" />
      </div>
      <Skeleton className="h-8 w-32" />
      <Skeleton className="h-3 w-20" />
    </div>
  );
}

// Skeleton для строки таблицы
export function TableRowSkeleton({ columns = 8 }: { columns?: number }) {
  return (
    <tr className="border-b border-border/50">
      {Array.from({ length: columns }).map((_, i) => (
        <td key={i} className="p-3">
          <Skeleton className="h-4 w-full" />
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
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-8 w-24" />
      </div>
      
      {/* Table skeleton */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              {Array.from({ length: 10 }).map((_, i) => (
                <th key={i} className="p-3">
                  <Skeleton className="h-4 w-16" />
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
    <div className="p-8 space-y-8">
      {/* Header */}
      <div className="flex justify-between items-center">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-10 w-32" />
      </div>
      
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <StatsCardSkeleton key={i} />
        ))}
      </div>
      
      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="cyber-card p-4 h-64">
          <Skeleton className="h-4 w-32 mb-4" />
          <Skeleton className="h-full w-full rounded" />
        </div>
        <div className="cyber-card p-4 h-64">
          <Skeleton className="h-4 w-32 mb-4" />
          <Skeleton className="h-full w-full rounded" />
        </div>
      </div>
      
      {/* Trade list */}
      <div className="cyber-card p-4">
        <Skeleton className="h-4 w-40 mb-4" />
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 p-3 border border-border/30 rounded">
              <Skeleton className="h-6 w-16" />
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-16" />
              <Skeleton className="h-4 w-20 ml-auto" />
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
    <div className={`cyber-card p-4 ${height}`}>
      <div className="flex justify-between items-center mb-4">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-6 w-20" />
      </div>
      <div className="relative h-[calc(100%-40px)]">
        {/* Fake chart lines */}
        <div className="absolute inset-0 flex flex-col justify-between opacity-20">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-px w-full" />
          ))}
        </div>
        {/* Fake bars */}
        <div className="absolute bottom-0 left-0 right-0 h-3/4 flex items-end gap-2 justify-around">
          {Array.from({ length: 12 }).map((_, i) => (
            <Skeleton 
              key={i} 
              className="w-4" 
              style={{ height: `${30 + Math.random() * 60}%` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
