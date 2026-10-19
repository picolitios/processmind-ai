# Distributed audit load evidence v1

## Goal

Measure the real HTTP → import worker → outbox → RabbitMQ → audit consumer path with synthetic purchases and concurrent, isolated organizations. The earlier `benchmark_pipeline.py` measures a sequential in-process path and remains useful for regression comparison.

## Acceptance

- A CLI drives registration, organization creation, upload, mapping, import completion, audit request, audit completion and findings through the public nginx URL. Each simulated user has a separate HTTP session and organization.
- The CLI accepts bounded user count, rounds, synthetic row count and job deadline. It runs only against loopback URLs when `PROCESSMIND_LOAD_TEST=1` is explicitly set.
- JSON results include request count, HTTP status counts, HTTP and workflow error rates, completed workflows per second, per-operation latency p50/p95/p99, import and audit completion p50/p95/p99, and error class/count. They exclude credentials, cookies, user/org identifiers, file contents and response bodies.
- The browser CI job runs a small concurrent sample on its disposable Compose stack after E2E, uploads the JSON result, and fails on any workflow error. Numeric performance thresholds are not gates until measured repeatedly on representative hardware.
- Unit tests cover percentile math, aggregate summaries and failure reporting. The CI run verifies the complete distributed workflow.

## Limits

The CI runner varies in available CPU and IO. Its measurements establish repeatable behavior and catch functional regressions under modest concurrency, but do not define production capacity or an SLO. The output has no retained history until an explicit baseline policy is approved.
