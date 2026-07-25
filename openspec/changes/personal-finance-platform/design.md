# Design: Personal Finance Platform

## Technical Approach

Build a small monorepo with a vanilla HTML/CSS/ES-module client, a FastAPI boundary, and Supabase Auth/PostgreSQL. The browser authenticates with Supabase, sends its access token to FastAPI, and never receives privileged credentials. FastAPI verifies the JWT, validates domain commands, and uses a request-scoped Supabase client carrying that same token; PostgreSQL row-level security (RLS), constraints, and transactional functions remain the final authorization and consistency boundary. The workbook stays reference-only.

## Architecture Decisions

| Decision | Choice | Alternatives / rationale |
|---|---|---|
| Service shape | Static web + modular FastAPI + managed PostgreSQL | A direct browser client is cheaper but scatters business rules; Django adds framework weight before domain fundamentals are learned. |
| Ownership | Every finance row has immutable `user_id`; RLS uses `auth.uid()`; cross-owner lookup returns the same 404 as missing data | API-only checks are insufficient defense for sensitive records. |
| Ledger model | Separate `income_entries` and `expense_entries`, backed by typed categories | Preserves the requested spreadsheet mental model and prevents invalid entry kinds without polymorphic checks. |
| Money/time | `bigint amount_minor`, profile ISO currency and decimal scale; `date` for financial dates, UTC timestamps for audit | Floating point is unsafe for money; dates avoid timezone shifts in budget boundaries. |
| Period semantics | User periods cannot overlap. Writes resolve exactly one open period; no match is rejected. A debt schedule requires a later defined period or returns 409 | Deterministic classification and “next period” scheduling require unambiguous boundaries. |
| Derived behavior | Dashboard and alerts are query-time aggregates; debt generation is one idempotent `SECURITY INVOKER` transaction with `UNIQUE(debt_id, ordinal)` | Avoids background workers/free-tier cost while preventing duplicate installments. |
| Concurrent edits | Mutable rows carry integer `version`; updates require `If-Match` and return 409 on stale versions | Spreadsheet-like editing otherwise risks silent lost updates. |

## Data Flow

    Browser ──Supabase login──> Auth
       │ Bearer JWT
       ▼
    FastAPI ──verified, user-scoped command──> Supabase REST/RPC
                                                   │
                                             RLS + constraints
                                                   ▼
                                               PostgreSQL
       ▲──DTO / 404 / 409──────── aggregates <─────┘

Closing/reopening a period appends `period_events`; entries are preserved. Archived categories remain readable but cannot be assigned. Alerts compare stored per-user rules with current aggregates.

## File Changes

| File | Action | Description |
|---|---|---|
| `web/index.html` | Create | Accessible application shell |
| `web/assets/styles.css` | Create | Ledger/dashboard layouts |
| `web/src/{auth,api,state}.js` | Create | Session, HTTP, and client state boundaries |
| `web/src/views/{income,expenses,periods,debts,dashboard}.js` | Create | Feature views |
| `api/pyproject.toml` | Create | FastAPI/runtime/test dependencies |
| `api/app/main.py` | Create | App factory, middleware, route registration |
| `api/app/core/{config,auth,errors}.py` | Create | Settings, JWT verification, stable errors |
| `api/app/domain/{money,periods,debts,alerts}.py` | Create | Pure rules |
| `api/app/routes/{profile,categories,income,expenses,periods,debts,insights,account}.py` | Create | HTTP adapters |
| `api/app/repositories/supabase.py` | Create | User-token data gateway |
| `supabase/migrations/0001_baseline.sql` | Create | Tables, indexes, constraints, RLS, RPCs |
| `api/tests/{unit,integration}/` | Create | Domain and database tests |
| `web/tests/e2e/finance.spec.js` | Create | Browser workflows |

## Interfaces / Contracts

Resources: `profiles`, `categories(kind,status)`, `budget_periods(status,version)`, `period_events`, separate ledgers, `debts`, `debt_installments`, and `alert_rules`. All IDs are UUIDs. Routes are under `/v1`; ledger CRUD is split between `/income` and `/expenses`; `POST /periods/{id}/close|reopen`, `POST /debts/{id}/schedule`, `GET /insights?period_id=`, `GET /account/export`, and `DELETE /account`. Errors use `{\"code\",\"message\",\"field_errors\",\"request_id\"}`; financial values cross JSON as integer minor units.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | Money, period transitions, next-period schedule, thresholds | Pytest table/property tests; no I/O |
| Integration | RLS isolation, archived categories, closed writes, RPC idempotency, version conflicts, export/delete | Local Supabase migrations with two users; test both API and constraints |
| E2E | Login, separate ledgers, close/reopen, dashboard, alert | Playwright against seeded disposable stack |

## Threat Matrix

| Boundary | Applicability | Design response / RED tests |
|---|---|---|
| Documentation-like paths | N/A — no executable classification |
| Git repository selection | N/A — no VCS automation |
| Commit state | N/A — no commit integration |
| Push state | N/A — no push integration |
| PR commands | N/A — no PR automation |

HTTP routing is covered by API integration tests; no matrix-defined shell/process boundary exists.

## Migration / Rollout

Apply the baseline migration to an empty project, then release slices in proposal order: identity, ledgers, periods, debts, insights. Seed only synthetic development data. Do not import or deploy the workbook. Each slice is independently removable without deleting persisted user rows; export is available before inviting additional users.

## Open Questions

None blocking. Hosting vendors and configured free-tier quotas remain deployment-time configuration, not domain behavior.

---

# Phase 3 Addendum: Debt Cadence and Alert Rules

Resolves the two gaps `sdd-explore` flagged. Schema statements below are verified against `supabase/migrations/0001_baseline.sql` and `0002_pr1_hardening.sql`.

## Correction to Inherited Assumptions

`debts` really is `(bank, principal_minor, installment_minor, installment_count, created_at)`. There is no `cadence_months`, `start_period_id`, `label`, `kind`, or `status`; `debt_installments` has no `status`; `alert_rules` has only `threshold_minor`. Any plan reusing those fields is invalid.

## Architecture Decisions

| Decision | Choice | Alternatives / rationale |
|---|---|---|
| Installment cadence | Fixed 1-calendar-month step from installment #1, with end-of-month clamping (Jan 31 → Feb 28) | A `cadence_months` column is speculative: no spec or workbook requirement configures it, and it can be added later with `default 1` without rewriting rows. Anchoring installments 2..N to `budget_periods` is rejected — user periods are arbitrary-length and future ones need not exist, which contradicts the "only a later period must exist" 409 rule. |
| Schedule anchor | RPC resolves it server-side: earliest `budget_periods.starts_on > debts.created_at::date`; none → `no_later_period` (409) | Passing the anchor from the client would let a caller bypass the "next period start" rule; resolving inside the locked transaction also closes the TOCTOU between reading periods and inserting. |
| Installment amount | Every installment carries `installment_minor` verbatim; creation rejects `installment_minor * installment_count < principal_minor` as `installment_total_below_principal` (422) | Distributing `principal_minor` with a remainder invents an interest-free amortization the workbook never describes, produces a final installment the user's bank never charges, and can compute values ≤ 0 that violate `check (amount_minor > 0)`. Excess over principal is legitimate interest/fees. |
| Where the math lives | Server-authoritative plpgsql RPC `generate_debt_schedule(p_debt_id)`; `domain/debts.py` mirrors it for unit tests and `InMemorySupabaseGateway` | Mirrors the accepted `close_period` convention (route pre-checks in Python, RPC re-checks in SQL). Duplication risk is pinned by a differential integration test asserting the SQL and Python schedules are byte-identical. |
| Alert rule shape | Add `label`, `kind in ('expense_total','debt_due')`, nullable `category_id`; reject `period_id`, `is_enabled`, `last_triggered_at` | `kind` is forced by "budget or debt conditions"; `label` by "identifies the condition". `period_id` is redundant — `GET /insights?period_id=` already scopes evaluation to the viewed period. `last_triggered_at` would make a GET mutate state to serve push-style dedup that is explicitly out of scope for in-app alerts. Dropping `is_enabled` also drops the PATCH route: delete-and-recreate covers it, and PR3 already forecasts High size risk. |
| Aggregates | Computed in Python from existing `list_entries(user_id, table, period_id)` plus one new installment-range read; no SQL view | Keeps Phase 3's only new SQL to the RPC and the `alert_rules` columns, and keeps aggregation unit-testable. Tradeoff: linear in entries per period, acceptable at personal-budget scale; a `period_totals` view is the documented escape hatch. |

Both rule kinds compare one minor-unit aggregate with `>=` against `threshold_minor`: `expense_total` sums `expense_entries` in the period (optionally one category), `debt_due` sums `debt_installments` whose `due_on` falls inside the period. Payment tracking (`installment.status`), `savings_below`, and multi-operator rules are out of scope.

## Data Flow

    POST /v1/debts/{id}/schedule
       │
       ▼
    routes/debts.py ──> gateway.generate_debt_schedule
                              │
                              ▼
             RPC (security invoker, search_path=public)
             lock debt ─> resolve next period ─> insert 1..N
             on conflict (debt_id, ordinal) do nothing
                              │
       ◀── installments ──────┘   404 debt_not_found | 409 no_later_period

    GET /v1/insights?period_id= ─> list_entries + installments in range
       ──> domain/alerts.evaluate(rules, aggregates) ──> triggered only

## File Changes

| File | Action | Description |
|---|---|---|
| `supabase/migrations/0006_debt_schedule_and_alerts.sql` | Create | `generate_debt_schedule` RPC; `alert_rules` gains `label`, `kind`, `category_id` with the composite `(user_id, category_id) -> categories(user_id, id)` FK from the 0002 pattern |
| `api/app/domain/debts.py` | Create | `add_months` clamp, next-period resolution, installment validation, `DebtScheduleError.code` |
| `api/app/domain/alerts.py` | Create | Pure period aggregation and threshold evaluation |
| `api/app/routes/debts.py` | Create | `POST/GET /v1/debts`, `GET /v1/debts/{id}`, `POST /v1/debts/{id}/schedule` |
| `api/app/routes/alert_rules.py` | Create | `POST/GET /v1/alert-rules`, `DELETE /v1/alert-rules/{id}` |
| `api/app/routes/insights.py` | Create | `GET /v1/insights?period_id=` |
| `api/app/repositories/supabase.py` | Modify | Extend `FinanceGateway` and both implementations in lockstep; keep `export_account` consistent with `EXPORT_TABLES` |
| `api/app/main.py` | Modify | Register three routers |
| `api/README.md` | Modify | Document migrations 0004–0006 (fixes existing 0004/0005 omission) |

## Interfaces

```
GET /v1/insights?period_id= ->
{ "period_id", "income_minor", "expense_minor", "balance_minor",
  "debt_due_minor", "by_category": [{"category_id","name","kind","total_minor"}],
  "alerts": [{"rule_id","label","kind","threshold_minor","actual_minor"}] }
```

Errors keep `{code, message, field_errors, request_id}`; `_ERROR_STATUS` maps `no_later_period` → 409 and `installment_total_below_principal` → 422.

## Testing Strategy (Phase 3)

| Layer | What | Approach |
|---|---|---|
| Unit | `add_months` clamping (Jan 31, leap-year Feb 29), next-period resolution, installment validation, threshold evaluation and category scoping | Pytest table tests, no I/O |
| Integration | Differential SQL-vs-Python schedule equality, repeat and concurrent generation duplicate-free, `no_later_period` 409, cross-user RLS on installments and rules, insights totals, alert firing | Local Supabase migrations, two users |
| E2E | Debt schedule and private alert in the dashboard | Playwright (task 3.4) |

## Migration / Rollout (Phase 3)

`0006` is additive. New `alert_rules` columns are added with defaults and the defaults are then dropped, so the migration is safe even on a non-empty table. Existing installment rows are untouched; the RPC only inserts missing ordinals.

## Open Questions

None blocking.
