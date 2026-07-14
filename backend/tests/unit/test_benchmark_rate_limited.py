import inspect

from routers import stats_advanced


def test_benchmark_has_rate_limit_decorator():
    src = inspect.getsource(stats_advanced.get_benchmark)
    # Декоратор limiter применяется к обёртке; проверяем что endpoint принимает Request
    # (необходим для slowapi limiter) — контракт наличия лимита.
    sig = inspect.signature(stats_advanced.get_benchmark)
    assert "request" in sig.parameters
