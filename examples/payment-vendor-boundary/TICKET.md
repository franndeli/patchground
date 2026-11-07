# A Paysafe SDK upgrade would touch every billing rule

**Reported by:** the billing team, ahead of the Paysafe SDK 3.0 migration
**Component:** `billing`

## Symptom

Paysafe announced SDK 3.0: response codes become strings like `"approved"`, timestamps become
ISO strings and `PsTimeout` is renamed. We estimated the upgrade and found the SDK everywhere:

- `billing/invoices.py` imports `PsResponse` and `PsTimeout`, compares raw codes such as `"51"`
  and converts `ts_ms` itself.
- `Invoice` stores the vendor's `PsResponse` in `last_response`.
- `billing/dunning.py` reads `invoice.last_response.rc` to choose the reminder email.

We also want to add a second provider next year. Today that means a second copy of every rule.

## Reproduction

Search `src/billing/` for `paysafe`, `rc`, `ts_ms` and `last_response`.

## Expected

Put an anti-corruption layer between billing and the vendor:

- `src/billing/payments.py` is billing's port, in billing's terms. It defines `Outcome`
  (`APPROVED`, `DECLINED`, `RETRY`), `Reason`, a `StrEnum` whose values are today's wording
  (`card declined`, `insufficient funds`, `issuer unavailable`, `gateway timeout`) with members
  `CARD_DECLINED`, `INSUFFICIENT_FUNDS`, `ISSUER_UNAVAILABLE` and `GATEWAY_TIMEOUT`, and
  a frozen dataclass `PaymentResult(outcome, reason, reference, paid_at)`. It also defines
  `PaymentGatewayError(RuntimeError)` and a `@runtime_checkable` `Protocol` called
  `PaymentGateway` with `charge(invoice_id, amount_cents, currency) -> PaymentResult`.
- `src/billing/paysafe_gateway.py` defines `PaysafeGateway(client)`, the only billing module
  that speaks Paysafe apart from the composition root. It maps every code and the timeout to a
  `PaymentResult`, converts `ts_ms` to an aware UTC `datetime`, and raises `PaymentGatewayError`
  for unknown codes or a charged amount or currency that does not match the request.
- `InvoiceService(gateway)` depends only on the port. `Invoice` loses `last_response`. Every
  other field and every outcome stays the same.
- Dunning decides from billing's own data.
- `billing.app.build_invoice_service(client)` is the composition root that wires the adapter in.
  The visible tests use it and must pass unchanged.

## Notes

- `src/paysafe/` is vendored third-party code: do not edit it.
- This is an architecture change: no outcome, wording or error class may change for callers.
- Add a test that collects an invoice through `InvoiceService` with a fake gateway and no SDK.
- Run `pgnd check` from the session workspace to check your changes in Docker.
- You may use your own editor and AI tools. The goal is a domain that would survive SDK 3.0
  unchanged, not merely tests that pass.
