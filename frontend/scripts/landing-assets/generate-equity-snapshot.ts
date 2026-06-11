/**
 * Heuristic генерация cohort-anonymous equity curve.
 * Сейчас данные в hero-equity-snapshot.ts захардкожены вручную; этот скрипт —
 * для будущей идемпотентной регенерации из dev DB через backend admin endpoint.
 *
 * TODO (out-of-scope этой итерации): подключить backend /admin/cohort-equity
 * с RBAC и подписью данных, потом запускать этот скрипт перед каждым релизом
 * landing-данных.
 *
 * Пока скрипт — placeholder с printout текущего размера снапшота для аудита.
 */
import { heroEquity } from "../../src/components/landing/data/hero-equity-snapshot";
console.log(`hero equity snapshot: ${heroEquity.length} points, range ${Math.min(...heroEquity)}..${Math.max(...heroEquity).toFixed(2)}`);
