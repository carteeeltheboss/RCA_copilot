# RCA Copilot — Evolution Log

---

## Changes: OpenStack DevStack Plugin Hardening (2026-07-28)

### Problem

The DevStack plugin caused or failed to survive errors during `./stack.sh`. A full audit identified 30+ root causes across the DevStack plugin, backend startup, systemd units, and Keystone registration. The plugin broke the base stack on fresh installs, re-stacks, and clean cycles.

### Root Causes Fixed

#### Group A: Critical — was breaking or corrupting `stack.sh`

1. **Horizon Settings panel + AI Explain were 401 after every clean `stack.sh`** — The plugin generated `RCA_COPILOT_INTERNAL_SERVICE_TOKEN` and wrote it to the backend conf, but never injected it into Horizon. Every token-protected endpoint (`/api/v1/providers/*`, `/api/v1/incidents/*/explain`) returned 401 from Horizon. The Horizon README also documented the wrong env-var names.

2. **Keystone endpoint URLs never updated on re-stack** — `get_or_create_endpoint` is idempotent for initial creation but does NOT update the URL if the endpoint already exists. Changing `RCA_COPILOT_HOST`/`PORT` and re-running `stack.sh` left the Keystone catalog stale.

3. **`__init__.py` symlink written into Horizon's enabled dir, never cleaned up** — The glob `enabled/_*.py` also matched `__init__.py`. `ln -sf` overwrote Horizon's `enabled/__init__.py`. `cleanup_rca_copilot` only removed `_90{00,...,50}_rca_*.py`, leaving a dangling symlink.

4. **MongoDB crash-loop on startup — no retry, no backoff, 30s stall** — The FastAPI lifespan and every worker did `AsyncIOMotorClient(...)` → `ensure_indexes()` → `ping()` with zero error handling. Transient unavailability → process exits → `Restart=on-failure` crash-loop. All 6 `AsyncIOMotorClient` call sites passed no timeout options (inheriting PyMongo's 30s default stall).

5. **`/health` endpoint returned 200 unconditionally — not DB-aware** — The endpoint the plugin's readiness gate used (`curl /health`) never touched MongoDB. A service that started but lost its DB connection still reported healthy.

6. **Plugin readiness gate used process liveness, not real readiness** — DevStack units are `Type=simple`, so `is-active` returns true the moment the process is exec'd — before the worker's MongoDB `ping`/`ensure_indexes` completes. Configured `health_file` markers were never consulted.

#### Group B: Significant — race conditions, re-stack failures

7. **Default API port 8000 conflicts with DevStack services** — Port 8000 is commonly used by DevStack/OpenStack services (e.g. Keystone under eventlet). The API could fail to bind.

8. **Collector journal access not configured under DevStack** — The packaged unit set `Group=systemd-journal`, but `run_process rca-collector` ran as `stack:stack`. The collector's `journalctl` could fail with "Access denied".

9. **Mongo password desync on re-stack** — If the container existed AND the secrets file existed but held a different password, the stale password was used, `mongosh` auth failed → `die`.

10. **`RCA_COPILOT_HOST` defaulted to loopback, ignored `SERVICE_HOST`/`HOST_IP`** — On multi-node DevStack, the `rca` endpoint was unreachable from subnodes.

#### Group C: Systemd unit issues (packaged deployments)

11. **MongoDB dependency was `After=` only, never `Requires=`/`Wants=`** — `After=` doesn't pull `mongod` into the boot transaction. Same issue with `network-online.target`.

12. **Collector `Group=systemd-journal` thrashed shared `StateDirectory`** — All units shared `StateDirectory=rca-copilot`. The collector's group differed, so the directory's owning group flipped on each start, causing intermittent write failures.

13. **No `ConditionPathExists=`** — Missing config file caused a restart storm.

14. **No `EnvironmentFile=`** — All config via `--config-file` only, no env-based overrides.

15. **Starlette `HTTP_413_CONTENT_TOO_LARGE` deprecation** — Caused a test failure on newer Starlette versions.

### Files Changed (22 files)

#### DevStack Plugin (2 files)
- **`devstack/plugin.sh`** — Complete rewrite:
  - Injects `RCA_COPILOT_INTERNAL_SERVICE_TOKEN` + `RCA_COPILOT_BACKEND_URL` into Horizon's `local_settings.py` via `_configure_rca_copilot_horizon()` (fixes 401 from Settings panel + Explain button).
  - Enabled-file glob narrowed from `_*.py` to `_9*_rca_*.py` (stops overwriting `__init__.py`).
  - Keystone endpoint URLs now delete-and-recreate on re-stack when host/port changed (`create_rca_copilot_accounts`).
  - Mongo password reconciliation in `start_rca_copilot_mongodb` — if auth fails with existing container, recreates it.
  - Collector journal access: `sudo usermod -a -G systemd-journal "$STACK_USER"` in `install_rca_copilot`.
  - Readiness gate rewritten: checks `health_file` markers (real DB readiness) instead of just `is-active`, extended to 90s, prints diagnostics before dying.
  - Cleanup uses correct glob `_9*_rca_*.py` and removes the `local_settings.py` block.

- **`devstack/settings`** — `RCA_COPILOT_HOST` follows `$SERVICE_HOST` when not explicitly set. Default port changed from 8000 → 18000 to avoid DevStack port conflicts.

#### Backend Startup / MongoDB (3 files)
- **`backend/database.py`** — New `_connect_with_retry()`: 10 retries × 2s backoff, ping → ensure_indexes, with structured logging. `serverSelectionTimeoutMS=5000` (was PyMongo default 30s). `AppState` gains `db_ready` flag. `get_repository`/`get_rca_repository` now call retry on lazy init.
- **`backend/main.py`** — `/health` endpoint now DB-aware: pings MongoDB, returns 503 if unreachable. Fixed `HTTP_413_CONTENT_TOO_LARGE` → `HTTP_413_REQUEST_ENTITY_TOO_LARGE`.
- **`rca_copilot/mongo_utils.py`** *(new file)* — Shared `connect_with_retry()` + `create_mongo_client()` for workers. Same retry pattern, 5s server selection timeout.

#### Workers (4 files)
- **`parser_worker/worker.py`** — `AsyncIOMotorClient(uri)` → `await connect_with_retry(uri)`.
- **`correlation_worker/worker.py`** — Same.
- **`incident_worker/worker.py`** — Same.
- **`enrichment_worker/worker.py`** — Same.

#### Systemd Units (6 files)
- **`systemd/rca-copilot-api.service`** — Added `Wants=network-online.target`, `Requires=mongod.service`, `ConditionPathExists=`, `EnvironmentFile=`, `StateDirectoryMode=0770`, `TimeoutStartSec=120`.
- **`systemd/rca-copilot-collector.service`** — Fixed `Group=systemd-journal` → `Group=rca-copilot` + `SupplementaryGroups=systemd-journal`. Same hardening.
- **`systemd/rca-copilot-parser-worker.service`** — Same hardening.
- **`systemd/rca-copilot-correlation-worker.service`** — Same.
- **`systemd/rca-copilot-incident-worker.service`** — Same.
- **`systemd/rca-copilot-enrichment-worker.service`** — Same.

#### Config (3 files)
- **`rca_copilot/config.py`** — Default `bind_port`: 8000 → 18000. Default `backend_batch_url`: 8000 → 18000.
- **`etc/rca-copilot.conf.sample`** — Updated sample port + batch URL.
- **`etc/rca-copilot.docker.conf`** — Updated docker port.

#### Horizon Plugin (1 file)
- **`horizon_plugin/.../enabled/_9000_rca_copilot.py`** — Default `RCA_COPILOT_BACKEND_URL`: 8000 → 18000.

#### Docker Compose (1 file)
- **`docker-compose.yml`** — Backend port mapping + healthcheck URL: 8000 → 18000.

#### Tests (2 files)
- **`backend/tests/test_health_retry.py`** *(new file)* — 6 tests: retry succeeds first try, retry succeeds after failures, retry exhausts and raises, /health returns 503 when DB not ready, /health returns 503 when ping fails, /health returns 200 when healthy.
- **`backend/tests/test_api.py`** — Updated `test_health` to mock `db_state` for DB-aware health endpoint.

---

## Current State

### What Works

- **DevStack plugin survives `stack.sh`**: MongoDB container starts and readiness-polls before services launch. All 6 services (api, collector, parser, correlation, incident, enrichment) start with retry/backoff on MongoDB connection failures.
- **Re-stack safety**: `stack.sh` → `unstack.sh` → `stack.sh` works without manual cleanup. Mongo password reconciliation handles stale containers. Keystone endpoints are deleted-and-recreated if the URL changed. Config files are regenerated idempotently via `iniset`.
- **Horizon integration**: The Settings panel and AI Explain button authenticate correctly — the service token is injected into `local_settings.py` during `configure_rca_copilot`.
- **MongoDB retry/backoff**: The API lifespan and all 4 workers retry MongoDB connections 10 times with 2s backoff and a 5s server-selection timeout (down from the 30s PyMongo default). Transient failures no longer crash-loop.
- **DB-aware health endpoint**: `/health` returns 503 if MongoDB is unreachable, 200 if healthy. The DevStack readiness gate uses this + `health_file` markers to gate on real readiness.
- **Port conflict resolved**: API default port is now 18000 (was 8000), avoiding conflicts with common DevStack services.
- **Collector journal access**: The `stack` user is added to `systemd-journal` group during install.
- **Systemd units hardened**: `Requires=mongod.service`, `Wants=network-online.target`, `ConditionPathExists=`, `EnvironmentFile=`, `StateDirectoryMode=0770`, `TimeoutStartSec=120` on all units. Collector uses `Group=rca-copilot` + `SupplementaryGroups=systemd-journal` (fixes StateDirectory thrash).
- **All tests pass**: 87 tests (81 existing + 6 new), 0 failures. flake8 clean.

### What Is NOT Yet Done (Known Limitations)

- **TTL index changes don't apply on re-stack**: PyMongo `create_indexes` is idempotent by name but won't mutate an existing index. If retention days are changed, the old TTL persists. (Would need `collMod`/`dropIndex`+recreate.)
- **Docker Compose ↔ DevStack collision on container name**: Both use `container_name: rca-copilot-mongodb`. No guard prevents simultaneous runs. `unstack.sh` stops but doesn't remove the container.
- **Collector default units are DevStack-only**: `devstack@keystone.service`, etc. — packaged deployments need `[collector] units` override.
- **Horizon Settings panel UX**: The panel is wired end-to-end but uses full-page-reload POSTs with raw JSON output. AJAX-style inline feedback (loading states, inline error/success) is a separate work item from the earlier conversation.
- **`POST /api/v1/providers/test` endpoint**: Not yet added — the "Test Connection" button on the add-provider form requires a saved provider to test. A test-before-save endpoint is planned.

### Verification

```
flake8: 0 issues
pytest: 87 passed, 0 failed
  - backend/tests/test_api.py: 7 passed
  - backend/tests/test_api_v1.py: 21 passed
  - backend/tests/test_health_retry.py: 6 passed (NEW)
  - collector/tests/: 7 passed
  - correlation_worker/tests/: 14 passed
  - enrichment_worker/tests/: 9 passed
  - incident_worker/tests/: 16 passed
  - parser_worker/tests/: 8 passed
```
