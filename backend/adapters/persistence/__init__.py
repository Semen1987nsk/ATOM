"""
Async SQLAlchemy репозитории. Реализуют Protocol-интерфейсы из
`domain.repositories`. Используют `pg_insert(...).on_conflict_do_update(...)`
для идемпотентного UPSERT (см. PR 5).
"""
