# =============================================================================
# SD LMS - Dockerfile
# Multi-stage build for Django application
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Base Python image
# -----------------------------------------------------------------------------
FROM python:3.12.1-slim as python-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

# -----------------------------------------------------------------------------
# Stage 2: Builder
# -----------------------------------------------------------------------------
FROM python-base as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    pkg-config \
    libcairo2-dev \
    libglib2.0-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements/base.txt requirements/base.txt
COPY requirements/production.txt requirements/production.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements/production.txt

# -----------------------------------------------------------------------------
# Stage 3: Development
# -----------------------------------------------------------------------------
FROM python-base as development

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    postgresql-client \
    gettext \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install development dependencies
# Need base.txt because local.txt has `-r base.txt`
COPY requirements/base.txt requirements/base.txt
COPY requirements/local.txt requirements/local.txt
RUN pip install -r requirements/local.txt

# Create non-root user
RUN useradd -m -u 1000 appuser
USER appuser

WORKDIR /app

# Expose port
EXPOSE 8000

# Default command
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# -----------------------------------------------------------------------------
# Stage 4: Production
# -----------------------------------------------------------------------------
FROM python-base as production

# Install runtime dependencies
# weasyprint deps: pango, cairo, gdk-pixbuf, shared-mime-info
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libcairo2 \
    libcairo-gobject2 \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    gettext \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Cache-bust del layer de código (SD#140): con --cache-from :latest, un COPY
# sin nada que cambie entre líneas puede reusar la capa vieja aunque el
# contenido real del repo haya cambiado -- deploy "verde" con código stale
# (imagen no trae el commit que dice traer). Este ARG/RUN garantiza cache-miss
# en cada SHA distinto, justo antes del COPY, sin perder el cache de apt/pip
# de arriba (ver memoria feedback_deploy_buildkit_cache_stale_gitsha).
ARG GIT_SHA=dev
RUN echo "code build ${GIT_SHA}"

# Copy application code
COPY --chown=appuser:appuser . .

# Collect static files (using base settings to avoid external dependencies)
ENV SECRET_KEY="build-time-secret-key"
RUN python manage.py collectstatic --noinput --settings=config.settings.base

# Switch to non-root user
USER appuser

# Expose port (Cloud Run uses 8080)
EXPOSE 8080

# Run with gunicorn (Cloud Run uses PORT env var)
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 2 --threads 2 config.wsgi:application"]
