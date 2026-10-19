# Local deployment and release gate

ProcessMind AI currently runs as a single-host Docker Compose installation.
The [Oracle Always Free demo guide](demo-oracle-always-free.md) prepares a public
TLS installation but has not been deployed or validated on a public VM. The
local installation has no public TLS endpoint, offsite backup schedule,
high availability or production recovery objective. Do not expose its bound
local ports as a customer service without designing and validating those
operational controls.

## Fresh installation

Use the [installation guide](installation.md) to create `.env`, apply Alembic
migrations, provision the two runtime roles and start Compose. Confirm both
readiness endpoints, then run the read-only release gate:

```powershell
python scripts/verify_deployment.py
```

Exit `0` with `"status":"ok"` means all 11 persistent services are running,
the six services with healthchecks are healthy, the database revision matches
the checked out image, the identity and business runtime roles reject
cross-domain access, and the audit outbox/queues have no selected alert. Exit
`2` means at least one check failed. The JSON names only stable checks and
service states. Use `docker compose ps`, the [audit operations command](../specs/architecture/audit-operations-v1.md)
and service logs for follow-up; do not infer customer data from this gate.

The age threshold defaults to 300 seconds and can be selected with
`--max-pending-age-seconds`. The command never applies migrations, changes
data, restarts a container or replays a dead letter.

## Upgrade sequence

1. Record the current image commit, Alembic revision and current health. Read
   the release's specs, migrations and rollback notes. Test the target image
   and migration in an isolated project first.
2. Create a [quiesced backup](backup-and-restore.md) of PostgreSQL and private
   uploads. Preserve a protected, separate copy and verify it. Stop writers
   before migrating the existing installation.
3. Build the target images, apply only the reviewed Alembic upgrade with
   `db-admin`, and provision runtime roles. Follow any feature-specific
   reconciliation gate in [the installation guide](installation.md).
4. Start services, run `python scripts/verify_deployment.py`, then perform the
   browser E2E flow on an isolated or approved demonstration installation.
   Inspect `audit-monitor` and outbox/queue state before accepting new work.
5. If the gate fails, investigate its named checks. Roll back the image or
   schema only by the migration-specific documented sequence; never restore a
   backup into a live volume or downgrade a populated schema automatically.

The CI performs the release gate on a disposable migrated stack before browser
E2E, then exercises load and isolated database and upload-volume restore checks. It provides repeatable
local evidence, not a production deployment approval. A customer deployment
still needs TLS, secret management, access controls for ports and volumes,
encrypted offsite backups with tested restore, monitoring retention and
alerting, capacity measurements on representative hardware, data retention
policy and documented RPO/RTO.
