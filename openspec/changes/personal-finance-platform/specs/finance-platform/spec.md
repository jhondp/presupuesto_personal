# Personal Finance Platform Specifications

## User Finance Profile Specification
### Requirement: Identity, Ownership, and Currency
The system MUST authenticate users and enforce ownership isolation for every finance resource. A profile MUST default to CLP with zero decimal places and MAY select another supported currency; conversion is out of scope.
#### Scenario: Isolated profile
- GIVEN two authenticated users
- WHEN one requests the other's resource
- THEN access is denied without disclosing its data
#### Scenario: Default currency
- GIVEN a newly created profile
- WHEN no currency is selected
- THEN amounts display as CLP with zero decimals

### Requirement: Privacy Controls and Free-Tier Resilience
The system MUST use protected transport, avoid logging financial content or secrets, and provide user-readable export and account/data deletion. It MUST document and enforce configured free-tier usage limits; availability guarantees are out of scope.
#### Scenario: Export and deletion
- GIVEN an authenticated user
- WHEN the user exports or requests deletion
- THEN only that user's data is exported or deleted
#### Scenario: Limit reached
- GIVEN a configured usage limit is reached
- WHEN a user attempts the limited operation
- THEN the system explains the limit and preserves existing data

## Category Management Specification
### Requirement: User-Owned Categories
The system MUST let a user create, rename, and archive categories for their own records; another user MUST NOT view or alter them.
#### Scenario: Archive in-use category
- GIVEN a category used by ledger entries
- WHEN its owner archives it
- THEN historic entries retain their category and new assignment is prevented

## Income Ledger Specification
### Requirement: Spreadsheet-Like Income Entries
The system MUST provide a separate tabular income ledger with dated, categorized, amount, and optional note fields, supporting review by budget period.
#### Scenario: Record income
- GIVEN an open period and owned category
- WHEN the user saves a valid income entry
- THEN it appears in the income ledger and period totals

## Expense Ledger Specification
### Requirement: Spreadsheet-Like Expense Entries
The system MUST provide a separate tabular expense ledger with dated, categorized, amount, and optional note fields, supporting review by budget period.
#### Scenario: Closed-period edit
- GIVEN an expense belongs to a closed period
- WHEN the user attempts to alter it
- THEN the system rejects the change until the period is reopened

## Budget Periods Specification
### Requirement: Custom Period Lifecycle
The system MUST let an owner define period boundaries and transition a period from open to closed and explicitly back to open. Closing or reopening MUST preserve records and history.
#### Scenario: Close period
- GIVEN an open custom period
- WHEN its owner closes it
- THEN ledger changes in that period are blocked
#### Scenario: Reopen period
- GIVEN a closed period
- WHEN its owner explicitly reopens it
- THEN permitted changes resume without deleting records

## Debt Schedules Specification
### Requirement: Deterministic Debt Installments
The system MUST capture bank, principal amount, installment amount/count, and create installments beginning on the first day of the next budget period after debt creation. Repeated generation MUST be deterministic and duplicate-free.
#### Scenario: Next-period start
- GIVEN a debt created during an open period
- WHEN its schedule is generated
- THEN installment one is dated at the next period start
#### Scenario: Repeat generation
- GIVEN a generated debt schedule
- WHEN generation is requested again
- THEN the same installments exist exactly once

## Financial Insights Specification
### Requirement: Dashboard and Analysis
The system MUST show the authenticated user totals and category comparisons derived only from that user's income, expenses, periods, and debt installments.
#### Scenario: Period dashboard
- GIVEN a user selects a period
- WHEN the dashboard loads
- THEN it reports that period's income, expenses, balance, and category breakdown

### Requirement: In-App Alerts
The system MUST show in-app alerts for configured budget or debt conditions using the user's current records. Email and push delivery are out of scope.
#### Scenario: Threshold alert
- GIVEN an expense total reaches a configured threshold
- WHEN the user views the relevant period
- THEN an in-app alert identifies the condition without exposing another user's data

## Non-Goals

Spreadsheet import or workbook parity, shared households/delegated access, bank sync, payments, investments, taxes, currency conversion, email/push alerts, advanced forecasting, and production availability guarantees are out of scope.
