// ⚠️  PLACEHOLDER — этот файл будет ПЕРЕЗАПИСАН при регене типов из OpenAPI.
//
// Чтобы получить реальные типы:
//   1. cd backend && python scripts/dump_openapi.py > openapi.json
//   2. cd frontend && npm run gen:api-types:from-file
//
// Не правь этот файл руками — изменения пропадут.
// Удобные алиасы: см. ./api.ts (он re-export'ит отсюда).

export interface paths {
  // Заглушка. После регенерации здесь будет полный набор endpoint'ов
  // вида "/trades/": { get: { ... }, post: { ... } }, ...
  [path: string]: unknown;
}

export interface components {
  schemas: {
    // ⚠️ После регена все Pydantic-схемы появятся здесь автоматически.
    // Текущие заглушки — лишь чтобы import './api' компилировался.
    Trade: { id: number; symbol: string; [k: string]: unknown };
    TradeCreate: { symbol: string; [k: string]: unknown };
    TradeUpdate: { [k: string]: unknown };
    TradeClose: { exit_price: number; [k: string]: unknown };
    UserResponse: { id: number; email: string; [k: string]: unknown };
    ImportResultResponse: {
      message: string;
      imported: number;
      skipped: number;
      duplicates_found: number;
      total_in_file: number;
      balance_saved?: boolean;
      range_processed?: { start: number; end: number; count: number };
    };
    MessageResponse: { message: string; detail?: string | null };
    HealthResponse: { status: string; service: string; version?: string | null };
    ReadinessResponse: {
      status: string;
      service: string;
      version: string;
      checks: Record<string, { ok: boolean; error?: string | null; note?: string | null }>;
    };
  };
}

export type webhooks = Record<string, never>;
export type operations = Record<string, never>;
export type external = Record<string, never>;
