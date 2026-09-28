"""
Синхронизация с брокером. Polling-режим с `OperationsByCursor`.

- `orchestrator.py`       — bulkhead, fair queue, scheduling.
- `pipeline.py`           — fetch → enrich → fifo → upsert → events.
- `adaptive_interval.py`  — 5/15/60 мин по активности пользователя.
"""
