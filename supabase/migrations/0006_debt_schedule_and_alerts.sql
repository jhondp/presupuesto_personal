-- Phase 3A: deterministic, idempotent debt installment scheduling.
-- `debts`, `debt_installments`, and `alert_rules` already exist with the
-- corrected shape from 0001_baseline.sql (no `cadence_months`/`label`/`kind`/
-- `status` columns on debts; no `status` on debt_installments). This file
-- only adds the schedule-generation RPC; `alert_rules` gains its `label`/
-- `kind`/`category_id` columns in a later revision of this same file (PR3B),
-- per design.md's Phase 3 addendum.

begin;

-- Adds whole calendar months to `p_date`, clamping the day to the target
-- month's length (Jan 31 + 1 month -> Feb 28, leap Feb 29 preserved when the
-- source day is <= 29). Mirrors `app.domain.debts.add_months` exactly so a
-- differential test can assert the two never disagree.
create or replace function public.add_months_clamped(p_date date, p_months integer)
returns date
language plpgsql immutable set search_path = public as $$
declare
  v_total_months integer;
  v_year integer;
  v_month integer;
  v_day integer;
  v_last_day integer;
begin
  v_total_months := (extract(year from p_date)::integer * 12 + extract(month from p_date)::integer - 1) + p_months;
  v_year := v_total_months / 12;
  v_month := v_total_months % 12 + 1;
  v_last_day := extract(day from ((make_date(v_year, v_month, 1) + interval '1 month') - interval '1 day'))::integer;
  v_day := least(extract(day from p_date)::integer, v_last_day);
  return make_date(v_year, v_month, v_day);
end;
$$;

-- Generates (or, on repeat calls, completes) a debt's installment schedule.
-- `security invoker` + `for update` means this carries no privilege beyond
-- the caller's own RLS-granted access, and a locked read prevents two
-- concurrent calls from resolving different anchor periods for the same
-- debt. `on conflict (debt_id, ordinal) do nothing` (see the 0001 unique
-- constraint) makes repeat generation a no-op rather than a duplicate error.
create or replace function public.generate_debt_schedule(p_debt_id uuid)
returns setof public.debt_installments
language plpgsql security invoker set search_path = public as $$
declare
  v_debt public.debts;
  v_start date;
  i integer;
begin
  select * into v_debt from public.debts
    where id = p_debt_id and user_id = auth.uid()
    for update;
  if not found then
    raise exception 'debt_not_found';
  end if;

  select starts_on into v_start from public.budget_periods
    where user_id = auth.uid() and starts_on > v_debt.created_at::date
    order by starts_on asc
    limit 1;
  if v_start is null then
    raise exception 'no_later_period';
  end if;

  for i in 1..v_debt.installment_count loop
    insert into public.debt_installments (user_id, debt_id, ordinal, due_on, amount_minor)
      values (auth.uid(), p_debt_id, i, public.add_months_clamped(v_start, i - 1), v_debt.installment_minor)
      on conflict (debt_id, ordinal) do nothing;
  end loop;

  return query
    select * from public.debt_installments
      where debt_id = p_debt_id and user_id = auth.uid()
      order by ordinal;
end;
$$;

commit;
