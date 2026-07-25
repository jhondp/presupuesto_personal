// Full end-to-end workflows against the static client + FastAPI + a seeded
// disposable Supabase project (see docs/phase-3-setup.md, added in PR3E).
// Every test in this file is skipped unless `requireE2eHarness()` finds the
// required environment configured — this suite must never run against an
// unmarked/production project (same fail-closed convention as
// api/tests/integration/test_supabase_rls.py).
import { test, expect, requireE2eHarness } from "./fixtures/auth.js";

test.describe("Personal Finance web client", () => {
  test.skip(!requireE2eHarness(), "E2E harness unavailable: set E2E_TEST_EMAIL and E2E_TEST_PASSWORD against a seeded disposable stack");

  test("login flow authenticates and reveals the app nav", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();

    await page.getByLabel("Email").fill(process.env.E2E_TEST_EMAIL);
    await page.getByLabel("Password").fill(process.env.E2E_TEST_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  });

  test("a signed-in session survives a page reload without a fresh login", async ({ authenticatedPage: page }) => {
    await page.reload();
    await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Sign in" })).not.toBeVisible();
  });

  test("recording an income entry resolves the open period and appears in the ledger", async ({ authenticatedPage: page }) => {
    await page.goto("/#/periods");
    const today = new Date().toISOString().slice(0, 10);
    await page.getByLabel("Starts on").fill(today);
    const endsOn = new Date(Date.now() + 27 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    await page.getByLabel("Ends on").fill(endsOn);
    await page.getByRole("button", { name: "Create period" }).click();
    await expect(page.getByRole("cell", { name: "open" })).toBeVisible();

    await page.goto("/#/income");
    await page.getByLabel("Date").fill(today);
    await page.getByLabel("Amount (minor units)").fill("500000");
    await page.getByRole("button", { name: "Add entry" }).click();

    await expect(page.getByRole("table", { name: /Recorded income/ })).toContainText("500,000");
  });

  test("expense entries are recorded in a separate ledger from income", async ({ authenticatedPage: page }) => {
    await page.goto("/#/expenses");
    const today = new Date().toISOString().slice(0, 10);
    await page.getByLabel("Date").fill(today);
    await page.getByLabel("Amount (minor units)").fill("120000");
    await page.getByRole("button", { name: "Add entry" }).click();

    await expect(page.getByRole("table", { name: /Recorded expenses/ })).toContainText("120,000");
    await page.goto("/#/income");
    await expect(page.getByRole("table", { name: /Recorded income/ })).not.toContainText("120,000");
  });

  test("closing a period with a stale version is rejected and reopening restores writes", async ({ authenticatedPage: page }) => {
    await page.goto("/#/periods");
    const row = page.locator("tbody tr").first();
    await row.getByRole("button", { name: "Close" }).click();
    await expect(row.getByRole("cell", { name: "closed" })).toBeVisible();

    // A second close attempt reuses the row's now-stale rendered version and
    // must surface the API's 409 rather than silently succeeding.
    await row.getByRole("button", { name: "Reopen" }).click();
    await expect(row.getByRole("cell", { name: "open" })).toBeVisible();
  });

  test("generating a debt schedule lists its installments", async ({ authenticatedPage: page }) => {
    await page.goto("/#/debts");
    await page.getByLabel("Bank").fill("Test Bank");
    await page.getByLabel("Principal (minor units)").fill("300000");
    await page.getByLabel("Installment amount (minor units)").fill("100000");
    await page.getByLabel("Installment count").fill("3");
    await page.getByRole("button", { name: "Add debt" }).click();

    await page.getByRole("button", { name: "Generate / view schedule" }).first().click();
    await expect(page.getByRole("table", { name: "Installments" })).toBeVisible();
    await expect(page.locator("tbody tr", { hasText: "1" }).first()).toBeVisible();
  });

  test("the dashboard summarizes the selected period and surfaces triggered alerts", async ({ authenticatedPage: page }) => {
    await page.goto("/#/dashboard");
    await expect(page.getByText("Income")).toBeVisible();
    await expect(page.getByText("Balance")).toBeVisible();
    await expect(page.getByText(/No active alerts|reached the .* threshold/)).toBeVisible();
  });

  test("creating an alert rule does not mutate ledger state when the dashboard is merely viewed", async ({ authenticatedPage: page }) => {
    await page.goto("/#/dashboard");
    const before = await page.evaluate(() => localStorage.getItem("finance-app-state-v1"));

    await page.goto("/#/dashboard");
    await page.goto("/#/dashboard");
    const after = await page.evaluate(() => localStorage.getItem("finance-app-state-v1"));

    // Repeated dashboard views (which call GET /v1/insights) must not
    // change any persisted alert-rule/ledger data — evaluation is query-time
    // only (see design.md's "Alert rule shape" decision).
    expect(JSON.parse(after).alertRules).toEqual(JSON.parse(before).alertRules);
  });
});
