# Signed identity-call correlation v1

Status: operational observability increment for the private identity boundary.
The business API generates a fresh UUID for each incoming request. Its private
session, membership and member-reference calls currently create unrelated
identity request IDs, making a failed authorization hard to follow in logs.

## Contract

1. The business request middleware stores its generated correlation UUID only
   for the lifetime of that request. Browser-supplied correlation headers do
   not override it. Concurrent requests cannot inherit one another's IDs.
2. The three private identity calls include `X-Internal-Correlation-ID` when a
   business request context exists. The existing short-lived HMAC covers this
   ID as well as the timestamp, session token and operation subject. Calls
   outside an HTTP request retain the old signature and omit the header.
3. Identity accepts the UUID only after the HMAC is verified. Its response
   header and allowlisted HTTP log then use the originating business ID.
   An invalid or unsigned ID cannot become the identity log correlation ID.
4. This changes no public API body or event version. Logs still omit raw URLs,
   tenant data, session tokens and private request bodies. Correlated records
   are not full distributed spans or retained tracing telemetry.

## Acceptance

- Tests prove valid signed propagation, tampering rejection, browser-header
  rejection, missing-context compatibility and isolation of request contexts.
- Existing identity authorization, tenant isolation and browser gates pass.
- Ruff, mypy and API test gates pass before integration.
