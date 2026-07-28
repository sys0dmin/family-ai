#!/usr/bin/env bash
set -euo pipefail

ROLE="${1:?usage: harden_network.sh ROLE GATEWAY_IP}"
GATEWAY_IP="${2:?gateway IP is required}"

[[ "$(id -u)" -eq 0 ]] || {
  echo "harden_network.sh must run as root" >&2
  exit 1
}
[[ "$ROLE" =~ ^(database|speech)$ ]] || {
  echo "network hardening is only defined for database and speech" >&2
  exit 1
}

export DEBIAN_FRONTEND=noninteractive
apt-get install -y nftables

if [[ "$ROLE" == "database" ]]; then
  PROTECTED_PORTS="5432, 9100"
else
  PROTECTED_PORTS="8010, 9100"
fi

cat >/etc/nftables.conf <<EOF
#!/usr/sbin/nft -f
flush ruleset

table inet filter {
    chain input {
        type filter hook input priority filter;
        policy accept;

        iifname "lo" accept
        ct state established,related accept
        ip saddr ${GATEWAY_IP} tcp dport { ${PROTECTED_PORTS} } accept
        tcp dport { ${PROTECTED_PORTS} } drop
    }

    chain forward {
        type filter hook forward priority filter;
        policy accept;
    }

    chain output {
        type filter hook output priority filter;
        policy accept;
    }
}
EOF

nft -c -f /etc/nftables.conf
systemctl enable nftables
systemctl restart nftables
echo "network hardening applied for role=$ROLE"
