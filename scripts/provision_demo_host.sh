#!/usr/bin/env bash
# Prepare a new Ubuntu ARM64 VM for the reproducible, single-host demo.
set -euo pipefail
umask 077

key_source="${1:-}"
deploy_user=processmind
checkout=/opt/processmind
repository=https://github.com/picolitios/processmind-ai.git

# Refuse unsupported hosts and missing access keys before changing the system.
if [[ "$(id -u)" != 0 ]]; then
  echo "Run as root (sudo bash scripts/provision_demo_host.sh PUBLIC_KEY_FILE)" >&2
  exit 2
fi
if [[ ! -f /etc/os-release ]]; then
  echo "Ubuntu 24.04 is required" >&2
  exit 2
fi
# shellcheck source=/dev/null
. /etc/os-release
if [[ "${ID:-}" != ubuntu || "${VERSION_ID:-}" != 24.04 || "$(dpkg --print-architecture)" != arm64 ]]; then
  echo "This script supports only Ubuntu 24.04 ARM64" >&2
  exit 2
fi
if [[ ! -f "$key_source" || ! -s "$key_source" ]]; then
  echo "Provide a readable, nonempty SSH public key file" >&2
  exit 2
fi
if [[ "$(grep -Ec '^ssh-ed25519 [A-Za-z0-9+/=]+( .*)?$' "$key_source")" != 1 ]] ||
  [[ "$(wc -l < "$key_source")" != 1 ]]; then
  echo "Use a file containing exactly one Ed25519 SSH public key" >&2
  exit 2
fi
if [[ -e "$checkout" && ! -d "$checkout/.git" ]]; then
  echo "$checkout exists but is not a Git checkout; inspect it manually" >&2
  exit 2
fi
if [[ -d "$checkout/.git" ]] &&
  [[ "$(git -c safe.directory="$checkout" -C "$checkout" remote get-url origin)" != "$repository" ]]; then
  echo "Existing checkout has a different origin; inspect it manually" >&2
  exit 2
fi

# Docker's official Ubuntu repository provides the Engine and Compose plugin.
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git python3 openssh-client unattended-upgrades
if ! ssh-keygen -lf "$key_source" >/dev/null 2>&1; then
  echo "SSH public key is invalid" >&2
  exit 2
fi
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: arm64
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

# Keep OS security updates enabled without unattended release upgrades.
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

# The deploy account has no password or sudo membership. Docker group access
# is still root-equivalent, so this key and account are dedicated to the demo.
if ! id -u "$deploy_user" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$deploy_user"
fi
usermod -aG docker "$deploy_user"
deploy_home="$(getent passwd "$deploy_user" | cut -d: -f6)"
install -d -m 0700 -o "$deploy_user" -g "$deploy_user" "$deploy_home/.ssh"
install -m 0600 -o "$deploy_user" -g "$deploy_user" "$key_source" "$deploy_home/.ssh/authorized_keys"

# A repeat run keeps application data, local secrets and the current commit.
if [[ ! -d "$checkout/.git" ]]; then
  install -d -m 0750 -o "$deploy_user" -g "$deploy_user" "$checkout"
  runuser -u "$deploy_user" -- git clone --branch main --single-branch "$repository" "$checkout"
fi

docker compose version >/dev/null
echo "Host prepared. Verify the CI-approved commit, DNS and firewall before bootstrap."
