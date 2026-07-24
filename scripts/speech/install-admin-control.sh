#!/bin/sh
set -eu

SERVICE_USER="${1:-familyai-deploy}"
RUNTIME_DIR="/var/lib/family-ai-speech"
RUNTIME_ENV="${RUNTIME_DIR}/runtime.env"
RESTART_REQUEST="${RUNTIME_DIR}/restart.request"
DROP_IN_DIR="/etc/systemd/system/family-ai-speech.service.d"
PATH_UNIT="/etc/systemd/system/family-ai-speech-admin.path"
SERVICE_UNIT="/etc/systemd/system/family-ai-speech-admin.service"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root." >&2
  exit 1
fi

id "${SERVICE_USER}" >/dev/null 2>&1

install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0750 "${RUNTIME_DIR}"
if [ ! -e "${RUNTIME_ENV}" ]; then
  install -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0600 /dev/null "${RUNTIME_ENV}"
else
  chown "${SERVICE_USER}:${SERVICE_USER}" "${RUNTIME_ENV}"
  chmod 0600 "${RUNTIME_ENV}"
fi

install -d -o root -g root -m 0755 "${DROP_IN_DIR}"
cat >"${DROP_IN_DIR}/runtime-settings.conf" <<EOF
[Service]
EnvironmentFile=-${RUNTIME_ENV}
EOF

cat >"${PATH_UNIT}" <<EOF
[Unit]
Description=Watch for a Family AI Speech Admin restart request

[Path]
PathExists=${RESTART_REQUEST}
Unit=family-ai-speech-admin.service

[Install]
WantedBy=multi-user.target
EOF

cat >"${SERVICE_UNIT}" <<EOF
[Unit]
Description=Schedule a verified restart of Family AI Speech

[Service]
Type=oneshot
ExecStart=/usr/bin/rm -f ${RESTART_REQUEST}
ExecStart=/usr/bin/systemd-run --quiet --collect --unit=family-ai-speech-admin-restart --on-active=2s /usr/bin/systemctl restart family-ai-speech.service
EOF

rm -f /etc/sudoers.d/family-ai-speech-admin
rm -f /usr/local/sbin/family-ai-speech-schedule-restart

systemctl daemon-reload
systemctl enable --now family-ai-speech-admin.path
systemctl restart family-ai-speech.service

echo "Speech Admin control installed for ${SERVICE_USER}."
