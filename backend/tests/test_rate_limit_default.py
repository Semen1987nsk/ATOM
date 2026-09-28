"""API-03: limiter несёт дефолтный read-rate-limit на все роуты.

slowapi 0.1.9 хранит дефолты в `limiter._default_limits` как список
`LimitGroup`-объектов. Каждый раскрывается в `Limit`-объекты, чей
`.limit` сравним через `limits.parse(...)` (str-форма "120 per 1 minute"),
поэтому ассерт не зависит от формата исходной строки.
"""

from limits import parse


def test_limiter_has_default_read_limit():
    from rate_limiter import limiter
    from config import settings

    default_groups = getattr(limiter, "_default_limits", [])
    assert default_groups, "limiter has no default_limits configured"

    parsed_defaults = [item.limit for group in default_groups for item in group]
    expected = parse(settings.READ_RATE_LIMIT)
    assert any(str(d) == str(expected) for d in parsed_defaults)
