# Identity data ownership cutover

Status: migration design. No schema or credential cutover is authorized by this document alone. The public `/api/v1` contract, existing data and tenant isolation must survive every increment.

## Current dependency inventory

| Dependency | Current reason | Exit condition |
| --- | --- | --- |
| `organizations` | Audit creation still locks the row to serialize with settings writes; the audit settings copy now has an additive business-owned table | Remove the transitional cross-domain write and lock after a durable contract preserves the versioned snapshot; import deduplication already has a domain advisory lock |
| `organization_memberships` | Case FKs reference assignee and comment author; identity validates active membership and resolves display IDs through private contracts | Keep historical UUIDs and tenant validation after removing cross-domain FKs; reconcile references before any constraint change |
| `users` | Imports, audits and AI jobs store actor UUIDs with FKs | Validate the actor through identity at request time, retain immutable UUIDs, and reconcile all existing references |
| `audit_events` | Identity owns user/session/organization events; business routes and workers still append a legacy copy inside the same transaction | Business events now have an additive business-owned table and backfill; remove the transitional legacy write only after reconciliation and a rollback plan, never replace atomic recording with best-effort HTTP |
| `organizations` FKs | Imports, purchases, jobs, audits, analyses, cases and outbox rows reference the tenant | Retain tenant-scoped composite business FKs and application authorization; reconcile tenant UUIDs before dropping cross-domain FKs |

The current shared PostgreSQL instance can host separate schemas and roles. Separate service credentials are meaningful only after no process queries another owner's private tables. Moving tables to schemas without first removing those queries does not establish data ownership.

## Safe sequence

1. Audit settings belong to audit (ADR 0003). Preserve the existing snapshot fields, public settings response and audit idempotency.
2. Move upload deduplication locking to a domain-scoped transaction advisory key derived from the organization ID. Keep the unique/idempotency checks and tenant authorization. Test concurrent uploads of the same hash and key before removing the organization row lock.
3. The additive audit-owned table is backfilled from existing settings. Verify counts and versions before enabling `AUDIT_CONFIG_MODE=owned`; Compose uses this mode. The public identity route temporarily writes both rows in one database transaction, which is explicitly documented in ADR 0003. Keep legacy data and `AUDIT_CONFIG_MODE=legacy` for rollback. Replace this cross-domain write before credential isolation.
4. Business actions belong to the business audit trail (ADR 0004). Backfill historical actions and temporarily write both tables atomically. Before retiring the legacy write, verify reconciliation and rollback. Use a transactionally written outbox if event delivery crosses service boundaries.
5. The read-only reference reconciliation in `app.db.reconcile_identity` now checks actor, tenant and membership UUIDs, including same-tenant membership links and business tables without FKs. Run it before any schema or credential cutover; the local result is recorded in `reference-reconciliation-2026-10-16.md`. Preserve business-to-business composite FKs. Drop cross-domain FKs only after verified contracts, historical references, deletion policy and rollback exist; no physical data deletion belongs to this increment.
6. Move tables into separate PostgreSQL schemas or databases with distinct service roles. Use a separate migration role for DDL. Prove that each runtime credential cannot SELECT or mutate another owner's private tables.

## Gates and rollback

- Run two-tenant authorization and ID-mismatch tests, role changes, session revocation, case history, concurrent import deduplication, concurrent settings update/audit snapshot, audit outbox recovery, and browser E2E.
- The current shared-row implementation has a regression test requiring each concurrent audit snapshot to contain a matching settings version and values. Any data-ownership cutover must pass the same invariant.
- Compare counts and sampled IDs before and after backfill. Fail closed on identity or settings-owner outage; do not silently use stale configuration.
- Apply additive migrations first. Delay constraint removal and credential revocation until all tests and reconciliation checks pass. Preserve legacy data for rollback; no destructive migration or direct production operation is implied.
