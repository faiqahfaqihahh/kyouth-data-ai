FROM python:3.14.4-bookworm

# Install uv globally inside the container
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency structures
COPY pyproject.toml ./

# Install dependencies and update lock file
RUN uv sync

# Copy source maps
COPY . .

ENTRYPOINT ["uv", "run", "uvicorn"]
# Note: Backend runs internally on Port 8001 to prevent conflicts with frontend on 8000
CMD ["--app-dir", "src", "--host", "0.0.0.0", "--port", "8001", "app:app"]