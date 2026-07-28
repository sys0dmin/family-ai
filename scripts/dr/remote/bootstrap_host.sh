#!/usr/bin/env bash
set -euo pipefail

ROLE="${1:?usage: bootstrap_host.sh ROLE SERVICE_USER HOST_IP}"
SERVICE_USER="${2:-familyai-deploy}"
HOST_IP="${3:?host IP is required}"

[[ "$(id -u)" -eq 0 ]] || {
  echo "bootstrap_host.sh must run as root" >&2
  exit 1
}
[[ "$ROLE" =~ ^(gateway|database|speech)$ ]] || {
  echo "unsupported host role: $ROLE" >&2
  exit 1
}
[[ "$HOST_IP" =~ ^[0-9a-fA-F:.]+$ ]] || {
  echo "invalid host IP" >&2
  exit 1
}

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  ca-certificates \
  curl \
  gzip \
  openssh-client \
  python3 \
  python3-venv \
  sudo \
  tar

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$SERVICE_USER"
fi

install -d -m 0755 /etc/family-ai /srv/family-ai
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0755 /srv/family-ai/tools

case "$ROLE" in
  gateway)
    apt-get install -y prometheus-node-exporter
    cat >/etc/default/prometheus-node-exporter <<'EOF'
ARGS="--web.listen-address=127.0.0.1:9100"
EOF
    systemctl enable prometheus-node-exporter
    systemctl restart prometheus-node-exporter
    ;;
  database)
    apt-get install -y postgresql postgresql-client prometheus-node-exporter
    cat >/etc/default/prometheus-node-exporter <<EOF
ARGS="--web.listen-address=${HOST_IP}:9100"
EOF
    systemctl enable --now postgresql
    systemctl enable prometheus-node-exporter
    systemctl restart prometheus-node-exporter
    ;;
  speech)
    apt-get install -y ffmpeg libgomp1 libsndfile1 prometheus-node-exporter
    cat >/etc/default/prometheus-node-exporter <<EOF
ARGS="--web.listen-address=${HOST_IP}:9100"
EOF
    install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 \
      /var/lib/family-ai-speech \
      /var/lib/family-ai-speech/models
    systemctl enable prometheus-node-exporter
    systemctl restart prometheus-node-exporter
    ;;
esac

echo "bootstrapped role=$ROLE host_ip=$HOST_IP service_user=$SERVICE_USER"
