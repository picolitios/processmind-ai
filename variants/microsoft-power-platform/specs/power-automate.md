# Power Automate flow blueprint

No cloud flows were created. These action definitions map to the verified HTTP
contract in [architecture](architecture.md). Use a solution flow and a secure,
delegated connector after the identity bridge is complete. Connection references
and secret values must be configured in the environment.

## RequestAudit

Trigger: `When an agent calls the flow` for agent use, or `When Power Apps calls
a flow` for the app. Inputs: one to 50 UUID import IDs and one 8–128-character
idempotency key. Validate shape, length and duplicates. Call `POST /audits` with
the active organization context and key. Return `{ok,auditId,status,message}`
immediately on 202. Do not wait for audit completion. A retry must reuse the
same key; 409 is a conflict, not a new request.

## GetAudit / ListAudits / ListFindings

Read through the delegated connector. Inputs: selected audit ID and optional
backend cursor. Output: actual status, count, findings/evidence and `next_cursor`.
Use bounded pages (max 100 by backend contract; 50 recommended). Do not merge
data from another organization or convert an empty page into a positive finding.
Failed audit returns its limitation. A missing ID returns `not_found`.

## Question flow

Create a temporary conversation for a **completed** audit, submit a question
with a stable idempotency key, return its question ID and queued status. A
separate read action checks `GET /ai/copilot/questions/{id}`. Only display
`succeeded` text when citations are present; otherwise return a limitation.
This pattern respects the asynchronous model worker.

## Optional notification

Only after the tenant has approved a notification connector: scheduled polling
of explicitly tracked audit IDs checks status with the same delegated identity.
Send one completion notification per audit ID/status transition. Store only
minimal metadata, enforce retention, and never include full evidence in email.
No notification service is configured in this repository.

## Failure handling

Use a Scope with success/catch branches. Map 401/403 to access denied, 404 to
not found, 409 to conflict, 422 to invalid input, 429 to retry later, and
5xx/timeout to unavailable. Bound transient retries; do not retry a POST with
a new idempotency key. Log correlation ID/status only, without token, request
body, imported content or prompt. The agent-facing branches must all return
the same output schema. Microsoft documents the [trigger, response and
real-time requirements](https://learn.microsoft.com/microsoft-copilot-studio/flow-modify-use-with-agent).
