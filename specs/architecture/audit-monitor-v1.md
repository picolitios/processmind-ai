# Audit dispatch monitor v1

Status: approved operational increment after `audit-operations-v1.md` and the
RabbitMQ recovery CI gate. It reuses the aggregate read-only diagnostics and
does not change audit processing or expose a public route.

## Contract

1. A dedicated Compose process samples the audit outbox, audit jobs and four
   RabbitMQ queues every configured interval. It checks pending outbox age,
   oldest queued audit job, expired audit leases and nonempty dead-letter
   queue. The default age threshold is 300 seconds; the interval is 60 seconds.
2. Each sample atomically replaces a local status file with UTC observation
   time, `ok`, `threshold_exceeded` or `unavailable`, and stable failure codes.
   Database or broker failure is `unavailable`. Neither file nor logs contain
   tenant IDs, payloads, prompt content, credentials or exception messages.
3. Docker Compose health is healthy only for a fresh `ok` sample. An alert or
   stale/unavailable sample marks the monitor container unhealthy without
   restarting workers or discarding any event. A later healthy sample clears
   the condition. The monitor logs state changes as JSON.
4. Operators inspect `docker compose ps audit-monitor` and
   `docker compose logs audit-monitor`, then use the detailed read-only
   operations command to investigate. This is a local health signal, not a
   paging system or proof that individual workers are responsive.

## Acceptance

- Unit tests cover healthy, alert, unavailable and stale states, recovery,
  invalid configuration, and output redaction.
- Compose builds and starts the monitor, reaches healthy on a working stack,
  and turns unhealthy when a simulated data source is unavailable.
- Ruff, mypy, relevant API tests and Compose configuration pass.

## Limits

The status file is inside the container and is not durable. No metric
retention, Prometheus endpoint, automatic dead-letter replay or destructive
cleanup is introduced. Aggregate telemetry is available only to operators
with access to the local Compose runtime.
