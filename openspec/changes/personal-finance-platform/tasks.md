# Tasks: Personal Finance Platform

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines (Phase 3) | ~3,325 total across 5 slices |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR3A debts → PR3B alerts → PR3C web → PR3D e2e → PR3E docs |
| Delivery strategy | auto-forecast (not a canonical value; treated as `ask-on-risk` until confirmed) |
| Chain strategy | stacked-to-main |
| Configured review budget (Phase 3 override) | 800 lines |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

## Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Auth, RLS, profile, account safety (done) | PR1 merged | `pytest tests/integration/test_profile.py` | Local Supabase two-user isolation | `api/app/core`, profile/account routes |
| 2 | Categories, ledgers, periods (done) | PR2 merged | `pytest tests/unit tests/integration/test_ledgers.py` | Seeded API close/reopen + entry write | ledger/period routes and tables |
| 3A | Debt schedule + installments (~700 LOC, done) | PR3A branch `pr3a-debts-backend` | `pytest tests/unit tests/integration/test_debts*.py` | Local Supabase: schedule generation twice, concurrently | `domain/debts.py`, `routes/debts.py`, `0006_*.sql` |
| 3B | Insights + alert evaluation (~575 LOC, done) | PR3B branch `pr3b-alerts-insights` | `pytest tests/unit tests/integration/test_alerts*.py test_insights*.py` — 20 passed | Two-user rule isolation, GET-no-mutation check | `domain/alerts.py`, `routes/alert_rules.py`, `routes/insights.py` |
| 3C | Web client, no build step (~1,400 LOC, done — `size:exception` approved) | PR3C branch `pr3c-web-client` | Manual smoke (`node --check` all modules, passing); formal coverage in 3D | N/A — static assets only | `web/index.html`, `web/assets`, `web/src` |
| 3D | Playwright E2E (~450 LOC, done) | PR3D branch `pr3d-e2e-tests` | `npx playwright test` — 8 skipped (harness unconfigured in this sandbox; discovery/fixtures verified) | Seeded disposable Supabase stack (no Docker daemon available here) | `web/tests/e2e/finance.spec.js` |
| 3E | Docs + cleanup (~250 LOC) | PR3E → main | `pytest -v` + `npx playwright test` | Full-suite rerun | `api/README.md`, `docs/`, root `README.md` |

## Phase 1: Foundation
- [x] 1.1 Create `api/pyproject.toml`, app factory, config, stable errors, JWT verification, request-scoped Supabase gateway.
- [x] 1.2 RED: two-user API/RLS tests for indistinguishable missing/cross-owner 404s, no financial/secret logging.
- [x] 1.3 Create `supabase/migrations/0001_baseline.sql` — UUID rows, ownership, money/date fields, RLS, constraints.
- [x] 1.4 RED: default CLP scale, user-only export/deletion, configured-limit rejection preserving data.
- [x] 1.5 Implement `profile`/`account` routes, export, deletion, limit guard, shared DTO validation.

## Phase 2: Ledgers and periods
- [x] 2.1 RED: non-overlapping periods, no-period rejection, close/reopen preservation, stale `If-Match`, closed-write rejection.
- [x] 2.2 Implement `domain/periods.py`, `routes/periods.py`, period events, versioned mutation RPCs.
- [x] 2.3 RED: owner-only categories, archival retaining historic entries, blocked new assignment, ledger totals.
- [x] 2.4 Implement typed categories, separate income/expense routes/tables, ownership-aware validation.

## Phase 3A: Debts backend (schedules + installments)
- [x] 3A.1 RED `api/tests/unit/test_debts.py` — `add_months` clamp (Jan 31→Feb 28, leap Feb 29), next-period resolution, `installment_total_below_principal` (422).
- [x] 3A.2 RED integration — differential SQL-vs-Python schedule equality, idempotent repeat/concurrent generation (`UNIQUE(debt_id, ordinal)`), `no_later_period` (409), cross-user RLS 404.
- [x] 3A.3 Implement `api/app/domain/debts.py` — clamp math, validation, `DebtScheduleError.code`.
- [x] 3A.4 Implement `supabase/migrations/0006_debt_schedule_and_alerts.sql` — `generate_debt_schedule(p_debt_id)`, SECURITY INVOKER, locked, `on conflict do nothing` (debts part; alert_rules columns land in same file, see 3B.4).
- [x] 3A.5 Implement `api/app/routes/debts.py` — `POST/GET /v1/debts`, `GET /v1/debts/{id}`, `POST /v1/debts/{id}/schedule`.
- [x] 3A.6 Extend `FinanceGateway` (both impls) with debt/installment methods; extend `export_account`/`EXPORT_TABLES`.
- [x] 3A.7 Register debts router in `api/app/main.py`; run test command from Unit 3A.

## Phase 3B: Insights + alerts backend
- [x] 3B.1 RED `api/tests/unit/test_alerts.py` — threshold compare, category-scoped `expense_total`, `debt_due` by `due_on` range.
- [x] 3B.2 RED integration — insights totals, alert firing/no-fire, cross-user RLS on `alert_rules`/installments, no state mutation on GET.
- [x] 3B.3 Implement `api/app/domain/alerts.py` — pure period aggregation, `>=` threshold evaluation.
- [x] 3B.4 Extend `supabase/migrations/0006_debt_schedule_and_alerts.sql` — add `alert_rules.label`, `kind in ('expense_total','debt_due')`, nullable `category_id` FK (no `is_enabled`/`period_id`/`last_triggered_at`).
- [x] 3B.5 Implement `api/app/routes/alert_rules.py` (`POST/GET /v1/alert-rules`, `DELETE /v1/alert-rules/{id}`) and `api/app/routes/insights.py` (`GET /v1/insights?period_id=`).
- [x] 3B.6 Extend `FinanceGateway` with alert/insight methods; extend `export_account`.
- [x] 3B.7 Register routers in `api/app/main.py`; run test command from Unit 3B.

## Phase 3C: Web client (no build step)
- [x] 3C.1 Create `web/index.html` — accessible app shell, nav, main region.
- [x] 3C.2 Create `web/assets/styles.css` — ledger/period/debt/dashboard layouts.
- [x] 3C.3 Create `web/src/auth.js` (Supabase login/logout/session recovery) and `web/src/api.js` (JWT header, error mapping).
- [x] 3C.4 Create `web/src/state.js` — categories/periods/entries/debts/alerts, localStorage sync.
- [x] 3C.5 Create `web/src/views/income.js` and `expenses.js` — entry form/list/edit, minor units.
- [x] 3C.6 Create `web/src/views/periods.js` — create/list/close/reopen with `If-Match`.
- [x] 3C.7 Create `web/src/views/debts.js` — create debt, trigger `/schedule`, read-only installment list (no payment-status field exists on `debt_installments`).
- [x] 3C.8 Create `web/src/views/dashboard.js` — summary stats, debt-due summary, active alerts from `/v1/insights`.
- [x] 3C.9 Wire router/nav in `web/index.html` (via `web/src/app.js`); manual smoke test = `node --check` on every module (all pass); formal browser coverage lands in PR3D.

## Phase 3D: Playwright E2E
- [x] 3D.1 Create `web/tests/e2e/finance.spec.js` + auth fixture (login, clear state).
- [x] 3D.2 8 test suites written: login/session recovery, income+expense entry, period close/reopen, debt schedule+installment list, dashboard summary, alert-rule no-mutation-on-evaluate. Gated by `requireE2eHarness()` (mirrors `test_supabase_rls.py`'s opt-in pattern) — real RED-then-GREEN against a live stack requires the seeded disposable Supabase project this sandbox has no Docker daemon to run (see docs/phase-3-setup.md, PR3E).
- [x] 3D.3 `npx playwright test` run in this sandbox (chromium installed): all 8 correctly skip closed (no harness env configured) rather than failing against nothing — confirms discovery, fixture wiring, and the fail-closed gate all work; full execution needs the harness from 3E's setup doc.

## Phase 3E: Documentation
- [ ] 3E.1 Update `api/README.md` — migrations 0004–0006, RPC auth flow.
- [ ] 3E.2 Create `docs/phase-3-setup.md` — local Supabase, seed script, configured limits, export/recovery.
- [ ] 3E.3 Update root `README.md` — workbook is reference-only, never imported/deployed.
- [ ] 3E.4 Update `.gitignore` — Playwright reports, `.env.local`.
- [ ] 3E.5 Run `pytest -v` (api) and `npx playwright test` (web).

## Notes / Decisions Needed
- PR3C (~1,400 LOC) exceeds the 800-line budget by ~600; needs `size:exception` approval or a further split (auth+state+forms / views+dashboard) before apply.
- `0006_debt_schedule_and_alerts.sql` is one file per design; PR3B depends on PR3A merging first (shared migration).
- "auto-forecast" delivery strategy is not canonical (`ask-on-risk|auto-chain|single-pr|exception-ok`) — confirm intended value before apply.
