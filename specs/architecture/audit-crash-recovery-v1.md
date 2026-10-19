# Audit consumer crash recovery v1

Status: approved implementation increment of `audit-events-v1.md`. The public API,
event envelope, three-attempt limit and one-hour database-worker lease remain unchanged.

## Contract

1. A broker delivery can reclaim a `running` audit job before its lease expires
   when no transaction holds the job row. RabbitMQ requeues an unacknowledged
   delivery after the consumer connection closes. A locked row means another
   attempt is processing; the delivery goes through the existing delayed queue
   without consuming another attempt.
2. Each broker claim persists a fresh opaque attempt token. The audit worker
   checks it while holding the job row lock before writing findings. A previous
   attempt that loses the claim does not change job or run state. Its delivery
   may be acknowledged because the current owner has its own delivery.
3. Every claim increments `attempt_count`. Three crashed or failed attempts
   end in `failed` and dead letter. Successful and terminal jobs retain their
   existing idempotent behavior. Existing jobs with a null token are claimable.
4. The token stays in the business database, never in the event envelope,
   response or logs. The additive migration is reversible while preserving jobs.

## Acceptance

- Simulate a process exit after a committed claim and before processing. A
  re-delivery completes the same audit immediately without waiting for the lease.
- A concurrent delivery cannot take a row locked by active processing; an old
  token cannot write findings or overwrite a newer attempt's failure state.
- Duplicate success, tenant mismatch, transient retry and broker outage tests
  still pass. Alembic, Ruff, mypy and the complete CI pipeline pass.
