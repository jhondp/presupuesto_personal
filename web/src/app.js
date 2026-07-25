// App shell bootstrap: wires Supabase auth state to the nav/view switch and
// a tiny hash router. This is the only module index.html loads directly.
import { getSession, onAuthStateChange, signIn, signOut } from "./auth.js";
import { api } from "./api.js";
import { getState, resetState, setState } from "./state.js";
import { refreshIncome, renderIncome } from "./views/income.js";
import { refreshExpenses, renderExpenses } from "./views/expenses.js";
import { refreshPeriods, renderPeriods } from "./views/periods.js";
import { refreshDebts, renderDebts } from "./views/debts.js";
import { refreshInsights, renderDashboard } from "./views/dashboard.js";

const authView = document.getElementById("auth-view");
const appView = document.getElementById("app-view");
const nav = document.querySelector(".app-nav");
const viewRoot = document.getElementById("view-root");
const signOutButton = document.getElementById("sign-out-button");
const authForm = document.getElementById("auth-form");
const authError = document.getElementById("auth-error");

const routes = {
  dashboard: renderDashboard,
  income: renderIncome,
  expenses: renderExpenses,
  periods: renderPeriods,
  debts: renderDebts,
};

function currentRoute() {
  const hash = window.location.hash.replace(/^#\/?/, "");
  return routes[hash] ? hash : "dashboard";
}

function renderRoute() {
  const token = getState().session?.access_token;
  if (!token) return;
  routes[currentRoute()](viewRoot, token);
}

async function loadAccountData(token) {
  const categories = await api.get("/v1/categories", { token });
  setState({ categories });
  await Promise.all([refreshIncome(token), refreshExpenses(token), refreshPeriods(token), refreshDebts(token)]);
  const { periods } = getState();
  const openPeriod = periods.find((period) => period.status === "open") || periods[0];
  if (openPeriod) await refreshInsights(token, openPeriod.id);
}

async function showAuthenticated(session) {
  setState({ session });
  authView.hidden = true;
  appView.hidden = false;
  nav.hidden = false;
  signOutButton.hidden = false;
  await loadAccountData(session.access_token);
  renderRoute();
}

function showSignedOut() {
  resetState();
  authView.hidden = false;
  appView.hidden = true;
  nav.hidden = true;
  signOutButton.hidden = true;
}

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authError.textContent = "";
  const email = document.getElementById("auth-email").value;
  const password = document.getElementById("auth-password").value;
  try {
    const session = await signIn(email, password);
    await showAuthenticated(session);
  } catch (error) {
    authError.textContent = error.message || "Sign-in failed";
  }
});

signOutButton.addEventListener("click", () => {
  signOut();
});

// The single source of truth for auth state: fires on sign-in, sign-out,
// and token refresh, so both the initial load and every later transition
// go through this one handler instead of duplicating the same logic.
onAuthStateChange((session) => {
  if (session) showAuthenticated(session);
  else showSignedOut();
});

window.addEventListener("hashchange", renderRoute);

// Session recovery on first load/reload of the tab.
getSession().then((session) => {
  if (session) showAuthenticated(session);
  else showSignedOut();
});
