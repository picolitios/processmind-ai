# ProcessMind AI

ProcessMind AI is a local-first B2B purchase audit platform. Teams import CSV/XLSX records, run versioned deterministic checks, review evidence-backed findings, and resolve cases. Optional local Ollama explanations cite stored evidence; they do not determine whether fraud occurred.

## Implemented

- React/Vite UI, a dedicated identity FastAPI process for client-facing auth/organization routes, and a business FastAPI process. Organization membership, RBAC, session cookies and CSRF behavior remain compatible with the MVP.
- PostgreSQL 16 with Alembic migrations, tenant-scoped purchases, audit runs, findings, cases and action trail.
- Separate import and local-model worker processes plus an audit event path. An audit request commits a job and outbox event together; a publisher confirms delivery to RabbitMQ, and a consumer commits findings before acknowledging. The API exposes status and results.
- Optional local Ollama explanations with validation and explicit fallback. Audit rules work without a model.
- Conversational copilot for findings and audits, with tenant-scoped shared memory, temporary chats, approval policy and evidence citations. Model answers require optional local Ollama.

Business domains remain a **modular monolith**. Identity runs as a separate process behind nginx. In Compose, business requests ask identity to validate sessions, CSRF and tenant membership, and case routes resolve member references through identity. Both processes use one PostgreSQL database with separate `identity` and `business` schemas and runtime credentials; each credential is denied access to the other's tables. Audit creation locks an audit-owned configuration row. Organization settings use a durable identity command and a private audit-owner apply contract, with a reconciler for failures. Business events use their own trail, with an optional legacy mirror for rollback. The RabbitMQ audit path is the first event boundary. Notification and analytics workers and distributed tracing remain planned. See [current state](docs/architecture/current-state.md), [target state](docs/architecture/target-state.md) and [migration plan](docs/architecture/migration-plan.md).

## Architecture choice

The MVP used one transaction and a PostgreSQL job worker to preserve correctness with low local operating cost. RabbitMQ now dispatches long-running audit work through a real versioned event. The [transactional outbox](docs/architecture/decisions/0001-audit-outbox-rabbitmq.md) keeps a committed request pending when the broker is unavailable. Delivery is at least once; job state handles duplicates. See the [event catalog](docs/architecture/event-catalog.md) for the implemented contract, retry and dead-letter behavior.

nginx in the web container is the client entry point. FastAPI currently owns authentication, authorization, CORS and correlation IDs. Domain extraction will follow measured needs and a data ownership migration.

## Run locally

Requirements: Docker Desktop with Compose. Python 3.12 and Node.js 24 are only needed for host-side development and tests. Docker services use free local infrastructure; Ollama is optional.

```powershell
Copy-Item .env.example .env
# Set POSTGRES_PASSWORD and the matching DATABASE_URL in .env.
# Set distinct random IDENTITY_DB_PASSWORD and BUSINESS_DB_PASSWORD values (32+ characters).
# Set a random AUTH_HASH_KEY of at least 32 characters.
docker compose up -d db rabbitmq
docker compose build db-admin api identity identity-config-reconciler worker model-worker audit-publisher audit-consumer audit-monitor web
docker compose run --rm --no-deps db-admin alembic upgrade head
docker compose run --rm --no-deps db-admin python -m app.db.provision_roles
docker compose up -d --no-build api identity identity-config-reconciler worker model-worker audit-publisher audit-consumer audit-monitor web
docker compose ps
```

UI: <http://localhost:5173>. Business API docs: <http://localhost:8000/docs>. Identity API docs: <http://localhost:8001/docs>. API readiness: <http://localhost:8000/api/v1/health/ready>. RabbitMQ management: <http://localhost:15672> (local credentials from `.env`). Follow the [installation guide](docs/installation.md) before upgrading an existing installation; apply the additive migration before restarting workers and drain old queued audits before switching dispatch modes. Preserve Compose volumes containing business data.
For an existing installation, run the reconciliation gates, stop writers, and migrate with `db-admin` **before** recreating runtime containers; the [installation guide](docs/installation.md) has the exact commands.

The [user guide](docs/user-guide.md) and [example CSV](examples/compras-exemplo.csv) cover import, audit, case review and dashboards.

## Test and inspect

Run `ruff check .`, `mypy app`, migrations and `pytest` from `apps/api` with a fresh test database (`DATABASE_URL`, `RUN_DB_TESTS=1`). Run `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build` and `npm run test:e2e` from `apps/web`; E2E uses the running Compose stack. CI runs API and web gates plus an isolated PostgreSQL/RabbitMQ recovery test (`RUN_BROKER_TESTS=1`).

The [MVP stabilization results](specs/testing/phase7-results.md), [load report](specs/testing/phase7-load-report.md), [audit evaluation](specs/testing/audit-evaluation.md) and [delivery evidence](specs/testing/phase8-delivery.md) contain measured results and limitations. The [distributed-load result](specs/testing/distributed-load-results.md) covers a small concurrent broker-path sample, not production capacity.

For an aggregate audit-dispatch snapshot, run `docker compose run --rm --no-deps audit-publisher python -m app.features.audit.operations --max-pending-age-seconds 300 --fail-on-expired-leases --fail-on-dead-letter`. The read-only command returns JSON and exits with code 2 when a selected threshold is exceeded; see the [operations contract](specs/architecture/audit-operations-v1.md). It does not expose tenant data or event payloads.

Compose runs `audit-monitor` every 60 seconds and marks that container unhealthy when the outbox or an audit job has waited over five minutes, an audit lease has expired, a dead letter exists, or a dependency is unavailable. Check `docker compose ps audit-monitor` and `docker compose logs audit-monitor`; the [monitor contract](specs/architecture/audit-monitor-v1.md) defines the signal and its limits.

Business and identity HTTP requests, audit publication and audit delivery emit allowlisted JSON records with correlation IDs. The request response header is persisted in the audit event and reused by publisher and consumer records. Inspect `docker compose logs api identity audit-publisher audit-consumer` and search by `correlation_id`; these records omit raw URLs, tenant data and event payloads. The [observability contract](specs/architecture/audit-observability-v1.md) describes the supported fields and limits.

The [OpenAPI contract](specs/architecture/openapi.yaml), [event catalog](docs/architecture/event-catalog.md), [data model](specs/architecture/data-model.md), [security model](specs/security/security-model.md) and [ADRs](specs/decisions/) document established behavior. Audit requests use `202 Accepted`, idempotency keys and tenant-scoped result reads. API readiness currently verifies PostgreSQL; Compose checks broker health. Automatic outbox cleanup, a physically separate identity database and distributed tracing remain migration work.

The browser CI job also runs [concurrent synthetic import and audit journeys](specs/testing/distributed-load-v1.md) through the public nginx URL on its disposable stack. It uploads JSON latency, throughput and error measurements as a workflow artifact. These exploratory results are not production capacity claims.
The [local measurement report](specs/testing/distributed-load-results.md) records the first complete distributed run and its limits.

For local data protection, follow the [quiesced backup and isolated restore guide](docs/backup-and-restore.md). It covers PostgreSQL and private uploads and refuses a backup while application writers or audit dispatch remain active. No automated offsite retention or production recovery objective is established.
