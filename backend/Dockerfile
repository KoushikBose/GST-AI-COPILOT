FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System dependencies:
# - libpq-dev/gcc: build asyncpg/psycopg
# - tesseract-ocr: default OCR engine
# - libgl1: required by some PDF/image libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    libgl1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
# setuptools' packages.find (include = ["app*"]) needs the package directory
# to exist on disk at install time, or the editable install registers no
# package at all — a placeholder here lets it discover "app" before the real
# source is copied in below, which then overwrites the placeholder.
RUN mkdir -p app && touch app/__init__.py \
    && pip install --upgrade pip && pip install -e ".[dev]"

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=10 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
