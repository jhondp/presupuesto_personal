# Proposal: Personal Finance Platform

## Intent

Replace manual spreadsheet upkeep with a private multi-user web product for recording and understanding personal finances. Keep it viable on free tiers and deliver it through learning-sized vertical slices.

## Scope

### In Scope
- Independent accounts with strict per-user data isolation.
- User-selected currency, defaulting to CLP with zero decimals.
- User-defined categories and separate spreadsheet-like income and expense tables.
- Custom budget periods with open, closed, and explicitly reopenable states.
- Debts with bank, amount, installment amount/count, and deterministic schedules; the first installment starts on the first day of the next budget period.
- Baseline dashboards, analysis, and in-app alerts.

### Out of Scope
- Spreadsheet import or workbook formula/pivot parity.
- Shared households, delegated access, or cross-user budgets.
- Bank synchronization, payments, investments, taxes, or currency conversion.
- Email/push alerts, advanced forecasting, and production availability guarantees.

## Capabilities

### New Capabilities
- `user-finance-profile`: Ownership boundary and currency preference.
- `category-management`: User-defined categories.
- `income-ledger`: Income entry and review.
- `expense-ledger`: Expense entry and review.
- `budget-periods`: Custom periods and lifecycle.
- `debt-schedules`: Debt capture and deterministic installments.
- `financial-insights`: Dashboards, analysis, and in-app alerts.

### Modified Capabilities
None.

## Approach

Deliver usable slices in order: identity/profile; categories/ledgers; budget periods; debt schedules; insights/alerts. Validate each domain rule before widening scope. Treat the workbook as private reference material, never deployed content.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| Product domain | New | User-owned records and lifecycle rules |
| User experience | New | Ledgers, budgets, debts, insights |
| Security | New | Authentication, authorization, isolation, safe logging |
| Operations | New | Free-tier limits, export, backup, recovery |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Data exposure | Medium | Deny cross-user access; protect secrets; test ownership |
| Period/debt ambiguity | Medium | Specify transitions and schedule examples |
| Free-tier changes | High | Limit usage; provide export and recovery |
| Excessive first scope | High | Enforce slice order and non-goals |

## Rollback Plan

Disable incomplete slices and restore the last compatible snapshot. Never expose or delete user records to roll back behavior.

## Success Criteria

- [ ] Users cannot access another user's finance data.
- [ ] Currency defaults to CLP/0 decimals and is user-selectable.
- [ ] Users manage categories and separate income/expense entries.
- [ ] Periods close and reopen without data loss.
- [ ] Repeated schedule generation is duplicate-free and starts next period.
- [ ] Dashboards and alerts match the user's records.
- [ ] Core workflows fit documented free-tier constraints.
