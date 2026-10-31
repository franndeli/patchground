# Duplicate charges after a payment retry

Support reproduced a checkout charging twice when the provider accepted a payment
but its response timed out. The next transport attempt returned success, so the
customer saw one successful checkout and two ledger entries.

Fix the payment flow and add a regression check. The public entry point is
`PaymentService(gateway, max_attempts=3).pay(request_id, amount_cents)` in
`src/payments/service.py`. Use the offline gateway in `src/payments/gateway.py`;
its scripted events reproduce outages without network access or sleeps.

Required behavior:
- One logical request must create at most one charge, including after a lost
  success response and when submitted again through a new service instance
  sharing the same gateway. Successful repeats return the same receipt.
- Different request IDs represent different payments even for equal amounts.
  Reusing an ID with a different amount raises `RequestConflict`.
- Retry only `GatewayTimeout`, at most `max_attempts` total calls per invocation.
  If all attempts time out, expose the final timeout. Propagate `PaymentDeclined`
  and invalid input immediately. Amounts are positive integer cents.
- Preserve the `Receipt(charge_id, amount_cents)` API and gateway semantics.

The simulator persists accepted requests only for the lifetime of its gateway
instance. Cross-process persistence, concurrent workers, real providers, backoff,
credentials and payment security are outside this exercise. Work in application
code and conventional pytest checks; keep verification configuration intact.

Run checks using Patchground's container commands. No real payments are made.
