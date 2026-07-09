# 04 Nova Build Failure

## Purpose

Validate that RCA Copilot detects a real Nova instance build failure in DevStack.

## Safety Level

Manual only. Medium risk. Use a small flavor and clean up any failed server afterward.

## Commands

Options include:

```bash
source /opt/stack/devstack/openrc admin admin
openstack server create --flavor m1.nano --image missing-image validation-fail
```

Or use a deliberately invalid network:

```bash
openstack server create --flavor m1.nano --image cirros --network 00000000-0000-0000-0000-000000000000 validation-fail
```

Watch Nova logs:

```bash
sudo journalctl -u 'devstack@n-*' -n 200 --no-pager
```

## Expected Logs

- Nova API accepts/rejects the request or scheduler/build logs show failure.
- Instance UUID or request ID appears in logs.
- Error or warning appears in Nova compute/scheduler/api logs.

## Expected Incident Behavior

- RCA should identify Nova as the primary service.
- Graph should connect events by request ID or instance UUID.
- Timeline should show API, scheduler, and compute sequence if logs are available.
- AI explanation should separate facts from hypotheses.

## Rollback/Recovery

Delete any validation server if it exists:

```bash
openstack server delete validation-fail
```

## Horizon Screenshots

- Incident details with instance UUID
- Correlation graph
- AI explanation panel

