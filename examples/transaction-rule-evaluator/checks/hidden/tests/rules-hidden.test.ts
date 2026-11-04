import { test, expect } from "vitest";
import { evaluateRules } from "../src/evaluator.js";
import { RuleValidationError } from "../src/rule-types.js";

function leaf(field: string, op: string, value: unknown) {
  return { kind: "predicate", field, op, value };
}

function errorAt(rules: unknown, tx: unknown = { amount_cents: 0, country: "CA", merchant: "book" }) {
  try {
    evaluateRules(rules, tx);
  } catch (error) {
    expect(error).toBeInstanceOf(RuleValidationError);
    if (error instanceof RuleValidationError) return { ruleId: error.ruleId, path: error.path, code: error.code };
    throw error;
  }
  throw new Error("invalid input was accepted");
}

test("numeric operators agree with independent signed integer comparisons", () => {
  for (const amount of [-101, -1, 0, 1, 101]) {
    for (const threshold of [-100, 0, 100]) {
      const rules = [
        { id: "gt", when: leaf("amount_cents", "gt", threshold) },
        { id: "eq", when: leaf("amount_cents", "eq", threshold) },
        { id: "gte", when: leaf("amount_cents", "gte", threshold) },
      ];
      const expected: string[] = [];
      if (amount > threshold) expected.push("gt");
      if (amount === threshold) expected.push("eq");
      if (amount >= threshold) expected.push("gte");
      expect(evaluateRules(rules, { amount_cents: amount, country: "CA", merchant: "book" })).toEqual(expected);
    }
  }
});

test("all string fields compare literally including code-like merchant text", () => {
  const merchant = "globalThis.shouldNeverExecute = true";
  expect(evaluateRules([
    { id: "code-is-data", when: leaf("merchant", "eq", merchant) },
    { id: "literal-membership", when: leaf("merchant", "in", ["other", merchant, merchant]) },
    { id: "case", when: leaf("country", "eq", "ca") },
    { id: "whitespace", when: leaf("country", "in", [" CA", "CA "]) },
    { id: "exact", when: leaf("country", "in", ["CA"]) },
  ], { amount_cents: 0, country: "CA", merchant })).toEqual(["code-is-data", "literal-membership", "exact"]);
});

test("nested boolean rules return all matches in caller order", () => {
  const yes = leaf("amount_cents", "gte", 0);
  const no = leaf("merchant", "eq", "");
  expect(evaluateRules([
    { id: "z-last-name", when: { kind: "any", children: [no, { kind: "all", children: [yes, { kind: "not", child: no }] }] } },
    { id: "a-first-name", when: { kind: "not", child: { kind: "not", child: yes } } },
    { id: "miss", when: { kind: "all", children: [yes, no] } },
  ], { amount_cents: 0, country: "CA", merchant: "book" })).toEqual(["z-last-name", "a-first-name"]);
});

test("invalid nodes cannot hide behind successful any or failing all branches", () => {
  const cases = [
    { kind: "any", children: [leaf("amount_cents", "eq", 0), { kind: "predicate", field: "merchant", op: "eq", value: null }] },
    { kind: "all", children: [leaf("amount_cents", "gt", 0), { kind: "predicate", field: "merchant", op: "eq", value: null }] },
  ];
  for (const when of cases) expect(errorAt([{ id: "branch", when }])).toEqual({
    ruleId: "branch", path: "rules[0].when.children[1].value", code: "validation_error",
  });
});

test("all rule records are validated even after a prior match", () => {
  const yes = leaf("country", "eq", "CA");
  expect(errorAt([{ id: "first", when: yes }, { id: "second", when: { kind: "not", child: yes, children: [] } }]))
    .toEqual({ ruleId: "second", path: "rules[1].when.children", code: "validation_error" });
});

test("rule depth is bounded on all any and not paths with precise error location", () => {
  let when: unknown = leaf("country", "eq", "CA");
  let path = "rules[0].when";
  const segments: string[] = [];
  for (let i = 0; i < 7; i += 1) {
    if (i % 3 === 0) { when = { kind: "not", child: when }; segments.unshift(".child"); }
    else { when = { kind: i % 3 === 1 ? "all" : "any", children: [when] }; segments.unshift(".children[0]"); }
  }
  expect(evaluateRules([{ id: "depth", when }], { amount_cents: 0, country: "CA", merchant: "book" })).toEqual([]);
  when = { kind: "all", children: [when] };
  path += ".children[0]" + segments.join("");
  expect(errorAt([{ id: "depth", when }])).toEqual({
    ruleId: "depth", path, code: "validation_error",
  });
});

test("extra and missing keys are rejected for every JSON node shape", () => {
  const yes = leaf("country", "eq", "CA");
  const cases = [
    { when: { ...yes, child: yes }, suffix: ".child" },
    { when: { kind: "all", children: [yes], value: 0 }, suffix: ".value" },
    { when: { kind: "any", children: [yes], op: "eq" }, suffix: ".op" },
    { when: { kind: "not", child: yes, field: "country" }, suffix: ".field" },
    { when: { kind: "all" }, suffix: ".children" },
    { when: { kind: "predicate", field: "country", value: "CA" }, suffix: ".op" },
    { when: { kind: "predicate", op: "eq", value: "CA" }, suffix: ".field" },
  ];
  for (const item of cases) expect(errorAt([{ id: "shape", when: item.when }])).toEqual({
    ruleId: "shape", path: "rules[0].when" + item.suffix, code: "validation_error",
  });
});

test("non-object and malformed child collections never coerce into nodes", () => {
  for (const when of [[], false, "true", 0]) {
    expect(errorAt([{ id: "bad", when }]).path).toBe("rules[0].when");
  }
  for (const kind of ["all", "any"]) {
    for (const children of [[], {}, null, "children"]) {
      expect(errorAt([{ id: "bad", when: { kind, children } }]).path).toBe("rules[0].when.children");
    }
    expect(errorAt([{ id: "bad", when: { kind, children: [null] } }]).path).toBe("rules[0].when.children[0]");
  }
});

test("strict predicate operands reject string amount and non-string list members", () => {
  const cases = [
    { field: "amount_cents", op: "gte", value: false, suffix: ".value" },
    { field: "amount_cents", op: "gt", value: -Infinity, suffix: ".value" },
    { field: "merchant", op: "in", value: ["book", null], suffix: ".value[1]" },
    { field: "merchant", op: "eq", value: ["book"], suffix: ".value" },
    { field: "merchant", op: "gte", value: "book", suffix: ".op" },
    { field: "country", op: "includes", value: ["CA"], suffix: ".op" },
    { field: "amount", op: "eq", value: 0, suffix: ".field" },
  ];
  for (const item of cases) expect(errorAt([{ id: "types", when: leaf(item.field, item.op, item.value) }]).path)
    .toBe("rules[0].when" + item.suffix);
});

test("transaction types and exact required keys are enforced for empty rules", () => {
  const base = { amount_cents: 0, country: "CA", merchant: "book" };
  for (const tx of [[], "transaction", false]) expect(errorAt([], tx).path).toBe("transaction");
  for (const amount_cents of [null, true, "0", NaN, Infinity, -0.5]) {
    expect(errorAt([], { ...base, amount_cents })).toEqual({
      ruleId: null, path: "transaction.amount_cents", code: "validation_error",
    });
  }
  expect(errorAt([], { amount_cents: 0, merchant: "book" }).path).toBe("transaction.country");
  expect(errorAt([], { ...base, merchant: 4 }).path).toBe("transaction.merchant");
  expect(errorAt([], { ...base, extra: 0 }).path).toBe("transaction.extra");
});

test("rule ID validation rejects malformed IDs and preserves distinct exact IDs", () => {
  const when = leaf("country", "eq", "CA");
  for (const rules of [null, {}, "rules"]) expect(errorAt(rules).path).toBe("rules");
  expect(errorAt([{ when }])).toEqual({ ruleId: null, path: "rules[0].id", code: "validation_error" });
  expect(errorAt([{ id: "\t\n", when }]).path).toBe("rules[0].id");
  expect(errorAt([{ id: "x", when }, { id: "x", when }])).toEqual({
    ruleId: "x", path: "rules[1].id", code: "validation_error",
  });
  expect(evaluateRules([{ id: " x ", when }, { id: "x", when }, { id: "__proto__", when }], {
    amount_cents: 0, country: "CA", merchant: "book",
  })).toEqual([" x ", "x", "__proto__"]);
});

test("successful and failed rule validation leave nested caller data untouched", () => {
  const tx = Object.freeze({ amount_cents: -2, country: "", merchant: "" });
  const values = Object.freeze(["", "CA"]);
  const yes = Object.freeze(leaf("country", "in", values));
  const rules = Object.freeze([Object.freeze({
    id: "kept", when: Object.freeze({ kind: "any", children: Object.freeze([yes]) }),
  })]);
  const before = JSON.stringify({ tx, rules });
  expect(evaluateRules(rules, tx)).toEqual(["kept"]);
  expect(evaluateRules(rules, tx)).toEqual(["kept"]);
  expect(JSON.stringify({ tx, rules })).toBe(before);
  const bad = Object.freeze([Object.freeze({ id: "bad", when: Object.freeze({
    kind: "all", children: Object.freeze([yes, Object.freeze({ kind: "invalid" })]),
  }) })]);
  const badBefore = JSON.stringify(bad);
  expect(errorAt(bad, tx).path).toBe("rules[0].when.children[1].kind");
  expect(JSON.stringify(bad)).toBe(badBefore);
});
