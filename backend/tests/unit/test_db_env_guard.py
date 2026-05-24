"""PERF-01: в проде (DEBUG=false) SQLite запрещён — только Postgres.
Гард — чистая функция, чтобы тестировать без import-time эффектов."""
from __future__ import annotations

import pytest

from database import _assert_db_safe_for_env


def test_sqlite_in_prod_raises():
    with pytest.raises(RuntimeError, match="SQLite"):
        _assert_db_safe_for_env("sqlite:///./atom.db", debug=False)


def test_sqlite_in_debug_ok():
    _assert_db_safe_for_env("sqlite:///./atom.db", debug=True)  # no raise


def test_postgres_in_prod_ok():
    _assert_db_safe_for_env("postgresql://u:p@h/db", debug=False)  # no raise
