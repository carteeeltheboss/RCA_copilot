FROM python:3.12.4-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY enrichment_worker/requirements.txt ./enrichment-worker-requirements.txt
COPY enrichment_worker/requirements-test.txt ./enrichment-worker-requirements-test.txt
RUN pip install --no-cache-dir -r enrichment-worker-requirements.txt -r enrichment-worker-requirements-test.txt

COPY correlation_worker ./correlation_worker
COPY enrichment_worker ./enrichment_worker

CMD ["python", "-m", "enrichment_worker.worker"]
