# Local deployment preflight v1

Status: operational increment for the existing Docker Compose installation.
The command is a release/upgrade gate after migrations and service startup,
not a production deployment system.

## Contract

1. A read-only host command checks that all 11 persistent Compose services are
   running and that the services with healthchecks (`db`, `rabbitmq`, `api`,
   `identity`, `web`, `audit-monitor`) are healthy. It emits only stable service
   names and statuses, not container IDs, environment variables or logs.
2. An administrative, read-only command compares the database's current
   Alembic revision set to the source image's head set. Missing, divergent or
   multiple unexpected revisions fail closed. It never applies migrations.
3. The host command executes the existing runtime credential probes for the
   business and identity schemas. Either cross-domain grant failure rejects
   the preflight.
4. The host command executes the existing aggregate audit dispatch snapshot
   with a 300-second default age threshold (operator adjustable), expired
   lease and dead-letter gates.
   Database or broker unavailability rejects the preflight. No tenant IDs,
   queue bodies, upload names or prompt contents appear in output.
5. The command returns one JSON result and exits nonzero if any check fails.
   Checks are independent so an outage still permits a bounded diagnosis of
   the remaining components. It does not restart containers, replay messages,
   migrate schemas or modify customer data.

## Acceptance

- Unit tests cover healthy and unhealthy services, malformed Compose output,
  command failure and aggregate failure behavior without Docker mutations.
- CI runs the preflight against a disposable migrated Compose stack before
  browser E2E. The role, revision and broker checks all pass.
- Local execution against the existing Compose stack is recorded without
  claiming a production deployment or recovery objective.
