import {parse, type Version} from "./parse";

type Order = -1 | 0 | 1;

function lexical(a: string, b: string): Order {
  return a === b ? 0 : a < b ? -1 : 1;
}

function precedence(a: Version, b: Version): Order {
  for (let i = 0; i < 3; i += 1) {
    const order = lexical(a.core[i], b.core[i]);
    if (order !== 0) return order;
  }
  if (a.prerelease.length === 0 && b.prerelease.length === 0) return 0;
  if (a.prerelease.length === 0) return -1;
  if (b.prerelease.length === 0) return 1;
  return lexical(a.prerelease.join("."), b.prerelease.join("."));
}

export function compare(a: string, b: string): Order {
  return precedence(parse(a), parse(b));
}

export function sortVersions(versions: readonly string[]): string[] {
  const parsed = versions.map(value => ({value, parsed: parse(value)}));
  parsed.sort((a, b) => precedence(a.parsed, b.parsed));
  return parsed.map(item => item.value);
}

export function latest(
  versions: readonly string[],
  options: {includePrerelease?: boolean} = {},
): string | undefined {
  const parsed = versions.map(value => ({value, parsed: parse(value)}));
  const eligible = parsed.filter(item => options.includePrerelease || item.parsed.prerelease.length === 0);
  let best: typeof eligible[number] | undefined;
  for (const item of eligible) {
    if (best === undefined || precedence(item.parsed, best.parsed) > 0) best = item;
  }
  return best?.value;
}
