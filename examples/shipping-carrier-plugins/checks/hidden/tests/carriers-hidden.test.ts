import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import type { Carrier } from "../src/carrier";
import { UnknownCarrierError, UnsupportedShipmentError } from "../src/errors";
import { availableCarriers, quote } from "../src/quotes";

// Loaded per test so a missing module fails the tests that need it, not the whole file.
const plugins = async () => ({
  createQuoter: (await import("../src/quoter")).createQuoter,
  postnl: (await import("../src/carriers/postnl")).postnl,
  dhl: (await import("../src/carriers/dhl")).dhl,
  ups: (await import("../src/carriers/ups")).ups,
});

const source = (file: string) => readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8");
const small = { weightGrams: 1500, destination: "NL", express: false };
const bike: Carrier = {
  id: "bike",
  supports: (s) => s.destination === "NL" && s.weightGrams <= 5000 && !s.express,
  price: () => 500,
};

test("hidden a new carrier plugs in without editing the quoter", async () => {
  const { createQuoter, postnl } = await plugins();
  const quoter = createQuoter([postnl, bike]);
  expect(quoter.quote(small, "bike")).toBe(500);
  expect(quoter.availableCarriers(small)).toEqual(["bike", "postnl"]);
  expect(quoter.availableCarriers({ ...small, destination: "BE" })).toEqual(["postnl"]);
  expect(() => quoter.quote(small, "ups")).toThrow(UnknownCarrierError);
  expect(() => quoter.quote({ ...small, weightGrams: 9000 }, "bike")).toThrow(UnsupportedShipmentError);
});

test("hidden the quoter knows no carrier by name", () => {
  const quoter = source("quoter.ts");
  expect(quoter).not.toMatch(/postnl|dhl|ups/i);
  expect(quoter).not.toMatch(/from\s+["']\.\/carriers/);
  expect(quoter).not.toMatch(/\bswitch\s*\(/);
});

test("hidden each carrier owns its own rules", async () => {
  const { postnl, dhl, ups } = await plugins();
  const heavyDe = { weightGrams: 12_500, destination: "DE", express: true };
  expect([postnl.id, dhl.id, ups.id]).toEqual(["postnl", "dhl", "ups"]);
  expect([postnl.price(small), dhl.price(small), ups.price(small)]).toEqual([695, 1500, 1230]);
  expect([postnl.supports(heavyDe), dhl.supports(heavyDe), ups.supports(heavyDe)]).toEqual([false, true, true]);
  expect([dhl.price(heavyDe), ups.price(heavyDe)]).toEqual([4725, 4550]);
  for (const file of ["carriers/postnl.ts", "carriers/dhl.ts", "carriers/ups.ts"]) {
    expect(source(file)).not.toMatch(/from\s+["']\.\.\/(quoter|quotes)["']/);
  }
});

test("hidden ties are broken by carrier id and validation still runs first", async () => {
  const { createQuoter } = await plugins();
  const flat = (id: string): Carrier => ({ id, supports: () => true, price: () => 700 });
  const quoter = createQuoter([flat("zed"), flat("amp"), flat("mid")]);
  expect(quoter.availableCarriers(small)).toEqual(["amp", "mid", "zed"]);
  expect(() => quoter.availableCarriers({ ...small, weightGrams: -1 })).toThrow(RangeError);
  expect(() => quoter.quote({ ...small, weightGrams: 1.5 }, "amp")).toThrow(RangeError);
});

test("hidden duplicate ids are rejected and the quoter keeps its own copy", async () => {
  const { createQuoter, postnl } = await plugins();
  expect(() => createQuoter([bike, { ...bike }])).toThrow(/bike/);
  const list: Carrier[] = [bike];
  const quoter = createQuoter(list);
  list.push(postnl);
  expect(quoter.availableCarriers(small)).toEqual(["bike"]);
});

test("hidden the public functions delegate to a quoter of the three carriers", () => {
  const quotes = source("quotes.ts");
  expect(quotes).not.toMatch(/\bswitch\s*\(/);
  expect(quotes).toMatch(/createQuoter\s*\(/);
  expect(availableCarriers({ weightGrams: 25_000, destination: "FR", express: false })).toEqual(["dhl"]);
  expect(quote({ weightGrams: 3001, destination: "BE", express: false }, "postnl")).toBe(895);
  expect(() => quote(small, "fedex")).toThrow(UnknownCarrierError);
});
