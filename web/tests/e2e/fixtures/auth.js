// Opt-in authenticated-page fixture: never runs against an unmarked project.
// Mirrors api/tests/integration/test_supabase_rls.py's disposable-harness
// gate — a live Supabase project, a seeded test user, and a running
// FastAPI + static-client stack must be explicitly configured (E2E_TEST_EMAIL
// and E2E_TEST_PASSWORD at minimum), or every test using `authenticatedPage`
// is skipped rather than failing against nothing.
import { test as base, expect } from "@playwright/test";

export const REQUIRED_ENVIRONMENT = ["E2E_TEST_EMAIL", "E2E_TEST_PASSWORD"];

export function requireE2eHarness() {
  return REQUIRED_ENVIRONMENT.every((name) => Boolean(process.env[name]));
}

export const test = base.extend({
  authenticatedPage: async ({ page }, use) => {
    await page.goto("/");
    await page.getByLabel("Email").fill(process.env.E2E_TEST_EMAIL || "");
    await page.getByLabel("Password").fill(process.env.E2E_TEST_PASSWORD || "");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
    // Clear any localStorage state left by a previous run so each test
    // starts from a clean, independent slate.
    await page.evaluate(() => localStorage.removeItem("finance-app-state-v1"));
    await use(page);
  },
});

export { expect };
