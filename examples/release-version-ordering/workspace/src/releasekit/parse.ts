/** Strict label parsing; numeric components stay as strings to preserve precision. */
export class InvalidVersionError extends Error {
  constructor() {
    super("Invalid semantic version");
    this.name = "InvalidVersionError";
  }
}

export interface Version {
  readonly core: readonly string[];
  readonly prerelease: readonly string[];
}

const grammar = /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$/;

export function parse(value: string): Version {
  const match = grammar.exec(value);
  if (match === null || match[0] !== value) throw new InvalidVersionError();
  const prerelease = match[4] === undefined ? [] : match[4].split(".");
  if (prerelease.some(part => /^[0-9]+$/.test(part) && part.length > 1 && part[0] === "0")) {
    throw new InvalidVersionError();
  }
  return {core: [match[1], match[2], match[3]], prerelease};
}
