"""LTTB (Largest-Triangle-Three-Buckets) downsample для equity_curve.

Сохраняет визуальную форму ряда при сжатии до N точек. Используется в
`/stats/` чтобы не отдавать 5000+ точек JSON фронту при ~5000 трейдов.

Алгоритм: Steinarsson, 2013. Делит ряд на N бакетов, в каждом выбирает
точку, образующую наибольший треугольник с предыдущей выбранной точкой
и средней точкой следующего бакета. Первая и последняя точки сохраняются
всегда.
"""
from __future__ import annotations
from typing import Sequence


def lttb(points: Sequence[tuple[float, float]], threshold: int) -> list[tuple[float, float]]:
    """Сжать ряд (x, y) точек до `threshold` точек методом LTTB.

    Args:
        points: исходный ряд [(x0, y0), (x1, y1), ...].
        threshold: целевое число точек на выходе (>= 3).

    Returns:
        Список выбранных точек длиной ровно `threshold`, либо исходный
        ряд если threshold >= len(points) или threshold < 3.

    Inv: первая и последняя точки исходного ряда сохраняются.
    """
    n = len(points)
    if threshold >= n or threshold < 3:
        return list(points)
    bucket_size = (n - 2) / (threshold - 2)
    out: list[tuple[float, float]] = [points[0]]
    a = 0
    for i in range(threshold - 2):
        avg_start = int((i + 1) * bucket_size) + 1
        avg_end = int((i + 2) * bucket_size) + 1
        avg_end = min(avg_end, n)
        if avg_end <= avg_start:
            continue
        avg_x = sum(p[0] for p in points[avg_start:avg_end]) / (avg_end - avg_start)
        avg_y = sum(p[1] for p in points[avg_start:avg_end]) / (avg_end - avg_start)
        range_start = int(i * bucket_size) + 1
        range_end = int((i + 1) * bucket_size) + 1
        max_area = -1.0
        chosen = points[range_start]
        chosen_idx = range_start
        ax, ay = points[a]
        for j in range(range_start, min(range_end, n)):
            p = points[j]
            area = abs((ax - avg_x) * (p[1] - ay) - (ax - p[0]) * (avg_y - ay)) * 0.5
            if area > max_area:
                max_area = area
                chosen = p
                chosen_idx = j
        out.append(chosen)
        a = chosen_idx
    out.append(points[-1])
    return out
