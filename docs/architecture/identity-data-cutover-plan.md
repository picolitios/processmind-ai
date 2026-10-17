# Identity data ownership cutover

Status: steps 1–6 implemented in Compose. The schema and credential increment is specified in `specs/architecture/identity-schema-credential-boundary-v1.md`. The public `/api/v1` contract, existing data and tenant isolation survive the cutover.

## Current dependency inventory

| Dependency | Current reason | Exit condition |
| --- | --- | --- |
| `organizations` | Identity owns the active-organization check; remote business authorization does not read or lock this row. Legacy database authorization remains an administrative-credential rollback path | Retire the rollback path only after the old image is no longer needed |
| `organization_memberships` | Case assignee and comment author retain historical membership UUIDs; identity resolves display IDs through private contracts | Reconcile references and block physical member deletion during the FK transition; preserve the member UUIDs |
| `users` | Imports, audits and AI jobs retain historical actor UUIDs | Validate the actor through identity at request time, reconcile references and block physical user deletion during the FK transition |
| `audit_events` | Identity owns user/session/organization events; business routes and workers can still append a legacy copy in `dual` mode | Compose selects business-owned writes after reconciliation; retain the temporary dual mode and controlled legacy-copy restoration for rollback until the old application image is retired |
| `organizations` FKs | Business tables retain tenant UUIDs without cross-schema FKs; tenant-scoped composite FKs between business tables remain | Reconcile tenant UUIDs before and after the cutover; keep the physical deletion guard until a retention flow exists |

The shared PostgreSQL instance now hosts separate schemas and roles. The Compose runtime uses only remote cross-domain contracts; shared-table modes are reserved for rollback with the administrative credential.

## Safe sequence

1. Audit settings belong to audit (ADR 0003). Preserve the existing snapshot fields, public settings response and audit idempotency.
2. Move upload deduplication locking to a domain-scoped transaction advisory key derived from the organization ID. Keep the unique/idempotency checks and tenant authorization. Test concurrent uploads of the same hash and key before removing the organization row lock.
3. The additive audit-owned table is backfilled from existing settings. Verify counts and versions before enabling `AUDIT_CONFIG_MODE=owned`; Compose uses this mode. `audit-configuration-coordination-v1.md` replaces the transitional identity write with a durable command and signed audit-owner apply contract in Compose. `organization-authorization-boundary-v1.md` removes the business-side organization row lock in identity mode and serializes snapshots on the audit-owned configuration row. The old shared transaction remains a rollback mode; drain pending commands and compare both copies before using it.
4. Business actions belong to the business audit trail (ADR 0004). Backfill historical actions and temporarily write both tables atomically. `business-audit-trail-cutover-v1.md` defines owned-only writes, reconciliation and controlled rollback. Verify the copies before switching an existing deployment; use a transactionally written outbox if event delivery later crosses service boundaries.
5. The read-only reference reconciliation in `app.db.reconcile_identity` checks actor, tenant and membership UUIDs, including same-tenant membership links and business tables without FKs. Run it before and after the reversible cutover in `identity-reference-fk-cutover-v1.md`; the original local result is recorded in `reference-reconciliation-2026-10-16.md`. Preserve business-to-business composite FKs. A temporary database guard rejects physical deletion of organizations, users and memberships until a future retention policy and deletion flow exist.
6. Implemented: identity and business tables reside in separate PostgreSQL schemas with distinct runtime roles. A separate administrative credential performs DDL and reconciliation. Integration tests and the runtime credential probe require cross-owner SELECT/INSERT/UPDATE/DELETE denial.

## Gates and rollback

- Run two-tenant authorization and ID-mismatch tests, role changes, session revocation, case history, concurrent import deduplication, concurrent settings update/audit snapshot, audit outbox recovery, and browser E2E.
- The audit-owned configuration implementation has a regression test requiring each concurrent audit snapshot to contain a matching settings version and values.
- Compare counts and sampled IDs before and after backfill. Fail closed on identity or settings-owner outage; do not silently use stale configuration.
- Preserve legacy copies for rollback. The schema move runs transactionally after reconciliation with writers stopped; no destructive data migration or direct production operation is implied.
