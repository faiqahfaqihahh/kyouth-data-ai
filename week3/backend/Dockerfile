FROM python:3.14.4-bookworm

# Import uv dependency engine mirror
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy project config
COPY pyproject.toml ./

# Install dependencies and generate lock file
RUN uv sync

# Transfer source directory files
COPY . .

ENTRYPOINT ["uv", "run", "uvicorn"]
CMD ["--app-dir", "src", "--host", "0.0.0.0", "--port", "8001", "app:app"]