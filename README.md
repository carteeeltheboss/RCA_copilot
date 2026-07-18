# OpenStack RCA Copilot

Local-first root cause analysis support for OpenStack logs.

RCA Copilot is packaged as an OpenStack-style service. A DevStack deployment
is enabled with ``enable_plugin rca-copilot <repository-url>``; ``stack.sh``
then installs, configures, registers, and starts the API and all five pipeline
processes. Production hosts can use ``pip install .`` and the six units in
``systemd/``. Docker Compose remains supported for local, non-integrated use.

## OpenStack installation

Add this to ``devstack/local.conf`` before stacking:

```ini
[[local|localrc]]
enable_plugin rca-copilot https://example.invalid/RCA_copilot.git
RCA_COPILOT_MONGO_URI=mongodb://rca_admin:password@127.0.0.1:27017/rca_copilot?authSource=admin
```

For a packaged host installation:

```console
python3 -m pip install .
sudo install -d /etc/rca-copilot
sudo install -m 0640 etc/rca-copilot.conf.sample /etc/rca-copilot/rca-copilot.conf
sudo install -m 0644 systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rca-copilot-api rca-copilot-parser-worker \
  rca-copilot-correlation-worker rca-copilot-incident-worker \
  rca-copilot-enrichment-worker rca-copilot-collector
```

All binaries accept ``--config-file`` and default to
``/etc/rca-copilot/rca-copilot.conf``. Generate an annotated sample with
``tox -e genconfig``.

OpenStack RCA Copilot collects host journald records, stores the raw evidence,
parses operational signals, correlates related events, detects incident
candidates, and enriches each incident with a deterministic investigation
summary. The current implementation is evidence-first and privacy-preserving:
all processing runs locally, and raw infrastructure logs stay on the machine.

![OpenStack RCA Copilot presentation title](docs/assets/presentation-title.png)

## Why This Exists

OpenStack failures are rarely isolated to one service or one log line. A Nova
error can be caused by a Neutron binding problem, a Keystone token issue, a
Placement scheduling mismatch, or a delayed dependency several minutes earlier.
Manual investigation usually means jumping between services, request IDs,
resource UUIDs, timestamps, and hosts.

This project turns that investigation flow into a repeatable pipeline:

- capture raw evidence from journald;
- preserve every raw record before parsing;
- extract structured fields such as service, level, request ID, resource IDs,
  host, module, file, and line;
- connect related events with directed correlation edges;
- detect incident seeds with deterministic rules;
- build bounded incident subgraphs around the seed event;
- enrich incidents with timelines, observed impact, evidence counts, and
  human-readable summaries.

## Current Status

The implemented system covers the evidence and deterministic analysis plane.
It does not currently call an LLM, create embeddings, run ChromaDB, use
Ollama, expose incident chat, or generate TikZ causal graphs from incidents.
Those pieces are part of the broader product direction and are shown as future
components in the architecture diagrams.

Implemented now:

| Area | Status |
|------|--------|
| FastAPI raw log ingestion | Implemented |
| MongoDB persistence | Implemented |
| Host journald collector | Implemented |
| Parser worker | Implemented |
| Correlation worker | Implemented |
| Incident worker | Implemented |
| Enrichment worker | Implemented |
| Docker Compose runtime | Implemented |
| Worker health checks | Implemented |
| Provider-agnostic AI backend configuration | Implemented |
| Unit tests | Implemented |
| Production AI generation, embeddings, RAG retrieval, chat UI | Planned |

## Architecture

The project is designed as a two-machine RCA assistant. The MacBook/OpenStack
host runs the implemented evidence pipeline. A future MSI Raider/GPU machine can
host the retrieval and local AI plane over a private network boundary.

![Overall two-machine architecture](docs/assets/overall-architecture.png)

The simplified final architecture separates current implemented services from
future local AI components.

![Final architecture overview](docs/assets/final-architecture.png)

Current implemented data flow:

```text
journald
  -> collector
  -> FastAPI backend
  -> MongoDB raw_logs
  -> parser-worker
  -> MongoDB parsed_logs
  -> correlation-worker
  -> MongoDB event_edges
  -> incident-worker
  -> MongoDB incidents
  -> enrichment-worker
  -> enriched incidents
```

AI providers are configured behind the FastAPI backend. The browser and Horizon
plugin never call Ollama, OpenAI-compatible endpoints, Gemini-compatible
endpoints, Claude-compatible endpoints, custom HTTP providers, MongoDB, or a
vector store directly.

```text
Horizon UI
  -> RCA FastAPI backend
  -> active provider adapter
  -> external or local AI provider
```

## Repository Layout

```text
.
+-- backend/               FastAPI ingestion service
+-- collector/             Host journald collector
+-- correlation_worker/    Builds edges between related parsed events
+-- enrichment_worker/     Adds deterministic investigation summaries
+-- incident_worker/       Detects incident seeds and subgraphs
+-- parser_worker/         Parses raw log records into structured events
+-- systemd/               Optional collector systemd unit
+-- latex/                 Presentation source, notes, and compiled deck
+-- docs/assets/           README-rendered images copied from the deck
+-- docker-compose.yml     Local MongoDB plus service/worker stack
+-- requirements.txt       Backend/runtime Python dependencies
+-- requirements-dev.txt   Test dependencies
+-- pytest.ini             Test configuration
```

## Components

### Backend

`backend/main.py` exposes the ingestion API:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/health` | Backend health check |
| `POST` | `/logs/batch` | Store raw journal records |

`POST /logs/batch` accepts a list of raw journal records. Each record must
include `boot_id`, `journal_cursor`, and `message`; additional journald fields
are accepted and preserved. The backend adds `received_at` and de-duplicates by
`boot_id` plus `journal_cursor`.

The versioned RCA API also exposes provider administration under
`/api/v1/providers`. Those endpoints require `X-RCA-Service-Token` with the
server-side `RCA_INTERNAL_SERVICE_TOKEN`; the token is intended for Horizon
server-side calls and must not be sent to browser JavaScript.

### Provider Framework

Provider configuration is stored in MongoDB `provider_configs`, with
non-secret lifecycle history in `config_audit_log`. The backend supports these
provider kinds:

- `ollama`
- `openai_compatible`
- `gemini`
- `anthropic`
- `custom_http`
- `chroma` as a vector store placeholder only

Provider types are `llm`, `embedding`, `reranker`, and `vector_store`.
Adapters declare capabilities from `llm`, `embedding`, `reranker`, `vision`,
`streaming`, and `model_listing`. Unsupported operations return a structured
unavailable result instead of crashing. Production `generate`, `embed`, and
`rerank` calls are intentionally left as extension points; the current code
implements validation, connection testing, simple model listing where practical,
activation, rollback, audit, and health state.

Provider lifecycle:

```text
create draft -> validate locally -> save draft -> test connection -> activate
```

Only one provider can be active for each provider type. Activation requires a
successful connection test unless the config is explicitly marked as an
offline placeholder in `extra_config`. A failed activation does not disable the
previous active provider. Rollback activates a previous version only if that
version previously tested successfully.

Secrets are write-only. API keys are encrypted with authenticated encryption
from `cryptography.fernet` using `RCA_PROVIDER_MASTER_KEY`, are never returned
by GET APIs, and are masked in Horizon. If the master key is missing, provider
configs without secrets still work, saving a secret fails clearly, and the
deterministic RCA pipeline remains healthy.

Provider URL safety is enforced server-side: only `http` and `https` are
allowed, embedded credentials are rejected, trailing slashes are normalized,
redirects are disabled, requests have timeouts and response-size limits, and
metadata, link-local, loopback, private, or reserved addresses are blocked
unless explicitly allowed.

Provider configuration options in the ``[provider]`` and ``[api]`` groups:

| Option | Purpose |
|----------|---------|
| `[api] internal_service_token` | Internal server-side token for Horizon/provider API calls |
| `[provider] master_key` | Master key used to encrypt provider API keys |
| `[provider] allowed_cidrs` | CIDRs allowed for provider URLs, such as a Tailscale range |
| `[provider] allowed_hosts` | Hostnames exempt from DNS/IP blocking |
| `[provider] allow_localhost` | Allows localhost provider URLs when true |
| `[provider] request_timeout_seconds` | Default provider request timeout |

To add Ollama later, create an `ollama` provider with a backend-reachable base
URL and model name, test it, then activate it. To add an OpenAI-compatible
endpoint later, use `openai_compatible` and the endpoint's `/v1` base URL. To
add Gemini later, use `gemini` and save the API key through the provider form.
To add Claude later, use `anthropic` and save the API key through the provider
form. In all cases the backend owns validation, secret storage, connection
tests, activation, rollback, health, and external calls.

If no valid active provider exists, AI explanation and similar-incident
endpoints return HTTP 503 with:

```json
{"status": "unavailable", "reason": "No active LLM provider configured"}
```

They do not fake AI answers. Collector, ingestion, parser, correlation,
incident detection, and deterministic enrichment do not depend on provider
health and continue without AI.

### Collector

The collector runs on the OpenStack host, outside Docker. It follows journald
with `journalctl -f -o json --show-cursor`, batches records, posts them to the
backend, and saves the last backend-acknowledged cursor. This gives at-least-once
delivery while the backend handles duplicate records safely.

Default monitored DevStack units include Keystone, Nova API, Nova scheduler,
Nova conductor, Nova compute, Neutron API, and Placement API.

### Parser Worker

The parser worker reads `raw_logs` and writes `parsed_logs`. It preserves raw
documents unchanged and writes parse failures as structured rows with
`parse_status="failure"` and `parse_error`.

Extracted fields include:

- service or systemd unit;
- normalized log level;
- OpenStack request ID;
- resource UUIDs, excluding the request UUID;
- host, process ID, module, file, line, and function when available;
- parser version and parse timestamp.

### Correlation Worker

The correlation worker reads successful parsed events and creates directed
`event_edges` when events share a useful identifier.

| Rule | Reason | Confidence | Default gap |
|------|--------|------------|-------------|
| Same request ID | `same_request_id` | `1.0` | 5 minutes |
| Shared resource ID | `shared_resource_id` | `0.9` | 10 minutes |

Edges are chronological: the earlier event is `source_event_id`, and the later
event is `target_event_id`. Self edges, equal-timestamp edges, oversized groups,
and periodic groups are skipped where practical. Upserts are idempotent.

### Incident Worker

The incident worker reads successful parsed events and detects candidate incident
seeds using deterministic rules:

- `ERROR` or `CRITICAL` level;
- `Traceback`;
- `Exception`;
- `failed` or `failure`;
- `timeout` or `timed out`;
- resource entering `ERROR` state;
- service, daemon, unit, or process failure.

Obvious false positives such as `0 failures`, `no error`, counters set to zero,
error-rate metrics, and quoted or historical examples are suppressed.

For each seed, the worker traverses existing `event_edges` both incoming and
outgoing. Traversal is bounded by depth, event count, and a time window around
the seed. The result is an incident candidate with event IDs, edge IDs,
services, resources, severity, seed reason, and version metadata.

### Enrichment Worker

The enrichment worker reads candidate incidents, loads their referenced events
and edges, and updates each incident with:

- ordered event timeline;
- request IDs, resources, hosts, levels, services;
- first and last event timestamps;
- duration, event count, edge count, error count, warning count;
- deterministic `summary`, `impact_summary`, and `evidence_summary`;
- `status="enriched"`.

Enrichment describes observed evidence only. It does not infer root cause, rank
causes, call an LLM, create embeddings, or add causal edges.

## Quick Start

Prerequisites:

- Docker and Docker Compose;
- Python 3.11+ for local tests and the optional host collector;
- access to journald if running the collector.

Create local configuration:

```bash
cp .env.example .env
```

For real deployments, edit `.env` and change `MONGO_INITDB_ROOT_PASSWORD`.

Validate Compose:

```bash
docker compose config
```

Start the full local pipeline:

```bash
docker compose up -d --build
```

Check service health:

```bash
docker compose ps
curl http://127.0.0.1:8000/health
```

Follow logs:

```bash
docker compose logs -f backend parser-worker correlation-worker incident-worker enrichment-worker
```

Stop containers while keeping MongoDB data:

```bash
docker compose down
```

Remove MongoDB data too:

```bash
docker compose down -v
```

## Ingest a Test Log

Start the stack, then post a synthetic OpenStack-style error:

```bash
curl -s http://127.0.0.1:8000/logs/batch \
  -H 'Content-Type: application/json' \
  -d '{
    "records": [
      {
        "boot_id": "boot-demo",
        "journal_cursor": "cursor-demo-001",
        "service": "devstack@n-api.service",
        "priority": "3",
        "timestamp": "2026-07-05T10:00:00Z",
        "host": "compute-01",
        "message": "2026-07-05 10:00:00.000 1234 ERROR nova.api.openstack [req-11111111-1111-4111-8111-111111111111] instance 22222222-2222-4222-8222-222222222222 failed"
      }
    ]
  }'
```

Inspect the parsed event:

```bash
docker compose exec mongodb mongosh --quiet \
  "mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/$MONGO_INITDB_DATABASE?authSource=admin" \
  --eval 'db.parsed_logs.findOne({request_id:"req-11111111-1111-4111-8111-111111111111"},{_id:0,service:1,level:1,request_id:1,resource_ids:1,parse_status:1})'
```

Inspect enriched incidents:

```bash
docker compose exec mongodb mongosh --quiet \
  "mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/$MONGO_INITDB_DATABASE?authSource=admin" \
  --eval 'db.incidents.find({}, {_id:0,incident_id:1,status:1,seed_reason:1,summary:1,evidence_summary:1}).limit(5)'
```

## Host Journald Collector

Install collector dependencies on the host:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r collector/requirements.txt
```

Create a user-owned state directory for manual runs:

```bash
install -d -m 0755 "$HOME/.local/state/rca-copilot"
```

Run the collector:

```bash
RCA_COLLECTOR_STATE_FILE=$HOME/.local/state/rca-copilot/journal.cursor \
python -m collector.runner
```

The collector user must be able to read journald. On Ubuntu, use root or add the
user to the `systemd-journal` group and start a new login session.

An optional systemd unit is provided:

```bash
systemd-analyze verify systemd/rca-copilot-journald-collector.service
sudo install -d -m 0755 /etc/rca-copilot
sudo install -m 0644 systemd/rca-copilot-journald-collector.service /etc/systemd/system/
sudo tee /etc/rca-copilot/journald-collector.env >/dev/null <<'EOF'
RCA_COLLECTOR_BACKEND_URL=http://127.0.0.1:8000/logs/batch
RCA_COLLECTOR_BATCH_SIZE=50
RCA_COLLECTOR_FLUSH_INTERVAL_SECONDS=2
EOF
sudo systemctl daemon-reload
sudo systemctl start rca-copilot-journald-collector.service
```

Follow collector logs:

```bash
sudo journalctl -u rca-copilot-journald-collector.service -f
```

## Configuration

Core database settings:

| Variable | Default | Purpose |
|----------|---------|---------|
| `MONGO_BIND_HOST` | `127.0.0.1` | Host interface for MongoDB |
| `MONGO_PORT` | `27017` | Host MongoDB port |
| `MONGO_INITDB_ROOT_USERNAME` | `rca_admin` | MongoDB root user |
| `MONGO_INITDB_ROOT_PASSWORD` | `change-me` | MongoDB root password |
| `MONGO_INITDB_DATABASE` | `rca_copilot` | Application database |
| `MONGO_URI` | see `.env.example` | Local app connection string |
| `MONGO_DATABASE` | `rca_copilot` | Database selected by services |

Collections:

| Variable | Default |
|----------|---------|
| `MONGO_RAW_LOGS_COLLECTION` | `raw_logs` |
| `MONGO_PARSED_LOGS_COLLECTION` | `parsed_logs` |
| `MONGO_EVENT_EDGES_COLLECTION` | `event_edges` |
| `MONGO_INCIDENTS_COLLECTION` | `incidents` |
| `MONGO_WORKER_STATE_COLLECTION` | `worker_state` |

Worker controls:

| Variable | Default |
|----------|---------|
| `PARSER_VERSION` | `parser-v1` |
| `PARSER_BATCH_SIZE` | `100` |
| `PARSER_POLL_INTERVAL_SECONDS` | `2` |
| `CORRELATION_VERSION` | `correlation-v1` |
| `CORRELATION_BATCH_SIZE` | `100` |
| `CORRELATION_POLL_INTERVAL_SECONDS` | `2` |
| `CORRELATION_REQUEST_ID_MAX_GAP_SECONDS` | `300` |
| `CORRELATION_RESOURCE_ID_MAX_GAP_SECONDS` | `600` |
| `INCIDENT_VERSION` | `incident-v1` |
| `INCIDENT_BATCH_SIZE` | `100` |
| `INCIDENT_POLL_INTERVAL_SECONDS` | `2` |
| `INCIDENT_MAX_DEPTH` | `3` |
| `INCIDENT_MAX_EVENTS` | `100` |
| `INCIDENT_WINDOW_BEFORE_SECONDS` | `600` |
| `INCIDENT_WINDOW_AFTER_SECONDS` | `120` |
| `ENRICHMENT_VERSION` | `enrichment-v1` |
| `ENRICHMENT_BATCH_SIZE` | `100` |
| `ENRICHMENT_POLL_INTERVAL_SECONDS` | `2` |

Collector controls:

| Variable | Default |
|----------|---------|
| `RCA_COLLECTOR_BACKEND_URL` | `http://127.0.0.1:8000/logs/batch` |
| `RCA_COLLECTOR_STATE_FILE` | `/var/lib/rca-copilot-journald-collector/state.json` |
| `RCA_COLLECTOR_BATCH_SIZE` | `50` |
| `RCA_COLLECTOR_FLUSH_INTERVAL_SECONDS` | `2` |
| `RCA_COLLECTOR_REQUEST_TIMEOUT_SECONDS` | `5` |
| `RCA_COLLECTOR_RETRY_MAX_ATTEMPTS` | `5` |
| `RCA_COLLECTOR_RETRY_INITIAL_DELAY_SECONDS` | `0.5` |
| `RCA_COLLECTOR_RETRY_MAX_DELAY_SECONDS` | `8` |

## Development

Create a local virtual environment and run tests:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Run a focused test module:

```bash
pytest parser_worker/tests/test_parser.py
```

Format and linting are not wired into this repository yet. Keep changes small,
run the test suite, and avoid committing generated caches or local service data.

## Presentation Assets

The Beamer presentation lives under `latex/`:

- `latex/openstack_rca_copilot_beamer.tex`;
- `latex/openstack_rca_copilot_beamer.pdf`;
- `latex/speaker_notes.md`.

README images are copied into `docs/assets/` so they render on GitHub. The
`latex/build/` directory and common LaTeX compiler outputs are ignored because
they are generated artifacts.

Build the deck from `latex/`:

```bash
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build openstack_rca_copilot_beamer.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build openstack_rca_copilot_beamer.tex
cp build/openstack_rca_copilot_beamer.pdf openstack_rca_copilot_beamer.pdf
```

Regenerate slide previews when needed:

```bash
pdftoppm -r 90 -png openstack_rca_copilot_beamer.pdf build/preview
```

## Backup and Restore

Create a MongoDB archive backup:

```bash
mkdir -p backups
docker compose exec mongodb mongodump \
  --username "$MONGO_INITDB_ROOT_USERNAME" \
  --password "$MONGO_INITDB_ROOT_PASSWORD" \
  --authenticationDatabase admin \
  --archive > backups/mongodb-$(date +%Y%m%d-%H%M%S).archive
```

Load variables first if your shell does not already have them:

```bash
set -a
. .env
set +a
```

## Roadmap

Planned next layers:

- incident retrieval over enriched incident history;
- embeddings and optional vector-store-backed semantic search;
- provider-backed LLM generation through local or external adapters;
- operator chat over frozen incident context;
- graph visualization and RCA explanation UI;
- evaluation harness for retrieval quality and RCA consistency.

The current code intentionally stops before these features so the evidence
pipeline remains deterministic, testable, and auditable.

## License

See [LICENSE](LICENSE).
