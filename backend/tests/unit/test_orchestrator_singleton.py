"""S2-16: scheduler переиспользует один orchestrator между итерациями,
а не строит новый (с новым Redis-клиентом) каждые 60с.
"""
from unittest.mock import MagicMock, patch

from sync_scheduler import SyncScheduler  # имя класса по факту файла


def test_orchestrator_built_once_across_iterations():
    sched = SyncScheduler()
    built = []

    def _factory():
        o = MagicMock()
        built.append(o)
        return o

    with patch("application.sync.orchestrator.build_default_orchestrator", _factory):
        first = sched._get_orchestrator()
        second = sched._get_orchestrator()

    assert first is second
    assert len(built) == 1
