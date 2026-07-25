import { api, ApiError } from "../api.js";
import { escapeHtml } from "../format.js";
import { getState, setState } from "../state.js";

export async function refreshPeriods(token) {
  const periods = await api.get("/v1/periods", { token });
  setState({ periods });
}

export function renderPeriods(container, token) {
  const { periods } = getState();

  container.innerHTML = `
    <h2>Budget periods</h2>
    <form id="period-form" novalidate>
      <div class="field">
        <label for="period-starts">Starts on</label>
        <input id="period-starts" type="date" required />
      </div>
      <div class="field">
        <label for="period-ends">Ends on</label>
        <input id="period-ends" type="date" required />
      </div>
      <button type="submit">Create period</button>
      <p class="error-text" id="period-error" role="alert"></p>
    </form>
    <table class="ledger-table">
      <caption>Periods</caption>
      <thead>
        <tr><th scope="col">Starts</th><th scope="col">Ends</th><th scope="col">Status</th><th scope="col">Action</th></tr>
      </thead>
      <tbody>
        ${periods
          .map((period) => {
            const nextAction = period.status === "open" ? "close" : "reopen";
            return `<tr data-period-id="${period.id}" data-version="${period.version}">
              <td>${escapeHtml(period.starts_on)}</td>
              <td>${escapeHtml(period.ends_on)}</td>
              <td>${escapeHtml(period.status)}</td>
              <td><button type="button" class="transition-button" data-action="${nextAction}">${nextAction === "close" ? "Close" : "Reopen"}</button></td>
            </tr>`;
          })
          .join("")}
      </tbody>
    </table>
  `;

  const form = container.querySelector("#period-form");
  const errorEl = container.querySelector("#period-error");
  const rerender = async () => {
    await refreshPeriods(token);
    renderPeriods(container, token);
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorEl.textContent = "";
    const startsOn = container.querySelector("#period-starts").value;
    const endsOn = container.querySelector("#period-ends").value;
    try {
      await api.post("/v1/periods", { token, body: { starts_on: startsOn, ends_on: endsOn } });
      form.reset();
      await rerender();
    } catch (error) {
      errorEl.textContent = error instanceof ApiError ? error.message : "Could not create the period";
    }
  });

  container.querySelectorAll(".transition-button").forEach((button) => {
    button.addEventListener("click", async () => {
      const row = button.closest("tr");
      const periodId = row.dataset.periodId;
      const version = row.dataset.version;
      const action = button.dataset.action;
      errorEl.textContent = "";
      try {
        await api.post(`/v1/periods/${periodId}/${action}`, { token, headers: { "If-Match": version } });
        await rerender();
      } catch (error) {
        // A 409 here means another request changed this period's version
        // since the list was loaded (stale If-Match) — refresh so the
        // displayed version matches reality instead of retrying blindly.
        await rerender();
        errorEl.textContent = error instanceof ApiError ? error.message : "Could not update the period";
      }
    });
  });
}
