# =============================================================================
# Stage 1 — Builder
# Installs all project dependencies using pip.
# =============================================================================
FROM python:3.13 AS builder

WORKDIR /build

# Install build dependencies
RUN pip install --no-cache-dir setuptools wheel

# Copy only the dependency metadata first to leverage Docker cache.
COPY pyproject.toml .
# Create a minimal package structure so setuptools can resolve ``where = ["app"]``.
RUN mkdir -p /build/app && touch /build/app/__init__.py
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

# =============================================================================
# Stage 2 — Runtime
# Minimal Python 3.13-slim image with only the runtime dependencies.
# =============================================================================
FROM python:3.13-slim AS runtime

WORKDIR /app

# Create a non-root user for security.
RUN groupadd -r trace && useradd -r -g trace trace

# Copy pre-built wheels from the builder stage.
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels activia-trace && \
    rm -rf /wheels

# Copy application code.
COPY app/ /app/app/
COPY alembic.ini alembic/ /app/

# Switch to non-root user.
USER trace

EXPOSE 8000

# Default command: start the FastAPI app with uvicorn.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
