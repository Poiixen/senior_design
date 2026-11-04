import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT_PREFERENCES, PREFERENCES_KEY, readPreferences, writePreferences, resolveAppearance, sortReports, validatePreferences, initializeAppearance } from "../frontend/app/lib/preferences.ts";

test("missing, invalid, and obsolete preferences use safe defaults", () => {
  for (const value of [null, [], "bad", { theme: "blue", accent: "neon", palette: "__proto__", density: "tiny", motion: "fast", reportSort: "__proto__", sidebarCollapsed: "yes" }]) {
    assert.deepEqual(validatePreferences(value), DEFAULT_PREFERENCES);
  }
  assert.deepEqual(readPreferences({ getItem: () => "{bad json" }), DEFAULT_PREFERENCES);
  assert.deepEqual(readPreferences({ getItem: () => { throw Error("blocked"); } }), DEFAULT_PREFERENCES);
});

test("storage round trips supported preferences and strips sensitive or unknown fields", () => {
  let stored;
  const storage = { getItem: () => stored, setItem: (key, value) => { assert.equal(key, PREFERENCES_KEY); stored = value; } };
  const value = { theme: "dark", palette: "forest", accent: "teal", density: "compact", motion: "reduce", reportSort: "most-rows", sidebarCollapsed: true };
  writePreferences(storage, { ...value, email: "private", password: "never-store", report: "private" });
  assert.deepEqual(readPreferences(storage), value);
  assert.doesNotMatch(stored, /private|password|email/);
  writePreferences(storage, DEFAULT_PREFERENCES);
  assert.deepEqual(readPreferences(storage), DEFAULT_PREFERENCES);
  assert.doesNotThrow(() => writePreferences({ setItem: () => { throw Error("blocked"); } }, value));
});

test("system appearance responds to device preferences and explicit overrides win", () => {
  assert.deepEqual(resolveAppearance(DEFAULT_PREFERENCES, true, true), { theme: "dark", motion: "reduce" });
  assert.deepEqual(resolveAppearance(DEFAULT_PREFERENCES, false, false), { theme: "light", motion: "full" });
  assert.deepEqual(resolveAppearance({ ...DEFAULT_PREFERENCES, theme: "light", motion: "full" }, true, true), { theme: "light", motion: "full" });
});

test("all six report sorts use real values, keep unknown counts last, and preserve the input", () => {
  const reports = [
    { analysis_id: 1, completed_at: "2026-10-01", summary: { issues_detected: 8 }, dataset: { rows: 10 } },
    { analysis_id: 2, completed_at: "2026-10-03", summary: { issues_detected: 0 }, dataset: { rows: 300 } },
    { analysis_id: 3, completed_at: "2026-10-02", summary: { issues_detected: 2 }, dataset: { rows: 100 } },
  ];
  const expected = { newest: [2, 3, 1], oldest: [1, 3, 2], "most-issues": [1, 3, 2], "fewest-issues": [2, 3, 1], "most-rows": [2, 3, 1], "fewest-rows": [1, 3, 2] };
  for (const [sort, ids] of Object.entries(expected)) assert.deepEqual(sortReports(reports, sort).map(item => item.analysis_id), ids);
  assert.deepEqual(reports.map(item => item.analysis_id), [1, 2, 3]);
  assert.equal(sortReports([...reports, { analysis_id: 4 }], "fewest-issues").at(-1).analysis_id, 4);
});

test("appearance bootstrap applies validated stored values before rendering", () => {
  const old = { localStorage: globalThis.localStorage, document: globalThis.document, matchMedia: globalThis.matchMedia };
  const dataset = {};
  try {
    globalThis.document = { documentElement: { dataset } };
    globalThis.localStorage = { getItem: () => JSON.stringify({ theme: "dark", palette: "forest", accent: "teal", density: "compact", motion: "reduce" }) };
    globalThis.matchMedia = () => ({ matches: false });
    initializeAppearance();
    assert.deepEqual(dataset, { theme: "dark", palette: "forest", accent: "teal", density: "compact", motion: "reduce" });
    globalThis.localStorage = { getItem: () => JSON.stringify({ theme: "unsupported", density: "wrong", motion: "wrong" }) };
    globalThis.matchMedia = () => ({ matches: true });
    initializeAppearance();
    assert.deepEqual(dataset, { theme: "dark", palette: "neutral", accent: "violet", density: "comfortable", motion: "reduce" });
  } finally {
    for (const [key, value] of Object.entries(old)) { if (value === undefined) delete globalThis[key]; else globalThis[key] = value; }
  }
});
