# 01 Fake Error Injection

## Purpose

Inject a controlled OpenStack-like Nova compute error through the backend ingestion API and verify that RCA Copilot creates, enriches, graphs, timelines, and explains the incident.

## Safety Level

Safe. The scenario uses `/logs/batch` only and does not alter DevStack services.

## Commands

```bash
bash validation/scripts/run_safe_validation.sh
```

## Expected Logs

The injected error message resembles:

```text
ERROR nova.compute.manager Build failed due to timeout for instance <uuid> request_id=<req-id>
```

It uses `devstack@n-cpu.service`, a unique boot ID, and a unique journal cursor.

## Expected Incident Behavior

- A new incident is created for the unique request ID/resource UUID.
- Detected service should be Nova compute or `devstack@n-cpu.service`.
- Timeline should show the injected context and error records.
- Correlation graph should contain the injected events and same-request/resource edge when correlation completes.
- AI explanation should reference only the injected evidence and note limitations if evidence is thin.

## Rollback/Recovery

No rollback is required. The injected records are validation evidence and should remain available for audit.

## Horizon Screenshots

- Incidents row for the validation incident
- Investigation header
- Correlation graph
- Timeline selection
- AI explanation panel

