# Distributed-load measurements

## Local development run — 2026-10-19

The running local Compose stack used PostgreSQL, separate identity and business APIs, the import worker, outbox publisher, RabbitMQ and the audit consumer. `scripts/benchmark_distributed.py` submitted six independent synthetic organizations, each with 1,000 purchase rows, using three concurrent clients over the nginx URL. The run lasted 15.923 s, completed all six workflows, made 94 HTTP requests and recorded a 0% workflow error rate. Completed-workflow throughput was 0.377/s for this small sample.

| Measure | p50 | p95 | p99 | Count |
| --- | ---: | ---: | ---: | ---: |
| Import completion, seconds | 2.256 | 2.787 | 2.791 | 6 |
| Audit completion, seconds | 1.409 | 2.192 | 2.194 | 6 |
| Audit creation HTTP, seconds | 0.083 | 0.103 | 0.108 | 6 |
| Audit status HTTP, seconds | 0.039 | 0.049 | 0.077 | 21 |

The script produced the complete per-operation report in the ignored `synthetic-output/distributed-load-local.json`. Six workflows are too few for a stable p99 or capacity estimate. Local resource use, pre-existing test records and host contention were not controlled; no production SLO follows from this run. The CI job repeats the same six-workflow shape on disposable volumes and publishes its JSON report as an artifact.
