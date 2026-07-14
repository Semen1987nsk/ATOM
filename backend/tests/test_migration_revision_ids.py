"""
S1-02: alembic_version.version_num — VARCHAR(32) (Postgres enforce'ит строго,
SQLite нет — потому баг не ловился в dev). Revision id длиннее 32 символов
роняет `alembic upgrade head` на проде с `22001 value too long`.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

VERSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic", "versions")

MAX_REVISION_LEN = 32

_REVISION_RE = re.compile(r'^revision\s*:\s*str\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def _iter_revision_ids():
    for name in sorted(os.listdir(VERSIONS_DIR)):
        if not name.endswith(".py") or name == "__init__.py":
            continue
        path = os.path.join(VERSIONS_DIR, name)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        match = _REVISION_RE.search(content)
        assert match, f"{name}: не найден `revision: str = ...`"
        yield name, match.group(1)


def test_all_migration_revision_ids_fit_varchar_32():
    """alembic_version.version_num создаётся как String(32) — Postgres enforce'ит строго."""
    violations = [
        (name, rev, len(rev))
        for name, rev in _iter_revision_ids()
        if len(rev) > MAX_REVISION_LEN
    ]
    assert not violations, (
        f"revision id(s) длиннее {MAX_REVISION_LEN} символов "
        f"(упадёт на Postgres alembic_version VARCHAR(32)): {violations}"
    )


def test_0023_revision_id_renamed():
    """S1-02: старый id 0023_position_authoritative_fields (34 симв.) не используется."""
    ids = dict(_iter_revision_ids())
    assert "0023_position_authoritative_fields" not in ids.values()
