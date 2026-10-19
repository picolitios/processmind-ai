# Identity-dependent readiness v1

Status: operational increment for the existing Compose deployment. Business
requests in `BUSINESS_AUTH_MODE=identity` require the identity process to
authorize every session and membership; database-only readiness is misleading
when identity is unavailable.

## Contract

1. `/api/v1/health/live` remains a process liveness check. The identity API's
   readiness continues to require its database only.
2. The business API's readiness requires its database and, in identity mode,
   a bounded GET of the identity process's private-network readiness endpoint.
   Accept only HTTP 200 with `{"status":"ok"}` and the identity service
   marker header. Timeout, connection failure, malformed response or another
   status yields the existing 503 `{"status":"unavailable"}` response.
   The check sends no user credential, cookie or tenant data and logs no URL.
3. In the documented database rollback mode, business readiness requires its
   own database only. RabbitMQ and Ollama are intentionally excluded: an
   audit request can persist in the outbox during a broker outage, and model
   output is optional. The audit monitor retains the broker signal.
4. The web container's Compose healthcheck probes the nginx-proxied business
   readiness endpoint so a broken gateway route is visible, while static UI
   liveness remains available independently.

## Acceptance

- Unit tests cover identity success, non-200, wrong service marker, malformed
  body, timeout and database rollback mode. The existing database readiness
  test remains green.
- In an isolated Compose CI stack, stopping identity makes business and web
  readiness return 503; restarting it restores HTTP 200, and browser E2E
  still passes.
- API and web checks, Compose config, specs validation and full PR gates pass.
