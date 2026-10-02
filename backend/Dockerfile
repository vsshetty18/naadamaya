# NAADAMAYA backend image.
# The same image runs the API server and the Celery analysis worker;
# docker-compose.yml chooses which command to run.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System packages:
#   ffmpeg          decoding, validating and converting uploaded audio
#   libsndfile1     used by soundfile / librosa
#   libpq5          PostgreSQL client library used by psycopg
#   curl            used by the container health check
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first so Docker can cache this layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Application code.
COPY . .

# Run as a non-root user. Uploaded audio lives in /data/uploads, outside the code.
RUN useradd --create-home --uid 1000 naadamaya \
    && mkdir -p /data/uploads \
    && chown -R naadamaya:naadamaya /app /data

USER naadamaya

EXPOSE 8000

# Numba (used by librosa) needs a writable cache directory.
ENV NUMBA_CACHE_DIR=/tmp/numba_cache

# Default command: the API server. The worker overrides this in docker-compose.yml.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
