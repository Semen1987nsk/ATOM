# ADR-0002: Версионирование согласия на ОПД + двухфазное удаление

**Статус:** Принято и реализовано (PR1 от 2026-05-07)
**Контекст PR:** Закрытие блокера C1 из аудита (152-ФЗ ст. 9 ч. 4 + ст. 21 ч. 5)

## Контекст

152-ФЗ требует **доказательной базы** что субъект ПД дал согласие осознанно — а РКН при проверке требует показать конкретный текст политики, который видел юзер, IP/UA на момент клика, и временную метку.

Также ст. 21 ч. 5 даёт пользователю право требовать удаления — но удаление должно быть **обратимым** в течение разумного срока (юзер может передумать, ошибиться) и **необратимым** после.

## Решение

### Согласие — отдельная таблица `pd_consents`

```
PdConsent {
  id, user_id (FK), consent_text_version ("v1", "v2"...),
  accepted_at, ip_address, user_agent, revoked_at
}
```

- Каждое согласие — отдельная строка. Никогда не перезаписываем — только revoke + новый consent.
- `consent_text_version` инкрементируется при существенных изменениях политики. Юзер должен подтвердить заново.
- Composite index `(user_id, revoked_at)` — для быстрого «есть ли активное согласие».

### Удаление — двухфазное

**Phase 1 (`request_account_deletion`):**
- `User.is_active = 0`, `deletion_requested_at = now()`
- `revoked_at = now()` для всех активных `pd_consents`
- `BrokerConnection.api_token = "REVOKED_BY_USER_DELETION"`, `is_active = 0` — **сразу**, не ждём 30 дней (это доступ к чужим деньгам)
- Cookies сбрасываются (`clear_auth_cookies`)

**Phase 2 (`finalize_deletion`, через 30 дней, scheduler-triggered):**
- `User.email = "deleted-{id}@anon.eqio"`, остальные ПД-поля → NULL
- `Trade.notes/screenshot_url/entry_reason/exit_reason/news_event/ai_analysis` → NULL (свободный текст пользователя)
- `DailyReview.reflection/intention/trade_reflections` → NULL
- **Не трогаем:** `Payment.card_last4/external_id` (402-ФЗ — бухучёт хранится 4 года), агрегатные числовые поля Trade (для статистики)

**Restore:**
- `restore_account()` возможно пока `now() < deletion_requested_at + 30 дней`. После — невозможно (Phase 2 необратима).

## Последствия

**Плюсы:**
- Полная доказательная база для РКН (версия + IP + UA + timestamp)
- Право на «передумать» в течение grace period
- Брокерские токены не утекают если юзер захотел удалиться
- Бухучёт (Payment) сохраняется как требует 402-ФЗ

**Минусы / риски:**
- `finalize_deletion` должна вызываться регулярно — нужен scheduler (пока не подключён, ручной запуск через `pd_deletion.run_pending_deletions(db)`)
- Версия политики `v1` хардкодится в коде регистрации — при смене версии нужно менять и UI (текст чекбокса), и backend, и `policy-versions.md`

## Поведенческие правила

1. **Менять текст политики `/privacy` → инкрементировать версию.** В коде это два места: `consent_text_version` в `routers/auth.py:register` и frontend-чекбокс «(версия v1)».
2. **Никогда не делать UPDATE на pd_consents.** Только INSERT новых, UPDATE только для `revoked_at`.
3. **Никогда не удалять Payment.** Это нарушение 402-ФЗ.
4. **Все mutating endpoints касающиеся ПД** должны проверять `user.deletion_requested_at IS NULL` (юзер не должен мутировать свой данные после запроса на удаление).

## Связанные ADR

- Будущий ADR-0005 «Scheduler для finalize_deletion» — когда подключим Celery / cron
