# Compose restart recovery v1

## Observed failure

On 2026-10-19, after the local Docker engine restarted, PostgreSQL, RabbitMQ, business API, identity API and web remained stopped while the import/model workers restarted and failed to resolve `db`. Bringing dependencies back with `docker compose up -d --no-build` and restarting the workers restored health. No data migration or volume removal was needed.

## Acceptance

- Every long-lived Compose service has `restart: unless-stopped`. The one-shot `db-admin` tool has no restart policy.
- Startup still uses health-aware `depends_on` for `docker compose up`; runtime restarts may happen before dependencies become healthy, so services must retry or regain health as dependencies return.
- A local update preserves the existing PostgreSQL, RabbitMQ and upload volumes. All services return to running, and every service with a healthcheck becomes healthy; an end-to-end browser flow or synthetic load smoke succeeds afterward. CI checks the actual restart policy on every long-lived container in its disposable stack.
- The guide distinguishes Docker-engine restart from an intentional `docker compose stop`, which needs an explicit `start`/`up` to resume.

This is local Compose lifecycle resilience. It is not high availability, automatic failover between hosts, or a production orchestration policy.
