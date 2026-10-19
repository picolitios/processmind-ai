#!/usr/bin/env bash
# Initialize a new demo stack only when no ProcessMind data volume exists.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."

host="${1:-}"
if [[ ! "$host" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]$ ]]; then
  echo "Expected the public DNS hostname" >&2
  exit 2
fi
if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo "Bootstrap requires a clean checkout" >&2
  exit 2
fi
if [[ ! -f .env || "$(stat -c %a .env)" != 600 ]]; then
  echo "Create a private .env with mode 600" >&2
  exit 2
fi

# Validate only required deployment settings; never print their values.
python3 - "$host" <<'PY'
import re
import sys
from pathlib import Path

values = {}
for raw in Path(".env").read_text(encoding="utf-8").splitlines():
    if raw and not raw.startswith("#") and "=" in raw:
        key, value = raw.split("=", 1)
        values[key] = value
secrets = (
    "POSTGRES_PASSWORD", "IDENTITY_DB_PASSWORD", "BUSINESS_DB_PASSWORD",
    "AUTH_HASH_KEY", "RABBITMQ_PASSWORD",
)
valid = (
    values.get("DEMO_HOST") == sys.argv[1]
    and values.get("WEB_ORIGIN") == f"https://{sys.argv[1]}"
    and values.get("APP_ENV") == "demo"
    and all(re.fullmatch(r"[0-9a-f]{64}", values.get(key, "")) for key in secrets)
    and len({values.get(key) for key in secrets}) == len(secrets)
)
if not valid:
    raise SystemExit("Invalid demo origin, environment or unique 64-character hex secrets")
PY

docker compose -f compose.yaml -f compose.demo.yaml config --quiet
if [[ -n "$(docker compose -f compose.yaml -f compose.demo.yaml ps --all -q)" ]]; then
  echo "Bootstrap refuses an existing Compose installation" >&2
  exit 2
fi

# Existing named volumes may hold data even if all containers were removed.
volumes="$(docker compose -f compose.yaml -f compose.demo.yaml config --format json |
  python3 -c 'import json,sys; print("\n".join(v["name"] for v in json.load(sys.stdin)["volumes"].values()))')"
while IFS= read -r volume; do
  if docker volume inspect "$volume" >/dev/null 2>&1; then
    echo "Bootstrap refuses an existing ProcessMind volume" >&2
    exit 2
  fi
done <<< "$volumes"

docker compose up -d --wait db rabbitmq
docker compose -f compose.yaml -f compose.demo.yaml build db-admin api identity identity-config-reconciler worker model-worker audit-publisher audit-consumer audit-monitor web
docker compose run --rm --no-deps db-admin alembic upgrade head
docker compose run --rm --no-deps db-admin python -m app.db.provision_roles
docker compose -f compose.yaml -f compose.demo.yaml up -d --no-build --wait --wait-timeout 180
python3 scripts/verify_deployment.py
curl --fail --silent --show-error --max-time 20 "https://${host}/api/v1/health/ready" >/dev/null
echo "Initial demo stack is healthy; run synthetic browser E2E before enabling deploy"
