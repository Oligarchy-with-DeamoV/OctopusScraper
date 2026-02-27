# ============================================================
# Stage 1: Build — install Poetry and project dependencies
# ============================================================
FROM python:3.10-slim AS builder

RUN pip install --no-cache-dir poetry

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

# Copy dependency manifests first for better layer caching.
# Changes to source code won't invalidate the dependency layer.
COPY pyproject.toml poetry.lock README.md ./
COPY resources/ ./resources/

# Install production dependencies only, then remove the cache
RUN poetry install --without dev --no-root && rm -rf "$POETRY_CACHE_DIR"

# Copy the application source code
COPY src/ ./src/

# Install the project itself (root package)
RUN poetry install --without dev && rm -rf "$POETRY_CACHE_DIR"

# ============================================================
# Stage 2: Runtime — minimal image with only what's needed
# ============================================================
FROM python:3.10-slim AS runtime

# Install minimal runtime dependencies (lxml, etc. may need these)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only the virtual environment and source code from the builder
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/src ./src

# Activate the virtual environment via PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Use the installed script directly — Poetry is NOT in this image
ENTRYPOINT ["octopus_service", "--host", "0.0.0.0", "--port", "8000"]