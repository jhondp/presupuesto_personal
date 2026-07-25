// In-memory application state with a localStorage mirror for instant reload
// (categories/periods/entries), and a small pub-sub so views re-render on
// change. The Supabase session/access token is deliberately excluded from
// the persisted snapshot — Supabase's own client already persists the
// session more safely, and this app never needs to read a stale token back
// out of localStorage.

const STORAGE_KEY = "finance-app-state-v1";

const defaults = {
  categories: [],
  periods: [],
  income: [],
  expenses: [],
  debts: [],
  installmentsByDebt: {},
  alertRules: [],
  insights: null,
  view: "dashboard",
};

let state = { ...defaults, session: null };
const listeners = new Set();

function loadPersisted() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    state = { ...state, ...saved };
  } catch {
    // Corrupt or unavailable storage — fall back to defaults silently.
  }
}

function persist() {
  try {
    const { session, ...persisted } = state;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(persisted));
  } catch {
    // Storage full/unavailable/disabled — the app still works in memory.
  }
}

loadPersisted();

export function getState() {
  return state;
}

export function setState(patch) {
  state = { ...state, ...patch };
  persist();
  for (const listener of listeners) listener(state);
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function resetState() {
  state = { ...defaults, session: null };
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
  for (const listener of listeners) listener(state);
}
