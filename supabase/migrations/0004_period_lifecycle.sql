-- Phase 2: period_events audit trail plus atomic, ownership-scoped
-- close/reopen RPCs, so a period's status/version transition and its event
-- record are written in one transaction. Apply after 0001-0003 on the same
-- project; those files are historical record and are not edited.

begin;

create table public.period_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  period_id uuid not null,
  event_type text not null check (event_type in ('closed', 'reopened')),
  from_version integer not null check (from_version > 0),
  to_version integer not null check (to_version > from_version),
  occurred_at timestamptz not null default now(),
  -- Composite, ownership-aware FK (mirrors 0002_pr1_hardening.sql): a plain
  -- FK on period_id alone only proves the period exists, not that it
  -- belongs to this row's user_id. Without this, RLS's insert policy below
  -- (`user_id = auth.uid()`) would let an authenticated caller insert a
  -- period_events row directly via PostgREST — bypassing close_period/
  -- reopen_period entirely — with period_id pointing at another user's
  -- period, since RLS never checks that period_id and user_id agree.
  constraint period_events_period_owner_fkey
    foreign key (user_id, period_id) references public.budget_periods(user_id, id) on delete cascade
);

create index period_events_owner_idx on public.period_events(user_id, period_id, occurred_at);

alter table public.period_events enable row level security;
-- Owners may read their own event history; rows are only ever written by
-- close_period/reopen_period below (never directly by a client), so those
-- functions need their own insert policy.
create policy "own period events only" on public.period_events for select using (user_id = auth.uid());
create policy "insert own period events" on public.period_events for insert with check (user_id = auth.uid());

create or replace function public.close_period(p_period_id uuid, p_expected_version integer)
returns public.budget_periods
language plpgsql security invoker set search_path = public as $$
declare
  v_period public.budget_periods;
begin
  select * into v_period from public.budget_periods
    where id = p_period_id and user_id = auth.uid()
    for update;
  if not found then
    raise exception 'period_not_found';
  end if;
  if v_period.status <> 'open' then
    raise exception 'period_already_closed';
  end if;
  if v_period.version <> p_expected_version then
    raise exception 'version_conflict';
  end if;

  update public.budget_periods
    set status = 'closed', version = version + 1
    where id = p_period_id
    returning * into v_period;

  insert into public.period_events (user_id, period_id, event_type, from_version, to_version)
    values (auth.uid(), p_period_id, 'closed', p_expected_version, v_period.version);

  return v_period;
end;
$$;

create or replace function public.reopen_period(p_period_id uuid, p_expected_version integer)
returns public.budget_periods
language plpgsql security invoker set search_path = public as $$
declare
  v_period public.budget_periods;
begin
  select * into v_period from public.budget_periods
    where id = p_period_id and user_id = auth.uid()
    for update;
  if not found then
    raise exception 'period_not_found';
  end if;
  if v_period.status <> 'closed' then
    raise exception 'period_already_open';
  end if;
  if v_period.version <> p_expected_version then
    raise exception 'version_conflict';
  end if;

  update public.budget_periods
    set status = 'open', version = version + 1
    where id = p_period_id
    returning * into v_period;

  insert into public.period_events (user_id, period_id, event_type, from_version, to_version)
    values (auth.uid(), p_period_id, 'reopened', p_expected_version, v_period.version);

  return v_period;
end;
$$;

commit;
