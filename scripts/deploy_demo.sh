#!/usr/bin/env bash
# Deploy a CI-verified main commit on the dedicated demo VM, preserving data.
set -euo pipefail
umask 077

target="${1:-}"
host="${2:-}"
if [[ ! "$target" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Expected a full commit SHA" >&2
  exit 2
fi
if [[ ! "$host" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]$ ]]; then
  echo "Expected the configured public DNS hostname" >&2
  exit 2
fi

cd "$(dirname "$0")/.."
if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo "Deployment checkout contains uncommitted files" >&2
  exit 2
fi
if [[ ! -f .env || "$(stat -c %a .env)" != 600 ]]; then
  echo "Create a private .env with mode 600 before deployment" >&2
  exit 2
fi

# A failed pre-migration backup can restart the old application. After a
# migration starts, an operator must inspect schema compatibility before rollback.
stage=pre_migration
resume_old_stack() {
  if [[ "$stage" == pre_migration ]]; then
    docker compose -f compose.yaml -f compose.demo.yaml up -d --no-build --no-recreate || true
  elif [[ "$stage" == checkout_changed ]]; then
    git switch --detach "$current" || true
    docker compose -f compose.yaml -f compose.demo.yaml up -d --no-build --no-recreate || true
  else
    echo "Deployment interrupted after migration began; inspect the rollback runbook" >&2
  fi
}
trap resume_old_stack ERR

git fetch --quiet origin main
git cat-file -e "$target^{commit}"
git merge-base --is-ancestor "$target" origin/main
current="$(git rev-parse HEAD)"
if [[ "$current" == "$target" ]]; then
  echo "Commit already deployed: $target"
  exit 0
fi

docker compose -f compose.yaml -f compose.demo.yaml config --quiet
python3 scripts/verify_deployment.py

# Stop new work, then give in-flight audit messages time to finish. The backup
# script independently rejects any remaining work or running writer.
docker compose -f compose.yaml -f compose.demo.yaml stop caddy web api identity identity-config-reconciler worker model-worker
sleep 30
docker compose stop audit-publisher audit-consumer
backup="backups/demo-$(date -u +%Y%m%dT%H%M%SZ)-${current:0:12}"
python3 scripts/backup_local.py backup "$backup"
python3 scripts/backup_local.py verify "$backup"

git switch --detach "$target"
stage=checkout_changed
docker compose -f compose.yaml -f compose.demo.yaml build db-admin api identity identity-config-reconciler worker model-worker audit-publisher audit-consumer audit-monitor web
stage=migration_started
docker compose run --rm --no-deps db-admin alembic upgrade head
docker compose run --rm --no-deps db-admin python -m app.db.provision_roles
docker compose -f compose.yaml -f compose.demo.yaml up -d --no-build --wait --wait-timeout 180
python3 scripts/verify_deployment.py
curl --fail --silent --show-error --max-time 15 "https://${host}/api/v1/health/ready" >/dev/null
trap - ERR
echo "Deployment succeeded: $target; protected backup: $backup"
