# OpenStack RCA Copilot

> A local-first, privacy-preserving AI debugging assistant for OpenStack infrastructure.
> It watches your logs, understands your incidents, explains what broke and why —
> and when you need more, you just ask.

---

## What is this?

When something breaks in OpenStack, the real root cause is almost never on the line
where the error appears. A `nova-compute` failure traces back to a neutron port binding
issue which traces back to a keystone token that expired three hours ago. By the time a
sysadmin opens a terminal, the trail is cold and the logs are thousands of lines long.

**OpenStack RCA Copilot** is an AIOps service that solves exactly this. It runs
alongside your OpenStack deployment, continuously watches logs, detects incidents the
moment they happen, and uses a Retrieval-Augmented Generation (RAG) pipeline backed by
a local LLM to produce a plain-language root cause analysis automatically — no ticket,
no manual grep, no waiting.

If the sysadmin doesn't understand the explanation, they open a chat linked to that
specific incident and ask follow-up questions. If they need a visual, the system
generates a TikZ causal graph they can compile into a diagram.

Everything runs locally. No data leaves the machine. No cloud API keys.

---

## Core Concepts (read this before touching the code)

### What is an "incident"?

In OpenStack, multiple services (Nova, Neutron, Keystone, Glance, Cinder, Heat, Aodh...)
log independently and asynchronously. An incident is not a single error line — it is a
**burst of related errors across multiple services within a time window**, correlated by
timestamps and optionally by request/trace IDs.

The first job of this system is to detect those boundaries and group everything belonging
to one event into one coherent unit before doing anything else.

### What is RAG?

Retrieval-Augmented Generation means the LLM is not guessing from memory — it is
reasoning over **documents you retrieved** that are specifically relevant to the current
incident. Instead of asking "what do you know about nova failures?", you ask "here are
the three most similar past incidents we resolved, and here are the relevant docs — now
explain this new one."

This eliminates hallucination on infrastructure-specific details because the LLM is
always grounded in real, sourced context.

### Why three retrieval tiers?

Because speed and accuracy trade off against each other:

| Tier | Method | Speed | When it fires |
|------|--------|-------|---------------|
| 1 | MongoDB structured lookup | instant | exact match on error type + component |
| 2 | ChromaDB semantic search | fast | similar but not identical past incidents |
| 3 | Raw log brute force | slow | never seen this before, last resort |

New incidents resolved via Tier 3 are automatically promoted into Tier 1 + 2 so the
system gets smarter over time and Tier 3 fires less and less.

---

## Architecture

Current implemented ingestion path:

```
journald
  -> collector
  -> FastAPI
  -> raw_logs
  -> parser-worker
  -> parsed_logs
  -> correlation-worker
  -> event_edges
  -> incident-worker
  -> enrichment-worker
  -> incidents
```

The correlation worker reads only successful `parsed_logs` documents and preserves
`parsed_logs` unchanged. It writes directed edges to `event_edges` when events share a
non-null `request_id` or a resource ID.

Edge direction is chronological: the earlier parsed event is `source_event_id`, and the
later parsed event is `target_event_id`. Equal-timestamp and self edges are skipped.
Edges are upserted idempotently with a unique key on `source_event_id`,
`target_event_id`, `reason`, `shared_value`, and `correlation_version`.

The incident worker reads only successful `parsed_logs` documents, preserves
`parsed_logs` and `event_edges` unchanged, and writes deterministic incident
candidates to `incidents`. It does not merge incidents, infer causality, identify a
root cause, rank causes, call an LLM, create embeddings, or use ChromaDB.

The enrichment worker reads candidate incidents, loads the referenced `event_ids` from
`parsed_logs` and `edge_ids` from `event_edges`, and updates each incident with a
versioned deterministic investigation record. It preserves the original incident
fields, writes `enrichment_version`, `enriched_at`, an ordered `timeline`, involved
request IDs, resources, hosts, levels, timing/count metrics, and deterministic
`summary`, `impact_summary`, and `evidence_summary` fields before setting
`status` to `enriched`.

Enrichment is intentionally bounded: it does not call an LLM, infer root cause, rank
causes, create causal edges, create embeddings, use ChromaDB, or integrate with MSI.
Summaries describe only observed events, services, resources, requests, warnings,
errors, and correlation edge counts. If only one event is available, the evidence
summary states that evidence is limited to one event.

Incident seeds are detected by deterministic rules:

- `level` is `ERROR` or `CRITICAL`
- message contains `Traceback`
- message contains `Exception`
- message contains `failed` or `failure`
- message contains `timeout` or `timed out`
- message indicates a resource entered an `ERROR` state
- message indicates a service or process failure

Obvious false positives such as `0 failures`, `no error`, `error rate`, and quoted or
historical text are suppressed where practical. Each incident stores the primary
`seed_reason` plus detailed `seed_detection_reasons` and
`seed_detection_exclusions`.

Incident subgraphs start from the seed event and traverse existing `event_edges` in
both incoming and outgoing directions. Traversal is bounded by maximum depth, maximum
events, and a time window around the seed. Defaults are depth `3`, `100` events, `10`
minutes before the seed, and `2` minutes after the seed. Incidents are upserted
idempotently with a unique index on `seed_event_id` and `incident_version`.

Default correlation windows:

| Rule | Reason | Confidence | Maximum gap |
|------|--------|------------|-------------|
| Same request ID | `same_request_id` | `1.0` | 5 minutes |
| Shared resource ID | `shared_resource_id` | `0.9` | 10 minutes |

Configure the worker with:

| Variable | Default |
|----------|---------|
| `MONGO_EVENT_EDGES_COLLECTION` | `event_edges` |
| `CORRELATION_VERSION` | `correlation-v1` |
| `CORRELATION_BATCH_SIZE` | `100` |
| `CORRELATION_POLL_INTERVAL_SECONDS` | `2` |
| `CORRELATION_REQUEST_ID_MAX_GAP_SECONDS` | `300` |
| `CORRELATION_RESOURCE_ID_MAX_GAP_SECONDS` | `600` |

Incident worker configuration:

| Variable | Default |
|----------|---------|
| `MONGO_INCIDENTS_COLLECTION` | `incidents` |
| `INCIDENT_VERSION` | `incident-v1` |
| `INCIDENT_BATCH_SIZE` | `100` |
| `INCIDENT_POLL_INTERVAL_SECONDS` | `2` |
| `INCIDENT_MAX_DEPTH` | `3` |
| `INCIDENT_MAX_EVENTS` | `100` |
| `INCIDENT_WINDOW_BEFORE_SECONDS` | `600` |
| `INCIDENT_WINDOW_AFTER_SECONDS` | `120` |

Enrichment worker configuration:

| Variable | Default |
|----------|---------|
| `MONGO_INCIDENTS_COLLECTION` | `incidents` |
| `MONGO_WORKER_STATE_COLLECTION` | `worker_state` |
| `ENRICHMENT_VERSION` | `enrichment-v1` |
| `ENRICHMENT_BATCH_SIZE` | `100` |
| `ENRICHMENT_POLL_INTERVAL_SECONDS` | `2` |

```
┌─────────────────────────────────────────────────────────────┐
│                     OpenStack Deployment                     │
│  Nova │ Neutron │ Keystone │ Heat │ Ceilometer │ Aodh │ ... │
└──────────────────────────┬──────────────────────────────────┘
                           │ raw logs + Alertmanager webhooks
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     INGESTION LAYER                          │
│                                                              │
│  log_watcher.py          watches log files in real time      │
│       │                                                      │
│       ▼                                                      │
│  incident_parser.py      detects incident boundaries,        │
│                          groups related cross-service errors  │
│       │                                                      │
│       ▼                                                      │
│  preprocessor.py         extracts: component, error_type,    │
│                          error_code, causal chain, tags      │
└──────────────────────────┬──────────────────────────────────┘
                           │ structured incident documents
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
     MongoDB           ChromaDB           Disk
  (structured        (embeddings        (raw logs,
   incidents)         of summaries       referenced
   Tier 1             only) Tier 2       by path)
                                         Tier 3
          └────────────────┬────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                     RETRIEVAL LAYER                          │
│                                                              │
│  tiered_retriever.py     orchestrates Tier 1 → 2 → 3        │
│  multi_hop.py            extracts sub-entities, runs N       │
│                          parallel sub-queries per entity     │
│  dependency_graph.py     expands component scope             │
│                          (nova query → also fetches neutron) │
│  reranker.py             cross-encoder re-scores shortlist   │
│                          before sending to LLM               │
└──────────────────────────┬──────────────────────────────────┘
                           │ ranked, grounded context
┌──────────────────────────▼──────────────────────────────────┐
│                      LLM LAYER (local)                       │
│                                                              │
│  ollama_client.py        wraps Ollama (deepseek-r1:8b)       │
│  rca_generator.py        structured RCA output with schema   │
│                          validation + retry on bad output    │
│  tikz_generator.py       causal graph as compilable LaTeX    │
│  prompts.py              all prompt templates in one place   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                       API LAYER                              │
│                                                              │
│  POST /webhook/alert     Alertmanager fires this on incident │
│  GET  /incidents         list all stored incidents           │
│  GET  /incidents/{id}    single incident + RCA               │
│  POST /incidents/{id}/chat   follow-up conversation          │
│  GET  /incidents/{id}/graph  returns compilable TikZ LaTeX   │
└─────────────────────────────────────────────────────────────┘
```

---

## Three Interaction Modes

### Mode 1 — Automatic (always on)

Prometheus Alertmanager sends a webhook to `/webhook/alert` the moment a rule fires.
The system fetches the relevant log window, runs the full RAG pipeline, and stores a
complete RCA. The sysadmin comes back later and the answer is already there.

### Mode 2 — Conversational follow-up

```
Sysadmin: "why did keystone get involved here?"
System:    [reasons over frozen incident context, answers]
Sysadmin: "I still don't get the token expiry part"
System:    [goes deeper, same context, consistent]
```

Context is **frozen per incident** — the same retrieved documents are reused across
the whole conversation so answers never drift or contradict each other.

### Mode 3 — TikZ causal graph

```
Sysadmin: "show me the graph"
System:    returns LaTeX → sysadmin compiles with pdflatex → clean diagram
```

---

## RAG Quality Mechanisms

| Mechanism | What it solves |
|-----------|----------------|
| Incident boundary chunking | Never splits a stack trace across chunks |
| Multi-hop retrieval | Catches root causes buried in sub-entities |
| Component dependency expansion | nova query auto-includes neutron/keystone |
| Parent document retrieval | Small chunks indexed, full parent returned to LLM |
| Cross-encoder reranker | Re-scores shortlist by true relevance, not just vector distance |
| Summary-only embeddings | Raw logs never embedded — noise is excluded from vector space |

---

## MLOps Layer

- **MLflow** tracks every embedding pipeline run, model version, and retrieval experiment
- **Hit@K + MRR** evaluated against a hand-labeled ground truth set of known incidents
- **Chunking strategy comparison** — fixed-size vs. semantic boundary (report section)
- **Feedback loop** — resolved incidents ingested back, system improves over time
- **Embedding pipeline versioned** — re-embeddable when knowledge base is updated

---

## Tech Stack

| Layer | Tool | Why |
|-------|------|-----|
| LLM | Ollama / deepseek-r1:8b | local, private, no API cost |
| Vector store | ChromaDB | lightweight, embeds + queries in one lib |
| Document store | MongoDB | flexible schema, fast structured queries |
| Embeddings | sentence-transformers | runs offline, good semantic quality |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 | fast, accurate shortlist re-scoring |
| Experiment tracking | MLflow | standard, integrates cleanly |
| API | FastAPI | async, automatic OpenAPI docs |
| Alert trigger | Prometheus Alertmanager | standard OpenStack monitoring stack |
| Graph output | TikZ / pdflatex | compilable, reproducible diagrams |
| Packaging | Docker Compose | one command to run the whole stack |

---

## Project Structure

```
openstack-rca-copilot/
│
├── docker-compose.yml          # infrastructure milestone 1: MongoDB only
├── .env.example                # copy to .env and set MongoDB values
├── requirements.txt
├── config.py                   # central config loaded from .env
│
├── ingestion/
│   ├── log_watcher.py          # tails OpenStack log files, feeds parser
│   ├── incident_parser.py      # boundary detection, cross-service grouping
│   └── preprocessor.py         # extracts structured fields from raw incident
│
├── storage/
│   ├── schemas.py              # Pydantic models — single source of truth for data shape
│   ├── mongo_client.py         # Tier 1 store: structured incident CRUD
│   └── chroma_client.py        # Tier 2 store: embed + query summaries
│
├── retrieval/
│   ├── embedder.py             # sentence-transformers wrapper
│   ├── reranker.py             # cross-encoder shortlist re-scoring
│   ├── multi_hop.py            # entity extraction + parallel sub-queries
│   ├── dependency_graph.py     # static OpenStack component dependency map
│   └── tiered_retriever.py     # orchestrates Tier 1 → 2 → 3, promotes new results
│
├── llm/
│   ├── ollama_client.py        # Ollama HTTP wrapper with retry logic
│   ├── prompts.py              # all prompt templates in one place, nothing hardcoded
│   ├── rca_generator.py        # structured RCA: output schema + validation + retry
│   └── tikz_generator.py       # causal graph generation + LaTeX compilation check
│
├── api/
│   ├── main.py                 # FastAPI app, middleware, lifespan
│   └── routes/
│       ├── webhook.py          # POST /webhook/alert — Alertmanager entry point
│       ├── incidents.py        # GET /incidents, GET /incidents/{id}
│       └── chat.py             # POST /incidents/{id}/chat, GET /incidents/{id}/graph
│
├── evaluation/
│   ├── benchmark.py            # computes Hit@K and MRR against ground truth
│   └── ground_truth.json       # hand-labeled: {query, correct_incident_id}
│
└── mlops/
    └── tracker.py              # MLflow logging: embeddings, retrievals, experiments
```

---

## Milestone 2: Ingestion Backend

### Prerequisites

- Docker + Docker Compose

This milestone runs MongoDB and a FastAPI ingestion backend. It does not include the
collector, parsing, ChromaDB, embeddings, graph logic, MSI integration, Ollama, or any
DevStack changes.

### 1. Configure

```bash
cp .env.example .env
# edit .env and replace MONGO_INITDB_ROOT_PASSWORD
```

### 2. Validate Docker Compose

```bash
docker compose config
```

### 3. Start

```bash
docker compose up -d --build
```

MongoDB is bound to `127.0.0.1:27017`. The backend is bound to `127.0.0.1:8000`,
waits for MongoDB to become healthy, and stores raw records in
`rca_copilot.raw_logs`.

### 4. Stop

```bash
docker compose stop
```

To stop and remove containers while keeping the named MongoDB volume:

```bash
docker compose down
```

### 5. Check status

```bash
docker compose ps
```

### 6. Check health

```bash
curl http://127.0.0.1:8000/health
docker inspect --format='{{json .State.Health}}' rca-copilot-mongodb
docker inspect --format='{{json .State.Health}}' rca-copilot-backend
```

Or ping MongoDB directly through the container:

```bash
docker compose exec mongodb mongosh --quiet --eval 'db.adminCommand("ping")'
```

### 7. Ingest raw logs

`POST /logs/batch` stores raw journal records without parsing or modifying the
`message` field. The backend appends `received_at` in UTC and ignores duplicate
records with the same `boot_id` and `journal_cursor`.

```bash
curl -s http://127.0.0.1:8000/logs/batch \
  -H 'Content-Type: application/json' \
  -d '{
    "records": [
      {
        "boot_id": "boot-123",
        "journal_cursor": "s=cursor-001",
        "message": "nova-api raw log message",
        "unit": "nova-api.service"
      }
    ]
  }'
```

Example response:

```json
{
  "received_count": 1,
  "inserted_count": 1,
  "duplicate_count": 0
}
```

### 8. Run tests

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

### 9. Back up MongoDB

```bash
mkdir -p backups
docker compose exec mongodb mongodump \
  --username "$MONGO_INITDB_ROOT_USERNAME" \
  --password "$MONGO_INITDB_ROOT_PASSWORD" \
  --authenticationDatabase admin \
  --archive > backups/mongodb-$(date +%Y%m%d-%H%M%S).archive
```

Run `set -a; source .env; set +a` first if the MongoDB credentials are not already
exported in your shell.

---

## Milestone 3: Host Journald Collector

This milestone adds only the host-level journald collector. It runs on the Ubuntu host,
outside Docker, reads journald with `journalctl -f -o json --show-cursor`, batches raw
records, and posts them to `http://127.0.0.1:8000/logs/batch`.

The collector monitors these systemd units by default:

- `devstack@keystone.service`
- `devstack@n-api.service`
- `devstack@n-sch.service`
- `devstack@n-cond-cell1.service`
- `devstack@n-cpu.service`
- `devstack@neutron-api.service`
- `devstack@placement-api.service`

It persists the last backend-acknowledged journald cursor in a local state file and
uses `--after-cursor` on restart. The cursor is saved only after the backend returns a
successful response, so retries are at-least-once and backend duplicate handling remains
safe.

### Manual run

Install the collector dependencies on the host:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r collector/requirements.txt
```

Start MongoDB and the backend first:

```bash
docker compose up -d --build
```

Run the collector:

```bash
RCA_COLLECTOR_STATE_FILE=$HOME/.local/state/rca-copilot/journal.cursor \
python -m collector.runner
```

For manual host runs, create the user-owned state directory first:

```bash
install -d -m 0755 "$HOME/.local/state/rca-copilot"
RCA_COLLECTOR_STATE_FILE=$HOME/.local/state/rca-copilot/journal.cursor \
python -m collector.runner
```

The user running the collector must be able to read journald for the DevStack services.
On Ubuntu this usually means running as root or adding the user to the `systemd-journal`
group and starting a new login session. The systemd unit runs as `stack` and grants
`systemd-journal` as a supplementary group.

### Systemd installation

A service template is provided at `systemd/rca-copilot-journald-collector.service`.
It is not installed, enabled, or started by this repository.

Validate the unit before installing it:

```bash
systemd-analyze verify systemd/rca-copilot-journald-collector.service
```

Install the unit without enabling or starting it:

```bash
sudo install -d -m 0755 /etc/rca-copilot
sudo install -m 0644 systemd/rca-copilot-journald-collector.service /etc/systemd/system/
sudo tee /etc/rca-copilot/journald-collector.env >/dev/null <<'EOF'
RCA_COLLECTOR_BACKEND_URL=http://127.0.0.1:8000/logs/batch
RCA_COLLECTOR_BATCH_SIZE=50
RCA_COLLECTOR_FLUSH_INTERVAL_SECONDS=2
EOF
sudo systemctl daemon-reload
```

Start the service only when ready:

```bash
sudo systemctl start rca-copilot-journald-collector.service
```

Check status:

```bash
sudo systemctl status rca-copilot-journald-collector.service
```

Follow service logs:

```bash
sudo journalctl -u rca-copilot-journald-collector.service -f
```

Restart after changing configuration:

```bash
sudo systemctl restart rca-copilot-journald-collector.service
```

Uninstall the service and remove its systemd-managed state directory:

```bash
sudo systemctl stop rca-copilot-journald-collector.service
sudo systemctl disable rca-copilot-journald-collector.service
sudo rm -f /etc/systemd/system/rca-copilot-journald-collector.service
sudo rm -f /etc/rca-copilot/journald-collector.env
sudo rm -rf /var/lib/rca-copilot-journald-collector
sudo systemctl daemon-reload
sudo systemctl reset-failed rca-copilot-journald-collector.service
```

### Collector configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `RCA_COLLECTOR_BACKEND_URL` | Backend batch ingestion endpoint | `http://127.0.0.1:8000/logs/batch` |
| `RCA_COLLECTOR_STATE_FILE` | Local cursor state file | `/var/lib/rca-copilot-journald-collector/journal.cursor` |
| `RCA_COLLECTOR_BATCH_SIZE` | Records per POST batch | `50` |
| `RCA_COLLECTOR_FLUSH_INTERVAL_SECONDS` | Maximum seconds before flushing a partial batch | `2` |
| `RCA_COLLECTOR_REQUEST_TIMEOUT_SECONDS` | HTTP request timeout | `5` |
| `RCA_COLLECTOR_RETRY_MAX_ATTEMPTS` | Attempts per failed POST before returning to the run loop | `5` |
| `RCA_COLLECTOR_RETRY_INITIAL_DELAY_SECONDS` | First retry delay | `0.5` |
| `RCA_COLLECTOR_RETRY_MAX_DELAY_SECONDS` | Maximum retry delay | `8` |
| `RCA_COLLECTOR_JOURNALCTL_PATH` | `journalctl` executable path | `journalctl` |
| `RCA_COLLECTOR_UNITS` | Comma-separated systemd unit override | DevStack units listed above |

---

## Milestone 4: Parsing Pipeline

This milestone adds only the parser worker. It runs as a Docker Compose service, reads
unprocessed documents from MongoDB `raw_logs`, never modifies or deletes raw documents,
and writes parsed documents to `parsed_logs`.

The parser creates a unique index on `source_log_id` and `parser_version`, then uses
idempotent upserts so reruns and duplicate polling do not create duplicate parsed rows.
Parse failures are written with `parse_status=failure` and `parse_error` instead of
being dropped.

### Start

```bash
docker compose up -d --build mongodb backend parser-worker
```

### Status

```bash
docker compose ps
docker inspect --format='{{json .State.Health}}' rca-copilot-parser-worker
```

### Logs

```bash
docker compose logs -f parser-worker
```

### Restart

```bash
docker compose restart parser-worker
```

### Verification

Validate Compose:

```bash
docker compose config
```

Insert a raw log through the existing backend:

```bash
curl -s http://127.0.0.1:8000/logs/batch \
  -H 'Content-Type: application/json' \
  -d '{
    "records": [
      {
        "boot_id": "boot-parser-demo",
        "journal_cursor": "cursor-parser-demo",
        "service": "devstack@n-api.service",
        "priority": "3",
        "timestamp": "2026-07-05T10:00:00Z",
        "host": "compute-01",
        "message": "2026-07-05 10:00:00.000 1234 ERROR nova.api.openstack [req-11111111-1111-4111-8111-111111111111] instance 22222222-2222-4222-8222-222222222222 failed"
      }
    ]
  }'
```

Confirm the parsed document exists and that the request UUID was not copied into
`resource_ids`:

```bash
docker compose exec mongodb mongosh --quiet \
  "mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/$MONGO_INITDB_DATABASE?authSource=admin" \
  --eval 'db.parsed_logs.findOne({request_id:"req-11111111-1111-4111-8111-111111111111"},{_id:0,request_id:1,resource_ids:1,parse_status:1,host:1})'
```

---

## Milestone 6: Incident Detection and Subgraphs

This milestone adds only the incident worker. It consumes successful `parsed_logs`,
detects deterministic incident seeds, traverses existing `event_edges`, and writes
candidate incident subgraphs to `incidents`.

Start the pipeline through incident creation:

```bash
docker compose up -d --build mongodb backend parser-worker correlation-worker incident-worker
```

Check worker health:

```bash
docker compose ps
docker inspect --format='{{json .State.Health}}' rca-copilot-incident-worker
```

Follow incident worker logs:

```bash
docker compose logs -f incident-worker
```

Validate Compose:

```bash
docker compose config
```

Run tests:

```bash
pytest
```

Inspect incidents:

```bash
docker compose exec mongodb mongosh --quiet \
  "mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/$MONGO_INITDB_DATABASE?authSource=admin" \
  --eval 'db.incidents.find({}, {_id:0, incident_id:1, seed_event_id:1, seed_reason:1, event_ids:1, edge_ids:1}).limit(5)'
```

Run tests:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

### Parser configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MONGO_PARSED_LOGS_COLLECTION` | Parsed log collection name | `parsed_logs` |
| `PARSER_VERSION` | Parser version used in the unique upsert key | `parser-v1` |
| `PARSER_BATCH_SIZE` | Raw documents processed per poll | `100` |
| `PARSER_POLL_INTERVAL_SECONDS` | Seconds between polling cycles | `2` |

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MONGO_BIND_HOST` | Host interface for MongoDB port binding | `127.0.0.1` |
| `MONGO_PORT` | Host port for MongoDB | `27017` |
| `MONGO_INITDB_ROOT_USERNAME` | MongoDB root username created on first start | `rca_admin` |
| `MONGO_INITDB_ROOT_PASSWORD` | MongoDB root password created on first start | `change-me` |
| `MONGO_INITDB_DATABASE` | Initial application database | `rca_copilot` |
| `MONGO_URI` | Application connection string for local backend tests/runs | `mongodb://rca_admin:change-me@127.0.0.1:27017/rca_copilot?authSource=admin` |
| `MONGO_DATABASE` | Backend database name | `rca_copilot` |
| `MONGO_RAW_LOGS_COLLECTION` | Raw log collection name | `raw_logs` |
| `MONGO_PARSED_LOGS_COLLECTION` | Parsed log collection name | `parsed_logs` |
| `PARSER_VERSION` | Parser version used in parsed log idempotency key | `parser-v1` |
| `PARSER_BATCH_SIZE` | Parser documents per batch | `100` |
| `PARSER_POLL_INTERVAL_SECONDS` | Parser polling interval | `2` |

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health check |
| `POST` | `/logs/batch` | Store raw journal records in MongoDB |

---

## Example RCA Output

```json
{
  "incident_id": "a3f7c2b1-...",
  "detected_at": "2026-06-01T14:32:00Z",
  "component": "nova-compute",
  "severity": "critical",
  "error_type": "LiveMigrationFailed",
  "causal_chain": ["nova-compute", "neutron", "keystone"],
  "root_cause": "Keystone token expired mid-migration. Neutron failed to
    rebind the port on the destination host because nova-compute's token
    was no longer valid, causing the migration to abort after the instance
    memory was already transferred.",
  "resolution": "Increase token expiry TTL in keystone.conf or implement
    token refresh logic in nova's migration driver.",
  "confidence": 0.91,
  "retrieval_tier_used": 2,
  "sources": ["incident_b2c4...", "doc_neutron_port_binding"],
  "conversation_history": []
}
```

---

## Running the Evaluation

```bash
python -m evaluation.benchmark --ground-truth evaluation/ground_truth.json
```

Output:
```
Hit@1:  0.72
Hit@3:  0.88
Hit@5:  0.94
MRR:    0.81
```

Add queries to `ground_truth.json` as you resolve real incidents to keep the benchmark
representative of your actual environment.

---

## How the TikZ Graph Works

When a sysadmin sends `"show me the graph"` in the chat, the system extracts the causal
chain from the stored RCA and prompts the LLM to fill nodes and edges into a fixed TikZ
template. The template boilerplate is hardcoded — the LLM only fills in the content —
so the output always compiles without errors.

Compile the returned LaTeX with:

```bash
pdflatex incident_graph.tex
```

---

## Contributing

This project is structured so each layer is independently testable. If you are
extending the retrieval layer, you do not need to touch the LLM layer. If you are
adding a new prompt template, everything lives in `llm/prompts.py`.

Before opening a PR, run:

```bash
python -m evaluation.benchmark --ground-truth evaluation/ground_truth.json
```

and confirm Hit@3 does not drop below 0.85 vs the baseline.

---

## Author

Built during an AI/Data Engineering internship at Huawei Cloud Stack, Casablanca.
Supervised by Dr. HIDILA Zineb, EMSI Class of 2026.
