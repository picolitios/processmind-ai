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

## Isolated CI run — 2026-10-19

The [PR #28 CI run](https://github.com/picolitios/processmind-ai/actions/runs/39266661850) completed all six workflows with 1,000 rows per organization and three concurrent clients on newly migrated Compose volumes. It made 91 HTTP requests in 9.821 s. Both HTTP and workflow error rates were 0%; completed-workflow throughput was 0.611/s in this sample. The workflow uploaded the full JSON result as `distributed-load-result`.

| Measure | p50 | p95 | p99 | Count |
| --- | ---: | ---: | ---: | ---: |
| Import completion, seconds | 2.306 | 2.846 | 2.854 | 6 |
| Audit completion, seconds | 1.142 | 2.245 | 2.267 | 6 |
| Audit creation HTTP, seconds | 0.079 | 0.089 | 0.090 | 6 |
| Audit status HTTP, seconds | 0.044 | 0.080 | 0.099 | 20 |

The runner is shared and its resource allocation can change between runs. The observed CI p99 is an interpolation over a small sample, not a production tail-latency estimate. Compare repeated runs on representative hardware before setting capacity or alert thresholds.
