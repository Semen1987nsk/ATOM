/**
 * Парсит datetime из API. Backend хранит и отдаёт naive-UTC без суффикса
 * ('2026-07-02T12:30:00'), а new Date(строка-без-offset) трактует её как
 * ЛОКАЛЬНОЕ время → сдвиг на -3ч для МСК (S3-10). Добавляем Z, если offset
 * отсутствует.
 */
export function parseApiDate(s: string): Date {
  const hasTz = /(?:Z|[+-]\d{2}:?\d{2})$/.test(s);
  return new Date(hasTz ? s : `${s}Z`);
}
