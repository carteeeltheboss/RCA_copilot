# 00 Baseline

## Purpose

Capture system counts and provider state before running validation scenarios.

## Safety Level

Safe. Read-only.

## Commands

```bash
python3 validation/scripts/capture_baseline.py
```

## Expected Result

A JSON file is written to `validation/results/baseline_<timestamp>.json` containing raw log, parsed event, edge, incident, enriched incident, health, and provider status data.

## Horizon Screenshots

- RCA Copilot Overview
- RCA Copilot System Health

