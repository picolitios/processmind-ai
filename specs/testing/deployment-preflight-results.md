# Local deployment preflight result — 2026-10-19

The read-only `python scripts/verify_deployment.py` command exited `0` against
the existing developer Compose project. It reported `status=ok`: all 11
persistent services running; `db`, `rabbitmq`, `api`, `identity`, `web` and
`audit-monitor` healthy; the installed Alembic revision at the source image's
head; both runtime roles denied cross-schema access; no audit-dispatch alert
at the default 300-second age threshold. The gate took about 10 seconds.

Only `db-admin` was rebuilt locally for this check. Other locally running
images preceded the new deployment gate and identity-dependent readiness
change; the isolated CI Compose job is the validation of the complete new
image set. This single observation does not prove future availability,
production capacity or restore time.
