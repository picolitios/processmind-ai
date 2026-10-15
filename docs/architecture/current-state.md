# Current state (2026-10-15)

## Implemented

The MVP is a modular FastAPI application with domains for identity, ingestion, audit, AI explanations, cases and analytics. React/Vite serves the UI through nginx. PostgreSQL 16 stores tenant-scoped business data, sessions, jobs and the audit trail. Alembic owns schema changes. A separate process polls the `jobs` table for import, audit and optional Ollama explanation work. Docker Compose runs database, API, UI and worker. GitHub Actions runs Python and web quality gates. Existing API routes are versioned under `/api/v1` and audit creation returns 202 with a job ID. Existing regression and browser flows cover import through case resolution.

The audit engine is deterministic and stores findings with evidence. Ollama produces optional explanations; it does not determine audit findings. API authorization checks organization membership and role. Tenant-scoped tables use organization IDs and, where needed, composite foreign keys. The UI nginx container is the current client entry point; CORS and correlation IDs live in FastAPI. There is no independent identity service or broker.

## Risks and constraints

- Database polling couples audit dispatch to the shared job table. This is sufficient for the MVP, but gives no event contract for future independent consumers.
- One database and one application still own all domains. Calling these separate microservices today would misrepresent the implementation.
- The worker's one-hour lease and three attempts give recovery for many failures, but a crash during processing can delay retry until lease expiry.
- The API readiness check verifies PostgreSQL only. Queue health must be checked independently when messaging is introduced.
- Current API and web tests run in CI; the browser E2E suite and failure recovery checks require explicit local execution.
- `specs/decisions/0001-modular-monolith.md` correctly records the MVP decision. The new architecture request is an evolution, not a retroactive replacement.

## Reuse

Keep existing contracts, database migrations, tenant enforcement, deterministic rules, and the audit status endpoint. Introduce messaging at the audit job boundary before considering process or data ownership splits.
