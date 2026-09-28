"""
Инфраструктурный слой (Hexagonal architecture). Содержит:

- `tinkoff/`     — обёртки над gRPC SDK (PR 3+).
- `persistence/` — async SQLAlchemy репозитории (PR 2+).
- `security/`    — шифрование токенов AESGCM, audit log (PR 4).

Domain не должен импортировать ничего отсюда — связь только через
Protocol-интерфейсы из `domain.repositories`.
"""
