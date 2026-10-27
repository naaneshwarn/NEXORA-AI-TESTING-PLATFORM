# NEXORA FastAPI backend image.
#
# Build context is the repository root (see docker-compose.yml):
#   docker build -f backend/Dockerfile .
FROM python:3.12-slim

# Never write .pyc files and never buffer stdout — logs must be visible
# through `docker logs` immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first so the layer is cached across code changes.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# The app package must sit directly under /app so `app.main:app` resolves.
COPY backend/app ./app

# Persist the durable core-store snapshot outside the container layer so
# `docker compose restart` keeps agents, runs, leads and reports.
ENV NEXORA_STATE_DIR=/data/state
RUN mkdir -p /data/state && chown -R nobody:nogroup /data/state

USER nobody

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
