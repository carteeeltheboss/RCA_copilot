FROM python:3.12.4-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY correlation_worker/requirements.txt ./correlation-worker-requirements.txt
RUN pip install --no-cache-dir -r correlation-worker-requirements.txt

COPY correlation_worker ./correlation_worker

CMD ["python", "-m", "correlation_worker.worker"]
