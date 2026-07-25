import { api } from "../api.js";
import { setState } from "../state.js";
import { renderLedgerView } from "./_ledgerView.js";

export async function refreshIncome(token) {
  const entries = await api.get("/v1/income", { token });
  setState({ income: entries });
}

export function renderIncome(container, token) {
  renderLedgerView(container, {
    kind: "income",
    apiPrefix: "income",
    stateKey: "income",
    token,
    onChange: async () => {
      await refreshIncome(token);
      renderIncome(container, token);
    },
  });
}
