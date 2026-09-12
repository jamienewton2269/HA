#!/usr/bin/env bash
set -Eeuo pipefail

OPTIONS_FILE="/data/options.json"
TRANSFER_USER="jnstransfer"
CHROOT_ROOT="/srv/jns"
INCOMING_REAL="${CHROOT_ROOT}/incoming"
AUTHORIZED_DIR="/etc/ssh/authorized_keys"
AUTHORIZED_FILE="${AUTHORIZED_DIR}/${TRANSFER_USER}"
SSHD_CONFIG="/etc/ssh/sshd_config_jns"

log() {
  printf '[JNS Secure Transfer] %s\n' "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

[ -f "${OPTIONS_FILE}" ] || die "Home Assistant options file is missing: ${OPTIONS_FILE}"

mkdir -p "${CHROOT_ROOT}" "${INCOMING_REAL}" "${AUTHORIZED_DIR}" /run/sshd /opt/jns

# Create the dedicated transfer identity inside the App container.
if ! getent group "${TRANSFER_USER}" >/dev/null 2>&1; then
  addgroup -S "${TRANSFER_USER}"
fi

if ! id "${TRANSFER_USER}" >/dev/null 2>&1; then
  adduser -S -D -H -s /sbin/nologin -G "${TRANSFER_USER}" "${TRANSFER_USER}"
fi

# OpenSSH ChrootDirectory must be root-owned and not writable by the user.
chown root:root "${CHROOT_ROOT}"
chmod 0755 "${CHROOT_ROOT}"

chown "${TRANSFER_USER}:${TRANSFER_USER}" "${INCOMING_REAL}"
chmod 0700 "${INCOMING_REAL}"

# Build authorized_keys only from explicitly configured public SSH keys.
: > "${AUTHORIZED_FILE}"
python3 - "${OPTIONS_FILE}" "${AUTHORIZED_FILE}" <<'PY'
import json
import re
import sys
from pathlib import Path

options_path = Path(sys.argv[1])
dest = Path(sys.argv[2])

data = json.loads(options_path.read_text(encoding="utf-8"))
keys = data.get("authorized_keys", [])
if not isinstance(keys, list):
    raise SystemExit("authorized_keys must be a list")

allowed = re.compile(
    r"^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521)\s+[A-Za-z0-9+/=]+(?:\s+.*)?$"
)

lines = []
for raw in keys:
    key = str(raw).strip()
    if not key:
        continue
    if not allowed.fullmatch(key):
        raise SystemExit("One configured authorized_keys entry is not a supported OpenSSH public key")
    # Restrict the key at the authorized_keys layer as well as in sshd_config.
    lines.append(
        'restrict,no-agent-forwarding,no-port-forwarding,no-pty,no-user-rc,no-X11-forwarding '
        + key
    )

if not lines:
    raise SystemExit(
        "No SSH public keys are configured. Add at least one key to authorized_keys."
    )

dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

chown root:root "${AUTHORIZED_FILE}"
chmod 0600 "${AUTHORIZED_FILE}"

# Generate server host keys once per App data volume when possible.
HOSTKEY_DIR="/data/ssh_host_keys"
mkdir -p "${HOSTKEY_DIR}"
chmod 0700 "${HOSTKEY_DIR}"

for kind in ed25519 rsa; do
  key="${HOSTKEY_DIR}/ssh_host_${kind}_key"
  if [ ! -f "${key}" ]; then
    log "Generating ${kind} SSH host key"
    if [ "${kind}" = "ed25519" ]; then
      ssh-keygen -q -t ed25519 -N "" -f "${key}"
    else
      ssh-keygen -q -t rsa -b 3072 -N "" -f "${key}"
    fi
  fi
done

cat > "${SSHD_CONFIG}" <<EOF
Port 22
Protocol 2

HostKey ${HOSTKEY_DIR}/ssh_host_ed25519_key
HostKey ${HOSTKEY_DIR}/ssh_host_rsa_key

PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PermitRootLogin no
PermitEmptyPasswords no
PubkeyAuthentication yes
AuthenticationMethods publickey
AuthorizedKeysFile ${AUTHORIZED_DIR}/%u

AllowUsers ${TRANSFER_USER}
UsePAM no
PrintMotd no
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
PermitTunnel no
GatewayPorts no
PermitUserEnvironment no
PermitTTY no

Subsystem sftp internal-sftp

Match User ${TRANSFER_USER}
    ChrootDirectory ${CHROOT_ROOT}
    ForceCommand internal-sftp -d /incoming -u 077
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    AllowAgentForwarding no
    AllowTcpForwarding no
    X11Forwarding no
    PermitTTY no
EOF

# Start the package handoff worker only when explicitly enabled.
HANDOFF_ENABLED="$(jq -r '.jns_handoff.enabled // true' "${OPTIONS_FILE}")"

if [ "${HANDOFF_ENABLED}" = "true" ]; then
  log "Starting JNS package handoff worker"
  python3 /opt/jns/jns_handoff.py \
    --options "${OPTIONS_FILE}" \
    --incoming "${INCOMING_REAL}" \
    --ha-config "/homeassistant" &
  HANDOFF_PID=$!
  trap 'kill ${HANDOFF_PID:-0} 2>/dev/null || true' EXIT INT TERM
else
  log "JNS handoff worker disabled by configuration"
fi

log "SFTP endpoint ready: external Home Assistant port mapping defaults to 2222"
log "SFTP user: ${TRANSFER_USER}"
log "Writable SFTP drop-zone: /incoming"
log "Starting OpenSSH server"
exec /usr/sbin/sshd -D -e -f "${SSHD_CONFIG}"
