FROM python:3.14.4-bookworm

# Install uv globally inside the container
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files first to leverage Docker caching
COPY pyproject.toml uv.lock ./

# Install dependencies strictly using the lockfile
RUN uv sync --frozen --no-dev

# Copy the rest of the application source code
COPY . .

# Set up PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["uv", "run" "uvicorn"]
CMD ["uvicorn", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "app:app"]