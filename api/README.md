# Personal Finance API

## Local setup

1. Create and activate a Python 3.12 virtual environment.
2. Install dependencies: `pip install -e '.[dev]'` from this directory.
3. Copy deployment values into `.env`: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_JWT_SECRET`. Never put these three, or the browser, anywhere near the service-role key.
4. Set `SUPABASE_SERVICE_ROLE_KEY` as a server-only secret (never sent to a browser, never in client bundles). It is used exclusively inside `SupabaseGateway.delete_account`, via a short-lived client constructed fresh for that one call, to remove the caller's `auth.users` row through the Supabase Admin API after the RLS-scoped finance-data cleanup — every other gateway method keeps using the anon-key + user-JWT client so RLS stays the enforcement boundary. If unset, account deletion fails closed with `503 account_deletion_not_configured` before touching any data.
5. Apply every file in `../supabase/migrations/` **in order** to an empty Supabase project: `0001_baseline.sql`, `0002_pr1_hardening.sql`, `0003_pin_function_search_path.sql`, `0004_period_lifecycle.sql`, `0005_budget_periods_transition_guard.sql`, `0006_debt_schedule_and_alerts.sql`.
6. Run focused foundation tests: `pytest tests/integration/test_profile.py`.
7. Start locally: `uvicorn app.main:app --reload`.

## Migrations 0004–0006 (Phase 2 and 3)

| File | Adds |
|---|---|
| `0004_period_lifecycle.sql` | `period_events` audit table; `close_period(p_period_id, p_expected_version)` and `reopen_period(...)` RPCs — atomic, ownership-scoped (`security invoker`, `auth.uid()`), version-checked transitions that write the transition and its audit row in one transaction. |
| `0005_budget_periods_transition_guard.sql` | `guard_period_transition()` trigger on `budget_periods` — the RPCs above carry no privilege beyond the caller's own RLS grant, so a client could otherwise `PATCH budget_periods` directly via PostgREST and bypass the RPCs' status/version rules entirely; the trigger enforces the same rules regardless of how the row is written. |
| `0006_debt_schedule_and_alerts.sql` | `add_months_clamped(p_date, p_months)` and `generate_debt_schedule(p_debt_id)` RPCs (deterministic, idempotent debt installment scheduling — see "RPC auth flow" below); `alert_rules.label`/`kind`/`category_id` columns with an ownership-aware composite FK. |

### RPC auth flow

Every RPC in this API (`close_period`, `reopen_period`, `generate_debt_schedule`) is declared `security invoker`, not `security definer`: it runs with exactly the privileges the calling `SupabaseGateway` client already has — the same anon-key-plus-user-JWT client every other gateway method uses, never an elevated one. Each RPC re-derives the caller's identity from `auth.uid()` (never a client-supplied user id) and re-checks ownership, current status, and — where relevant — an expected version *inside* a row-locked (`for update`) read, so two concurrent calls for the same row can never both succeed on stale state. `SupabaseGateway` maps each RPC's exact `raise exception '...'` message (e.g. `period_not_found`, `version_conflict`, `debt_not_found`, `no_later_period`) to the matching domain-layer error or a `None` return — see `_transition_period` and `generate_debt_schedule` in `app/repositories/supabase.py`. Match the exact message string, not a loose substring: an unrecognized error must re-raise instead of being mislabeled as a different conflict.

`MAX_EXPORT_ROWS` is a deployment-time free-tier protection; rejected exports do not delete or alter records. Every gateway operation runs under the verified caller's Supabase JWT and RLS, except the auth-user removal step of account deletion, which is the one place the service-role key is used. Use synthetic data only; the spreadsheet under `example/` is reference material and is not imported or deployed.

## Disposable Supabase RLS validation

The local API tests use an ASGI transport rather than Starlette `TestClient`: this avoids the Python 3.14 worker-thread hang observed for synchronous request handlers. Run the focused suite with `./.venv/bin/python -m pytest tests/integration/test_profile.py tests/integration/test_supabase_rls.py -q`.

`test_supabase_rls.py` is deliberately skipped unless all of `SUPABASE_TEST_URL`, `SUPABASE_TEST_ANON_KEY`, `SUPABASE_TEST_SERVICE_ROLE_KEY`, `SUPABASE_TEST_JWT_SECRET`, and `SUPABASE_TEST_ALLOW_DESTRUCTIVE=true` are set. It creates and deletes two temporary Auth users, validates direct RLS isolation, and exercises API export/deletion against the disposable project. Never point these variables at a shared or production project.
