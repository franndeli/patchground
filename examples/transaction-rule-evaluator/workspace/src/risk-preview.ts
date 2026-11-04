import { evaluateRules } from "./evaluator.js";

export type RiskPreview = Readonly<{
  matchedRuleIds: readonly string[];
  needsReview: boolean;
}>;

export function previewTransaction(
  rules: unknown,
  transaction: unknown,
): RiskPreview {
  const matchedRuleIds = evaluateRules(rules, transaction);
  return { matchedRuleIds, needsReview: matchedRuleIds.length > 0 };
}
