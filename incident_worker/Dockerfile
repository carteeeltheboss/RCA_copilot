FROM python:3.12.4-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY incident_worker/requirements.txt ./incident-worker-requirements.txt
COPY incident_worker/requirements-test.txt ./incident-worker-requirements-test.txt
RUN pip install --no-cache-dir -r incident-worker-requirements.txt -r incident-worker-requirements-test.txt

COPY correlation_worker ./correlation_worker
COPY incident_worker ./incident_worker

CMD ["python", "-m", "incident_worker.worker"]
