# Horizon Demo Checklist

Use this checklist after running the safe validation flow.

- Open Horizon.
- Navigate to `RCA Copilot` -> `Overview`.
- Confirm pipeline counts and health cards load.
- Open `RCA Copilot` -> `Incidents`.
- Find the validation incident by request ID, resource ID, or recent timestamp.
- Open the incident investigation.
- Confirm the page title and incident header match the validation incident.
- Confirm the correlation graph renders.
- Click a timeline item and confirm the graph node selection changes.
- Click a graph node and confirm event details update.
- Click a graph edge, if present, and confirm reason/confidence displays.
- Click `Explain incident`.
- Confirm the AI panel shows `AI-assisted explanation from bounded evidence`.
- Confirm provider kind and model name are shown.
- Capture screenshots of Overview, Incidents, Investigation, and AI explanation.
- Open `RCA Copilot` -> `System Health`.
- Confirm backend, MongoDB, workers, and MSI provider are healthy or clearly labeled.
- Confirm `Settings` is visible only to admin users.

