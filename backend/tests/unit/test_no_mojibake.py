"""API-01 guard: mojibake в роутерах запрещён.

Mojibake = UTF-8-байты кириллицы, прочитанные как CP1251 («Аккаунт» →
«РђРєРєР°СѓРЅС‚»). Каждый кириллический символ в UTF-8 начинается с байта
0xD0/0xD1 (в CP1251 это «Р»/«С»), а второй байт 0x80-0xBF декодируется в
символы, которые в нормальном русском тексте после «Р»/«С» не встречаются.
Детектор: пара «Р|С» + символ из CP1251-декодинга диапазона 0x80-0xBF.
"""
import re
from pathlib import Path

ROUTERS_DIR = Path(__file__).resolve().parents[2] / "routers"


def _mojibake_pattern() -> re.Pattern:
    second_chars = []
    for b in range(0x80, 0xC0):
        try:
            second_chars.append(bytes([b]).decode("cp1251"))
        except UnicodeDecodeError:
            # 0x98 не определён в CP1251 — в mojibake-тексте его быть не может.
            continue
    return re.compile("[РС][" + re.escape("".join(second_chars)) + "]")


MOJIBAKE = _mojibake_pattern()


def test_detector_catches_known_mojibake():
    assert MOJIBAKE.search("РђРєРєР°СѓРЅС‚")
    assert MOJIBAKE.search("РђРєРєР°СѓРЅС‚ РЅРµ РЅР°Р№РґРµРЅ")
    assert MOJIBAKE.search("РЎСѓРјРјР° РїРѕРїРѕР»РЅРµРЅРёСЏ")


def test_detector_passes_clean_russian():
    clean = (
        "Аккаунт не найден. Начальный депозит установлен — счёт, Роутер, "
        "Сумма снятия должна быть положительной. Снимок баланса удалён."
    )
    assert not MOJIBAKE.search(clean)


def test_no_mojibake_in_routers():
    offenders = {}
    for path in sorted(ROUTERS_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        lines = [
            i for i, line in enumerate(text.splitlines(), start=1)
            if MOJIBAKE.search(line)
        ]
        if lines:
            offenders[path.name] = lines[:10]
    assert not offenders, f"mojibake в backend/routers: {offenders}"
