/**
 * Re-export типов из автогенерируемого api.generated.ts.
 *
 * api.generated.ts собирается командой `npm run gen:api-types:from-file`
 * и НЕ должен править руками — при следующем регене изменения пропадут.
 *
 * Эта обёртка существует, чтобы:
 * 1. Дать удобные алиасы для часто используемых типов (Trade, User, ...).
 * 2. Изолировать остальной код от точной структуры `paths`/`components.schemas`,
 *    которая меняется при апдейте openapi-typescript.
 *
 * Workflow:
 *   1. Backend: `cd backend && python scripts/dump_openapi.py > openapi.json`
 *   2. Frontend: `cd frontend && npm run gen:api-types:from-file`
 *   3. Использование: `import type { Trade, ImportResult } from '@/types/api';`
 */

// Если файл ещё не сгенерирован — компилятор подскажет команду.
// Чтобы build не падал на чистом checkout, делаем мягкий импорт.
import type { components } from "./api.generated";

export type Schemas = components["schemas"];

// Удобные алиасы. Имя в openapi совпадает с именем Pydantic-схемы.
export type Trade = Schemas["Trade"];
export type TradeCreate = Schemas["TradeCreate"];
export type TradeUpdate = Schemas["TradeUpdate"];
export type TradeClose = Schemas["TradeClose"];
export type UserResponse = Schemas["UserResponse"];
export type ImportResultResponse = Schemas["ImportResultResponse"];
export type MessageResponse = Schemas["MessageResponse"];
export type HealthResponse = Schemas["HealthResponse"];
export type ReadinessResponse = Schemas["ReadinessResponse"];

// Если поняли, что какого-то типа нет — добавляй его сюда, не разбрасывай
// `Schemas["Foo"]` по компонентам.
