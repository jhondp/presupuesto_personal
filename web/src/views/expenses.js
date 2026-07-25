import { api } from "../api.js";
import { setState } from "../state.js";
import { renderLedgerView } from "./_ledgerView.js";

export async function refreshExpenses(token) {
  const entries = await api.get("/v1/expenses", { token });
  setState({ expenses: entries });
}

export function renderExpenses(container, token) {
  renderLedgerView(container, {
    kind: "expense",
    apiPrefix: "expenses",
    stateKey: "expenses",
    token,
    onChange: async () => {
      await refreshExpenses(token);
      renderExpenses(container, token);
    },
  });
}
