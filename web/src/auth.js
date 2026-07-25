// Supabase Auth boundary: the browser authenticates directly with Supabase
// and only ever sends the resulting access token to FastAPI (see design.md's
// data-flow decision) — the anon key here is safe to ship to the browser,
// unlike the service-role key, which never appears in this codebase.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const env = window.__ENV__ || {};

export const supabase = createClient(env.SUPABASE_URL || "", env.SUPABASE_ANON_KEY || "");

export async function signIn(email, password) {
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw error;
  return data.session;
}

export async function signOut() {
  await supabase.auth.signOut();
}

/** Recovers a persisted session on page load/reload without a fresh login. */
export async function getSession() {
  const { data } = await supabase.auth.getSession();
  return data.session;
}

/** Fires on sign-in, sign-out, and token refresh, so callers always hold a
 * live access token instead of a stale one captured at page load. */
export function onAuthStateChange(callback) {
  const { data } = supabase.auth.onAuthStateChange((_event, session) => callback(session));
  return () => data.subscription.unsubscribe();
}
