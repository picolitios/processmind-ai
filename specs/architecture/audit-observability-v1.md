# Audit flow structured records v1

## Scope and acceptance

- The business and identity APIs emit one JSON record per HTTP request with UTC time, service, correlation ID, method, route template, status and duration. Raw paths, query strings, headers, bodies, session tokens and tenant data are excluded.
- The audit publisher and consumer emit JSON outcome records keyed by the `correlation_id` already stored in the versioned outbox envelope. Records contain only stable action/outcome names, event ID and error class when applicable. Invalid event bodies are never logged.
- Processing failures continue to use the existing retry and dead-letter semantics. Logging must not alter event delivery or acknowledgement.
- Tests verify the JSON fields, redaction and HTTP-to-outbox correlation. Existing broker recovery and browser gates remain green.

This increment uses Python's standard logging library. It supplies a searchable correlation trail in Compose logs, not retained telemetry, cross-service spans, external tracing infrastructure or an alerting service.
