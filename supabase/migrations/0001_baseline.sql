-- Baseline identity and ownership schema. Apply only to an empty Supabase project.
create extension if not exists pgcrypto;

create table public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  currency_code text not null default 'CLP' check (currency_code in ('CLP', 'USD', 'EUR')),
  decimal_scale smallint not null default 0 check (decimal_scale between 0 and 4),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((currency_code = 'CLP' and decimal_scale = 0) or (currency_code in ('USD', 'EUR') and decimal_scale = 2))
);

create table public.categories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  name text not null check (char_length(trim(name)) between 1 and 100),
  kind text not null check (kind in ('income', 'expense')),
  status text not null default 'active' check (status in ('active', 'archived')),
  created_at timestamptz not null default now(),
  unique (user_id, kind, name)
);

create table public.budget_periods (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  starts_on date not null,
  ends_on date not null check (ends_on >= starts_on),
  status text not null default 'open' check (status in ('open', 'closed')),
  version integer not null default 1 check (version > 0),
  created_at timestamptz not null default now(),
  unique (user_id, starts_on, ends_on)
);

create table public.income_entries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  category_id uuid references public.categories(id) on delete restrict,
  period_id uuid references public.budget_periods(id) on delete restrict,
  amount_minor bigint not null check (amount_minor > 0),
  occurred_on date not null,
  note text check (char_length(note) <= 1000),
  created_at timestamptz not null default now()
);

create table public.expense_entries (like public.income_entries including all);
alter table public.expense_entries alter column id set default gen_random_uuid();

create table public.debts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  bank text not null check (char_length(trim(bank)) between 1 and 100),
  principal_minor bigint not null check (principal_minor > 0),
  installment_minor bigint not null check (installment_minor > 0),
  installment_count integer not null check (installment_count > 0),
  created_at timestamptz not null default now()
);

create table public.debt_installments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  debt_id uuid not null references public.debts(id) on delete cascade,
  ordinal integer not null check (ordinal > 0),
  due_on date not null,
  amount_minor bigint not null check (amount_minor > 0),
  unique (debt_id, ordinal)
);

create table public.alert_rules (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  threshold_minor bigint not null check (threshold_minor > 0),
  created_at timestamptz not null default now()
);

create index categories_owner_idx on public.categories(user_id);
create index budget_periods_owner_idx on public.budget_periods(user_id, starts_on);
create index income_entries_owner_idx on public.income_entries(user_id, occurred_on);
create index expense_entries_owner_idx on public.expense_entries(user_id, occurred_on);
create index debts_owner_idx on public.debts(user_id);
create index debt_installments_owner_idx on public.debt_installments(user_id, due_on);

create or replace function public.immutable_user_id() returns trigger language plpgsql as $$
begin
  if old.user_id is distinct from new.user_id then
    raise exception 'user_id is immutable';
  end if;
  return new;
end;
$$;

create or replace function public.touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;

create trigger profiles_immutable_owner before update on public.profiles for each row execute function public.immutable_user_id();
create trigger categories_immutable_owner before update on public.categories for each row execute function public.immutable_user_id();
create trigger periods_immutable_owner before update on public.budget_periods for each row execute function public.immutable_user_id();
create trigger income_immutable_owner before update on public.income_entries for each row execute function public.immutable_user_id();
create trigger expense_immutable_owner before update on public.expense_entries for each row execute function public.immutable_user_id();
create trigger debts_immutable_owner before update on public.debts for each row execute function public.immutable_user_id();
create trigger installments_immutable_owner before update on public.debt_installments for each row execute function public.immutable_user_id();
create trigger alerts_immutable_owner before update on public.alert_rules for each row execute function public.immutable_user_id();
create trigger profiles_touch_updated_at before update on public.profiles for each row execute function public.touch_updated_at();

-- RLS is the final ownership boundary; every finance table is visible only to auth.uid().
alter table public.profiles enable row level security;
alter table public.categories enable row level security;
alter table public.budget_periods enable row level security;
alter table public.income_entries enable row level security;
alter table public.expense_entries enable row level security;
alter table public.debts enable row level security;
alter table public.debt_installments enable row level security;
alter table public.alert_rules enable row level security;

create policy "own profile only" on public.profiles for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "own categories only" on public.categories for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "own periods only" on public.budget_periods for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "own income only" on public.income_entries for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "own expenses only" on public.expense_entries for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "own debts only" on public.debts for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "own installments only" on public.debt_installments for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "own alerts only" on public.alert_rules for all using (user_id = auth.uid()) with check (user_id = auth.uid());

create or replace function public.delete_my_account() returns void
language plpgsql security invoker set search_path = public as $$
begin
  delete from public.profiles where user_id = auth.uid();
end;
$$;
