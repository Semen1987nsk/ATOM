# Load tests — k6

Нагрузочные сценарии для Empirik backend, Sprint 3 exit-критерий: 500 одновременных пользователей с записанным SLO (p95, error_rate, pool exhaustion).

## Установка k6

- Windows: `winget install k6` или `choco install k6`.
- macOS: `brew install k6`.
- Linux: `sudo apt-get install k6` (после `wget -q -O - https://dl.k6.io/key.gpg | sudo apt-key add -`).
- Docker: `docker run --rm -i grafana/k6 run - <scenarios/read_hot_path.js`.

## Локальный smoke (1 минута, ~5 VU)

```bash
k6 run \
  -e BASE_URL=http://localhost:8000 \
  -e AUTH_TOKEN="<bearer-token>" \
  --stage 30s:5,30s:0 \
  scenarios/read_hot_path.js
```

Получение AUTH_TOKEN:
1. `POST /auth/login` с тестовым юзером (см. seed-фикстуры или dev-аккаунт).
2. Достать `access_token` из cookie или ответа.
3. Положить в `.load-token` (не коммитить — `.gitignore`).

## Полный staging-прогон (10 минут, ramping → 500 VU)

```bash
k6 run \
  -e BASE_URL=https://staging.empirik.io \
  -e AUTH_TOKEN=$(cat .load-token) \
  scenarios/read_hot_path.js
```

## SLO цели (Sprint 3 exit-критерий)

- `p95(/stats/)` < 800 ms
- `p95(/trades/)` < 400 ms
- `p95(/trades/positions)` < 500 ms
- `p95(/market/prices)` < 600 ms
- `error_rate` < 1 %
- DB pool exhausted events == 0 (метрика из Sentry/logs)
- Event-loop stall events == 0 (метрика из Sentry/logs)

Baseline-цифры записываются в `baseline_slo.md` после первого прогона.

## Сценарии

- `read_hot_path.js` — основной mix: `/stats/`, `/trades/`, `/trades/positions`, `/market/prices` с think-time 1–3с. Имитирует активного юзера-журнала.
- `sync_idle.js` — 500 idle коннекций без активных запросов. Проверка, что keep-alive и idle-allocation не вызывают утечек.
