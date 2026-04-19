# ─────────────────────────────────────────────────────────────
# Bambusleitung – Dockerfile
# iperf3 Speedtest Scheduler mit Flask Web-UI
# ─────────────────────────────────────────────────────────────

# Build stage: Dependencies installieren
FROM python:3.12-slim AS builder

WORKDIR /build

# System-Dependencies für Builds
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python-Abhängigkeiten in einem Virtual Environment installieren
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─────────────────────────────────────────────────────────────
# Runtime stage
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Bambusleitung"
LABEL org.opencontainers.image.description="iperf3 Speedtest Scheduler mit Web-UI"
LABEL org.opencontainers.image.source="https://github.com/${GITHUB_REPOSITORY}"
LABEL org.opencontainers.image.licenses="MIT"

# iperf3 installieren
RUN apt-get update && apt-get install -y --no-install-recommends \
    iperf3 \
    && rm -rf /var/lib/apt/lists/*

# Python-Pakete (Virtual Environment) aus dem Builder kopieren
COPY --from=builder /opt/venv /opt/venv

# App-Code kopieren
WORKDIR /app
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Data-Volume vorbereiten
RUN mkdir -p /data

# Umgebungsvariablen (iperf3-Config kann per docker-compose oder -e überschrieben werden)
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_ENV=production \
    DATA_DIR=/data \
    PORT=5000 \
    IPERF_TARGET_IP="" \
    IPERF_TARGET_PORT=5201 \
    IPERF_INTERVAL_MINUTES=15 \
    IPERF_TEST_DURATION=10 \
    IPERF_ENABLED=false \
    IPERF_EXTRA_PARAMS="" \
    UI_PASSWORD="" \
    SECRET_KEY=""



EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/status')" || exit 1

CMD ["python", "backend/app.py"]
