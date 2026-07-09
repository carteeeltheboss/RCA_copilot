# RCA Copilot Validation

This folder contains repeatable validation material for the current RCA Copilot system. The goal is to prove the existing pipeline detects, correlates, enriches, and explains controlled OpenStack-like incidents.

Validation answers these questions for each scenario:

- Did RCA Copilot create an incident?
- Did it pick the correct service?
- Did it create a useful correlation graph?
- Did the timeline make sense?
- Did AI explanation stay grounded in evidence?
- Did it avoid false positives?

The default automated validation is intentionally safe. It injects synthetic OpenStack-like log records through the backend ingestion API (`/logs/batch`) and never writes directly to MongoDB, clears data, kills services, or modifies DevStack.

## Quick Start

Run the safe validation flow:

```bash
bash validation/scripts/run_safe_validation.sh
```

Generated artifacts are written under `validation/results/`.

## Safety Rules

- No ChromaDB or embeddings.
- No destructive commands.
- No direct MongoDB writes.
- No DevStack service restarts from automation.
- No fake AI output.
- Browser traffic must go through Horizon; validation scripts may call the backend API directly.
- The internal service token is read from `.env` only for server-side API calls and is never printed.

