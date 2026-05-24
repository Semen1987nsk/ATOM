"""
PR 26 — Regression test: Tinkoff API tokens MUST NEVER be logged in plain text.

Сканирует все source файлы backend на:
1. Прямые f-string логи токенов: `log.info(f"token={token}")`
2. Конкатенацию: `log.info("token: " + token)`
3. Любые `log.X(...)` где буквальная строка содержит `t.` префикс Tinkoff
   tokens (формат `t.<20+ base64-like chars>`).

Failures указывают на потенциальное leak'а — даже если сейчас никто
не вызывает этот код в проде, при ошибке/inactive ветке токен попадёт
в логи на диск или в Sentry.

Что РАЗРЕШЕНО:
- `log.X(..., mask_token(t))` — маскированные токены OK
- `log.X("token_id=%s", t)` — log_token_id, не сам токен
- Комментарии (всё что после `#`)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
SCAN_DIRS = ["adapters", "application", "routers", "services", "tools"]

# Pattern: реальный Tinkoff token format `t.<base64-like>{30+}` И содержит
# хотя бы один digit/dash/underscore (отсечь обычные python identifiers
# типа `trade.holding_time_minutes` где `t.` тоже длинный).
# Реальный Tinkoff token — 80+ символов, signature base64url.
TINKOFF_TOKEN_PATTERN = re.compile(r"\bt\.(?=[A-Za-z0-9_-]{30,})(?=[A-Za-z0-9_-]*[\d_\-])[A-Za-z0-9_-]+")

# Подозрительные паттерны в log statements.
# Эти подстроки в одной строке с `log.X(` сигнализируют о потенциальном leak.
SUSPICIOUS_IN_LOG = [
    re.compile(r"\btoken\b\s*[=:]"),  # f"token=...", f"token: ..."
    re.compile(r"\baccess_token\b"),
    re.compile(r"\bapi_token\b"),
    re.compile(r"\brefresh_token\b"),
    re.compile(r"\bbearer\b", re.IGNORECASE),
]

# Allowlist substrings — если строка содержит, считаем безопасной.
ALLOWLIST_SUBSTRINGS = [
    "mask_token",
    "token_id",
    "operation_id",
    "broker_account_id",
    "redacted",
    "no token",
    "without token",
    "missing token",
    "csrf_token",  # CSRF tokens NOT tinkoff API tokens
    "reset_token",  # password reset, not Tinkoff
    "next_cursor",  # cursor != token, but loose match
    "[redacted]",
    "***",
    "OBFUSCATED",
    "MASKED",
]


def _collect_py_files() -> list[Path]:
    files: list[Path] = []
    for d in SCAN_DIRS:
        root = BACKEND_ROOT / d
        if not root.exists():
            continue
        files.extend(root.rglob("*.py"))
    return files


def _strip_comment(line: str) -> str:
    """Грубо удаляем комментарии (всё после `#`)."""
    if "#" in line:
        # Не убираем `#` внутри строк — но для grep этого достаточно.
        # Истинно правильный подход — AST parse, но для регрессионного теста ОК.
        return line.split("#", 1)[0]
    return line


def _is_log_call(line: str) -> bool:
    """Содержит ли строка вызов logger?"""
    return bool(re.search(r"\b(log|logger|logging)\.(debug|info|warning|warn|error|exception|critical)\s*\(", line))


@pytest.mark.parametrize("py_file", _collect_py_files(), ids=lambda f: str(f.relative_to(BACKEND_ROOT)))
def test_no_tinkoff_token_in_logs(py_file: Path) -> None:
    """Каждый .py файл в проде-коде не должен логировать токены plain-text."""
    if not py_file.is_file():
        return
    text = py_file.read_text(encoding="utf-8", errors="ignore")
    issues: list[str] = []

    for idx, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw_line)
        if not line.strip():
            continue

        # Прямой Tinkoff token format в строке (не в комменте)
        if TINKOFF_TOKEN_PATTERN.search(line):
            # Внутри тестовых fixtures допускаем — fixture файлы должны быть
            # вне scan_dirs, но если кто-то поставил dummy токен в проде-коде,
            # лучше пометить.
            issues.append(f"  line {idx}: literal Tinkoff token pattern: {line.strip()[:120]}")

        # Подозрительный лог?
        if _is_log_call(line):
            line_lower = line.lower()
            if any(allow in line_lower for allow in ALLOWLIST_SUBSTRINGS):
                continue
            for pat in SUSPICIOUS_IN_LOG:
                if pat.search(line):
                    issues.append(
                        f"  line {idx}: log call with suspicious token reference: "
                        f"{line.strip()[:120]}"
                    )
                    break

    assert not issues, (
        f"\nPotential token leak in logs in file {py_file.relative_to(BACKEND_ROOT)}:\n"
        + "\n".join(issues)
        + "\n\nFix: route token through mask_token() helper or remove from log."
    )
