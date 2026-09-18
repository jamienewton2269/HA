# Changelog

## 0.2.3 — JNS v5.1.2+ inbox compatibility

- Fixes the 60-second Windows Manager handoff timeout when the Deployment Platform uses the v5.1.2+ direct SFTP inbox at `/config/jns/sftp/incoming`.
- The Gateway now prefers `jns/sftp/incoming` when that directory exists and falls back to the legacy `jns/inbox` path for older JNS platform versions.
- Keeps public-key-only SFTP, trusted-publisher verification, signature/hash validation, quarantine and atomic handoff unchanged.
- No Home Assistant package is installed by this update; it only corrects the Gateway destination path.


## 0.2.2 — reboot-persistence fix

- Fixes `jnstransfer` public-key authentication after App restart/rebuild by clearing the Alpine system-account lock at startup while keeping SSH password authentication disabled.
- Keeps `/etc/ssh/authorized_keys/jnstransfer` root-owned but changes it to mode `0644` so `sshd` can read the key after dropping privileges while the transfer user still cannot modify it.
- Removes unsupported `UsePAM no` from the Alpine OpenSSH configuration.
- Retains persistent SSH host keys in `/data/ssh_host_keys`, so verified host-key fingerprints survive normal App restarts and upgrades.
- Retains public-key-only SFTP, chrooted `/incoming`, signed JNS package validation, trusted publisher verification, quarantine, and atomic inbox handoff.

## 0.2.1 — migration release

- Marks v0.2.1 as the supported migration target from the old local `local_jns_secure_transfer` installation.
- Updates the App project URL to the dedicated `jamienewton2269/HA` Home Assistant App repository.
- Uses an explicit `FROM ghcr.io/home-assistant/base:latest` Docker base so the build no longer depends on the removed Supervisor `BUILD_FROM` fallback.
- Adds required local-build Home Assistant image labels:
  - `io.hass.version`
  - `io.hass.type=app`
  - `io.hass.arch=aarch64|amd64`
- Adds Home Assistant/App and OCI source metadata labels.
- Logs persistent SSH host-key SHA-256 fingerprints at startup to support safe migration and host-key pin replacement.
- Adds `MIGRATION.md` with a no-downtime-data-loss migration procedure.
- Retains the v0.2.0 security boundary: public-key-only SFTP, `jnstransfer`, chrooted `/incoming`, signed JNS package validation, trusted publisher verification, quarantine, and atomic inbox handoff.

## 0.2.0

- Adds validated `/incoming` to JNS inbox handoff.
- Verifies JNS v3/format-3 Ed25519 package signatures.
- Verifies trusted publisher identity, fingerprint and scope.
- Rechecks every declared payload SHA-256.
- Rejects encrypted archives, traversal, symlinks/special files, undeclared files, oversized members and archive-bomb ratios.
- Adds atomic read-back-verified handoff into `/homeassistant/jns/inbox`.
- Adds quarantine with rejection reason.
- Adds optional, explicitly gated public-publisher enrolment.
- Standardises external SFTP port on 2222 and user on `jnstransfer`.
- Keeps the SFTP identity chrooted and unable to write directly into Home Assistant configuration.
