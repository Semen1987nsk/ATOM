# Sprint 3 — Baseline SLO

Заполнять ПОСЛЕ выполнения первого прогона `read_hot_path.js` на staging.

## Дата baseline: _(заполнить)_

| Эндпойнт | p50 | p95 | p99 | Цель p95 |
|---|---|---|---|---|
| `/stats/` |  |  |  | < 800 ms |
| `/trades/` |  |  |  | < 400 ms |
| `/trades/positions` |  |  |  | < 500 ms |
| `/market/prices` |  |  |  | < 600 ms |
| `error_rate` overall |  | — | — | < 1 % |
| DB pool exhausted events |  | — | — | 0 |
| Rate-limited (429) count |  | — | — | — |

## Окружение

- Backend version: _(git SHA после Sprint 3 merge)_
- DB: _(Postgres N vCPU, M GB RAM)_
- Redis: _(versions, host)_
- Workers: _(N gunicorn workers)_

## Заметки

_(тут — что обнаружили, что нужно дальше тьюнить)_
