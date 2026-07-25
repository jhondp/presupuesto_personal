# Local Development Scripts

## Quick Start

### 1. First Time Setup

```bash
cd scripts
chmod +x setup-local.sh
./setup-local.sh
```

This will:
- Ask for Supabase credentials (URL, Anon Key, JWT Secret)
- Create `.env` file in `api/`
- Install Python dependencies
- Guide you through applying SQL migrations
- Update `web/index.html` with your Supabase credentials

### 2. Get Supabase Credentials

1. Go to https://supabase.com
2. Sign in (free account)
3. Create a new project (free tier)
4. Copy these values from the project settings:
   - `SUPABASE_URL` → Project URL
   - `SUPABASE_ANON_KEY` → API keys → anon (public)
   - `SUPABASE_JWT_SECRET` → Project settings → API → JWT secret

⚠️ **NEVER** use the `service_role` key in the browser or `.env`

### 3. Apply Migrations (One-time)

After `setup-local.sh` prompts you:

1. Open Supabase Dashboard → SQL Editor
2. For each file in `supabase/migrations/` (in order):
   ```
   0001_baseline.sql
   0002_pr1_hardening.sql
   0003_pin_function_search_path.sql
   0004_period_lifecycle.sql
   0005_budget_periods_transition_guard.sql
   0006_debt_schedule_and_alerts.sql
   ```
3. Copy the **entire file content** → paste in SQL Editor → click "Run"
4. Confirm in `setup-local.sh` when done

### 4. Start the Application

```bash
cd scripts
./run-local.sh
```

This will start:
- **Backend (FastAPI)** on `http://localhost:8000`
- **Frontend** on `http://localhost:4173`

Open `http://localhost:4173` in your browser

### 5. Sign Up & Test

1. Click "Sign up"
2. Enter email + password
3. Confirm email (check Supabase dashboard → Authentication if needed)
4. Log in
5. Create a category → budget period → add entries
6. Try debts, alerts, dashboard

---

## Detailed Instructions

### Applying Migrations Manually

If `setup-local.sh` doesn't run migrations automatically:

1. **Open Supabase Dashboard**
   - Go to https://supabase.com
   - Select your project
   - Click "SQL Editor" (left sidebar)

2. **Create New Query** for each migration file

3. **Copy file content** from your local repo:
   - `supabase/migrations/0001_baseline.sql`
   - Paste into SQL Editor
   - Click "Run"
   - Repeat for `0002_`, `0003_`, `0004_`, `0005_`, `0006_`

4. **No errors?** Great! Migrations applied ✓

### Manual Backend Start (without script)

```bash
cd api
source .venv/bin/activate
uvicorn app.main:app --reload
```

Backend available at `http://localhost:8000/docs` (interactive API docs)

### Manual Frontend Start (without script)

```bash
cd web
python3 -m http.server 4173
```

Frontend available at `http://localhost:4173`

---

## Troubleshooting

### "python3: command not found"
Install Python 3.12+:
```bash
# macOS
brew install python@3.12

# Ubuntu/Debian
sudo apt install python3.12 python3.12-venv

# Windows
# Download from python.org
```

### ".env file not found"
Run `setup-local.sh` in the `scripts/` directory (not `api/`)

### "ConnectionError: can't connect to Supabase"
- Check `SUPABASE_URL` is correct (should be `https://xxxxx.supabase.co`)
- Verify `SUPABASE_ANON_KEY` is the **public** key, not service_role
- Ensure migrations are applied (see "Applying Migrations" above)

### "Sign up button doesn't work"
- Check `web/index.html` has `window.__ENV__` filled in with Supabase credentials
- Open browser console (F12) → check for errors
- Verify `API_BASE_URL` is `http://localhost:8000`

### "Backend starts but frontend can't connect"
- Make sure both are running (check terminal output)
- Frontend needs backend at `http://localhost:8000`
- API_BASE_URL in `web/index.html` should be `http://localhost:8000`

---

## Environment Variables

If you need to change config after setup, edit `api/.env`:

```bash
# Required
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJhbGc...
SUPABASE_JWT_SECRET=your-jwt-secret

# Optional
MAX_EXPORT_ROWS=10000  # Free-tier limit protection
```

---

## Test Data

After signing up:

1. **Create Category**: "Salary", "Food", "Transport", etc.
2. **Create Period**: "July 2026", "August 2026"
3. **Add Income**: $2000 salary in July
4. **Add Expense**: $100 food, $50 transport
5. **Create Debt**: $1000 loan, 3 monthly installments
6. **View Dashboard**: See summary + alerts

---

## Clean Slate

To start fresh:

1. Delete the Supabase project (⚠️ this deletes all data)
2. Create a new project
3. Re-run `setup-local.sh` with new credentials
4. Re-apply all migrations

Or just sign up a new user in the same project (separate data per user).

---

## Next Steps

- Read `api/README.md` for API details
- Read `docs/phase-3-setup.md` for Phase 3 features
- Explore the code: `api/app/routes/`, `web/src/views/`
- Check tests: `cd api && pytest -v`

Enjoy! 🚀
