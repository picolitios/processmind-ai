# Current state (2026-10-16)

## Implemented

The MVP business API is a modular FastAPI application with domains for identity, ingestion, audit, AI explanations, cases and analytics. A dedicated FastAPI identity process serves public auth and organization routes through nginx. PostgreSQL 16 hosts separate `identity` and `business` schemas in one database. Runtime roles can access only their own schema; an administrative credential is reserved for migrations and cross-domain reconciliation. Alembic owns schema changes. One process polls the `jobs` table for import and optional Ollama explanation work. Audits are dispatched through an outbox publisher, RabbitMQ and an audit consumer in Compose; database polling remains a rollback mode. Docker Compose runs these processes with the database, API and UI. GitHub Actions runs Python and web quality gates. Existing API routes are versioned under `/api/v1` and audit creation returns 202 with a job ID. Existing regression and browser flows cover import through case resolution.

The audit engine is deterministic and stores findings with evidence. Ollama produces optional explanations; it does not determine audit findings. In Compose, business routes validate sessions, CSRF and active tenant membership through signed private identity requests without caching authorization decisions. Case routes also resolve assignee and author references through a bounded private identity lookup. Import deduplication uses a transaction-scoped PostgreSQL advisory lock keyed by tenant. Audit creation reads a locked audit-owned configuration row. Identity persists a durable settings command, calls the private audit-owner apply contract, and returns success only after confirmation; a dedicated identity reconciler retries outages. The shared-database write remains available only in rollback mode with an administrative credential. Business actions have their own append-only audit trail; Compose writes only there, while `dual` mode can retain a temporary legacy copy in `audit_events` for rollback. Case history reads the business table. Tenant-scoped tables use organization IDs and, where needed, composite foreign keys. The UI nginx container is the client entry point; CORS and correlation IDs live in FastAPI. Identity can be restarted independently and cannot read the business schema, but the processes still share one PostgreSQL instance and Python image.

## Risks and constraints

- The original database polling path is retained for rollback. The RabbitMQ path adds an event contract but still uses the shared job table and database; it is not yet a separately owned audit service.
- One database, migration role and shared Python image still couple identity and business operations. This is schema and runtime-credential isolation, not independent database infrastructure.
- The worker's one-hour lease and three attempts give recovery for many failures, but a crash during processing can delay retry until lease expiry.
- The API readiness check verifies PostgreSQL only. Compose checks RabbitMQ health independently; no queue-depth alert exists yet.
- Current API and web tests run in CI; the browser E2E suite and failure recovery checks require explicit local execution.
- `specs/decisions/0001-modular-monolith.md` correctly records the MVP decision. The new architecture request is an evolution, not a retroactive replacement.

## Reuse

The first increment reused existing contracts, database migrations, tenant enforcement, deterministic rules and the audit status endpoint. The remaining migration can focus on process and data ownership where justified.
