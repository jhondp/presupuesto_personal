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
