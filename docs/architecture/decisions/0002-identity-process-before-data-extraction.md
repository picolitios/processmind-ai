# ADR 0002: identity process before data extraction

Status: accepted for Phase 2 increment, 2026-10-15.

## Context

The modular API directly reads memberships and sessions, joins organization settings into audits, writes audit trail rows, and has tenant-scoped foreign keys into identity tables. Moving identity tables to a separate database in one step would break authorization, auditing and referential integrity. A process boundary can be verified first while retaining the current transaction model.

## Decision

Run the existing identity routers in a dedicated FastAPI process and route the public identity paths through nginx. Business routes introspect sessions and CSRF through a private signed HTTP contract; business membership and organization queries remain local. Keep the existing business API identity routes temporarily for direct API compatibility. Use the same PostgreSQL database and schema in this increment, with no claim of exclusive data ownership. Validate routing and tenant authorization through the gateway before replacing the remaining table access with explicit service contracts.

## Consequences

Identity traffic and process health can be operated independently, but the processes remain coupled through PostgreSQL and the shared Python image. Session, CSRF and membership authorization are private, signed and checked on business requests; organization settings and case membership references still come from the shared database. Future work must define organization setting ownership, case reference lookup, audit-trail ownership, migration of cross-domain FKs, database credentials and a no-downtime cutover. The gateway can be rolled back without migrating data.
