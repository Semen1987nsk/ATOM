"""API-03: SlowAPIMiddleware must be wired so default_limits gate undecorated routes."""
import main


def test_slowapi_middleware_registered():
    assert any("SlowAPI" in str(m.cls) for m in main.app.user_middleware)


def test_probe_routes_exempt_from_default_limit():
    """Liveness/readiness/root probes must be exempt from the default read limit
    so orchestrator probes aren't throttled."""
    from rate_limiter import limiter

    exempt = limiter._exempt_routes
    assert "main.read_root" in exempt
    assert "main.health_check" in exempt
    assert "main.readiness_check" in exempt
