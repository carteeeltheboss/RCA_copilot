# RCA Copilot Horizon Plugin

Horizon plugin for the local RCA Copilot pipeline. The browser talks only to Horizon. Horizon server-side views call the RCA FastAPI backend with `RCA_INTERNAL_SERVICE_TOKEN`.

## Install

```bash
cd /opt/stack/RCA_copilot/horizon_plugin
/opt/stack/data/venv/bin/pip install -e .
for file in /opt/stack/RCA_copilot/horizon_plugin/rca_copilot_horizon/enabled/_90*.py; do
  ln -sf "$file" "/opt/stack/horizon/openstack_dashboard/local/enabled/$(basename "$file")"
done
cd /opt/stack/horizon
/opt/stack/data/venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart apache2
```

Set these in Apache/Horizon environment before restart:

```bash
RCA_BACKEND_URL=http://127.0.0.1:8000
RCA_INTERNAL_SERVICE_TOKEN=<same token as backend>
```

## Uninstall

```bash
rm -f /opt/stack/horizon/openstack_dashboard/local/enabled/_90*_rca_*.py /opt/stack/horizon/openstack_dashboard/local/enabled/_9000_rca_copilot.py
/opt/stack/data/venv/bin/pip uninstall -y rca-copilot-horizon
sudo systemctl restart apache2
```

## Development

```bash
cd /opt/stack/RCA_copilot/horizon_plugin
/opt/stack/data/venv/bin/pip install -e .
cd /opt/stack/horizon
/opt/stack/data/venv/bin/python manage.py check
```

## Troubleshooting

- If pages show "backend unavailable", verify `RCA_BACKEND_URL`, `RCA_INTERNAL_SERVICE_TOKEN`, and `docker compose ps`.
- If static styling is missing, rerun `collectstatic`.
- If Settings returns permission denied, log in as a Horizon administrator.
- Provider URLs are tested only by the backend; failed tests do not affect ingestion or workers.
