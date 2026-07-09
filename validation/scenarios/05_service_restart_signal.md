# 05 Service Restart Signal

## Purpose

Validate whether RCA Copilot notices meaningful warnings or errors around an operator-controlled service restart.

## Safety Level

Manual only. Medium risk. Restart only a non-critical DevStack service during an agreed validation window.

## Commands

Inspect candidate services first:

```bash
systemctl list-units 'devstack@*.service'
```

If approved, restart one selected non-critical service:

```bash
sudo systemctl restart <service-name>
```

Watch recent logs:

```bash
sudo journalctl -u <service-name> -n 200 --no-pager
```

## Expected Logs

- Service stop/start messages.
- Possible warnings during reconnect or recovery.
- No persistent failure after restart.

## Expected Incident Behavior

- RCA may create a low/medium severity incident if ERROR/WARNING records are emitted.
- AI explanation should not claim a root cause beyond the restart evidence.
- System Health should return to healthy after the service stabilizes.

## Rollback/Recovery

If the service does not recover:

```bash
sudo systemctl status <service-name>
sudo systemctl restart <service-name>
```

Escalate only if the service remains failed.

## Horizon Screenshots

- System Health before/after
- Incident timeline around restart
- AI explanation limitations

