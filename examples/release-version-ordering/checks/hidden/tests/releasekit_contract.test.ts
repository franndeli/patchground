import {test, expect} from "vitest";
import {compare, sortVersions, latest, InvalidVersionError} from "../src/releasekit/index";

test("core components compare by exact numeric magnitude", () => {
  const pairs = [
    ["9.0.0", "10.0.0"], ["1.9.0", "1.10.0"], ["1.0.9", "1.0.10"],
    ["9007199254740992.0.0", "9007199254740993.0.0"],
    ["1.999999999999999999999999999999.0", "1.1000000000000000000000000000000.0"],
    ["1.0.9007199254740992", "1.0.9007199254740993"],
  ];
  for (const [lower, higher] of pairs) {
    expect(compare(lower, higher)).toBe(-1);
    expect(compare(higher, lower)).toBe(1);
  }
  expect(compare("10.0.0", "9.999.999")).toBe(1);
});

test("release has higher precedence than its prereleases", () => {
  expect(compare("1.0.0", "1.0.0-rc.1")).toBe(1);
  expect(compare("1.0.0-rc.1", "1.0.0")).toBe(-1);
  expect(latest(["1.0.0-rc.1", "1.0.0"], {includePrerelease: true})).toBe("1.0.0");
});

test("prerelease identifiers follow numeric and ASCII rules", () => {
  const pairs = [
    ["1.0.0-beta.2", "1.0.0-beta.11"],
    ["1.0.0-1", "1.0.0--"],
    ["1.0.0-0", "1.0.0-01a"],
    ["1.0.0-A", "1.0.0-a"],
    ["1.0.0-alpha", "1.0.0-alphabet"],
    ["1.0.0-alpha", "1.0.0-alpha.0"],
    ["1.0.0-beta.9007199254740992", "1.0.0-beta.9007199254740993"],
    ["1.0.0-99999999999999999999999999999", "1.0.0-100000000000000000000000000000"],
  ];
  for (const [lower, higher] of pairs) {
    expect(compare(lower, higher)).toBe(-1);
    expect(compare(higher, lower)).toBe(1);
  }
});

test("full SemVer precedence chain sorts independently of input order", () => {
  const chain = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta",
    "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"];
  expect(sortVersions([...chain].reverse())).toEqual(chain);
});

test("build metadata is ignored and ties preserve original labels", () => {
  const labels = ["1.0.0+build.09", "1.0.0+build.10", "1.0.0", "1.0.0+build.00"];
  for (const value of labels) expect(compare(value, "1.0.0")).toBe(0);
  expect(sortVersions(labels)).toEqual(labels);
  expect(latest(labels)).toBe(labels[0]);
  expect(compare("1.0.0-alpha+Z", "1.0.0-alpha+A")).toBe(0);
  expect(latest(["1.0.0-alpha+first", "1.0.0-alpha+second"],
    {includePrerelease: true})).toBe("1.0.0-alpha+first");
});

test("all entry points reject strict grammar violations including filtered labels", () => {
  const invalid = ["", "1", "1.0", "v1.0.0", "01.0.0", "1.01.0", "1.0.01", "1.0.0-01",
    "1.0.0-alpha.01", "1.0.0-", "1.0.0+", "1.0.0-a..b", "1.0.0+a..b", "1.0.0_a",
    " 1.0.0", "1.0.0 ", "1.0.0\n", "1.0.0+\n", "1.0.0-é", "１.0.0",
    "^1.0.0", "~1.0.0", ">=1.0.0", "1.0.*", "+1.0.0", "1.0.0+a+b"];
  for (const value of invalid) {
    expect(() => compare(value, "1.0.0")).toThrowError(InvalidVersionError);
    expect(() => compare("1.0.0", value)).toThrowError(InvalidVersionError);
    expect(() => sortVersions([value])).toThrowError(InvalidVersionError);
    expect(() => latest(["2.0.0", value])).toThrowError(InvalidVersionError);
    expect(() => latest([value], {includePrerelease: true})).toThrowError(InvalidVersionError);
  }
});

test("valid identifier edges and arbitrary length components remain accepted", () => {
  const labels = ["0.0.0", "1.0.0--", "1.0.0-01a", "1.0.0-a-b.0", "1.0.0+00.-.A",
    "999999999999999999999999999999999999999999999999999999999999.0.0"];
  for (const value of labels) expect(compare(value, value)).toBe(0);
});

test("empty fresh sort and latest never mutate even after invalid input", () => {
  const empty: string[] = [];
  const fresh = sortVersions(empty);
  expect(fresh).toEqual([]);
  expect(fresh).not.toBe(empty);
  expect(latest(empty, {includePrerelease: true})).toBeUndefined();
  const labels = ["1.0.0", "2.0.0-rc.1", "0.1.0"];
  const saved = [...labels];
  expect(latest(labels)).toBe("1.0.0");
  expect(latest(labels, {includePrerelease: true})).toBe("2.0.0-rc.1");
  expect(labels).toEqual(saved);
  const invalid = ["2.0.0", "invalid", "1.0.0"];
  expect(() => sortVersions(invalid)).toThrowError(InvalidVersionError);
  expect(() => latest(invalid)).toThrowError(InvalidVersionError);
  expect(invalid).toEqual(["2.0.0", "invalid", "1.0.0"]);
});
