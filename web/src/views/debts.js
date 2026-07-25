import { api, ApiError } from "../api.js";
import { escapeHtml, formatMinor } from "../format.js";
import { getState, setState } from "../state.js";

export async function refreshDebts(token) {
  const debts = await api.get("/v1/debts", { token });
  setState({ debts });
}

export function renderDebts(container, token) {
  const { debts, installmentsByDebt } = getState();

  container.innerHTML = `
    <h2>Debts</h2>
    <form id="debt-form" novalidate>
      <div class="field">
        <label for="debt-bank">Bank</label>
        <input id="debt-bank" type="text" maxlength="100" required />
      </div>
      <div class="field">
        <label for="debt-principal">Principal (minor units)</label>
        <input id="debt-principal" type="number" min="1" step="1" required />
      </div>
      <div class="field">
        <label for="debt-installment">Installment amount (minor units)</label>
        <input id="debt-installment" type="number" min="1" step="1" required />
      </div>
      <div class="field">
        <label for="debt-count">Installment count</label>
        <input id="debt-count" type="number" min="1" step="1" required />
      </div>
      <button type="submit">Add debt</button>
      <p class="error-text" id="debt-error" role="alert"></p>
    </form>
    <ul class="debt-list">
      ${debts
        .map((debt) => {
          const installments = installmentsByDebt[debt.id] || [];
          return `<li data-debt-id="${debt.id}">
            <h3>${escapeHtml(debt.bank)}</h3>
            <p>Principal ${escapeHtml(formatMinor(debt.principal_minor))} — ${debt.installment_count}× ${escapeHtml(formatMinor(debt.installment_minor))}</p>
            <button type="button" class="schedule-button">Generate / view schedule</button>
            ${
              installments.length
                ? `<table class="ledger-table">
                    <caption>Installments</caption>
                    <thead><tr><th scope="col">#</th><th scope="col">Due on</th><th scope="col">Amount</th></tr></thead>
                    <tbody>
                      ${installments
                        .map(
                          (installment) =>
                            `<tr><td>${installment.ordinal}</td><td>${escapeHtml(installment.due_on)}</td><td>${escapeHtml(formatMinor(installment.amount_minor))}</td></tr>`
                        )
                        .join("")}
                    </tbody>
                  </table>`
                : ""
            }
          </li>`;
        })
        .join("")}
    </ul>
  `;

  const form = container.querySelector("#debt-form");
  const errorEl = container.querySelector("#debt-error");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorEl.textContent = "";
    try {
      await api.post("/v1/debts", {
        token,
        body: {
          bank: container.querySelector("#debt-bank").value,
          principal_minor: Number(container.querySelector("#debt-principal").value),
          installment_minor: Number(container.querySelector("#debt-installment").value),
          installment_count: Number(container.querySelector("#debt-count").value),
        },
      });
      form.reset();
      await refreshDebts(token);
      renderDebts(container, token);
    } catch (error) {
      errorEl.textContent = error instanceof ApiError ? error.message : "Could not save the debt";
    }
  });

  container.querySelectorAll(".schedule-button").forEach((button) => {
    button.addEventListener("click", async () => {
      const debtId = button.closest("li").dataset.debtId;
      errorEl.textContent = "";
      try {
        // Idempotent by design (see design.md's Phase 3 addendum): the same
        // endpoint generates the schedule on first call and simply returns
        // the existing installments on every later call — there is no
        // separate read-only installments endpoint.
        const installments = await api.post(`/v1/debts/${debtId}/schedule`, { token });
        setState({ installmentsByDebt: { ...getState().installmentsByDebt, [debtId]: installments } });
        renderDebts(container, token);
      } catch (error) {
        errorEl.textContent = error instanceof ApiError ? error.message : "Could not generate the schedule";
      }
    });
  });
}
