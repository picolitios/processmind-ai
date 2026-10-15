# ADR 0001: RabbitMQ dispatch for audit jobs

Status: accepted for the first migration increment, 2026-10-15.

## Context

The MVP ADR in `specs/decisions/0001-modular-monolith.md` selected one API and PostgreSQL job polling. The new architecture objective needs a real producer/consumer boundary that can later support independently deployed audit consumers. Audits are long-running and already represented by persisted jobs. Publishing directly in the HTTP handler would lose a message if the broker is unavailable after the database commit.

## Decision

Keep the modular API and PostgreSQL. Atomically persist `audit_runs`, `jobs` and an outbox event in the API transaction. A separate publisher uses RabbitMQ publisher confirms; an audit-only consumer manually acknowledges after processing. The outbox and job status tolerate duplicate delivery. The original polling worker continues import and AI work; a configuration switch preserves the prior audit path for rollback. RabbitMQ runs locally in Compose with durable queues and delayed retry/DLQ.

This amends the MVP dispatch choice for audits only. It does not supersede the modular monolith's deployment or authorize a broad service split.

## Consequences

This adds a broker and two processes to operate. Delivery is at least once and requires idempotent handling. It removes audit dispatch dependence on the shared polling loop and demonstrates an actual event boundary. An outbox cleanup and observability policy are follow-up work. The migration is additive and can be rolled back by switching dispatch mode without dropping data.
