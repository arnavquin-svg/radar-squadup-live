# API and browser-based registration service.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production \
    RADAR_DB_PATH=/data/radar.db

WORKDIR /srv
RUN useradd --create-home --uid 10001 radar && mkdir -p /data && chown radar:radar /data

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY web ./web

USER radar
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1

# Behind a reverse proxy, also set FORWARDED_ALLOW_IPS to the proxy's address and TRUST_PROXY=true.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-server-header"]
