# Case membership lookup boundary v1

Status: approved incremental Phase 2 contract under `specs/architecture/membership-boundary-v1.md` and `specs/architecture/cases-and-analytics-v1.md`.

## Behavior and acceptance

1. In Compose, case routes resolve assignee and author membership references through a private identity batch endpoint. A signed request includes the caller's opaque session and organization ID; identity checks active caller membership before returning only requested references from that organization. The endpoint is absent from public OpenAPI and inaccessible through nginx.
2. Assignee selection accepts only an active member of that organization and otherwise keeps the existing `422 invalid_assignee`. Historical case and comment views retain user IDs for inactive members. Cross-tenant IDs never resolve.
3. Resolve at most 100 membership IDs and one assignee user ID per request. Case lists and comments remain paginated; no per-row HTTP requests. Identity outages fail closed with 503. Invalid caller sessions remain 401; missing caller membership remains tenant-safe 404.
4. Local database mode preserves the existing behavior for rollback. No schema or public API changes. Composite foreign keys and business transaction boundaries remain intact.

## Deferred

Organization settings snapshots, business audit trail writes and cross-domain foreign keys still prevent exclusive identity data ownership. Do not move tables or revoke database grants in this increment.
