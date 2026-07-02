FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y redis-server

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app /app

CMD redis-server --daemonize yes \
    --maxmemory 200mb \
    --maxmemory-policy allkeys-lru \
    --appendonly yes \
    --appendfsync everysec && \
    uvicorn main:app --host 0.0.0.0 --port ${PORT:-7201}