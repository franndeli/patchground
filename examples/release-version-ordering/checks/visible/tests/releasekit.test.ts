import {test, expect} from "vitest";
import {compare, sortVersions, latest, InvalidVersionError} from "../src/releasekit/index";

test("ordinary labels compare with normalized signs", () => {
  expect(compare("1.2.3", "1.2.3")).toBe(0);
  expect(compare("1.2.3", "2.0.0")).toBe(-1);
  expect(compare("2.0.0", "1.2.3")).toBe(1);
});

test("release picker handles double digit minor versions", () => {
  expect(latest(["1.9.0", "1.10.0", "1.2.0"])).toBe("1.10.0");
});

test("sort returns fresh material and ignores build labels", () => {
  const labels = ["1.0.0+z", "1.0.0+a", "0.9.0"];
  const ordered = sortVersions(labels);
  expect(ordered).toEqual(["0.9.0", "1.0.0+z", "1.0.0+a"]);
  expect(labels).toEqual(["1.0.0+z", "1.0.0+a", "0.9.0"]);
  expect(ordered).not.toBe(labels);
});

test("prerelease opt in and empty selection are explicit", () => {
  expect(latest([])).toBeUndefined();
  expect(latest(["2.0.0-rc.1"])).toBeUndefined();
  expect(latest(["2.0.0-rc.1", "1.0.0"])).toBe("1.0.0");
  expect(latest(["2.0.0-rc.1", "1.0.0"], {includePrerelease: true})).toBe("2.0.0-rc.1");
});

test("strict parsing rejects a leading zero", () => {
  expect(() => compare("01.0.0", "1.0.0")).toThrowError(InvalidVersionError);
});
