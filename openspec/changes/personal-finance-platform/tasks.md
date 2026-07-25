# Tasks: Personal Finance Platform

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 2,000–3,200 authored lines |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 identity/data; PR 2 ledgers/periods; PR 3 debts/insights/UI |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

## Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Auth, RLS, profile, account safety | PR 1 | `cd api && pytest tests/integration/test_profile.py` | Local Supabase: two-user isolation/export/delete | `api/app/core`, profile/account routes, baseline auth tables |
| 2 | Categories, ledgers, period lifecycle | PR 2 | `cd api && pytest tests/unit tests/integration/test_ledgers.py` | Seeded API: close/reopen then entry write | category/ledger/period routes and tables |
| 3 | Debt schedules, insights, alerts, web | PR 3 | `cd web && npx playwright test finance.spec.js` | Seeded browser: schedule then dashboard/alert | debts/insights routes and feature views |

## Phase 1: Foundation
- [x] 1.1 Create `api/pyproject.toml`, app factory, config, stable errors, JWT verification, and request-scoped Supabase gateway.
- [x] 1.2 RED: add two-user API/RLS tests for indistinguishable missing/cross-owner 404 responses and no financial/secrets logging.
- [x] 1.3 Create `supabase/migrations/0001_baseline.sql` with UUID rows, immutable ownership, money/date fields, RLS, indexes, and constraints; make 1.2 pass.
- [x] 1.4 RED: test default CLP scale, user-only export/deletion, and configured-limit rejection preserving data.
- [x] 1.5 Implement `profile` and `account` routes plus profile defaults, export, deletion, and limit guard; refactor shared DTO validation.

## Phase 2: Ledgers and periods
- [x] 2.1 RED: unit/integration tests for non-overlapping periods, no-period rejection, close/reopen preservation, stale `If-Match`, and closed-write rejection.
- [x] 2.2 Implement period rules/routes/events and versioned period mutation in `domain/periods.py`, `routes/periods.py`, and migration RPCs.
- [x] 2.3 RED: test owner-only categories, archival retaining historic entries, blocked new assignment, valid income totals, and separate expense rows.
- [x] 2.4 Implement typed categories and separate income/expense routes, tables, and ownership-aware validation; refactor shared ledger DTOs.

## Phase 3: Debts, insights, and client
- [ ] 3.1 RED: unit/RPC tests for next-period installment dates, absent-later-period 409, duplicate-free repeated generation, and threshold alerts.
- [ ] 3.2 Implement debt transaction with `UNIQUE(debt_id, ordinal)`, insights aggregates, and alert-rule evaluation.
- [ ] 3.3 Create accessible `web/index.html`, styles, auth/api/state modules, and income, expense, period, debt, dashboard views using minor units.
- [ ] 3.4 RED then implement Playwright workflows: login, category/ledger entry, close/reopen, debt schedule, dashboard, and private alert.
- [ ] 3.5 Document local migration, synthetic seed, configured limits, export/recovery, and workbook exclusion in `README.md`; run API and E2E suites.
