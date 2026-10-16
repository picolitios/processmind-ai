# Incremental migration plan

## First vertical: audit dispatch

Acceptance: creating an audit through the existing REST API commits the audit run, job and versioned outbox event atomically; a publisher confirms delivery to RabbitMQ; an audit consumer processes the job and acknowledges only after the database commit; the existing authenticated GET returns findings and a succeeded audit. Duplicate delivery leaves one result. Broker outage leaves the outbox pending and the API response valid. Import and AI jobs still run through the existing worker. Existing tests, lint, types, migration and Compose health must pass.

1. Add an outbox migration and event contract. Keep one database transaction for audit creation.
2. Add publisher and consumer processes to Compose, broker credentials scoped to local development, durable queue with delayed retry and DLQ.
3. Make the existing polling worker skip audit jobs in broker mode. Keep database mode for compatibility and rollback.
4. Test atomic enqueue, duplicate handling, broker interruption, and end-to-end result lookup. Document measured outcomes only.

## Subsequent increments

1. Stabilize contract and recovery tests; add queue depth, publish latency and worker metrics. Define ownership and retention for outbox and dead letters.
2. Put identity routes behind a dedicated process and gateway rule while preserving the shared transaction model. Test tenant authorization and rollback. Then replace direct business-module identity table reads with explicit contracts and migrate FKs/credentials/schema before declaring exclusive data ownership.
3. Extract audit/ingestion and AI on demonstrated scaling or security needs. Replace cross-domain table reads with versioned APIs/events and test authorization and reconciliation.
4. Add notification and analytics consumers only when product requirements call for them. Extend CI with contract, browser, recovery and load evidence, then document deployment.

The V2 conversational copilot design remains on `feature/v2-copilot` until this vertical is stable. Its history and access-policy decisions do not alter the first event contract.

## Identity data cutover dependencies

The dedicated identity process is live, but exclusive database ownership is blocked by concrete references that must be migrated in order:

| Business dependency | Current use | Required contract or data change |
| --- | --- | --- |
| `UserSession` and `User` | Business API previously validated the session cookie directly | Signed, bounded identity introspection with fail-closed behavior and revocation tests now handles business routes in Compose; direct identity routes remain for compatibility |
| `Organization` and `Membership` | Identity authorizes tenant membership and resolves case references through private contracts; audit reads an audit-owned configuration row in Compose but still locks the organization row | The direct identity write is replaced by a durable command and signed audit-owner apply call; remove the remaining cross-domain row lock and FKs only after authorization and snapshot gates pass |
| `AuditEvent` | Business modules own an append-only trail; Compose now omits the temporary legacy write, while `dual` mode remains for rollback | Verify the copies before cutover and restore missing legacy IDs before reverting to an older image; retire the shared-database rollback path before credential isolation |
| FKs to users, organizations and memberships | Jobs, audits, cases and evidence rely on shared referential integrity | Replace cross-domain FKs with validated identifiers and reconciliation before moving schemas |

Do not remove the compatibility identity routes in the business API or revoke table access until these contracts and a reversible data migration pass two-tenant regression, revocation, E2E and failure tests. Audit configuration writes are coordinated across processes in Compose, with a temporary shared-transaction mode for rollback. The business event trail supports owned-only writes in Compose, but rollback restoration still needs shared-database access.

The [identity data cutover plan](identity-data-cutover-plan.md) inventories the remaining table dependencies, sequence and release gates. ADR 0003 records audit ownership and the temporary shared lock.

Audit configuration rollout: apply the additive migrations first. Before enabling `AUDIT_CONFIG_MODE=owned` and `AUDIT_CONFIG_WRITE_MODE=coordinated`, compare organization and audit-configuration counts, versions and values. Recreate API and identity only after the copy is verified. Coordinated writes require owned snapshot reads. For a shared-database rollback, drain all configuration commands, verify the copies again, and select `AUDIT_CONFIG_WRITE_MODE=database` together with `AUDIT_CONFIG_MODE=legacy`; retain both tables and their synchronized data.

Identity rollback: remove the identity gateway locations, set `BUSINESS_AUTH_MODE=database` on the API, and recreate API/web before stopping identity. The shared schema and sessions require no data migration.

Rollback: stop publisher/consumer, set `AUDIT_DISPATCH_MODE=database` on API and polling worker, and retain the additive outbox table. Do not drop records or revert schema with live data.
Before switching from database to broker mode in an existing installation, drain queued audit jobs with the database worker or enqueue their events through a reviewed one-time migration; otherwise they have no outbox record for the broker publisher.
