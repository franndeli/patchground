export type Transaction = Readonly<{
  amount_cents: number;
  country: string;
  merchant: string;
}>;

export type RuleNode =
  | Readonly<{ kind: "predicate"; field: "amount_cents"; op: "gt" | "gte" | "eq"; value: number }>
  | Readonly<{ kind: "predicate"; field: "country" | "merchant"; op: "eq"; value: string }>
  | Readonly<{ kind: "predicate"; field: "country" | "merchant"; op: "in"; value: readonly string[] }>
  | Readonly<{ kind: "all" | "any"; children: readonly RuleNode[] }>
  | Readonly<{ kind: "not"; child: RuleNode }>;

export type Rule = Readonly<{ id: string; when: RuleNode }>;

export class RuleValidationError extends Error {
  readonly code = "validation_error";

  constructor(
    readonly ruleId: string | null,
    readonly path: string,
    detail: string,
  ) {
    super(`${path}: ${detail}`);
    this.name = "RuleValidationError";
  }
}
