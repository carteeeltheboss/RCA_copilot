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
- MongoDB is reachable from the host. RCA Copilot does not install MongoDB as
  part of the DevStack plugin.
- The operator can edit `local.conf` and rerun `stack.sh`.
- The `openstack-integration` branch is used. `main` is the original standalone
  baseline and does not contain this OpenStack integration.

### Install with the DevStack plugin

Add the following exact entry under `[[local|localrc]]` in
`/opt/stack/devstack/local.conf`:

```ini
[[local|localrc]]
enable_plugin rca-copilot https://github.com/carteeeltheboss/RCA_copilot.git openstack-integration

RCA_COPILOT_MONGO_URI=mongodb://rca_admin:change-me@127.0.0.1:27017/rca_copilot?authSource=admin
RCA_COPILOT_MONGO_DATABASE=rca_copilot
RCA_COPILOT_HOST=127.0.0.1
RCA_COPILOT_PORT=8000
```

Use a deployment-specific MongoDB account instead of the example password.
Then rerun DevStack so the plugin participates in the normal stack phases:

```console
cd /opt/stack/devstack
./stack.sh
```

The plugin enables these services by default:

```text
rca-api rca-collector rca-parser rca-correlation rca-incident rca-enrichment
```

### Configuration

The common configuration file is:

```text
/etc/rca-copilot/rca-copilot.conf
```

Edit it with the same operational care as other OpenStack service
configuration:

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
etc/                     sample configuration and policy stub
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
