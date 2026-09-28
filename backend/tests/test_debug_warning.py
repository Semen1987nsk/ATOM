"""API-12: boot-time WARNING when DEBUG=true."""
import logging


def _capture_atom_warnings(caplog, fn):
    """`atom` logger has propagate=False (logger.py) → caplog's root handler
    never sees its records. Attach caplog's handler directly to `atom`."""
    atom_logger = logging.getLogger("atom")
    atom_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger="atom"):
            fn()
    finally:
        atom_logger.removeHandler(caplog.handler)


def test_debug_true_logs_warning(monkeypatch, caplog):
    import main

    monkeypatch.setattr(main.settings, "DEBUG", True)
    _capture_atom_warnings(caplog, main._warn_if_debug)
    assert any("DEBUG" in r.message for r in caplog.records)


def test_debug_false_no_warning(monkeypatch, caplog):
    import main

    monkeypatch.setattr(main.settings, "DEBUG", False)
    _capture_atom_warnings(caplog, main._warn_if_debug)
    assert not any("DEBUG" in r.message for r in caplog.records)
