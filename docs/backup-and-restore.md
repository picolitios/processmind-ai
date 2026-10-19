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

On a separate host with empty Compose volumes and new local secrets, use the
same application commit as the backup. The commands below assume `$backup`
points to a copied and verified backup directory. Keep all application
processes stopped until both archives are restored. Do not run `alembic
upgrade` against an empty database first: the archive contains its own schema
and `public.alembic_version`.

```powershell
$backup = 'D:\protected\processmind-backup'
docker compose build db-admin api identity worker model-worker audit-publisher audit-consumer audit-monitor web identity-config-reconciler
docker compose up -d --wait db rabbitmq
python scripts/backup_local.py verify $backup
$databaseContainer = docker compose ps -q db
docker cp (Join-Path $backup 'database.dump') "${databaseContainer}:/tmp/processmind-restore.dump"
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl /tmp/processmind-restore.dump'
$backupPath = (Resolve-Path $backup).Path
docker compose run --rm --no-deps -T --volume "${backupPath}:/restore:ro" --entrypoint tar worker -C /data/uploads -xf /restore/uploads.tar
docker compose run --rm --no-deps db-admin python -m app.db.provision_roles
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT version_num FROM public.alembic_version"'
docker compose up -d --no-build --wait --wait-timeout 180
```

Before opening the UI, confirm `public.alembic_version` matches the checked
out image and run the browser acceptance flow against the restored environment.
The role-provisioning command recreates schema-scoped runtime roles and grants
using that environment's own passwords. The local `verify` action requires a
running `db` service for `pg_restore --list`.
If the source stack runs on the same host, its bound ports conflict with this
Compose file; use another host or an explicit isolated port configuration.

The CI gate executes the database restore into a separate temporary database
within a disposable Compose stack and compares record counts. It restores the
synthetic upload archive into a new Docker volume, compares every file's bytes
and set membership, and checks all import keys from the restored database. RabbitMQ starts
empty on restore because the backup preflight required all audit queues empty.
This procedure has no production RPO/RTO, automated schedule, or live restore
guarantee; test an offsite copy and document recovery objectives before using
it for real customer data.
