# Personal Finance Platform

A small private personal finance app: a FastAPI boundary in front of a
Supabase (PostgreSQL + Auth) project, and a vanilla HTML/CSS/ES-module web
client with no build step. Built under Spec-Driven Development (SDD); see
`CLAUDE.md` for the workflow this repository follows.

## Reference source, not a dependency

`example/Finanzas Personales 2026.xlsx` is the authoritative domain model
this project was designed from — 17 sheets documenting monthly income/expense
tracking, user workflows, and financial categories. **It is reference
material only: it is never imported, parsed, or deployed by any code in this
repository.** Spreadsheet import/workbook parity is an explicit non-goal
(see `openspec/specs/finance-platform/spec.md`'s Non-Goals section).

## What's implemented

| Phase | Scope |
|---|---|
| 1 | Identity, ownership/RLS, profile, currency, export, account deletion |
| 2 | Categories, separate income/expense ledgers, budget period lifecycle (create/close/reopen with optimistic concurrency) |
| 3 | Debt schedules (deterministic monthly cadence, idempotent generation), query-time insights/alerts, the web client, and Playwright E2E coverage |

## Getting started

- API: see `api/README.md` for local setup, migrations, and running tests.
- Phase 3 specifics (debt schedules, alerts, the web client, and the
  Playwright E2E harness): see `docs/phase-3-setup.md`.
- SDD artifacts (proposal, specs, design, tasks) live under
  `openspec/changes/personal-finance-platform/` while a change is in
  progress, and are merged into `openspec/specs/` once archived.

## Non-goals

Bank sync, payments, investments, taxes, currency conversion, shared
households/delegated access, email/push alerts, advanced forecasting, and
production availability guarantees are out of scope. See the spec's
Non-Goals section for the full list.
