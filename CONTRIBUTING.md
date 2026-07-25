# Contributing

This repository is in its foundation stage. Keep each change small, intentional, and easy to review.

## Quick path

1. Start from an approved issue and create a branch named `type/description`.
2. Make one reviewable work unit and run the deterministic checks below.
3. Open a pull request using the template, link the issue, add exactly one `type:*` label, and request the required human review.

## Local checks

Run checks that are deterministic and available in every clone before requesting review:

```sh
git diff --check
```

This command detects whitespace errors in the current diff. There is no application stack, test runner, linter, or formatter configured yet; do not invent commands or claim application tests have run.

When a stack is introduced, document its formatter, lint, unit, integration, and end-to-end commands here and add equivalent CI steps in the same work unit.

## Review and approval

Automated checks establish baseline repository hygiene. AI-assisted review is advisory, must be limited to the proposed diff, and never replaces accountable human review.

Changes involving authentication, authorization, secrets, personal or financial data, database migrations, deletion, exports, or other security-sensitive behavior require explicit human approval before merge. Reviewers should verify the issue scope, the diff, validation evidence, and rollback boundary.

## Branches, commits, and pull requests

- Create an approved issue first. Every PR must link it with `Closes #<number>`, `Fixes #<number>`, or `Resolves #<number>`.
- Use branches matching `^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)/[a-z0-9._-]+$`.
- Use Conventional Commits, for example `docs: add contribution workflow` or `ci(workflows): add repository hygiene check`.
- Add exactly one PR label: `type:bug`, `type:feature`, `type:docs`, `type:refactor`, `type:chore`, or `type:breaking-change`.
- Keep documentation and validation evidence with the behavior or workflow they describe. Do not add `Co-Authored-By` trailers.

## Future CI gates

The current workflow checks only diff whitespace because that is the sole repository-safe check available today. After the application stack exists, stage CI in this order:

1. Formatter and static analysis.
2. Unit tests.
3. Integration and security/data-boundary tests.
4. End-to-end tests and deployment-specific checks.

Each new gate must have a documented local command, deterministic inputs, and a clear failure signal before it becomes required for merge.
