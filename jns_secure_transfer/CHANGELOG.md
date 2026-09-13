# Changelog

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
