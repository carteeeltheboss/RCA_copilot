FROM python:3.12.4-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
COPY backend/requirements-test.txt ./backend/requirements-test.txt
RUN pip install --no-cache-dir --default-timeout=120 -r requirements.txt -r backend/requirements-test.txt

COPY backend ./backend

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
