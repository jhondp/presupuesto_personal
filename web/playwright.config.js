// @ts-check
import { defineConfig, devices } from "@playwright/test";

// Chromium only for now (design.md's Testing Strategy defers multi-browser
// coverage); `webServer` is left unset deliberately — this suite needs both
// the static client (`npm run serve`) and the FastAPI app running against a
// seeded disposable Supabase project, which the CI/local runner starts
// explicitly rather than this config guessing at.
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:4173",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
