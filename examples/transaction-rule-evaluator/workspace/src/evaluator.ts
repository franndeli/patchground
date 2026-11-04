import { RuleValidationError } from "./rule-types.js";
import type { Rule, RuleNode, Transaction } from "./rule-types.js";

function invalid(ruleId: string | null, path: string, detail: string): never {
  throw new RuleValidationError(ruleId, path, detail);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function record(value: unknown, ruleId: string | null, path: string): Record<string, unknown> {
  if (!isRecord(value)) invalid(ruleId, path, "expected an object");
  return value;
}

function keys(
  value: Record<string, unknown>,
  allowed: readonly string[],
  ruleId: string | null,
  path: string,
): void {
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) invalid(ruleId, `${path}.${key}`, "unknown key");
  }
}

function parseTransaction(input: unknown): Transaction {
  const value = record(input, null, "transaction");
  keys(value, ["amount_cents", "country", "merchant"], null, "transaction");
  const { amount_cents, country, merchant } = value;
  if (typeof amount_cents !== "number" || !Number.isInteger(amount_cents)) {
    invalid(null, "transaction.amount_cents", "expected an integer");
  }
  if (typeof country !== "string") invalid(null, "transaction.country", "expected a string");
  if (typeof merchant !== "string") invalid(null, "transaction.merchant", "expected a string");
  return { amount_cents, country, merchant };
}

function parseNode(input: unknown, ruleId: string, path: string, depth: number): RuleNode {
  invalid(ruleId, path, "implement rule tree validation");
}

function parseRules(input: unknown): Rule[] {
  if (!Array.isArray(input)) invalid(null, "rules", "expected an array");
  const seen = new Set<string>();
  return input.map((raw: unknown, index: number) => {
    const path = `rules[${index}]`;
    const value = record(raw, null, path);
    const id = value.id;
    if (typeof id !== "string" || id.trim().length === 0) {
      invalid(null, `${path}.id`, "expected a nonempty rule ID");
    }
    keys(value, ["id", "when"], id, path);
    if (seen.has(id)) invalid(id, `${path}.id`, "duplicate rule ID");
    seen.add(id);
    return { id, when: parseNode(value.when, id, `${path}.when`, 1) };
  });
}

function evaluateNode(node: RuleNode, transaction: Transaction): boolean {
  throw new Error("Implement typed rule interpretation");
}

export function evaluateRules(rules: unknown, transaction: unknown): string[] {
  const parsedTransaction = parseTransaction(transaction);
  const parsedRules = parseRules(rules);
  return parsedRules
    .filter(rule => evaluateNode(rule.when, parsedTransaction))
    .map(rule => rule.id);
}
