# Import deduplication lock v1

Status: approved as a reversible Phase 2 data-boundary increment under `specs/architecture/system-design.md`.

## Scope and acceptance

1. After authenticating and authorizing the organization, concurrent uploads for the same organization serialize the idempotency-key and file-hash checks within the same database transaction. Uploads for different organizations do not need to share a lock.
2. The lock uses a PostgreSQL transaction-scoped advisory key derived from the organization UUID and the import domain. No business process locks or reads the identity-owned `organizations` row solely for deduplication.
3. Existing responses remain: duplicate hash without reimport reason returns 409; retry with the same idempotency key and payload returns the existing import; reuse of a key with different content returns 409. The original file is removed on conflict or idempotent retry.
4. Existing and new concurrent upload tests, tenant isolation, lint, types and browser flow pass. No schema, public API or worker behavior changes. Rollback is restoring the previous organization row lock while the database remains shared.

This increment does not remove organization or user FKs, business audit-trail writes or the audit-settings snapshot dependency.
