# Audit dispatch operations v1

Status: approved incremental work under the architecture migration plan. This
increment observes the existing `audit.requested.v1` path. It does not change
the public API, event envelope, queue topology, or audit rules.

## Contract

1. An internal command reads aggregate outbox and audit-job state from the
   business schema and queue depth from the RabbitMQ management API. It emits
   one JSON object with a UTC observation time, pending outbox count and oldest
   age, publication latency for events published during the previous 24 hours,
   audit-job counts by state and expired running leases, and ready/unacknowledged
   message counts for the main, retry and dead-letter queues.
2. Publication latency is `published_at - created_at`, measured only for rows
   with both timestamps. Report count, mean and p95 in seconds; report null
   latencies when no rows qualify. Queue depth is a snapshot, not throughput.
3. The command has no tenant-scoped data, event body, job ID, credential or
   prompt in output. It is an operator-only command, not an HTTP route.
4. RabbitMQ/API or database failure produces a nonzero exit status. Optional
   thresholds fail the command when the oldest pending event exceeds the
   configured age, any audit lease is expired, or the dead-letter queue is
   nonempty. A threshold failure never modifies data.
5. The audit domain owns the outbox and queue topology. Published outbox rows
   and dead letters are retained without automatic deletion in v1. Operators
   investigate dead letters before replay or removal. A later bounded purge
   requires measured volume, backup/restore proof and a separate reviewed
   specification. Unpublished outbox rows are never eligible for purge.

## Acceptance

- Unit tests cover empty metrics, latency math, thresholds, unavailable broker
  and no secret or tenant detail in output.
- A running Compose stack returns a valid snapshot with all four audit queues.
- Ruff, mypy and the relevant API tests pass. Existing audit dispatch tests
  continue to pass.

## Operational limits

Metrics are point-in-time diagnostics, not a monitoring server or paging
system. A successful observation does not prove future broker availability.
The management API is reachable only on the local Compose host and internal
network. No automatic retention or dead-letter replay is introduced here.
