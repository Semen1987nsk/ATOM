"""
Reset Broker Account — полностью очищает sync-данные для одного аккаунта,
чтобы следующий sync прошёл с пустого cursor'а и перестроил всё с нуля
по актуальной логике.

ЦЕЛЬ: Когда меняется логика записи (например, после фикса Trade.symbol
с FIGI на ticker), существующие 336 сделок в БД остаются с протухшими
данными. Этот скрипт сбрасывает их и готовит к full re-sync.

ИСПОЛЬЗОВАНИЕ:

    cd backend
    python -m tools.reset_broker_account --account-id 1

    # или с подтверждением
    python -m tools.reset_broker_account --account-id 1 --yes

ЧТО ДЕЛАЕТ:
1. DELETE trades WHERE account_id = ? AND data_source = 'tinkoff_v2'
   (legacy и ручные сделки не трогаем — они не sync-данные)
2. DELETE positions WHERE account_id = ?
3. DELETE operations WHERE account_id = ?
4. UPDATE broker_connections SET sync_cursor = NULL,
                                  consecutive_failures = 0,
                                  circuit_open_until = NULL,
                                  total_synced_trades = 0
   WHERE account_id = ?

После этого скрипта следующий sync будет full (cursor пуст).
"""

from __future__ import annotations

import argparse
import sys

# Делаем backend импортируемым когда скрипт запускается как `python -m tools.x`.
# Без этого `import models` упадёт.
from database import SessionLocal
from logger import get_logger
from models import (
    BrokerConnection,
    OperationORM,
    PositionORM,
    Trade,
)

log = get_logger("reset_broker_account")


def reset_account(account_id: int, *, confirmed: bool = False) -> dict[str, int]:
    """
    Возвращает словарь со счётчиками удалённого/обновлённого.
    """
    if not confirmed:
        # Print to stderr so it doesn't pollute --save-report stdout pipelines.
        print(
            f"⚠ Reset account_id={account_id} удалит все Tinkoff-sync данные.\n"
            f"  - trades (data_source='tinkoff_v2')\n"
            f"  - positions\n"
            f"  - operations\n"
            f"  - sync_cursor → NULL (следующий sync будет full)\n\n"
            f"  Для подтверждения добавьте --yes или нажмите Ctrl-C для отмены.",
            file=sys.stderr,
        )
        try:
            input("Продолжить? Введите 'yes' и Enter: ")
        except (EOFError, KeyboardInterrupt):
            print("\nОтменено.", file=sys.stderr)
            sys.exit(1)

    session = SessionLocal()
    try:
        # 1. Trades — только sync-данные, не трогаем legacy/manual.
        trades_deleted = (
            session.query(Trade)
            .filter(Trade.account_id == account_id, Trade.data_source == "tinkoff_v2")
            .delete(synchronize_session=False)
        )

        # 2. Positions — все, т.к. это исключительно sync-данные.
        positions_deleted = (
            session.query(PositionORM)
            .filter(PositionORM.account_id == account_id)
            .delete(synchronize_session=False)
        )

        # 3. Operations — все, т.к. вся таблица — sync-данные.
        operations_deleted = (
            session.query(OperationORM)
            .filter(OperationORM.account_id == account_id)
            .delete(synchronize_session=False)
        )

        # 4. BrokerConnection: обнулить cursor и circuit-breaker.
        broker_connections_updated = (
            session.query(BrokerConnection)
            .filter(BrokerConnection.account_id == account_id)
            .update(
                {
                    "sync_cursor": None,
                    "consecutive_failures": 0,
                    "circuit_open_until": None,
                    "total_synced_trades": 0,
                    "last_sync_status": None,
                    "last_sync_error": None,
                },
                synchronize_session=False,
            )
        )

        session.commit()

        result = {
            "trades_deleted": trades_deleted,
            "positions_deleted": positions_deleted,
            "operations_deleted": operations_deleted,
            "broker_connections_updated": broker_connections_updated,
        }
        log.info("Reset account %d: %s", account_id, result)
        return result
    except Exception:
        session.rollback()
        log.exception("Reset failed for account_id=%d", account_id)
        raise
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset all Tinkoff sync data for one account."
    )
    parser.add_argument("--account-id", type=int, required=True, help="Account ID")
    parser.add_argument(
        "--yes", "-y", action="store_true", help="Не запрашивать подтверждение"
    )
    args = parser.parse_args()

    result = reset_account(args.account_id, confirmed=args.yes)

    print(
        f"OK: account {args.account_id} reset, ready for full re-sync.\n"
        f"  trades_deleted: {result['trades_deleted']}\n"
        f"  positions_deleted: {result['positions_deleted']}\n"
        f"  operations_deleted: {result['operations_deleted']}\n"
        f"  broker_connections_updated: {result['broker_connections_updated']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
