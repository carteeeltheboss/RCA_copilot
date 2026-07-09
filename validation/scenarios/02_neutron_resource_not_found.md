# 02 Neutron Resource Not Found

## Purpose

Validate that RCA Copilot detects and explains a harmless Neutron 404-like failure without breaking networking services.

## Safety Level

Manual only. Low risk when using read-only or intentionally invalid IDs.

## Commands

Use an invalid network ID and expect a not-found response:

```bash
source /opt/stack/devstack/openrc admin admin
openstack network show 00000000-0000-0000-0000-000000000000
```

Watch Neutron logs:

```bash
sudo journalctl -u 'devstack@q-*' -n 100 --no-pager
```

## Expected Logs

- Neutron API or plugin log entries containing not found, missing resource, or invalid UUID context.
- Request ID should be visible in OpenStack CLI output or service logs.

## Expected Incident Behavior

- RCA should identify Neutron as the primary service.
- Severity should remain low/medium unless multiple errors occur.
- Timeline should show request handling and failure.
- AI explanation should state that the resource was not found and avoid claiming an infrastructure outage.

## Rollback/Recovery

No rollback is needed because the command uses an invalid ID and does not mutate resources.

## Horizon Screenshots

- Incident row filtered by Neutron
- Investigation graph
- AI explanation limitations

