# Target state

The target is a set of **logical boundaries**, extracted into independently deployed services only when ownership and operational benefit justify the split. The first executable increment retains the modular API and database, while moving audit dispatch to RabbitMQ with a transactional outbox.

| Boundary | Current owner | Possible later extraction |
| --- | --- | --- |
| Client edge | nginx + FastAPI middleware | Consolidated gateway when routing across independently deployed APIs is needed |
| Identity | `features/identity` | Identity service with exclusive identity data ownership |
| Import and audit | `features/ingestion`, `features/audit` | Audit service; owns purchases, audit runs, findings and event outbox |
| AI explanation | `features/ai` | AI analysis service after independent scaling/security need |
| Notification | None | Worker only after a real notification use case exists |
| Analytics | `features/analytics` | Worker/materialized projections only if query load warrants it |

Redis, a custom gateway, notification and analytics workers are not included in the first increment. The existing PostgreSQL instance can later host separate databases or schemas with separate credentials. Until then, modules remain one deployment and may use the shared transaction; independently deployed services must not read another service's private tables.

```mermaid
flowchart LR
  UI[React UI / nginx] --> API[FastAPI modular API]
  API --> PG[(PostgreSQL)]
  PUB[Outbox publisher] --> PG
  PUB --> MQ[(RabbitMQ)]
  MQ --> CON[Audit consumer]
  CON --> PG
  API --> OLL[Optional local Ollama]
```

The broker uses durable queues, persistent messages, publisher confirms, manual consumer acknowledgment, retry with delay, and a dead-letter queue. A committed outbox record is the source for publication; delivery is **at least once**. The audit job remains the idempotency and status record, so duplicate messages cannot produce duplicate findings. `tenant_id` is checked against the job and run before processing. Public HTTP routes and authorization remain unchanged.

See `event-catalog.md` for the first real event and `migration-plan.md` for sequencing.

## C4 views of the first increment

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
  title Containers in the first distributed increment
  Person(reviewer, "Company reviewer")
  Container(web, "Web/nginx", "React, nginx", "UI and API proxy")
  Container(api, "API", "FastAPI", "Auth, import, audit, cases, analytics")
  Container(publisher, "Outbox publisher", "Python", "Confirmed audit event publication")
  Container(consumer, "Audit consumer", "Python", "Idempotent audit processing")
  Container(worker, "Import/AI worker", "Python", "Existing database jobs")
  ContainerDb(db, "PostgreSQL", "PostgreSQL 16", "Tenant data, jobs, outbox")
  ContainerQueue(broker, "RabbitMQ", "RabbitMQ 4", "Durable audit queue and retries")
  Rel(reviewer, web, "Uses")
  Rel(web, api, "Proxies /api/v1")
  Rel(api, db, "Commits audit, job, outbox")
  Rel(publisher, db, "Claims pending outbox rows")
  Rel(publisher, broker, "Publishes with confirm")
  Rel(broker, consumer, "Delivers audit.requested.v1")
  Rel(consumer, db, "Claims job, writes findings")
  Rel(worker, db, "Claims import and AI jobs")
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
