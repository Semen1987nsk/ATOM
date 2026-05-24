# Статус 152-ФЗ compliance в Empirik

**Последнее обновление:** 2026-05-07 (после PR1)

## Чеклист 7 пунктов

| # | Пункт | Статус | Детали |
| --- | --- | --- | --- |
| **1** | Уведомление РКН (форма Н-152) | 🔴 НЕ СДЕЛАНО | Внешний процесс на pd.rkn.gov.ru. См. `rkn-notification.md`. |
| **2** | Назначен ответственный за ОПД (DPO) | 🔴 НЕ СДЕЛАНО | Нужен email `privacy@empirik.io` + приказ |
| **3** | Политика конфиденциальности доступна на сайте | 🟢 СДЕЛАНО | `frontend/src/app/privacy/page.tsx`, версия v1 |
| **4** | Cookie consent banner | 🟡 ЧАСТИЧНО | `frontend/src/components/CookieConsent.tsx` — баннер есть, но cookies категорий нет (только base) |
| **5** | Согласие ОПД при регистрации + БД для хранения | 🟢 СДЕЛАНО | `pd_consents` таблица + checkbox в `register/page.tsx` + проверка в `routers/auth.py` |
| **6** | Право на удаление (`DELETE /auth/me`) | 🟢 СДЕЛАНО | Двухфазное: PR1 от 07.05.2026, см. ADR-0002 |
| **7** | Хостинг ПД на территории РФ | 🔴 НЕ СДЕЛАНО | BUSINESS_PLAN.md упоминал AWS/DigitalOcean. Нужно Yandex Cloud / Selectel / VK Cloud. |

## Закрыто блокером (что блокирует запуск платных функций)

- Пункты 1, 2, 7 — **юридический блок до boot**: без РКН-уведомления и хостинга в РФ — приём платежей на территории РФ юридически рискован.

## Закрыто PR1 от 2026-05-07

✅ **Pd consents** (журнал согласий с IP/UA/version) — миграция 0002_add_pd_consents
✅ **Чекбокс согласия** при регистрации — обязательное поле, без него API возвращает 400
✅ **Право на удаление** — `DELETE /auth/me` с soft-delete + 30-дневный grace
✅ **Анонимизация при finalize** — User.email/name → NULL, Trade.notes/screenshot_url → NULL, Payment остаётся (402-ФЗ)
✅ **Брокерские токены** — отзываются СРАЗУ (не ждут 30 дней)
✅ **Политика /privacy** — 8 разделов с реальным юридическим текстом

## Что нужно сделать перед платным запуском

### Обязательно (юридические блоки)

1. **Назначить DPO**, прописать email в `policy-versions.md`. Сейчас в политике стоит `privacy@empirik.io` — этот ящик нужно создать и слушать.
2. **Подать уведомление в РКН** через pd.rkn.gov.ru (форма Н-152). Срок рассмотрения 15-30 дней.
3. **Перенести production-инфру в РФ** — Yandex Cloud (приоритет) или Selectel.
4. **Проверить политику с юристом.** Текущий текст в `/privacy` — рабочий шаблон, не финальная редакция.

### Желательно (улучшение compliance)

- **Cookie banner с категориями** — сейчас только base-согласие. По хорошему: «строго необходимые / аналитика / маркетинг».
- ~~**Запуск scheduler'а для finalize_deletion**~~ ✅ **СДЕЛАНО 2026-05-07** — подключено к `sync_scheduler.SyncScheduler._check_pd_finalizations()` с интервалом 24 часа. Smoke-тест в `backend/scripts/_smoke_pd_finalize_scheduler.py`.
- ~~**Endpoint экспорта ПД** (`GET /auth/me/export`)~~ ✅ **СДЕЛАНО 2026-05-07** — `services/pd_export.build_user_export()` собирает все домены данных, endpoint с rate-limit `5/hour`, кнопка «Скачать JSON» в `/profile`. Smoke в `backend/scripts/_smoke_pd_export.py`. Без `hashed_password` и `BrokerConnection.api_token`.

## История изменений

| Дата | Что сделано |
| --- | --- |
| 2026-05-07 | PR1: pd_consents + checkbox + DELETE /auth/me + /privacy + CookieConsent. Метрика 18 в аудите: 3 → 5. |
| 2026-05-07 | Scheduler подключён к finalize_deletion (24h цикл). |
| 2026-05-07 | Endpoint `GET /auth/me/export` (152-ФЗ ст. 14) реализован. Метрика 18: 6 → 7. |

## Связанные документы

- ADR-0002 (`tech/decisions/0002-pd-consent-versioning.md`) — архитектура согласия
- skill `152-fz-compliance-checklist` (`.claude/skills/`) — методичка для следующих задач
- `policy-versions.md` — история текста политики
- `rkn-notification.md` — как подавать уведомление
- `data-retention.md` — сроки хранения
