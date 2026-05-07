# Deployment

> Скелет. Заполнить после переноса на Yandex Cloud.

## Текущее состояние (07.05.2026)

- **Локально:** SQLite + uvicorn / npm dev
- **Docker Compose:** есть в `docker-compose.yml`, но Docker не установлен на dev-машине
- **Production:** **отсутствует** (см. `tech/audit-report.md` C2/C3)

## Целевая архитектура (Q2 2026)

| Компонент | Где | Зачем |
|---|---|---|
| Backend (FastAPI) | Yandex Cloud Compute Cloud | Близко к РФ-юзерам |
| PostgreSQL | Yandex Managed PostgreSQL | Бэкапы, репликация |
| Redis | Yandex Managed Redis | Кэш, rate-limit |
| Frontend (Next.js) | Yandex Cloud Compute или Vercel-РФ-аналог | SSR требует runtime |
| Object Storage | Yandex Object Storage (S3-совместимый) | Скриншоты сделок |
| Sentry | Self-hosted в Yandex Cloud | 152-ФЗ — нельзя слать в sentry.io |

## CI/CD (план)

*[добавить когда подключим: GitHub Actions / GitLab CI / Yandex Container Registry]*

## Чеклист перед первым проддеплоем

- [ ] РКН-уведомление подано и одобрено
- [ ] DPO email активен
- [ ] Юрист утвердил `policy-versions.md` v1
- [ ] SECRET_KEY и REFRESH_SECRET_KEY сгенерированы и сохранены в Yandex Lockbox
- [ ] TLS-сертификаты выпущены (Let's Encrypt через certbot)
- [ ] Sentry DSN прописан, PII-фильтр работает
- [ ] Бэкап-план PostgreSQL (раз в сутки + WAL)
- [ ] Мониторинг доступности (`/health` / `/ready`)
- [ ] Smoke-тесты на стейджинге зелёные
- [ ] DNS direct → балансировщик
- [ ] Юкасса в продовом режиме

## Связанное

- `tech/audit-report.md` — блокеры C2/C7/C8
- `monitoring.md` — что смотрим после деплоя
