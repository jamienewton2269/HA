# JNS Secure Transfer Gateway v0.2.0

Home Assistant App providing the restricted SFTP ingress used by the JNS deployment system.

## Security boundary

The App exposes only a dedicated OpenSSH `internal-sftp` account:

- external Home Assistant port default: **2222**
- container SSH port: **22**
- transfer user: **`jnstransfer`**
- public-key authentication only
- no shell
- no password login
- no port/X11/agent forwarding
- chrooted SFTP filesystem
- only `/incoming` is writable by the transfer account

The transfer account does **not** receive direct write access to `/config`.

The Gateway worker validates a completed upload and then performs the privileged local handoff:

```text
Windows JNS Manager
    |
    | SFTP :2222, user jnstransfer
    v
/incoming
    |
    | ZIP safety + payload SHA-256
    | JNS format-3 signature
    | trusted publisher + scope
    v
/homeassistant/jns/inbox
```

Home Assistant maps its configuration share into the App as `/homeassistant`.

## JNS handoff defaults

```yaml
jns_handoff:
  enabled: true
  require_native_jns_signature: true
  verify_against_jns_trust: true
  allow_trust_enrolment: false
```

Publisher enrolment is deliberately disabled in normal operation.

## Trust store

The worker first looks for:

`/homeassistant/jns/trust/publishers.json`

and also recognises the older fallback:

`/homeassistant/jns/publishers.json`

Only an enabled publisher with the required `config`/`platform` scope and a valid Ed25519 signature is accepted when trust verification is enabled.

## Installation / publication

This directory is the Home Assistant App source directory. Publish the `jns_secure_transfer` folder in a Home Assistant App repository and set the repository metadata accordingly.

After refreshing the App repository, Home Assistant should offer version `0.2.0`.

## Source and release archives

The source release is intentionally separate from JNS config deployment packages. The Gateway itself is a Home Assistant App and must be built/updated by Supervisor.
