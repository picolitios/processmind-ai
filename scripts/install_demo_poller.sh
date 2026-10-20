#!/usr/bin/env bash
# Register an outbound-only CI deployment timer after the first healthy boot.
set -euo pipefail
umask 077

host="${1:-}"
checkout=/opt/processmind
if [[ "$(id -u)" != 0 ]]; then
  echo "Run as root (sudo bash scripts/install_demo_poller.sh HOST)" >&2
  exit 2
fi
if [[ ! "$host" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]$ ]]; then
  echo "Expected the public DNS hostname" >&2
  exit 2
fi
if [[ ! -f "$checkout/.env" || ! -f "$checkout/scripts/poll_demo_deploy.py" ]]; then
  echo "Bootstrap the clean demo checkout before enabling the timer" >&2
  exit 2
fi
if [[ "$(stat -c %a "$checkout/.env")" != 600 ]]; then
  echo "The demo .env must have mode 600" >&2
  exit 2
fi
if [[ "$(stat -c %U "$checkout/.env")" != processmind ]]; then
  echo "The demo .env must be owned by processmind" >&2
  exit 2
fi
cd "$checkout"
runuser -u processmind -- python3 "$checkout/scripts/verify_deployment.py"
curl --fail --silent --show-error --max-time 20 \
  "https://${host}/api/v1/health/ready" >/dev/null

# Keep the polling gate outside the Git checkout so a deploy cannot replace
# the running verifier before it has checked the next CI result.
install -d -m 0755 /usr/local/libexec/processmind-demo
install -m 0755 "$checkout/scripts/poll_demo_deploy.py" \
  /usr/local/libexec/processmind-demo/poll_deploy.py
cat >/etc/systemd/system/processmind-demo-deploy.service <<EOF
[Unit]
Description=Deploy the CI-approved ProcessMind demo commit
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
User=processmind
Group=processmind
SupplementaryGroups=docker
WorkingDirectory=$checkout
Environment=DEMO_HOST=$host
ExecStart=/usr/bin/python3 /usr/local/libexec/processmind-demo/poll_deploy.py
TimeoutStartSec=7500

EOF
cat >/etc/systemd/system/processmind-demo-deploy.timer <<'EOF'
[Unit]
Description=Check GitHub CI for a new ProcessMind demo release

[Timer]
OnCalendar=*:0/10
RandomizedDelaySec=2min
Persistent=true
Unit=processmind-demo-deploy.service

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now processmind-demo-deploy.timer
echo "Deploy timer enabled; inspect systemctl status and journalctl before relying on it."
