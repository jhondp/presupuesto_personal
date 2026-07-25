-- Pin search_path on trigger functions to close the mutable-search_path
-- security advisory (schema-shadowing risk); mirrors delete_my_account's
-- existing `set search_path = public` pattern. Found via `supabase db
-- advisors` after applying 0001+0002 to a live project.

create or replace function public.immutable_user_id() returns trigger
language plpgsql set search_path = public as $$
begin
  if old.user_id is distinct from new.user_id then
    raise exception 'user_id is immutable';
  end if;
  return new;
end;
$$;

create or replace function public.touch_updated_at() returns trigger
language plpgsql set search_path = public as $$
begin new.updated_at = now(); return new; end;
$$;
