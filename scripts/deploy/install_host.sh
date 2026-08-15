#!/usr/bin/env bash
set -euo pipefail

COMPONENT="${1:-}"
ASSETS="${2:-}"
DEPLOY_USER="${3:-familyai-deploy}"
ROOT="/srv/family-ai"

[[ "$EUID" -eq 0 ]] || { echo "run install_host.sh through sudo" >&2; exit 1; }
id "$DEPLOY_USER" >/dev/null
[[ -d "$ASSETS" ]] || { echo "unit assets directory not found" >&2; exit 1; }

install -d -m 0755 "$ROOT"
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0755 "$ROOT/tools"
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0755 \
  "$ROOT/$COMPONENT" \
  "$ROOT/$COMPONENT/releases" \
  "$ROOT/$COMPONENT/venvs" \
  "$ROOT/$COMPONENT/incoming"
install -d -m 0755 /etc/family-ai

install_unit() {
  install -o root -g root -m 0644 "$ASSETS/$1" "/etc/systemd/system/$1"
}

case "$COMPONENT" in
  gateway)
    install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0700 \
      /var/lib/family-ai-config \
      /var/lib/family-ai-config/gateway
    if [[ ! -f /etc/family-ai/gateway.env ]]; then
      if [[ -f /home/familyai-deploy/family-ai/.env ]]; then
        install -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0600 \
          /home/familyai-deploy/family-ai/.env /etc/family-ai/gateway.env
      else
        echo "/etc/family-ai/gateway.env is required on a fresh host" >&2
        exit 1
      fi
    fi
    if [[ ! -e "$ROOT/gateway/current" ]]; then
      if [[ -d /home/familyai-deploy/family-ai ]]; then
        ln -s /home/familyai-deploy/family-ai "$ROOT/gateway/current"
        echo "legacy" >"$ROOT/gateway/deployed-version"
        chown "$DEPLOY_USER:$DEPLOY_USER" "$ROOT/gateway/deployed-version"
      else
        echo "fresh Gateway host: current will be created during activation"
      fi
    fi
    install_unit family-ai-gateway.service
    install_unit family-ai-admin.service
    install_unit family-ai-retention.service
    install_unit family-ai-retention.timer
    systemctl enable family-ai-gateway.service family-ai-admin.service \
      family-ai-retention.timer >/dev/null
    ;;
  speech)
    [[ -f /etc/family-ai/speech.env ]] ||
      { echo "/etc/family-ai/speech.env is required" >&2; exit 1; }
    if [[ ! -e "$ROOT/speech/current" ]]; then
      if [[ -d /home/familyai-deploy/family-ai/speech ]]; then
        ln -s /home/familyai-deploy/family-ai/speech "$ROOT/speech/current"
        echo "legacy" >"$ROOT/speech/deployed-version"
        chown "$DEPLOY_USER:$DEPLOY_USER" "$ROOT/speech/deployed-version"
      else
        echo "fresh Speech host: current will be created during activation"
      fi
    fi
    install_unit family-ai-speech.service
    systemctl enable family-ai-speech.service >/dev/null
    ;;
  *)
    echo "unknown component: $COMPONENT" >&2
    exit 1
    ;;
esac

cat >/etc/sudoers.d/family-ai-release <<EOF
Cmnd_Alias FAMILY_AI_RELEASE_CONTROL = /usr/bin/systemctl restart family-ai-gateway.service, /usr/bin/systemctl restart family-ai-admin.service, /usr/bin/systemctl restart family-ai-speech.service
$DEPLOY_USER ALL=(root) NOPASSWD: FAMILY_AI_RELEASE_CONTROL
EOF
chmod 0440 /etc/sudoers.d/family-ai-release
visudo -cf /etc/sudoers.d/family-ai-release >/dev/null
systemctl daemon-reload
