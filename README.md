# JNS Home Assistant

Home Assistant integrations and supporting tools.

## RLM — Runtime Lease Manager

RLM provides restart-safe maximum runtimes for Home Assistant actuators.

### What it does

- Persists only active runtime leases.
- Uses an absolute UTC deadline so Home Assistant downtime never extends a maximum runtime.
- On startup, resumes only the remaining runtime or immediately stops an actuator whose lease expired while Home Assistant was offline.
- Automatically removes completed, cancelled and expired leases.
- Emits structured Home Assistant lifecycle events for external audit/syslog consumers.
- Does not include a database, web server, queue, or syslog transport.

### HACS installation

1. Open HACS in Home Assistant.
2. Add this repository as a **Custom repository**: `https://github.com/jamienewton2269/HA`
3. Select category **Integration**.
4. Install **RLM - Runtime Lease Manager**.
5. Add the following to `configuration.yaml`:

```yaml
rlm:
```

6. Restart Home Assistant.

### Manual installation

From the Home Assistant configuration directory, the included `install-rlm.sh` script downloads the RLM integration files from this repository. Review the script before running it.

### Services

- `rlm.start`
- `rlm.complete`
- `rlm.cancel`
- `rlm.reconcile`

Example timed fan:

```yaml
actions:
  - action: rlm.start
    data:
      entity_id: fan.wc_extractor
      max_runtime_seconds: 40
      activate: true
      source: downstairs_wc_motion_clear
```

RLM stores active leases in `.storage/rlm.active_leases`. Historical lifecycle information is emitted as Home Assistant events rather than retained as stale lease records.

## Other content

This repository also contains JNS Home Assistant app/deployment components.
