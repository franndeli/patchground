# Evaluate transaction rules without executing code

The risk-preview endpoint already accepts parsed JSON and builds an explanation
in `src/risk-preview.ts`. Complete validation and interpretation in
`src/evaluator.ts`. It must handle untrusted rule data, not execute it.

## Entry point and data

`evaluateRules(rules: unknown, transaction: unknown): string[]` returns **every**
matching rule ID, in input order. `src/rule-types.ts` supplies the validated
domain types and the public `RuleValidationError`. Empty rules return `[]`
for a valid transaction; transaction validation still applies to empty rules.

A transaction is an object with **exactly** these keys:
`amount_cents` (finite integer, including zero or negative amounts),
`country` (string), and `merchant` (string). No coercion is allowed.
Rules are an array of objects with exactly `id` and `when` keys.
An ID must be a string containing a non-whitespace character. Preserve IDs
verbatim and reject duplicate IDs by exact equality; do not trim valid IDs.

Each `when` is a JSON node with one of these exact shapes:

- `{ kind: "predicate", field: "amount_cents", op: "gt" | "gte" | "eq", value: integer }`
- `{ kind: "predicate", field: "country" | "merchant", op: "eq", value: string }`
- `{ kind: "predicate", field: "country" | "merchant", op: "in", value: string[] }`
- `{ kind: "all", children: [node, ...] }`
- `{ kind: "any", children: [node, ...] }`
- `{ kind: "not", child: node }`

These are shape descriptions, not a textual expression grammar. All listed
keys are required; extra keys are invalid at every level. Reject unknown kinds,
fields, operators, mismatched field/operator pairs, missing keys, non-object
nodes, and values of the wrong type. Booleans are not numbers. Numeric
predicate values, like transaction amounts, must be finite integers.

## Matching and bounds

`gt` is strict greater-than; `gte` includes equality; `eq` is exact equality.
String comparisons are exact and case-sensitive, with no normalization.
`in` is exact membership; an empty string array is valid and matches nothing.
String values may be empty. `all` requires every child to match; `any`
requires at least one; `not` negates its single child. Both `children`
arrays must be nonempty.

Validate the **entire** rule set before evaluating any rule, including later
rules and branches an interpreter would short-circuit. Permit at most **eight
nodes along any root-to-leaf path**, counting the root as one and predicates
as nodes. Depth nine is invalid. Do not mutate the input transaction, rules,
nodes, child arrays, or membership arrays.

For example, the tree below matches a transaction with amount 500, country
`GB`, and merchant `market`:

```json
{
  "id": "review",
  "when": {
    "kind": "all",
    "children": [
      { "kind": "predicate", "field": "amount_cents", "op": "gte", "value": 500 },
      { "kind": "predicate", "field": "country", "op": "in", "value": ["GB", "IE"] },
      { "kind": "not", "child": { "kind": "predicate", "field": "merchant", "op": "eq", "value": "trusted" } }
    ]
  }
}
```

## Validation errors

Throw the supplied `RuleValidationError` (not a false match or coercion).
Its `code` is `"validation_error"`, `ruleId` is the offending rule's original
ID when a valid ID is available, otherwise `null`, and `path` identifies the
offending location. Messages must be explanatory, but no exact wording is required.

Paths start at `rules` or `transaction`. Use array indexes and key names:
`rules[0].id`, `rules[1].when.children[2].value`,
`rules[0].when.child.kind`, `transaction.amount_cents`.
An invalid list has path `rules`; invalid rule objects use `rules[i]`.
Missing keys use the missing key's path. Extra keys use the extra key's path.
Malformed children/member arrays use their property's path; a malformed array
element includes its index. A depth error names the first node beyond depth
eight. Transaction errors have `ruleId: null`. Duplicate IDs identify the
later occurrence's `id` path and duplicate ID. If there are multiple errors,
any one of them may be reported; validation order is not prescribed.

## Boundaries

Add regression checks under `tests/`. Use Patchground's Docker checks rather
than host npm. Keep the existing preview adapter usable.
Do not use `eval`, generated functions, executable strings, side effects, a
text parser, or a rule-engine dependency. Implement the validation and interpreter
yourself. No regex rule language, networking, dependencies, real fraud decisions,
or machine-learning model is needed. Inputs are ordinary parsed JSON data;
getters, proxies, prototype attacks, and cyclic non-JSON graphs are outside scope.

This is original generated practice material. Advanced difficulty and the
75-minute timebox are provisional author estimates, not human-calibrated or
employer-endorsed claims.
