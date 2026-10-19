# Backup and restore for local Compose

This procedure creates an offline, consistent backup of PostgreSQL and the
private upload volume. It requires downtime. Use a new directory on protected
storage; it contains customer records and original imported files. The script
does not stop services, delete volumes, or restore into a live installation.

## Create a backup

1. Stop the public entry point, API, identity, import/model workers and identity
   reconciler. Keep PostgreSQL, RabbitMQ, audit publisher and consumer running
   until their existing audit work drains.
2. Inspect audit dispatch. Require `pending=0`, no queued/running audit jobs,
   and no messages in any of the four audit queues. Investigate dead letters;
   do not discard them to make a backup pass.
3. Stop the publisher and consumer. Run the backup script. It repeats the
   database and queue checks and rejects any running application writer.
4. Restart services with Compose, then check their health.

```powershell
docker compose stop web api identity identity-config-reconciler worker model-worker
docker compose run --rm --no-deps audit-publisher python -m app.features.audit.operations
docker compose stop audit-publisher audit-consumer
python scripts/backup_local.py backup backups/processmind-2026-10-19
docker compose up -d --no-build --wait --wait-timeout 180
```

The monitor may remain active because it only reads. If the audit snapshot has
pending work, restore the publisher and consumer, let it finish, and repeat the
check. The backup command must never be used as a substitute for draining.
The output is `database.dump`, `uploads.tar` and `manifest.json` with SHA-256
digests. The destination must not already exist. An interrupted run leaves an
`.incomplete-*` directory that is **not** a valid backup. Protect the backup
with host access controls and encrypted offsite storage. The repository ignores
`backups/` but does not encrypt it.

## Verify and restore

Run `python scripts/backup_local.py verify <backup-directory>` while the source
database is available. It checks digests, tar member safety and the pg_dump
archive listing. A full restore test needs **fresh, isolated** Compose volumes.
Never run `pg_restore` against the source database or mix restored uploads with
an existing upload volume.

On a separate host or isolated Compose project with an empty PostgreSQL volume,
start only `db` and `rabbitmq`. Restore the database with `pg_restore` using
the administrative credential, then restore `uploads.tar` into its empty
`upload_data` volume. Apply no migrations until confirming the restored
`public.alembic_version` matches the application image. Run
`docker compose run --rm --no-deps db-admin python -m app.db.provision_roles`
to recreate the schema-scoped runtime roles using that environment's own
passwords and grants. Then start application services and
run the browser acceptance flow against the restored environment. Use the
same application version as the backup before attempting an upgrade.

The CI gate executes the database restore into a separate temporary database
within a disposable Compose stack and compares record counts. It checks the
upload archive integrity without extracting customer data. RabbitMQ starts
empty on restore because the backup preflight required all audit queues empty.
This procedure has no production RPO/RTO, automated schedule, or live restore
guarantee; test an offsite copy and document recovery objectives before using
it for real customer data.
