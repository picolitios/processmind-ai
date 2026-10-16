# Identity HTTP boundary v1

Status: approved as the first reversible Phase 2 extraction increment. This is a process and routing boundary, **not yet independent data ownership**. `specs/decisions/0002-tenancy-and-sessions.md` remains authoritative for session and tenant behavior.

## Scope and acceptance

1. A dedicated FastAPI process exposes only the existing `/api/v1/auth/*` and identity-owned `/api/v1/organizations` routes, plus liveness/readiness. Responses, cookies, CSRF, RBAC and error codes stay compatible with the MVP contract.
2. nginx routes those exact identity paths to the new process; import, audit, AI, case and analytics paths continue to the business API. nginx continues to resolve container addresses after recreation. No client-facing URL changes.
3. The identity process can start, report readiness, be tested and be restarted independently. It must not expose business routes. Existing direct API identity routes remain available during this compatibility increment.
4. The organization path router must cover list/create, organization detail/settings and users/membership endpoints without capturing `/imports`, `/audits`, `/findings`, `/cases`, `/analytics` or `/ai`.
5. Existing two-tenant authorization tests and browser flow must pass through the new gateway route. A service-specific response header proves which process served an identity request without exposing internals or credentials.
6. In this increment both processes still share PostgreSQL. Business modules continue to query identity tables and use cross-domain FKs. This is an explicitly transitional dependency; do not claim separate data ownership or Phase 2 completion.
7. In Compose, business routes validate opaque sessions and CSRF through a private identity introspection endpoint, with a timestamped HMAC request signature derived from the configured auth key. Introspection is not exposed by nginx. Session revocation is checked on every request; no authorization decision is cached. A business request fails closed when identity is unavailable. Role/membership checks remain in the shared database until the next extraction increment.

## Rollback

Route identity paths back to the existing business API and stop the dedicated identity process. No migration or data copy is required. Do not change session signing, cookie names or stored user IDs during the switch.
