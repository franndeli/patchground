import { test, expect } from "vitest";
import { evaluateRules } from "../src/evaluator.js";
import { RuleValidationError } from "../src/rule-types.js";
import { previewTransaction } from "../src/risk-preview.js";

const transaction = { amount_cents: 500, country: "GB", merchant: "market" };

function predicate(field: string, op: string, value: unknown) {
  return { kind: "predicate", field, op, value };
}

function validationError(rules: unknown, tx: unknown = transaction): RuleValidationError {
  try {
    evaluateRules(rules, tx);
  } catch (error) {
    if (error instanceof RuleValidationError) return error;
    throw error;
  }
  throw new Error("expected a RuleValidationError");
}

test("rule amounts implement gt gte and eq at the equality boundary", () => {
  const rules = [
    { id: "strict", when: predicate("amount_cents", "gt", 500) },
    { id: "inclusive", when: predicate("amount_cents", "gte", 500) },
    { id: "equal", when: predicate("amount_cents", "eq", 500) },
    { id: "less-threshold", when: predicate("amount_cents", "gt", 499) },
  ];
  expect(evaluateRules(rules, transaction)).toEqual(["inclusive", "equal", "less-threshold"]);
});

test("rule strings implement exact eq and in for both fields", () => {
  const rules = [
    { id: "country-eq", when: predicate("country", "eq", "GB") },
    { id: "country-in", when: predicate("country", "in", ["IE", "GB"]) },
    { id: "merchant-eq", when: predicate("merchant", "eq", "market") },
    { id: "merchant-in", when: predicate("merchant", "in", ["market", "other"]) },
    { id: "wrong-case", when: predicate("country", "eq", "gb") },
    { id: "empty-members", when: predicate("merchant", "in", []) },
  ];
  expect(evaluateRules(rules, transaction)).toEqual(["country-eq", "country-in", "merchant-eq", "merchant-in"]);
});

test("rule logic composes all any and unary not", () => {
  const yes = predicate("country", "eq", "GB");
  const no = predicate("merchant", "eq", "trusted");
  expect(evaluateRules([
    { id: "review", when: { kind: "all", children: [yes, { kind: "not", child: no }] } },
    { id: "either", when: { kind: "any", children: [no, yes] } },
    { id: "neither", when: { kind: "not", child: { kind: "any", children: [no, yes] } } },
    { id: "both", when: { kind: "all", children: [no, yes] } },
  ], transaction)).toEqual(["review", "either"]);
});

test("rule empty sets and the existing preview adapter remain usable", () => {
  expect(evaluateRules([], transaction)).toEqual([]);
  expect(previewTransaction([], transaction)).toEqual({ matchedRuleIds: [], needsReview: false });
  expect(previewTransaction([{ id: "review", when: predicate("country", "eq", "GB") }], transaction))
    .toEqual({ matchedRuleIds: ["review"], needsReview: true });
});

test("rule errors carry a stable structured identity and indexed tree path", () => {
  const error = validationError([{ id: "risk", when: { kind: "all", children: [
    predicate("country", "eq", "GB"),
    predicate("amount_cents", "gt", "500"),
  ] } }]);
  expect(error).toMatchObject({
    name: "RuleValidationError", code: "validation_error",
    ruleId: "risk", path: "rules[0].when.children[1].value",
  });
  expect(error.message.length).toBeGreaterThan(0);
});

test("rule validation rejects unknown fields operators and node keys", () => {
  const cases = [
    { when: predicate("currency", "eq", "GBP"), path: "rules[0].when.field" },
    { when: predicate("country", "gt", "GB"), path: "rules[0].when.op" },
    { when: predicate("amount_cents", "in", [500]), path: "rules[0].when.op" },
    { when: { ...predicate("country", "eq", "GB"), extra: true }, path: "rules[0].when.extra" },
    { when: { kind: "xor", children: [] }, path: "rules[0].when.kind" },
  ];
  for (const item of cases) {
    expect(validationError([{ id: "bad", when: item.when }])).toMatchObject({ ruleId: "bad", path: item.path });
  }
});

test("rule validation rejects wrong predicate value types without coercion", () => {
  for (const value of ["500", true, null, 1.5, NaN, Infinity]) {
    expect(validationError([{ id: "bad", when: predicate("amount_cents", "eq", value) }]).path)
      .toBe("rules[0].when.value");
  }
  expect(validationError([{ id: "bad", when: predicate("country", "eq", 1) }]).path).toBe("rules[0].when.value");
  expect(validationError([{ id: "bad", when: predicate("merchant", "in", "market") }]).path).toBe("rules[0].when.value");
  expect(validationError([{ id: "bad", when: predicate("country", "in", ["GB", 1]) }]).path)
    .toBe("rules[0].when.value[1]");
});

test("rule IDs must be nonempty unique strings and rule objects exact", () => {
  const leaf = predicate("country", "eq", "GB");
  for (const id of ["", "  ", null, 4]) {
    expect(validationError([{ id, when: leaf }])).toMatchObject({ ruleId: null, path: "rules[0].id" });
  }
  expect(validationError([{ id: "x", when: leaf }, { id: "x", when: leaf }]))
    .toMatchObject({ ruleId: "x", path: "rules[1].id" });
  expect(validationError([{ id: "x", when: leaf, active: true }]))
    .toMatchObject({ ruleId: "x", path: "rules[0].active" });
  expect(validationError("not-an-array")).toMatchObject({ ruleId: null, path: "rules" });
  expect(validationError([null])).toMatchObject({ ruleId: null, path: "rules[0]" });
});

test("rule shape errors name missing keys and malformed child locations", () => {
  const cases = [
    { when: {}, path: "rules[0].when.kind" },
    { when: null, path: "rules[0].when" },
    { when: { kind: "predicate", field: "country", op: "eq" }, path: "rules[0].when.value" },
    { when: { kind: "all", children: [] }, path: "rules[0].when.children" },
    { when: { kind: "any", children: "bad" }, path: "rules[0].when.children" },
    { when: { kind: "not" }, path: "rules[0].when.child" },
    { when: { kind: "all", children: [7] }, path: "rules[0].when.children[0]" },
  ];
  for (const item of cases) expect(validationError([{ id: "shape", when: item.when }]).path).toBe(item.path);
  expect(validationError([{ id: "missing" }]).path).toBe("rules[0].when");
});

test("rule validation includes short-circuited branches and later rules", () => {
  const yes = predicate("country", "eq", "GB");
  const no = predicate("country", "eq", "US");
  for (const when of [
    { kind: "any", children: [yes, { kind: "unknown" }] },
    { kind: "all", children: [no, { kind: "unknown" }] },
  ]) {
    expect(validationError([{ id: "branch", when }])).toMatchObject({
      ruleId: "branch", path: "rules[0].when.children[1].kind",
    });
  }
  expect(validationError([{ id: "first", when: yes }, { id: "later", when: { kind: "bad" } }]))
    .toMatchObject({ ruleId: "later", path: "rules[1].when.kind" });
});

test("rule depth counts the root and rejects only the ninth node", () => {
  let when: unknown = predicate("amount_cents", "eq", 500);
  for (let i = 0; i < 7; i += 1) when = { kind: "not", child: when };
  expect(evaluateRules([{ id: "eight", when }], transaction)).toEqual([]);
  when = { kind: "not", child: when };
  expect(validationError([{ id: "nine", when }])).toMatchObject({
    ruleId: "nine", path: "rules[0].when" + ".child".repeat(8),
  });
});

test("rule transaction validation runs even with no rules", () => {
  const cases = [
    { tx: null, path: "transaction" },
    { tx: { ...transaction, amount_cents: "500" }, path: "transaction.amount_cents" },
    { tx: { ...transaction, amount_cents: 0.5 }, path: "transaction.amount_cents" },
    { tx: { ...transaction, country: false }, path: "transaction.country" },
    { tx: { amount_cents: 1, country: "GB" }, path: "transaction.merchant" },
    { tx: { ...transaction, note: "extra" }, path: "transaction.note" },
  ];
  for (const item of cases) expect(validationError([], item.tx)).toMatchObject({
    ruleId: null, code: "validation_error", path: item.path,
  });
});

test("rule interpretation preserves caller input including membership and child arrays", () => {
  const tx = Object.freeze({ amount_cents: -10, country: "", merchant: "shop" });
  const membership = Object.freeze(["", "GB"]);
  const children = Object.freeze([
    Object.freeze(predicate("country", "in", membership)),
    Object.freeze(predicate("amount_cents", "gte", -10)),
  ]);
  const rules = Object.freeze([Object.freeze({
    id: " keep spaces ", when: Object.freeze({ kind: "all", children }),
  })]);
  const before = JSON.stringify({ rules, tx });
  expect(evaluateRules(rules, tx)).toEqual([" keep spaces "]);
  expect(JSON.stringify({ rules, tx })).toBe(before);
});
