"""Единая точка определения «singleton-воркера» для фоновых задач.

На multi-worker деплое (gunicorn --workers N) фоновые синглтоны — sync
scheduler И stream consumers — должны крутиться ровно на ОДНОМ воркере,
иначе N×gRPC-стримов мгновенно ловят IP-cooldown T-Bank. Поставьте
IS_SCHEDULER_WORKER=false на всех воркерах кроме одного.
"""
from __future__ import annotations

import os


def is_scheduler_worker() -> bool:
    return os.getenv("IS_SCHEDULER_WORKER", "true").lower() == "true"
