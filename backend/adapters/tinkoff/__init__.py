"""
Tinkoff Invest API adapter — единственное место, где приложение знает о gRPC SDK.

Транспорт: официальный пакет `tinkoff-investments` (Tinkoff/invest-python),
endpoints invest-public-api.tinkoff.ru:443 (prod) / sandbox-invest-public-api.tinkoff.ru:443.

Внешний интерфейс — domain-сущности (Operation, Trade, Instrument). Конвертация
из protobuf происходит в `proto_to_domain.py`.
"""
