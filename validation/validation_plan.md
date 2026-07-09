# Validation Plan

## Scope

This phase validates the already-built RCA Copilot pipeline and Horizon UI:

- ingestion
- parsing
- correlation
- incident creation
- enrichment
- timeline and graph APIs
- MSI Ollama-backed explanation
- Horizon demonstration flow

It does not add new AI features, ChromaDB, embeddings, or architecture changes.

## Automated Safe Scenario

`01_fake_error_injection` injects a synthetic Nova compute build failure through `/logs/batch`. The injected records include a unique request ID and resource UUID so a new incident can be identified without clearing existing data.

Success requires:

- RCA stack is healthy
- fake error is ingested
- parsed event appears
- incident is created
- incident is enriched
- graph endpoint works
- timeline endpoint works
- AI explain endpoint returns output
- validation report is generated

## Manual Scenarios

The remaining scenarios are documented for later operator-driven validation:

- Neutron resource not found
- Keystone auth failure
- Nova build failure
- Service restart signal

These are not automated because they may affect the live DevStack environment.

## Evidence Review

Each incident report records:

- expected and detected service
- severity
- event and edge counts
- timeline quality
- graph quality
- AI explanation summary and limitations
- pass/fail checklist

