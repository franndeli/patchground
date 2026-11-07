# Adding a shipping carrier means editing the quote engine

**Reported by:** the checkout team
**Component:** shipping quotes (`src/quotes.ts`)

## Symptom

We have signed with two regional couriers and a bike courier for same-city deliveries. Each one
needs a change inside `src/quotes.ts`: a new case in `supports`, a new case in `price` and a new
entry in `CARRIERS`. The last carrier added this way broke DHL's express rounding because the
cases share local variables, and every carrier change needs a review of the whole engine.

We want carriers to be plug-ins: the engine stays closed, and a carrier is added by writing one
new module and registering it.

## Reproduction

Open `src/quotes.ts`. Carrier rules are spread across two `switch` statements and a hardcoded
list. There is no way to quote with a carrier that is not in that file.

## Expected

- `src/carrier.ts` exports `interface Carrier { readonly id: string; supports(shipment): boolean;
  price(shipment): number }`. Prices are integer cents.
- `src/carriers/postnl.ts`, `src/carriers/dhl.ts` and `src/carriers/ups.ts` export `postnl`,
  `dhl` and `ups`: `Carrier` objects that hold today's rules for that carrier.
- `src/quoter.ts` exports `createQuoter(carriers)`, returning `{ quote(shipment, carrierId),
  availableCarriers(shipment) }` with today's semantics: validation first (`RangeError`),
  `UnknownCarrierError` for an id it was not given, `UnsupportedShipmentError` for a parcel the
  carrier refuses, and cheapest-first ordering with ties broken by id.
- The quoter names no carrier and imports nothing from `src/carriers/`. Two carriers with the same
  id are rejected when the quoter is created. Changing the array passed to `createQuoter`
  afterwards does not change that quoter.
- `quote` and `availableCarriers` in `src/quotes.ts` keep their signatures and results; they use
  a quoter built from the three existing carriers.

## Notes

- This is an architecture change: no price changes. The visible tests pin today's results.
- Add a test that registers a carrier defined in the test itself.
- Run `pgnd check` from the session workspace to check your changes in Docker.
- You may use your own editor and AI tools. The goal is an engine that is closed for modification
  and open for new carriers, not merely tests that pass.
