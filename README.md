# OpenStack RCA Copilot

## Overview

RCA Copilot is an OpenStack component for evidence-first root cause analysis.
It follows OpenStack service conventions: Python packages are built with pbr,
configuration is managed by `oslo.config`, logs use `oslo.log`, processes have
systemd units, DevStack installs and supervises the services through a plugin,
and operators access incidents through a Horizon dashboard.

The component collects records from the systemd journal, preserves raw
evidence in MongoDB, derives structured events, correlates related events,
constructs bounded incidents, and enriches each incident with a deterministic
investigation summary. Provider configuration for optional AI integrations is
kept behind the backend API; the evidence pipeline does not depend on an AI
provider being available.

![RCA Copilot presentation title](docs/assets/presentation-title.png)

## Architecture

RCA Copilot is installed as one Python distribution with six console scripts:

| Process | Console script | DevStack service | systemd unit |
|---|---|---|---|
| API backend | `rca-copilot-api` | `rca-api` | `rca-copilot-api.service` |
| journald collector | `rca-copilot-collector` | `rca-collector` | `rca-copilot-collector.service` |
| parser worker | `rca-copilot-parser-worker` | `rca-parser` | `rca-copilot-parser-worker.service` |
| correlation worker | `rca-copilot-correlation-worker` | `rca-correlation` | `rca-copilot-correlation-worker.service` |
| incident worker | `rca-copilot-incident-worker` | `rca-incident` | `rca-copilot-incident-worker.service` |
| enrichment worker | `rca-copilot-enrichment-worker` | `rca-enrichment` | `rca-copilot-enrichment-worker.service` |

All six processes read the same configuration file. Workers communicate
through MongoDB collections rather than direct RPC calls:

```text
OpenStack systemd units
        |
        v
     journald
        |
        v
rca-copilot-collector
        |
        v
rca-copilot-api --> MongoDB raw_logs
                           |
                           v
                 parser-worker --> parsed_logs
                                          |
                                          v
                              correlation-worker --> event_edges
                                                            |
                                                            v
                                                incident-worker --> incidents
                                                                          |
                                                                          v
                                                            enrichment-worker
                                                                          |
                                                                          v
                                                               enriched incidents
```

![Full RCA Copilot process and evidence flow](docs/assets/final-architecture.png)

The DevStack plugin performs package installation, writes
`/etc/rca-copilot/rca-copilot.conf`, registers the `rca` service and its
endpoints in Keystone, installs Horizon enabled-file symlinks, and starts the
six processes with DevStack's `run_process`. A packaged deployment uses the
equivalent units from `systemd/`.

![OpenStack-managed RCA Copilot architecture](docs/assets/overall-architecture.png)

The pipeline preserves source evidence. `raw_logs` is written before parsing;
`parsed_logs` retains lineage to raw records; `event_edges` state correlation
reasons and confidence; incidents are bounded by time, depth, and event count.
Correlation is supporting evidence and is not represented as proof of
causality.

## How to use

### Prerequisites

- DevStack has completed a successful `stack.sh` run.
- The operator can edit `local.conf` and rerun `stack.sh`.
- The `openstack-integration` branch is used. `main` is the original standalone
  baseline and does not contain this OpenStack integration.

### Install with the DevStack plugin

Add the following exact entry under `[[local|localrc]]` in
`/opt/stack/devstack/local.conf`:

```ini
[[local|localrc]]
enable_plugin rca-copilot https://github.com/carteeeltheboss/RCA_copilot.git openstack-integration

RCA_COPILOT_HOST=127.0.0.1
RCA_COPILOT_PORT=8000
```

Then rerun DevStack so the plugin participates in the normal stack phases:

```console
cd /opt/stack/devstack
./stack.sh
```

The plugin enables these services by default:

```text
rca-api rca-collector rca-parser rca-correlation rca-incident rca-enrichment
```

`stack.sh` provisions an authenticated MongoDB 7 container on loopback,
generates persistent deployment secrets, creates the database, collections,
query and TTL indexes, writes `/etc/rca-copilot/rca-copilot.conf` and
`policy.yaml`, and waits for all six services. No `mongosh`, Compose, or
post-stack configuration step is required. `unstack.sh` stops MongoDB and
`clean.sh` removes its container, volume, generated configuration, and
DevStack-only secrets.

### Configuration

The common configuration file is:

```text
/etc/rca-copilot/rca-copilot.conf
```

The DevStack plugin generates it. Optional overrides belong in `local.conf` so
they are reproduced by the next `stack.sh`; packaged deployments may edit it
with the same operational care as other OpenStack service configuration:

```console
sudoedit /etc/rca-copilot/rca-copilot.conf
```

Important groups are:

| Group | Responsibility |
|---|---|
| `[database]` | MongoDB connection, database, and collection names |
| `[api]` | bind address, port, worker count, and internal service token |
| `[collector]` | backend URL, journal units, batching, retry, and cursor state |
| `[parser]` | parser version, batch size, poll interval, and health file |
| `[correlation]` | correlation windows, group limits, version, and health file |
| `[incident]` | traversal bounds, incident window, versions, and health file |
| `[enrichment]` | enrichment version, batching, polling, and health file |
| `[provider]` | encrypted-provider master key, URL allowlists, and timeout |

Every console script accepts `--config-file`. The default is
`/etc/rca-copilot/rca-copilot.conf`. Generate the annotated sample after a
source checkout with:

```console
tox -e genconfig
```

Raw logs, parsed logs, and correlation edges have MongoDB TTL indexes. The
defaults retain each for 30 days; override
`database.raw_logs_retention_days`, `parsed_logs_retention_days`, and
`event_edges_retention_days` in `local.conf` when a different evidence window
is required. `/logs/batch` is capped by record count, body size, message size,
and requests per minute under the `[api]` options.

After changing configuration in DevStack, restart the affected
`devstack@rca-*` units. For a packaged installation, restart the corresponding
`rca-copilot-*` units.

### Manage DevStack services

DevStack's `run_process` creates systemd units named `devstack@<service>`.
Start all six:

```console
sudo systemctl start \
  devstack@rca-api \
  devstack@rca-collector \
  devstack@rca-parser \
  devstack@rca-correlation \
  devstack@rca-incident \
  devstack@rca-enrichment
```

Stop all six:

```console
sudo systemctl stop \
  devstack@rca-collector \
  devstack@rca-enrichment \
  devstack@rca-incident \
  devstack@rca-correlation \
  devstack@rca-parser \
  devstack@rca-api
```

Check all service states:

```console
systemctl is-active \
  devstack@rca-api \
  devstack@rca-collector \
  devstack@rca-parser \
  devstack@rca-correlation \
  devstack@rca-incident \
  devstack@rca-enrichment
```

Inspect one service and its logs:

```console
systemctl status devstack@rca-correlation
journalctl -u devstack@rca-correlation -f
```

The plugin's normal lifecycle is also available through DevStack:

```console
cd /opt/stack/devstack
./unstack.sh
./stack.sh
```

### Backup, retention, and upgrades

Before an upgrade, capture a consistent authenticated dump while the database
is running:

```console
docker exec rca-copilot-mongodb mongodump \
  --username rca_admin --authenticationDatabase admin \
  --archive=/data/db/rca-copilot.archive --db rca_copilot
docker cp rca-copilot-mongodb:/data/db/rca-copilot.archive ./
```

Obtain the generated password from the root-readable DevStack secrets file and
pass it with `--password` without placing it in shell history. Store the dump
off-host and test restores periodically. TTL indexes are the primary retention
control; backups require an independent lifecycle matching the site's policy.

For upgrades, back up first, review release notes and configuration changes,
update the plugin checkout/branch, then run `stack.sh`. The startup initializer
applies additive collections and indexes idempotently. Restore with
`mongorestore --drop` only during a planned outage, then restart all six RCA
services and verify `/health` and `/api/v1/system/health`.

### Verify a correlated incident

`validation/scripts/inject_correlated_incident.py` submits a Nova → Neutron →
Placement sequence with one request ID and resource ID. It waits for the live
pipeline and fails unless the resulting incident graph has at least three
connected nodes:

```console
python validation/scripts/inject_correlated_incident.py \
  --backend http://127.0.0.1:8000
```

### Manage packaged systemd services

For a non-DevStack OpenStack deployment, install the package, configuration,
service account, state directory, and units according to the distribution's
packaging policy. The repository units expect an `rca-copilot` user and the
shared configuration file under `/etc/rca-copilot/`.

Start or enable all packaged services:

```console
sudo systemctl enable --now \
  rca-copilot-api \
  rca-copilot-collector \
  rca-copilot-parser-worker \
  rca-copilot-correlation-worker \
  rca-copilot-incident-worker \
  rca-copilot-enrichment-worker
```

Stop them:

```console
sudo systemctl stop \
  rca-copilot-collector \
  rca-copilot-enrichment-worker \
  rca-copilot-incident-worker \
  rca-copilot-correlation-worker \
  rca-copilot-parser-worker \
  rca-copilot-api
```

Check their status:

```console
systemctl status \
  rca-copilot-api \
  rca-copilot-collector \
  rca-copilot-parser-worker \
  rca-copilot-correlation-worker \
  rca-copilot-incident-worker \
  rca-copilot-enrichment-worker
```

### Verify the deployment

Verify the API directly:

```console
curl --fail --silent --show-error http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Verify Keystone registration using the DevStack system-admin cloud:

```console
openstack --os-cloud devstack-system-admin service show rca
openstack --os-cloud devstack-system-admin endpoint list --service rca
```

The endpoint list must contain public, internal, and admin interfaces. With
the defaults, each URL is `http://127.0.0.1:8000`.

Open Horizon and select **RCA Copilot** from the dashboard navigation. The
overview is served at `/rca_copilot/`; the incident list is at
`/rca_copilot/incidents/`. The dashboard contains Overview, Incidents,
Investigation, System Health, and Settings panels.

### Docker Compose standalone alternative

Docker Compose is retained for development or evaluation outside an
OpenStack-integrated deployment. It is not the primary OpenStack installation
path and does not register a Keystone service or install the Horizon plugin.

Review and edit `etc/rca-copilot.docker.conf`, especially the MongoDB
credentials and provider settings, then run:

```console
docker compose up --build -d
docker compose ps
curl --fail --silent --show-error http://127.0.0.1:8000/health
```

Stop the standalone deployment with:

```console
docker compose down
```

The Compose deployment uses the same pbr package, console scripts, and
`oslo.config` option model as the OpenStack-integrated deployment.

## Provider framework

The backend supports `ollama`, `openai_compatible`, `gemini`, `anthropic`, and
`custom_http` providers, plus the existing vector-store placeholder. Provider
secrets are encrypted, provider URLs are validated against SSRF controls, and
configuration follows draft, test, activate, and rollback lifecycle rules.
Provider administration is exposed under `/api/v1/providers` and remains
independent of deterministic ingestion and analysis.

## Repository layout

```text
backend/                 FastAPI API and provider framework
collector/               journald collector
parser_worker/           raw-log parser
correlation_worker/      event correlation
incident_worker/         bounded incident construction
enrichment_worker/       deterministic incident enrichment
rca_copilot/             shared configuration and command initialization
devstack/                DevStack plugin and settings
horizon_plugin/          Horizon dashboard package and enabled files
systemd/                 packaged service units
etc/                     sample configuration and enforced RBAC policy
releasenotes/            reno release notes
latex/                   project presentation
docker-compose.yml       standalone alternative
```

## Development

Create a Python 3.11 environment, install tox, and run the OpenStack-style
checks:

```console
python3.11 -m venv .venv
.venv/bin/python -m pip install tox
.venv/bin/tox -e py311
.venv/bin/tox -e pep8
```

Run the existing pytest suite directly when iterating locally:

```console
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/pytest
```

Additional environments include `genconfig` and `releasenotes`:

```console
.venv/bin/tox -e genconfig,releasenotes
```

## Contribution

See [CONTRIBUTING.rst](CONTRIBUTING.rst) for the development workflow,
testing expectations, release-note policy, and contribution sign-off.

## License

The repository is licensed under the MIT License. See [LICENSE](LICENSE).
