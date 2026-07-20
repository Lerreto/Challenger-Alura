#!/usr/bin/env bash
# Bootstraps a fresh Oracle Cloud Infrastructure Compute VM (Ubuntu 22.04/24.04,
# Always Free A1.Flex or E-series) to run Nébula Tech RAG via Docker Compose.
#
# Usage (on the VM, after SSH-ing in):
#   git clone <your-repo-url> nebula-rag && cd nebula-rag
#   chmod +x deploy/oci-vm-setup.sh
#   ./deploy/oci-vm-setup.sh
#
# Safe to re-run: every step is idempotent. It installs Docker, opens the
# HTTP port on the VM's local firewall (the classic Oracle iptables trap),
# creates .env from .env.example if missing, and brings the stack up.
set -euo pipefail

APP_PORT="${APP_PORT:-80}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { printf '\n\033[1;32m==>\033[0m %s\n' "$1"; }

log "Updating apt and installing Docker Engine + Compose plugin"
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y ca-certificates curl gnupg
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  ARCH="$(dpkg --print-architecture)"
  CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")"
  echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
  log "Docker already installed, skipping install step"
fi

log "Enabling Docker at boot (restart: unless-stopped containers come back automatically)"
sudo systemctl enable --now docker

if ! groups "$USER" | grep -q docker; then
  log "Adding $USER to the docker group (log out/in or run 'newgrp docker' to use docker without sudo)"
  sudo usermod -aG docker "$USER"
fi

log "Opening tcp/${APP_PORT} on the VM's local firewall"
# Oracle's stock Ubuntu images ship an iptables ruleset that only allows SSH
# in by default; the OCI Security List/NSG alone is not enough. Insert an
# ACCEPT rule ahead of the default REJECT and persist it.
if ! sudo iptables -C INPUT -m state --state NEW -p tcp --dport "${APP_PORT}" -j ACCEPT 2>/dev/null; then
  # Insert at position 1: safe regardless of how many rules the image ships
  # with, and guaranteed to be evaluated before any catch-all REJECT further
  # down the chain.
  sudo iptables -I INPUT 1 -m state --state NEW -p tcp --dport "${APP_PORT}" -j ACCEPT
fi
if command -v netfilter-persistent >/dev/null 2>&1; then
  sudo netfilter-persistent save
else
  sudo apt-get install -y iptables-persistent
  sudo netfilter-persistent save
fi

cd "$REPO_DIR"
if [ ! -f .env ]; then
  log ".env not found — creating from .env.example. Edit it and set GROQ_API_KEY before continuing."
  cp .env.example .env
  echo "    -> nano ${REPO_DIR}/.env"
fi

log "Building and starting the stack (FRONTEND_PORT=${APP_PORT})"
FRONTEND_PORT="${APP_PORT}" docker compose up -d --build

log "Done. Containers:"
docker compose ps

cat <<EOF

Next steps:
  1. If this is the first run, confirm GROQ_API_KEY is set in ${REPO_DIR}/.env, then:
       FRONTEND_PORT=${APP_PORT} docker compose up -d --build
  2. In the OCI Console, open ingress for tcp/${APP_PORT} (and tcp/22 for SSH) on the
     VM's subnet Security List (VCN-only default) or the instance's Network
     Security Group.
  3. Visit http://<VM_PUBLIC_IP>:${APP_PORT}/ and check http://<VM_PUBLIC_IP>:${APP_PORT}/api/health/ready
EOF
