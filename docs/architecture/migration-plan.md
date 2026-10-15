# Incremental migration plan

## First vertical: audit dispatch

Acceptance: creating an audit through the existing REST API commits the audit run, job and versioned outbox event atomically; a publisher confirms delivery to RabbitMQ; an audit consumer processes the job and acknowledges only after the database commit; the existing authenticated GET returns findings and a succeeded audit. Duplicate delivery leaves one result. Broker outage leaves the outbox pending and the API response valid. Import and AI jobs still run through the existing worker. Existing tests, lint, types, migration and Compose health must pass.

1. Add an outbox migration and event contract. Keep one database transaction for audit creation.
2. Add publisher and consumer processes to Compose, broker credentials scoped to local development, durable queue with delayed retry and DLQ.
3. Make the existing polling worker skip audit jobs in broker mode. Keep database mode for compatibility and rollback.
4. Test atomic enqueue, duplicate handling, broker interruption, and end-to-end result lookup. Document measured outcomes only.

## Subsequent increments

1. Stabilize contract and recovery tests; add queue depth, publish latency and worker metrics. Define ownership and retention for outbox and dead letters.
2. Extract identity behind existing routes only when the transaction and tenant boundary can be preserved with a tested migration. Use separate credentials/schema before declaring data isolation.
3. Extract audit/ingestion and AI on demonstrated scaling or security needs. Replace cross-domain table reads with versioned APIs/events and test authorization and reconciliation.
4. Add notification and analytics consumers only when product requirements call for them. Extend CI with contract, browser, recovery and load evidence, then document deployment.

The V2 conversational copilot design remains on `feature/v2-copilot` until this vertical is stable. Its history and access-policy decisions do not alter the first event contract.

Rollback: stop publisher/consumer, set `AUDIT_DISPATCH_MODE=database` on API and polling worker, and retain the additive outbox table. Do not drop records or revert schema with live data.
Before switching from database to broker mode in an existing installation, drain queued audit jobs with the database worker or enqueue their events through a reviewed one-time migration; otherwise they have no outbox record for the broker publisher.
