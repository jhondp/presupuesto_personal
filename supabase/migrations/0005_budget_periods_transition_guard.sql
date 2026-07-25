-- close_period/reopen_period (0004) are `security invoker`, so they carry
-- no privilege beyond what the owner's own RLS policy on budget_periods
-- already grants ("own periods only" ... for all using/with check
-- user_id = auth.uid()). That policy still lets an authenticated owner
-- PATCH budget_periods.status/version directly via PostgREST, bypassing
-- the RPCs' transition/version validation and writing no period_events
-- row. A trigger is the only enforcement point that applies regardless of
-- how the UPDATE is issued (RPC or direct client PATCH).

begin;

create or replace function public.guard_period_transition() returns trigger
language plpgsql set search_path = public as $$
begin
  if new.status is distinct from old.status then
    if not (
      (old.status = 'open' and new.status = 'closed') or
      (old.status = 'closed' and new.status = 'open')
    ) then
      raise exception 'invalid_transition';
    end if;
    if new.version <> old.version + 1 then
      raise exception 'version_conflict';
    end if;
  elsif new.version is distinct from old.version then
    -- version must never move except alongside a valid status transition.
    raise exception 'invalid_transition';
  end if;
  return new;
end;
$$;

create trigger budget_periods_guard_transition
  before update on public.budget_periods
  for each row execute function public.guard_period_transition();

commit;
