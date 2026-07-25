// Shared money/date formatting. Amounts cross the API as integer minor
// units (see design.md's Money/time decision); this is the one place that
// converts them to a display string, using the profile's decimal scale
// rather than assuming CLP's zero decimals everywhere.

export function formatMinor(amountMinor, decimalScale = 0) {
  const divisor = 10 ** decimalScale;
  const value = amountMinor / divisor;
  return value.toLocaleString(undefined, {
    minimumFractionDigits: decimalScale,
    maximumFractionDigits: decimalScale,
  });
}

export function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}
