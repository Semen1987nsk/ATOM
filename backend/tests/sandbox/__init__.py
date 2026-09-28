"""
Sandbox-тесты против реального T-Invest sandbox API (PR 14).

Все тесты skip-able без env-переменной `TINKOFF_SANDBOX_TOKEN_TEST`.
Запуск: `pytest backend/tests/sandbox/ -v`.

Sandbox-токен создаётся в lk.tbank.ru → Инвестиции → API → Sandbox token.
Endpoint: `sandbox-invest-public-api.tinkoff.ru:443`.
"""
