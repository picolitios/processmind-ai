# ProcessMind AI

ProcessMind AI is a local-first B2B purchase audit platform. Teams import CSV/XLSX records, run versioned deterministic checks, review evidence-backed findings, and resolve cases. Optional local Ollama explanations cite stored evidence; they do not determine whether fraud occurred.

## Implemented

- React/Vite UI, a dedicated identity FastAPI process for client-facing auth/organization routes, and a business FastAPI process. Organization membership, RBAC, session cookies and CSRF behavior remain compatible with the MVP.
- PostgreSQL 16 with Alembic migrations, tenant-scoped purchases, audit runs, findings, cases and action trail.
- Separate import/AI worker and audit event path. An audit request commits a job and outbox event together; a publisher confirms delivery to RabbitMQ, and a consumer commits findings before acknowledging. The API exposes status and results.
- Optional local Ollama explanations with validation and explicit fallback. Audit rules work without a model.

Business domains remain a **modular monolith**. Identity now runs as a separate process behind nginx; in Compose, business requests ask identity to validate sessions, CSRF and tenant membership, and case routes resolve member references through identity. Both processes still share PostgreSQL; audit creation still locks the identity-owned organization row and identity still writes the audit-owned settings copy. Business events use their own trail, with an optional legacy mirror for rollback. This is not yet exclusive data ownership. The RabbitMQ audit path is the first event boundary. Notification and analytics workers, tracing and a conversational copilot are planned. See [current state](docs/architecture/current-state.md), [target state](docs/architecture/target-state.md) and [migration plan](docs/architecture/migration-plan.md).

## Architecture choice

The MVP used one transaction and a PostgreSQL job worker to preserve correctness with low local operating cost. RabbitMQ now dispatches long-running audit work through a real versioned event. The [transactional outbox](docs/architecture/decisions/0001-audit-outbox-rabbitmq.md) keeps a committed request pending when the broker is unavailable. Delivery is at least once; job state handles duplicates. See the [event catalog](docs/architecture/event-catalog.md) for the implemented contract, retry and dead-letter behavior.

nginx in the web container is the client entry point. FastAPI currently owns authentication, authorization, CORS and correlation IDs. Domain extraction will follow measured needs and a data ownership migration.

## Run locally

Requirements: Docker Desktop with Compose. Python 3.12 and Node.js 24 are only needed for host-side development and tests. Docker services use free local infrastructure; Ollama is optional.

```powershell
Copy-Item .env.example .env
# Set POSTGRES_PASSWORD and the matching DATABASE_URL in .env.
# Set a random AUTH_HASH_KEY of at least 32 characters.
docker compose up -d db rabbitmq
docker compose build api identity worker audit-publisher audit-consumer web
docker compose run --rm --no-deps api alembic upgrade head
docker compose up -d --no-build api identity worker audit-publisher audit-consumer web
docker compose ps
```

UI: <http://localhost:5173>. Business API docs: <http://localhost:8000/docs>. Identity API docs: <http://localhost:8001/docs>. API readiness: <http://localhost:8000/api/v1/health/ready>. RabbitMQ management: <http://localhost:15672> (local credentials from `.env`). Follow the [installation guide](docs/installation.md) before upgrading an existing installation; apply the additive migration before restarting workers and drain old queued audits before switching dispatch modes. Preserve Compose volumes containing business data.
For an existing installation, build images and run the additive migration in a one-off container **before** recreating the API; the [installation guide](docs/installation.md) has the exact commands.

The [user guide](docs/user-guide.md) and [example CSV](examples/compras-exemplo.csv) cover import, audit, case review and dashboards.

## Test and inspect

Run `ruff check .`, `mypy app`, migrations and `pytest` from `apps/api` with a fresh test database (`DATABASE_URL`, `RUN_DB_TESTS=1`). Run `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build` and `npm run test:e2e` from `apps/web`; E2E uses the running Compose stack. CI runs API and web gates.

The [MVP stabilization results](specs/testing/phase7-results.md), [load report](specs/testing/phase7-load-report.md), [audit evaluation](specs/testing/audit-evaluation.md) and [delivery evidence](specs/testing/phase8-delivery.md) contain measured results and limitations. No distributed-load benchmark is claimed for the broker path yet.

The [OpenAPI contract](specs/architecture/openapi.yaml), [event catalog](docs/architecture/event-catalog.md), [data model](specs/architecture/data-model.md), [security model](specs/security/security-model.md) and [ADRs](specs/decisions/) document established behavior. Audit requests use `202 Accepted`, idempotency keys and tenant-scoped result reads. API readiness currently verifies PostgreSQL; Compose checks broker health. Outbox retention, independent data ownership and distributed tracing remain migration work.
