# Phase 3 local setup

Covers the debt-schedule, insights/alerts, and web-client slices added in
Phase 3 (PR3A–PR3E). Read `api/README.md` first for the Phase 1/2 baseline
(profile/account, categories, ledgers, periods) — this document only adds
what Phase 3 changes.

## 1. Local Supabase project

1. Create a Supabase project (hosted free tier is fine for development —
   this app is designed around free-tier limits, not against them).
2. Apply every file in `supabase/migrations/` **in numeric order**:
   `0001_baseline.sql` → `0002_pr1_hardening.sql` →
   `0003_pin_function_search_path.sql` → `0004_period_lifecycle.sql` →
   `0005_budget_periods_transition_guard.sql` →
   `0006_debt_schedule_and_alerts.sql`. Each file is historical record and is
   never edited after landing; a later migration only adds to what came
   before.
3. Never point this at a shared or production project — every test path
   that touches a live Supabase project (below) creates and deletes real
   Auth users.

## 2. Seed data

Use synthetic data only. **The workbook under `example/Finanzas Personales
2026.xlsx` is reference material for understanding the domain model — it is
never imported, parsed, or deployed** (see the root `README.md`'s Non-Goals
note and `openspec/specs/finance-platform/spec.md`'s Non-Goals section).

A minimal manual seed for exercising Phase 3 features through the web
client:

1. Sign up a user through Supabase Auth (email/password is enough for
   local development).
2. Sign in via the web client (`web/index.html`) and create a category, a
   budget period, and an income/expense entry through the UI — `ensure_profile`
   creates the `profiles` row automatically on first authenticated request.
3. Create a debt (`POST /v1/debts`) with a later budget period already
   defined, then call `POST /v1/debts/{id}/schedule` — idempotent, so
   calling it again is how the web client re-fetches the current
   installment list (there is no separate read-only endpoint).
4. Create an alert rule (`POST /v1/alert-rules`) and view `GET
   /v1/insights?period_id=` (or the Dashboard view) to see it evaluated —
   evaluation is query-time only and never mutates the rule or an
   installment.

## 3. Configured limits

`MAX_EXPORT_ROWS` (default `10000`) is the one configured free-tier
protection in this API: `GET /v1/account/export` returns `429
usage_limit_reached` without deleting or altering any record once the
exported row count would exceed it. There is no other rate limiting in this
codebase — availability guarantees beyond this are explicitly out of scope
(see the spec's Non-Goals).

## 4. Export and recovery workflow

- `GET /v1/account/export` returns every table the authenticated user owns,
  including `debts`, `debt_installments`, and `alert_rules` added in Phase 3
  (see `EXPORT_TABLES` in `api/app/repositories/supabase.py`).
- `DELETE /v1/account` requires `SUPABASE_SERVICE_ROLE_KEY` to be configured
  server-side (never sent to the browser); it fails closed with `503
  account_deletion_not_configured` rather than deleting finance data and
  leaving the `auth.users` row (and thus the JWT) still valid.
- There is no soft-delete or undo: export before deleting if the data needs
  to be kept.

## 5. Disposable Supabase test harness (API integration tests)

Several integration tests (RLS isolation, the differential SQL-vs-Python
debt schedule check, concurrent generation) are opt-in and skipped unless a
disposable project is explicitly configured, mirroring
`api/tests/integration/test_supabase_rls.py`:

```
export SUPABASE_TEST_URL=...
export SUPABASE_TEST_ANON_KEY=...
export SUPABASE_TEST_SERVICE_ROLE_KEY=...
export SUPABASE_TEST_JWT_SECRET=...
export SUPABASE_TEST_ALLOW_DESTRUCTIVE=true
cd api && ./.venv/bin/python -m pytest tests/integration -q
```

These tests create and delete temporary Auth users against whatever project
these variables point at — never point them at a shared or production
project.

## 6. Web client (no build step)

The client is vanilla ES modules served as static files — no bundler, no
`npm run build`.

1. Fill in `window.__ENV__` in `web/index.html` with the project's
   `SUPABASE_URL`, `SUPABASE_ANON_KEY` (never the service-role key — it must
   never reach a browser), and the FastAPI `API_BASE_URL`.
2. Serve the directory: `cd web && npm run serve` (plain
   `python3 -m http.server 4173`), or any other static file server.
3. Run the FastAPI app (`uvicorn app.main:app --reload` from `api/`) so the
   client's `API_BASE_URL` resolves.

## 7. Playwright E2E harness

`web/tests/e2e/finance.spec.js` is opt-in for the same reason as the
disposable Supabase harness above: it needs a live seeded stack (Supabase +
FastAPI + the served static client) and a real test user, not a mock.

```
export E2E_TEST_EMAIL=...
export E2E_TEST_PASSWORD=...
export E2E_BASE_URL=http://localhost:4173   # defaults to this if unset
cd web && npx playwright install chromium   # one-time browser download
npx playwright test
```

Without `E2E_TEST_EMAIL`/`E2E_TEST_PASSWORD` set, every test in the suite
skips cleanly rather than failing against nothing — the same fail-closed
convention as the API's disposable harness.
