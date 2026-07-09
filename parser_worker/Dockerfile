FROM python:3.12.4-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY parser_worker/requirements.txt ./parser-worker-requirements.txt
COPY parser_worker/requirements-test.txt ./parser-worker-requirements-test.txt
RUN pip install --no-cache-dir -r parser-worker-requirements.txt -r parser-worker-requirements-test.txt

COPY parser_worker ./parser_worker

CMD ["python", "-m", "parser_worker.worker"]
