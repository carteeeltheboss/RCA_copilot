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
├── docker-compose.yml          # spin up everything: mongo, chroma, ollama, api
├── .env.example                # copy to .env and fill in your values
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

## Getting Started

### Prerequisites

- Docker + Docker Compose
- Ollama installed locally with `deepseek-r1:8b` pulled
- A running OpenStack deployment with Prometheus + Alertmanager configured
- Python 3.11+

### 1. Clone and configure

```bash
git clone https://github.com/yourname/openstack-rca-copilot
cd openstack-rca-copilot
cp .env.example .env
# edit .env with your OpenStack log paths and Ollama endpoint
```

### 2. Start the stack

```bash
docker-compose up -d
```

This starts MongoDB, ChromaDB, and the FastAPI service. Ollama runs separately on the host.

### 3. Point it at your logs

In `.env`, set the paths to your OpenStack log files:

```env
OPENSTACK_LOG_PATHS=/var/log/nova/nova-compute.log,/var/log/neutron/server.log
LOG_WATCH_INTERVAL_SECONDS=5
```

### 4. Configure Alertmanager

Add this receiver to your `alertmanager.yml`:

```yaml
receivers:
  - name: rca-copilot
    webhook_configs:
      - url: http://localhost:8000/webhook/alert
```

### 5. Verify it's running

```bash
curl http://localhost:8000/incidents
# returns [] on a fresh install, populates as incidents are detected
```

### 6. Build the knowledge base

Drop any existing OpenStack incident reports, resolved bug notes, or log files into
`knowledge_base/` and run the ingestion script:

```bash
python -m ingestion.bootstrap --path knowledge_base/
```

This parses, structures, and indexes everything into MongoDB + ChromaDB so the system
has prior knowledge before it ever sees a live incident.

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MONGO_URI` | MongoDB connection string | `mongodb://localhost:27017` |
| `CHROMA_HOST` | ChromaDB host | `localhost` |
| `CHROMA_PORT` | ChromaDB port | `8001` |
| `OLLAMA_BASE_URL` | Ollama API base URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Model name to use | `deepseek-r1:8b` |
| `OPENSTACK_LOG_PATHS` | Comma-separated log file paths | required |
| `LOG_WATCH_INTERVAL_SECONDS` | Polling interval | `5` |
| `TIER1_CONFIDENCE_THRESHOLD` | Min score to stop at Tier 1 | `0.85` |
| `TIER2_CONFIDENCE_THRESHOLD` | Min score to stop at Tier 2 | `0.70` |
| `INCIDENT_WINDOW_MINUTES` | Look-back window for grouping | `30` |
| `MLFLOW_TRACKING_URI` | MLflow server URI | `http://localhost:5000` |

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/webhook/alert` | Alertmanager webhook entry point |
| `GET` | `/incidents` | List all incidents, filterable by component/severity |
| `GET` | `/incidents/{id}` | Full incident detail + RCA |
| `POST` | `/incidents/{id}/chat` | Send a follow-up message, get a grounded reply |
| `GET` | `/incidents/{id}/graph` | Returns compilable TikZ LaTeX causal diagram |
| `GET` | `/health` | Service health check |

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
