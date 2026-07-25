// Shared rendering/submit logic for the income and expenses views. Both
// ledgers store identical fields in separate tables (see design.md's
// "Ledger model" decision); `income.js`/`expenses.js` are thin wrappers
// around this, mirroring how `routes/_ledger_router.py` shares logic
// between the API's own income/expenses routes.
import { api, ApiError } from "../api.js";
import { escapeHtml, formatMinor } from "../format.js";
import { getState } from "../state.js";

export function renderLedgerView(container, { kind, apiPrefix, stateKey, token, onChange }) {
  const state = getState();
  const categories = state.categories.filter((category) => category.kind === kind && category.status === "active");
  const entries = state[stateKey] || [];
  const categoriesById = new Map(state.categories.map((category) => [category.id, category]));

  container.innerHTML = `
    <h2>${kind === "income" ? "Income" : "Expenses"}</h2>
    <form id="${kind}-form" novalidate>
      <div class="field">
        <label for="${kind}-category">Category</label>
        <select id="${kind}-category" required>
          ${categories.map((category) => `<option value="${category.id}">${escapeHtml(category.name)}</option>`).join("")}
        </select>
      </div>
      <div class="field">
        <label for="${kind}-date">Date</label>
        <input id="${kind}-date" type="date" required />
      </div>
      <div class="field">
        <label for="${kind}-amount">Amount (minor units)</label>
        <input id="${kind}-amount" type="number" min="1" step="1" required />
      </div>
      <div class="field">
        <label for="${kind}-note">Note</label>
        <input id="${kind}-note" type="text" maxlength="1000" />
      </div>
      <button type="submit">Add entry</button>
      <p class="error-text" id="${kind}-error" role="alert"></p>
    </form>
    <table class="ledger-table">
      <caption>Recorded ${kind}</caption>
      <thead>
        <tr><th scope="col">Date</th><th scope="col">Category</th><th scope="col">Amount</th><th scope="col">Note</th></tr>
      </thead>
      <tbody>
        ${entries
          .map((entry) => {
            const category = categoriesById.get(entry.category_id);
            return `<tr>
              <td>${escapeHtml(entry.occurred_on)}</td>
              <td>${escapeHtml(category ? category.name : entry.category_id)}</td>
              <td>${escapeHtml(formatMinor(entry.amount_minor))}</td>
              <td>${escapeHtml(entry.note || "")}</td>
            </tr>`;
          })
          .join("")}
      </tbody>
    </table>
  `;

  const form = container.querySelector(`#${kind}-form`);
  const errorEl = container.querySelector(`#${kind}-error`);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorEl.textContent = "";
    const categoryId = container.querySelector(`#${kind}-category`).value;
    const occurredOn = container.querySelector(`#${kind}-date`).value;
    const amountMinor = Number(container.querySelector(`#${kind}-amount`).value);
    const note = container.querySelector(`#${kind}-note`).value || undefined;

    if (!categoryId) {
      errorEl.textContent = "Create a category first";
      return;
    }

    try {
      await api.post(`/v1/${apiPrefix}`, {
        token,
        body: { category_id: categoryId, occurred_on: occurredOn, amount_minor: amountMinor, note },
      });
      form.reset();
      await onChange();
    } catch (error) {
      errorEl.textContent = error instanceof ApiError ? error.message : "Could not save the entry";
    }
  });
}
