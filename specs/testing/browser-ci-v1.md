# Browser E2E gate in CI

## Goal

Run the existing Playwright browser suite against a fresh, migrated Compose stack on each pull request. The gate must exercise the public nginx entry point, dedicated identity process, business API, import and model workers, and RabbitMQ audit dispatch.

## Acceptance

- CI creates isolated test-only credentials at runtime, starts fresh PostgreSQL and RabbitMQ volumes, applies Alembic migrations, provisions the scoped runtime roles, and starts the application processes.
- The web container and the audit monitor report healthy before browser tests start.
- Chromium runs all tests under `apps/web/e2e`, including the registration-to-case flow, security headers, and keyboard/accessibility checks.
- A browser failure fails the PR gate. The job prints Compose process status on failure and stops its stack even when setup or tests fail.
- No production secrets, personal data, imported customer files, or long-lived test volumes are required. The tests use repository synthetic data and create new users/organizations within the disposable CI stack.

## Scope

This adds a CI gate and related documentation. It does not change product behavior or E2E assertions.
