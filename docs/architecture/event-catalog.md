# Event catalog

## `audit.requested` version 1

Produced only after a successful `POST /api/v1/organizations/{organization_id}/audits` transaction. Exchange: `processmind.events`; routing key: `audit.requested.v1`. It is a command-like domain event for an existing audit job, not a public API request. The event does not contain imports, evidence or secrets.

```json
{
  "event_id": "UUID",
  "event_type": "audit.requested",
  "event_version": 1,
  "occurred_at": "RFC3339 UTC timestamp",
  "correlation_id": "UUID",
  "causation_id": "UUID or null",
  "tenant_id": "organization UUID",
  "payload": {"audit_id": "UUID", "job_id": "UUID"}
}
```

The consumer rejects unsupported versions and validates `tenant_id`, `audit_id` and `job_id` against persisted rows. A broker duplicate may arrive after success; the job state makes it a no-op. Messages are acknowledged after transaction completion. Transient errors enter a delayed retry queue; exhausted or invalid messages enter the dead-letter queue for operator review. Queue payloads are not authorization credentials. Outbox records are retained until a measured retention policy is established.

No other event name is claimed as implemented. Existing `audit.completed` entries in the database audit trail are not broker events.
