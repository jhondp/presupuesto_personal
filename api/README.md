# Personal Finance API

## Local setup

1. Create and activate a Python 3.12 virtual environment.
2. Install dependencies: `pip install -e '.[dev]'` from this directory.
3. Copy deployment values into `.env`: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_JWT_SECRET`. Never put these three, or the browser, anywhere near the service-role key.
4. Set `SUPABASE_SERVICE_ROLE_KEY` as a server-only secret (never sent to a browser, never in client bundles). It is used exclusively inside `SupabaseGateway.delete_account`, via a short-lived client constructed fresh for that one call, to remove the caller's `auth.users` row through the Supabase Admin API after the RLS-scoped finance-data cleanup — every other gateway method keeps using the anon-key + user-JWT client so RLS stays the enforcement boundary. If unset, account deletion fails closed with `503 account_deletion_not_configured` before touching any data.
5. Apply `../supabase/migrations/0001_baseline.sql`, `0002_pr1_hardening.sql`, and `0003_pin_function_search_path.sql` in order to an empty Supabase project.
6. Run focused foundation tests: `pytest tests/integration/test_profile.py`.
7. Start locally: `uvicorn app.main:app --reload`.

`MAX_EXPORT_ROWS` is a deployment-time free-tier protection; rejected exports do not delete or alter records. Every gateway operation runs under the verified caller's Supabase JWT and RLS, except the auth-user removal step of account deletion, which is the one place the service-role key is used. Use synthetic data only; the spreadsheet under `example/` is reference material and is not imported or deployed.

## Disposable Supabase RLS validation

The local API tests use an ASGI transport rather than Starlette `TestClient`: this avoids the Python 3.14 worker-thread hang observed for synchronous request handlers. Run the focused suite with `./.venv/bin/python -m pytest tests/integration/test_profile.py tests/integration/test_supabase_rls.py -q`.

`test_supabase_rls.py` is deliberately skipped unless all of `SUPABASE_TEST_URL`, `SUPABASE_TEST_ANON_KEY`, `SUPABASE_TEST_SERVICE_ROLE_KEY`, `SUPABASE_TEST_JWT_SECRET`, and `SUPABASE_TEST_ALLOW_DESTRUCTIVE=true` are set. It creates and deletes two temporary Auth users, validates direct RLS isolation, and exercises API export/deletion against the disposable project. Never point these variables at a shared or production project.
