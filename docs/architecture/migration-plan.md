# Incremental migration plan

## First vertical: audit dispatch

Acceptance: creating an audit through the existing REST API commits the audit run, job and versioned outbox event atomically; a publisher confirms delivery to RabbitMQ; an audit consumer processes the job and acknowledges only after the database commit; the existing authenticated GET returns findings and a succeeded audit. Duplicate delivery leaves one result. Broker outage leaves the outbox pending and the API response valid. Import and AI jobs still run through the existing worker. Existing tests, lint, types, migration and Compose health must pass.

1. Add an outbox migration and event contract. Keep one database transaction for audit creation.
2. Add publisher and consumer processes to Compose, broker credentials scoped to local development, durable queue with delayed retry and DLQ.
3. Make the existing polling worker skip audit jobs in broker mode. Keep database mode for compatibility and rollback.
4. Test atomic enqueue, duplicate handling, broker interruption, and end-to-end result lookup. Document measured outcomes only.

## Subsequent increments

1. Stabilize contract and recovery tests; add queue depth, publish latency and worker metrics. CI exercises the real broker outage/recovery path on an isolated stack. Read-only diagnostics and the v1 no-deletion retention policy are specified in `specs/architecture/audit-operations-v1.md`. The local Compose health signal is specified in `specs/architecture/audit-monitor-v1.md`; correlated HTTP-to-audit-broker JSON records are specified in `specs/architecture/audit-observability-v1.md`, with signed business-to-identity correlation in `specs/architecture/identity-correlation-v1.md`. Retained time-series, external paging, distributed spans and a measured purge policy remain later work.
2. Put identity routes behind a dedicated process and gateway rule while preserving the shared transaction model. Test tenant authorization and rollback. Then replace direct business-module identity table reads with explicit contracts and migrate FKs/credentials/schema before declaring exclusive data ownership.
3. Separate import and model workers in Compose so local model latency does not claim import jobs; `specs/architecture/model-worker-boundary-v1.md` defines this process-only increment. Extract audit/ingestion and AI data ownership on demonstrated scaling or security needs. Replace cross-domain table reads with versioned APIs/events and test authorization and reconciliation.
4. Add notification and analytics consumers only when product requirements call for them. CI includes browser, real broker recovery and small concurrent distributed-load evidence; extend contract and representative load evidence when the related boundaries change. The local deployment sequence and read-only release gate are documented in `docs/deployment.md` and `specs/architecture/deployment-preflight-v1.md`; production hosting remains a separate decision.

The V2 conversational copilot is integrated on `main`. Its history and access-policy decisions do not alter the first event contract.

## Identity data cutover dependencies

The dedicated identity process and separate runtime schema credentials are live in Compose. The table dependencies below were migrated in order; rollback modes still require the administrative credential and reconciliation gates:

| Business dependency | Current use | Cutover and rollback note |
| --- | --- | --- |
| `UserSession` and `User` | Business API previously validated the session cookie directly | Signed, bounded identity introspection with fail-closed behavior and revocation tests now handles business routes in Compose; direct identity routes remain for compatibility |
| `Organization` and `Membership` | Identity authorizes tenant membership and resolves case references through private contracts; audit reads an audit-owned configuration row in Compose without locking the organization row | A durable command and signed audit-owner apply call coordinate settings; reference reconciliation and a physical-delete guard preceded isolated credentials |
| `AuditEvent` | Business modules own an append-only trail; Compose omits the temporary legacy write, while `dual` mode remains for rollback | Verify the copies and restore missing legacy IDs before reverting to an older image |
| FKs to users, organizations and memberships | Business tables retain historical UUIDs; public writes validate session, tenant and member references through identity | Cross-domain FKs were removed reversibly; business-to-business constraints and the physical-delete guard remain |

Compatibility identity routes remain in the business API for direct clients. Audit configuration writes are coordinated across processes in Compose, with a temporary shared-transaction mode for rollback. The business event trail uses owned-only writes in Compose, but rollback restoration still needs shared-database access.

The [identity data cutover plan](identity-data-cutover-plan.md) records the completed sequence and release gates. ADR 0003 records audit ownership and the former shared lock.

Audit configuration rollout: apply the additive migrations first. Before enabling `AUDIT_CONFIG_MODE=owned` and `AUDIT_CONFIG_WRITE_MODE=coordinated`, compare organization and audit-configuration counts, versions and values. Recreate API and identity only after the copy is verified. Coordinated writes require owned snapshot reads. For a shared-database rollback, drain all configuration commands, verify the copies again, and select `AUDIT_CONFIG_WRITE_MODE=database` together with `AUDIT_CONFIG_MODE=legacy`; retain both tables and their synchronized data.

Identity rollback: the former shared-schema image requires the documented schema downgrade, administrative credential and data reconciliation. Then remove the identity gateway locations, set `BUSINESS_AUTH_MODE=database` on the API, and recreate API/web before stopping identity. Follow `docs/installation.md`; do not switch modes against the current isolated roles.

Rollback: stop publisher/consumer, set `AUDIT_DISPATCH_MODE=database` on API and polling worker, and retain the additive outbox table. Do not drop records or revert schema with live data.
Before switching from database to broker mode in an existing installation, drain queued audit jobs with the database worker or enqueue their events through a reviewed one-time migration; otherwise they have no outbox record for the broker publisher.
