# Membership authorization boundary v1

Status: approved as the next reversible identity extraction increment. Session rules in `specs/decisions/0002-tenancy-and-sessions.md` remain authoritative.

## Scope and acceptance

1. In Compose, business routes ask identity for the active membership of the authenticated user in the requested organization. The request is signed, private, bounded and checked against the opaque session; no role decision is cached.
2. A missing or inactive organization or membership returns the existing tenant-safe 404. A valid member with insufficient role receives the existing 403. A revoked session returns 401; identity outage returns 503. Business data is not queried before membership authorization.
3. The identity process owns the authorization query. The business API may still read organization settings and case membership references from the shared database in this increment; this is not independent data ownership.
4. Existing two-tenant, role-change, session-revocation and browser flows remain green. The new internal endpoint is absent from public OpenAPI and inaccessible through nginx.
5. Local database mode remains a rollback path for host tests and existing deployments. Reverting Compose to database mode and the gateway to the business API needs no data migration.

## Deferred data extraction

Case assignee and author lookups, organization settings snapshots, cross-domain foreign keys and audit trail writes need separate contracts or ownership changes before database credentials can be isolated.
