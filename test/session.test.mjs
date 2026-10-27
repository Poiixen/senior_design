import assert from "node:assert/strict";
import { test } from "node:test";
import { ACTIVITY_SYNC_MS, SESSION_IDLE_MS, loginDestination } from "../frontend/app/lib/session.ts";

test("sign-in defaults to the product and preserves a safe internal destination", () => {
  assert.equal(loginDestination("http://localhost/login"), "/dashboard");
  assert.equal(loginDestination("http://localhost/login?next=%2Freports%2F7%3Fview%3Dcolumns"), "/reports/7?view=columns");
  for (const next of ["//external.example", "/\\external.example", "https://external.example", "/login", "/register"]) {
    assert.equal(loginDestination(`http://localhost/login?next=${encodeURIComponent(next)}`), "/dashboard");
  }
});

test("the client idle window is five minutes and active renewal is throttled", () => {
  assert.equal(SESSION_IDLE_MS, 300_000);
  assert.equal(ACTIVITY_SYNC_MS, 60_000);
});
