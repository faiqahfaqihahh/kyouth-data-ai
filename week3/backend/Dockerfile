FROM python:3.14.4-bookworm

# Pin uv to the exact required version (0.8.*)
COPY --from=ghcr.io/astral-sh/uv:0.8.24 /uv /usr/local/bin/uv

WORKDIR /app

# Copy manifest and lock file first for layer caching
COPY pyproject.toml uv.lock ./

# Install exact pinned dependencies from the lock file
RUN uv sync --frozen --no-dev --system

# Copy application source
COPY src/ ./src/

EXPOSE 8001

ENTRYPOINT ["uv", "run", "--system", "uvicorn"]
CMD ["--app-dir", "src", "--host", "0.0.0.0", "--port", "8001", "app:app"]
