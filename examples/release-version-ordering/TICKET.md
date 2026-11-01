# The release picker chooses the wrong version

Our changelog tool uses the small `releasekit` library in `src/releasekit/` to show release labels
in ascending order and select the latest release. Support reports that
`latest(["1.9.0", "1.10.0", "1.2.0"])` chooses `"1.9.0"`, and release candidates appear in surprising
positions. Fix the ordering behavior and add a regression check. Keep the public API below.

## Public API

Import from `src/releasekit/index.ts`:

- `compare(a: string, b: string): -1 | 0 | 1` returns the sign of the SemVer precedence comparison.
- `sortVersions(versions: readonly string[]): string[]` returns a **fresh**, ascending, stable array.
  The input is never mutated, including on error. Equal-precedence strings retain their input order.
- `latest(versions: readonly string[], options?: {includePrerelease?: boolean}): string | undefined`
  returns the original string with greatest precedence. By default prereleases are excluded;
  `{includePrerelease: true}` includes them. Return `undefined` for an empty input or when no eligible
  versions remain. Equal-precedence candidates keep the **first** eligible input string. Never mutate
  the input.
- `InvalidVersionError` is an exported `Error` subclass. Every API validates every supplied version,
  including a singleton array and prereleases that `latest` would filter out. Any invalid version
  throws `InvalidVersionError`; message text is unspecified. An empty array is valid.

Inputs to this API are strings and arrays of strings; handling other JavaScript types is outside
this ticket. Runtime checks exercise TypeScript code; they do not establish compiler type correctness.

## Accepted version strings

Use strict **SemVer 2.0.0**, with no trimming, normalization, range syntax or optional prefixes:

`MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]`

- MAJOR, MINOR and PATCH are nonempty ASCII decimal digit strings. Each is either `0` or begins with
  `1`–`9`; leading zeroes are invalid. Exactly three components are required.
- PRERELEASE and BUILD are nonempty lists of nonempty identifiers separated by `.`. Each identifier
  contains only ASCII letters `A`–`Z`/`a`–`z`, decimal digits `0`–`9`, or `-`.
- A prerelease identifier containing only decimal digits must be `0` or start with `1`–`9`. Build
  identifiers may have leading zeroes. A nonnumeric prerelease identifier such as `01a` is valid.
- No whitespace, Unicode letters/digits, leading `v`, signs, wildcards, operators (`^`, `~`, `>=`),
  missing components, empty identifiers or trailing characters are accepted. Hyphens within an
  identifier are allowed, including an identifier consisting only of a hyphen.
- Numeric components and numeric prerelease identifiers have **arbitrary precision**: their magnitude
  must be compared exactly regardless of length, without floating-point rounding or safe-integer
  rejection. Decimal-string comparison or BigInt is suitable. The ticket imposes no numeric length cap.

Parsing already works; keep its validation policy intact.

## Precedence

Compare core components MAJOR, then MINOR, then PATCH by numeric magnitude. For equal cores:

1. A version without a prerelease has higher precedence than one with a prerelease.
2. Compare prerelease identifiers from left to right. Two numeric identifiers compare by exact numeric
   magnitude. A numeric identifier has lower precedence than a nonnumeric identifier. Two nonnumeric
   identifiers compare by case-sensitive ASCII lexical order, including ordinary prefix ordering.
3. If all compared identifiers are equal, the shorter prerelease identifier list has lower precedence.

BUILD metadata has **no effect** on precedence, eligibility or tie breaking. Preserve original input
strings in returned arrays and in `latest` rather than reconstructing or dropping build metadata.
For example, this is an ascending precedence chain:

`1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0`

`1.0.0+build.09` and `1.0.0+build.10` compare equal. `latest(["2.0.0-rc.1", "1.0.0"])`
returns `"1.0.0"` by default, and `"2.0.0-rc.1"` when prereleases are included.

## Scope

Fix application code and add focused editable checks. Do not add a semver dependency or change the
runner, dependency recipe, or hidden checks. No range resolution, filesystem access, clocks, network,
CLI, or compatibility with a third-party semver package is required. The 45-minute timebox and
intermediate difficulty are author estimates, pending independent human usability testing.
