import { api } from "../api.js";
import { escapeHtml, formatMinor } from "../format.js";
import { getState, setState } from "../state.js";

export async function refreshInsights(token, periodId) {
  if (!periodId) {
    setState({ insights: null });
    return;
  }
  const insights = await api.get(`/v1/insights?period_id=${encodeURIComponent(periodId)}`, { token });
  setState({ insights });
}

export function renderDashboard(container, token) {
  const { periods, insights } = getState();
  const selectedId = insights ? insights.period_id : (periods.find((period) => period.status === "open") || periods[0] || {}).id;

  container.innerHTML = `
    <h2>Dashboard</h2>
    ${
      periods.length === 0
        ? `<p>Create a budget period to see a summary.</p>`
        : `
      <div class="field">
        <label for="dashboard-period">Period</label>
        <select id="dashboard-period">
          ${periods
            .map(
              (period) =>
                `<option value="${period.id}" ${period.id === selectedId ? "selected" : ""}>${escapeHtml(period.starts_on)} – ${escapeHtml(period.ends_on)}</option>`
            )
            .join("")}
        </select>
      </div>
      ${
        insights
          ? `
        <dl class="summary-grid">
          <div><dt>Income</dt><dd>${escapeHtml(formatMinor(insights.income_minor))}</dd></div>
          <div><dt>Expenses</dt><dd>${escapeHtml(formatMinor(insights.expense_minor))}</dd></div>
          <div><dt>Balance</dt><dd>${escapeHtml(formatMinor(insights.balance_minor))}</dd></div>
          <div><dt>Debt due</dt><dd>${escapeHtml(formatMinor(insights.debt_due_minor))}</dd></div>
        </dl>
        <h3>By category</h3>
        ${
          insights.by_category.length
            ? `<ul>${insights.by_category.map((row) => `<li>${escapeHtml(row.name || row.category_id)}: ${escapeHtml(formatMinor(row.total_minor))}</li>`).join("")}</ul>`
            : `<p>No entries recorded for this period yet.</p>`
        }
        <h3>Alerts</h3>
        ${
          insights.alerts.length
            ? `<ul class="alert-list" role="alert">${insights.alerts
                .map(
                  (alert) =>
                    `<li>${escapeHtml(alert.label)}: ${escapeHtml(formatMinor(alert.actual_minor))} reached the ${escapeHtml(formatMinor(alert.threshold_minor))} threshold</li>`
                )
                .join("")}</ul>`
            : `<p>No active alerts for this period.</p>`
        }
      `
          : `<p>Loading…</p>`
      }
    `
    }
  `;

  const select = container.querySelector("#dashboard-period");
  if (select) {
    select.addEventListener("change", async () => {
      await refreshInsights(token, select.value);
      renderDashboard(container, token);
    });
  }
}
