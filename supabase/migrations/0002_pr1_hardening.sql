-- PR1 hardening: restore expense-table foreign keys and add ownership-aware
-- composite foreign keys so a child row can never reference a parent row
-- owned by a different user. Apply after 0001_baseline.sql on the same
-- empty Supabase project; 0001 is kept as historical record and is not
-- edited.

begin;

-- Fix 1 (+ ownership parity): `create table expense_entries (like
-- income_entries including all)` never copied foreign key constraints —
-- Postgres LIKE does not copy FKs regardless of INCLUDING ALL/CONSTRAINTS.
-- That silently dropped BOTH the ownership FK (user_id -> profiles) and the
-- category/period FKs that income_entries has. Restore the ownership FK
-- directly; category_id/period_id are restored as ownership-aware composite
-- FKs below (Fix 2), since expense_entries never had plain FKs to begin
-- with.
alter table public.expense_entries
  add constraint expense_entries_user_id_fkey
    foreign key (user_id) references public.profiles(user_id) on delete cascade;

-- Fix 2: a plain FK (e.g. income_entries.category_id -> categories.id) only
-- proves the category exists, not that it belongs to the same owner as the
-- entry. Add composite unique constraints on the parent tables so a
-- composite FK can enforce (user_id, child_fk) -> (user_id, parent_id).
alter table public.categories
  add constraint categories_user_id_id_key unique (user_id, id);
alter table public.budget_periods
  add constraint budget_periods_user_id_id_key unique (user_id, id);
alter table public.debts
  add constraint debts_user_id_id_key unique (user_id, id);

-- Drop the plain (non-owner-aware) single-column FKs that 0001 created on
-- income_entries.category_id, income_entries.period_id, and
-- debt_installments.debt_id. Names are discovered dynamically via
-- pg_constraint instead of hardcoded, since the default
-- `<table>_<column>_fkey` naming is a convention, not a guarantee.
do $$
declare
  target record;
  fk_name text;
begin
  for target in
    select * from (values
      ('public.income_entries'::regclass, 'category_id'),
      ('public.income_entries'::regclass, 'period_id'),
      ('public.debt_installments'::regclass, 'debt_id')
    ) as t(rel, col)
  loop
    select con.conname into fk_name
    from pg_constraint con
    join pg_attribute att
      on att.attrelid = con.conrelid
     and att.attnum = con.conkey[1]
    where con.contype = 'f'
      and con.conrelid = target.rel
      and array_length(con.conkey, 1) = 1
      and att.attname = target.col;

    if fk_name is not null then
      execute format('alter table %s drop constraint %I', target.rel::text, fk_name);
    end if;
  end loop;
end;
$$;

-- Composite, ownership-aware foreign keys. MATCH SIMPLE (the Postgres
-- default) means the constraint is only checked when ALL referencing
-- columns are non-null, so category_id/period_id remain independently
-- nullable exactly as in 0001 — a null category_id or period_id is still
-- accepted without requiring the other to be null too.
alter table public.income_entries
  add constraint income_entries_category_owner_fkey
    foreign key (user_id, category_id) references public.categories(user_id, id) on delete restrict,
  add constraint income_entries_period_owner_fkey
    foreign key (user_id, period_id) references public.budget_periods(user_id, id) on delete restrict;

alter table public.expense_entries
  add constraint expense_entries_category_owner_fkey
    foreign key (user_id, category_id) references public.categories(user_id, id) on delete restrict,
  add constraint expense_entries_period_owner_fkey
    foreign key (user_id, period_id) references public.budget_periods(user_id, id) on delete restrict;

alter table public.debt_installments
  add constraint debt_installments_debt_owner_fkey
    foreign key (user_id, debt_id) references public.debts(user_id, id) on delete cascade;

-- Fix 3 (documentation only, no schema change): `delete_my_account()` still
-- only deletes the caller's `profiles` row, which cascades to all finance
-- data via the existing ON DELETE CASCADE chain — that behavior is correct
-- and unchanged. What was missing is removal of the `auth.users` row, so the
-- same still-valid JWT could call `ensure_profile` again and silently
-- recreate an empty profile. That gap is closed at the application layer
-- (SupabaseGateway.delete_account uses a service-role client to call
-- `auth.admin.delete_user`), not in SQL, since RPCs running under
-- `security invoker` cannot reach the `auth.users` table.

commit;
