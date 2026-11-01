# Order confirmations can't get an SMS channel or a fast test suite

**Reported by:** the notifications team and the storefront on-call rota
**Component:** `orders`

## Symptom

Two pieces of work are stuck on the same module:

1. Marketing wants confirmations by SMS as well as email. The SMS provider's client is ready, but
   there is nowhere to plug it in: `orders/service.py` imports `SmtpNotifier` and constructs it
   inside `confirm`.
2. The checkout team's tests take minutes because every `OrderService` test writes a SQLite file
   and an outbox file. They asked for an in-memory setup and were told "the service builds its own
   store, there's nothing to swap".

Both teams have proposed copy-pasting `OrderService`. We would rather fix the shape of the module.

## Reproduction

```python
from orders.service import OrderService

OrderService("orders.db", "outbox.jsonl")   # the only way to build one
```

Open `src/orders/service.py`: it imports `orders.sqlite_store` and `orders.smtp_gateway` directly
and instantiates both on every call.

## Expected

- `src/orders/ports.py` defines two `typing.Protocol`s, decorated `@runtime_checkable`:
  `OrderRepository` (`save_confirmed(order)`, `get(order_id)`) and `Notifier`
  (`send(to, subject, body)`).
- `OrderService` takes its collaborators by keyword: `OrderService(repository=..., notifier=...)`.
  It no longer accepts paths and no longer imports `orders.sqlite_store`, `orders.smtp_gateway`,
  `sqlite3` or `smtplib`.
- `SqliteOrderRepository` and `SmtpNotifier` keep their names and behaviour and satisfy the ports.
- `orders.app.build_service(db_path, outbox)` is the one place that wires the real adapters, so
  the existing end-to-end tests keep passing unchanged.
- The confirmation message format, the empty-order rejection and `find` behave exactly as before.

## Notes

- This is a refactor: no behaviour change is wanted. Visible tests go through `build_service` and
  must stay green throughout.
- Add a test that builds `OrderService` with in-memory fakes and checks a confirmation end to end,
  without touching the filesystem.
- Run `pgnd check` from the session workspace to check your changes in Docker.
- You may use your own editor and AI tools. The goal is a module whose boundaries are explicit,
  not merely tests that pass.
