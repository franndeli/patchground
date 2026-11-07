import { expect, test } from "vitest";
import { UnknownCarrierError, UnsupportedShipmentError } from "../src/errors";
import { availableCarriers, quote } from "../src/quotes";

const small = { weightGrams: 1500, destination: "NL", express: false };
const expressDe = { weightGrams: 12_500, destination: "DE", express: true };
const heavy = { weightGrams: 25_000, destination: "FR", express: false };

test("prices a small domestic parcel with every carrier", () => {
  expect([quote(small, "postnl"), quote(small, "dhl"), quote(small, "ups")]).toEqual([695, 1500, 1230]);
});

test("lists carriers that can ship, cheapest first", () => {
  expect(availableCarriers(small)).toEqual(["postnl", "ups", "dhl"]);
  expect(availableCarriers(expressDe)).toEqual(["ups", "dhl"]);
  expect(availableCarriers(heavy)).toEqual(["dhl"]);
});

test("express and international surcharges", () => {
  expect(quote(expressDe, "dhl")).toBe(4725);
  expect(quote(expressDe, "ups")).toBe(4550);
});

test("unknown carriers and unsupported parcels are different errors", () => {
  expect(() => quote(small, "fedex")).toThrow(UnknownCarrierError);
  expect(() => quote(heavy, "ups")).toThrow(UnsupportedShipmentError);
  expect(() => quote({ ...small, weightGrams: 0 }, "dhl")).toThrow(RangeError);
});
