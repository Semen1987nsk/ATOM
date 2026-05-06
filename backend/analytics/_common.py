"""
Общие хелперы для analytics-пакета.
"""
import math
from decimal import Decimal

# Sentinel для случая, когда метрика математически неопределена (нет убытков и т.п.).
# Возвращаем None — фронт явно отображает «—» вместо магического 99.99.
UNDEFINED = None


def _sanitize(value):
    """Превращает NaN/±Inf в None, иначе возвращает float со стабильным округлением."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f
