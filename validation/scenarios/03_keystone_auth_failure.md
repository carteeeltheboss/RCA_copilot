# 03 Keystone Auth Failure

## Purpose

Validate that RCA Copilot detects failed authentication attempts while Keystone remains healthy.

## Safety Level

Manual only. Low risk when using one or two intentionally invalid credentials.

## Commands

Run a single authentication attempt with an invalid password:

```bash
OS_USERNAME=admin \
OS_PASSWORD=definitely-wrong \
OS_PROJECT_NAME=admin \
OS_USER_DOMAIN_NAME=Default \
OS_PROJECT_DOMAIN_NAME=Default \
OS_AUTH_URL=http://127.0.0.1/identity \
openstack token issue
```

Watch Keystone logs:

```bash
sudo journalctl -u devstack@key -n 100 --no-pager
```

## Expected Logs

- Keystone authentication failure.
- HTTP 401 or invalid credentials message.
- Request ID if emitted by the service stack.

## Expected Incident Behavior

- RCA should identify Keystone as the service.
- Timeline should show a short failed authentication path.
- AI explanation should label the failure as an auth rejection, not a Keystone outage.

## Rollback/Recovery

No rollback is needed. Avoid repeated attempts that could look like brute force activity.

## Horizon Screenshots

- Keystone-filtered incident list
- Timeline with failed auth entry
- AI explanation recommended checks

