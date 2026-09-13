# Migration to repository-managed JNS Secure Transfer Gateway v0.2.1

This release is the supported migration target for installations currently
running the older local Home Assistant App `local_jns_secure_transfer`.

The old and new Apps should not be run at the same time because both normally
bind TCP port 2222.

## Before migration

Record the current local Gateway configuration, especially:

- all `authorized_keys` entries;
- external SFTP port (normally `2222`);
- current SSH host-key fingerprint pinned by the Windows Manager;
- current JNS trust-store state under `/config/jns/trust/`.

Do not copy private SSH keys into Home Assistant. The Gateway requires public
SSH keys only.

## Safe migration sequence

1. Add or refresh the Home Assistant App repository:
   `https://github.com/jamienewton2269/HA`
2. Confirm **JNS Secure Transfer Gateway v0.2.1** is visible.
3. Install the repository-managed App but do not start it yet if the old
   Gateway is still using TCP 2222.
4. Copy the old Gateway's **public** `authorized_keys` values into the new App.
5. Keep these secure defaults:
   - `jns_handoff.enabled: true`
   - `jns_handoff.require_native_jns_signature: true`
   - `jns_handoff.verify_against_jns_trust: true`
   - `jns_handoff.allow_trust_enrolment: false`
6. Stop `local_jns_secure_transfer`.
7. Start the repository-managed v0.2.1 App.
8. Read the new App log and record its SHA-256 SSH host-key fingerprint.
9. Compare/verify that fingerprint before replacing the old host-key pin in the
   Windows Manager. A new fingerprint is expected because this is a different
   Home Assistant App identity with its own persistent `/data` volume.
10. Test SFTP as `jnstransfer` on port 2222 and verify `/incoming` is writable.
11. Deploy one signed JNS test/config package.
12. Confirm the Gateway accepts it and hands it atomically into
    `/homeassistant/jns/inbox`.
13. Confirm Home Assistant JNS validation/plan/dry-run/install succeeds.
14. Only after all tests pass, uninstall the old local App.

## Rollback during migration

If the new App does not pass testing:

1. Stop the repository-managed App.
2. Restore the Windows Manager's old host-key pin if it was changed.
3. Start `local_jns_secure_transfer` again.
4. Do not uninstall either App until the cause is understood.

This migration does not require copying any private key from the old App.
