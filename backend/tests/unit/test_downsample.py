"""Unit-тесты для utils.downsample.lttb — PERF-10.

Проверяем: thresholding, passthrough при коротком ряде, сохранение
краёв (первая+последняя), монотонность по X.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from utils.downsample import lttb


def test_lttb_returns_threshold_points():
    pts = [(float(i), float(i * i)) for i in range(1000)]
    out = lttb(pts, 100)
    assert len(out) == 100
    assert out[0] == pts[0]
    assert out[-1] == pts[-1]


def test_lttb_passthrough_when_below_threshold():
    pts = [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]
    assert lttb(pts, 100) == pts


def test_lttb_handles_threshold_below_three():
    pts = [(float(i), float(i)) for i in range(10)]
    assert lttb(pts, 2) == pts
    assert lttb(pts, 0) == pts


def test_lttb_handles_threshold_equal_n():
    pts = [(float(i), float(i)) for i in range(50)]
    assert lttb(pts, 50) == pts


def test_lttb_monotonic_x_preserved():
    """LTTB должен сохранять порядок по X (выбирает по индексу из buckets)."""
    pts = [(float(i), float(i % 17 * 13 - 50)) for i in range(500)]
    out = lttb(pts, 50)
    xs = [p[0] for p in out]
    assert xs == sorted(xs), "X-координаты должны идти возрастающе"


def test_lttb_preserves_endpoints_on_volatile_series():
    """Шумный ряд: первая и последняя сохраняются, длина = threshold."""
    pts = [(float(i), float((i * 7919) % 1000)) for i in range(800)]
    out = lttb(pts, 250)
    assert len(out) == 250
    assert out[0] == pts[0]
    assert out[-1] == pts[-1]


def test_lttb_handles_empty_input():
    """Пустой ряд → пустой выход, без падения."""
    assert lttb([], 100) == []


def test_lttb_threshold_three_minimal():
    """threshold=3 — минимально допустимый: первая + одна из middle + последняя."""
    pts = [(float(i), float(i)) for i in range(100)]
    out = lttb(pts, 3)
    assert len(out) == 3
    assert out[0] == pts[0]
    assert out[-1] == pts[-1]
