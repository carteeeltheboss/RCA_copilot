FROM python:3.12.4-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PBR_VERSION=0.1.0

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir --default-timeout=120 .

EXPOSE 8000

CMD ["rca-copilot-api", "--config-file", "/etc/rca-copilot/rca-copilot.conf"]
