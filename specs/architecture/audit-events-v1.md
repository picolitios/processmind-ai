# Audit event dispatch v1

Status: approved for the first architecture migration increment. This specification extends the MVP audit contract without changing its HTTP routes or rule semantics. The complete envelope is in `docs/architecture/event-catalog.md`; migration and rollback are in `docs/architecture/migration-plan.md`.

## Functional contract

1. In broker mode, a successful audit POST persists `AuditRun`, `Job` and one `OutboxEvent` in one transaction. Replaying the idempotency key with the same imports returns the original audit without another event.
2. The publisher sends `audit.requested` version 1 with publisher confirm and mandatory routing. Failed publication leaves `published_at` null. A crash between confirmation and marking may produce a duplicate.
3. The consumer checks event version, tenant ID, audit ID, job ID and their persisted association. It claims a queued or expired audit job, processes existing deterministic rules and acknowledges after commit. A succeeded job makes duplicate delivery a no-op.
4. Transient failures retry with delayed queues and at most three processing attempts. Invalid, permanent and exhausted deliveries go to a dead-letter queue. Audit status becomes `failed` for permanent or exhausted processing errors. Tenant-authorized API reads expose status and findings.
5. Import and AI jobs remain on the database worker. In broker mode it must not claim audit jobs. Database mode preserves the old audit path for rollback.

## Acceptance evidence

- Fresh PostgreSQL migration and existing API regression suite pass.
- API test checks one event per idempotent audit, tenant mismatch rejection, duplicate consumption and pending outbox after publication failure.
- Compose browser E2E completes import → audit → findings → case, with `published_at` set and the audit job completed by the broker consumer.
- With RabbitMQ stopped, an audit POST remains accepted and queued. Restarting RabbitMQ leads to a succeeded audit without another POST.
- Ruff, mypy, web lint/types/tests/build and Compose health checks pass before PR readiness.

## Limits

This increment retains shared database ownership. Queue and outbox retention, distributed tracing, independent service APIs, separate schemas and load benchmarking are later migration items. No exactly-once guarantee is made.
