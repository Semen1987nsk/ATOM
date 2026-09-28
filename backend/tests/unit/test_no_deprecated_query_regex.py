"""Guard: в Pydantic v2 `Query(regex=...)` deprecated и может молча не
валидировать. Должно использоваться `pattern=`. Тест ловит регрессию."""
from __future__ import annotations

import pathlib


def test_no_deprecated_query_regex():
    routers_dir = pathlib.Path(__file__).resolve().parents[2] / "routers"
    offenders: list[str] = []
    for f in sorted(routers_dir.glob("*.py")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), start=1):
            if "Query(" in line and "regex=" in line:
                offenders.append(f"{f.name}:{i}")
    assert offenders == [], (
        "Использован устаревший Query(regex=...) — заменить на pattern=:\n  "
        + "\n  ".join(offenders)
    )
