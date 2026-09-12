# Changelog

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
