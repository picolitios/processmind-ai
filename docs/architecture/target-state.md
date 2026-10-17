# Target state

The target is a set of **logical boundaries**, extracted into independently deployed services only when ownership and operational benefit justify the split. The first executable increment retains the modular API and database, while moving audit dispatch to RabbitMQ with a transactional outbox.

| Boundary | Current owner | Possible later extraction |
| --- | --- | --- |
| Client edge | nginx + FastAPI middleware | Consolidated gateway when routing across independently deployed APIs is needed |
| Identity | dedicated process and `identity` schema with a scoped runtime credential | Physically separate identity database if operations justify it |
| Import and audit | `features/ingestion`, `features/audit` | Audit service; owns purchases, audit runs, findings and event outbox |
| AI explanation and copilot | dedicated model worker process, `features/ai` and `features/copilot`, shared business schema | AI analysis service with owned data and versioned evidence contracts after independent scaling/security need |
| Notification | None | Worker only after a real notification use case exists |
| Analytics | `features/analytics` | Worker/materialized projections only if query load warrants it |

Redis, a custom gateway, notification and analytics workers are not included in the first increment. The current PostgreSQL instance hosts separate schemas and runtime credentials. Identity and business remain in one instance and share a Python image; independently deployed services do not read another owner's private tables. Shared-transaction modes are retained only for rollback with the administrative credential.

```mermaid
flowchart LR
  UI[React UI / nginx] --> API[FastAPI business API]
  UI --> ID[FastAPI identity process]
  API -->|Signed session, membership and case reference lookups| ID
  API --> PG[(PostgreSQL)]
  ID --> PG
  PUB[Outbox publisher] --> PG
  PUB --> MQ[(RabbitMQ)]
  MQ --> CON[Audit consumer]
  CON --> PG
  MON[Audit monitor] --> PG
  MON -->|Queue counters| MQ
  IMPORT[Import worker] --> PG
  MODEL[Model worker] --> OLL[Optional local Ollama]
  MODEL --> PG
```

The broker uses durable queues, persistent messages, publisher confirms, manual consumer acknowledgment, retry with delay, and a dead-letter queue. A committed outbox record is the source for publication; delivery is **at least once**. The audit job remains the idempotency and status record, so duplicate messages cannot produce duplicate findings. `tenant_id` is checked against the job and run before processing. Public HTTP routes and authorization remain unchanged.

See `event-catalog.md` for the first real event and `migration-plan.md` for sequencing.

## C4 views of the current distributed deployment

```mermaid
C4Context
  title ProcessMind AI context
  Person(reviewer, "Company reviewer", "Imports purchases and reviews findings")
  System(processmind, "ProcessMind AI", "Tenant-scoped purchase audit and cases")
  System_Ext(ollama, "Local Ollama", "Optional evidence-based explanations")
  Rel(reviewer, processmind, "Uses", "HTTP locally")
  Rel(processmind, ollama, "Optional model request", "HTTP")
```

```mermaid
C4Container
  title Containers in the current distributed deployment
  Person(reviewer, "Company reviewer")
  Container(web, "Web/nginx", "React, nginx", "UI and API proxy")
  Container(api, "API", "FastAPI", "Import, audit, cases, analytics; compatibility identity routes")
  Container(identity, "Identity", "FastAPI", "Public auth and organization routes")
  Container(publisher, "Outbox publisher", "Python", "Confirmed audit event publication")
  Container(consumer, "Audit consumer", "Python", "Idempotent audit processing")
  Container(importworker, "Import worker", "Python", "Import database jobs")
  Container(modelworker, "Model worker", "Python", "Explanation and copilot database jobs")
  Container(monitor, "Audit monitor", "Python", "Aggregate dispatch health")
  ContainerDb(db, "PostgreSQL", "PostgreSQL 16", "Tenant data, jobs, outbox")
  ContainerQueue(broker, "RabbitMQ", "RabbitMQ 4", "Durable audit queue and retries")
  Rel(reviewer, web, "Uses")
  Rel(web, api, "Proxies business /api/v1 routes")
  Rel(web, identity, "Proxies auth and organization routes")
  Rel(api, identity, "Introspects sessions, CSRF, membership and case references")
  Rel(identity, db, "Sessions, users, memberships")
  Rel(api, db, "Commits audit, job, outbox")
  Rel(publisher, db, "Claims pending outbox rows")
  Rel(publisher, broker, "Publishes with confirm")
  Rel(broker, consumer, "Delivers audit.requested.v1")
  Rel(consumer, db, "Claims job, writes findings")
  Rel(importworker, db, "Claims import jobs")
  Rel(modelworker, db, "Claims explanation and copilot jobs")
  Rel(monitor, db, "Reads aggregate outbox and audit-job state")
  Rel(monitor, broker, "Reads queue counters")
```

```mermaid
sequenceDiagram
  participant U as Reviewer
  participant A as API
  participant P as PostgreSQL
  participant O as Outbox publisher
  participant Q as RabbitMQ
  participant W as Audit consumer
  U->>A: POST audit + Idempotency-Key
  A->>P: Commit run, job, outbox event
  A-->>U: 202 + audit ID and job ID
  O->>P: Claim unpublished event
  O->>Q: Publish audit.requested.v1 (confirm)
  Q-->>O: Confirm
  O->>P: Mark published
  Q->>W: Deliver event
  W->>P: Claim job, evaluate and commit findings
  W-->>Q: Acknowledge
  U->>A: GET audit and findings
  A->>P: Tenant-scoped lookup
  A-->>U: Succeeded audit and evidence
```
