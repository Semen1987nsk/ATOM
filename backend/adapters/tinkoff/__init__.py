"""
Tinkoff Invest API adapter — единственное место, где приложение знает о gRPC SDK.

Транспорт: официальный пакет `t-tech-investments` (хостится на
opensource.tbank.ru/invest/invest-python). Раньше был `tinkoff-investments`
0.2.0-beta117; после ребрендинга и переезда репозитория код тот же, но
namespace переименован: `tinkoff.invest.*` → `t_tech.invest.*`. См. AU10.

Endpoints: invest-public-api.tbank.ru:443 (prod) /
sandbox-invest-public-api.tbank.ru:443 (наш override через config.py).
SDK constants всё ещё указывают на legacy `.tinkoff.ru` — это работает
(DNS-alias), но мы явно прокидываем target=.tbank.ru через AsyncClient.

Внешний интерфейс — domain-сущности (Operation, Trade, Instrument). Конвертация
из protobuf происходит в `proto_to_domain.py`.
"""
