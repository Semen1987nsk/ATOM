"""
Дампит openapi.json без запуска сервера.

Использование:
    cd backend && python scripts/dump_openapi.py > openapi.json

Затем во фронте:
    cd frontend && npm run gen:api-types:from-file

Или одной командой через GitHub Actions / pre-commit (см. CI yaml).
"""
import json
import os
import sys

# Тестовые ENV — иначе fail-fast в config.py
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "dump-only-not-a-secret-1234567890abcdef")
os.environ.setdefault("REFRESH_SECRET_KEY", "dump-only-not-a-secret-fedcba0987654321")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402  (импорт после env override)


def dump_to_stdout() -> None:
    schema = app.openapi()
    json.dump(schema, sys.stdout, ensure_ascii=False, indent=2, default=str)


if __name__ == "__main__":
    dump_to_stdout()
