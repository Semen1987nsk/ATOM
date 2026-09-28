"""SEC: IDOR на скриншоты сделок через публичный static-mount `/uploads`.

Раньше `main.py` монтировал `app.mount("/uploads", StaticFiles(...))`, отдавая
любой файл под `uploads/screenshots/<uuid>.png` БЕЗ проверки ownership — любой,
кто угадал/перебрал UUID-имя, читал чужой скриншот (security through obscurity).

Скриншоты теперь отдаёт authenticated-эндпоинт `GET /trades/{id}/screenshot`
с проверкой account ownership. Публичный static-mount должен быть удалён.

Тест кладёт реальный файл в `uploads/screenshots/` и проверяет, что GET по
static-пути возвращает 404 — это отличает «mount удалён» от «файла нет на диске»
(StaticFiles вернул бы 404 и для отсутствующего файла).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

from fastapi.testclient import TestClient

from main import app

UPLOAD_DIR = Path("uploads/screenshots")


def test_static_uploads_screenshot_returns_404():
    """Реальный файл под uploads/screenshots/ НЕ должен отдаваться по /uploads/...

    Кладём настоящий PNG-байтстрим на диск, затем дёргаем static-путь. Если
    публичный mount всё ещё жив — StaticFiles вернёт 200 + содержимое (IDOR).
    После удаления mount маршрут не зарегистрирован → 404.
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    fname = "idor_probe_whatever.png"
    fpath = UPLOAD_DIR / fname
    # Минимальный валидный PNG-сигнатурный заголовок — чтобы файл реально лежал.
    fpath.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    try:
        client = TestClient(app)
        resp = client.get(f"/uploads/screenshots/{fname}")
        assert resp.status_code == 404, (
            f"Публичный static-mount /uploads всё ещё отдаёт скриншоты "
            f"(IDOR): статус {resp.status_code}, тело={resp.content[:32]!r}"
        )
    finally:
        try:
            fpath.unlink()
        except FileNotFoundError:
            pass
