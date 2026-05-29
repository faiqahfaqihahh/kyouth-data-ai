# Week 3 : System Integration & Application

A containerised, full-stack chat application built with **FastAPI**, **Jinja2**, **Uvicorn**, and the **Anthropic Claude API**. The system is split into two independent services orchestrated by Docker Compose.

---

## Project Overview

The goal is to build and containerise a full-stack chat application following a microservices architecture.

| Service      | Role                                                        | Port   |
|--------------|-------------------------------------------------------------|--------|
| **frontend** | Serves the chat UI (HTML + JS) via FastAPI / Jinja2         | `8000` |
| **backend**  | Exposes `POST /chat`; calls the Anthropic Claude API        | `8001` |

Users interact through the browser. The frontend sends user messages (and optional PDF text) to the backend, which queries Claude and returns the reply.

---

## Prerequisites

| Tool            | Required version |
|-----------------|-----------------|
| Docker          | ≥ 24            |
| Docker Compose  | ≥ 2 (bundled with Docker Desktop) |
| uv              | 0.8.*           |
| Python          | 3.14.4          |
| ruff            | 0.15.*          |

---

## Setup Instructions

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd week_3
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your Google Gemini API key:

```env
Google Gemini-ant-...
```

> **Never commit `.env` to version control.** It is listed in `.gitignore`.

### 3. (Optional) Install dependencies locally

Each service manages its own environment. From the service folder:

```bash
# Linux / macOS
cd frontend
uv sync

# Windows (PowerShell)
cd frontend
uv sync
```

`uv` reads `.python-version` (3.14.4) and `uv.lock` to reproduce the exact environment on any platform.

---

## Usage

### Start with Docker Compose

```bash
docker compose up --build
```

Open your browser at **http://localhost:8000**.

To stop all services:

```bash
docker compose down
```

### Running a single service manually (cross-platform)

```bash
# From the frontend/ directory
uv run uvicorn --app-dir src --host 0.0.0.0 --port 8000 app:app

# From the backend/ directory
uv run uvicorn --app-dir src --host 0.0.0.0 --port 8001 app:app
```

`uv run` works identically on Linux, macOS, and Windows — no shell-specific scripts are used.

### Expected inputs / outputs

| Input | Expected output |
|-------|-----------------|
| Type a message, press Enter | Reply bubble appears below |
| Attach a PDF then send a message | Claude answers in context of the PDF |
| Empty message | Nothing sent (input blocked in the UI) |

---

## API / Function Reference

### Backend — `POST /chat`

**URL**: `http://localhost:8001/chat`

**Request body (JSON)**:

```json
{
  "message": "What is FastAPI?",
  "pdf_text": ""
}
```

`pdf_text` is optional. When provided it is prepended to the system prompt (truncated at 8 000 chars).

**Response body (JSON)**:

```json
{
  "response": "FastAPI is a modern, fast web framework..."
}
```

**Error responses**:

| HTTP status | Meaning |
|-------------|---------|
| 400 | Empty `message` field |
| 401 | Invalid or missing `ANTHROPIC_API_KEY` |
| 429 | Anthropic rate limit reached |
| 500 | Unexpected server error |

### Backend — `GET /health`

Returns `{"status": "ok"}`. Used by Docker Compose's health-check to gate frontend startup.

### Frontend — `GET /`

Renders `chat_page.html` via Jinja2, injecting `BACKEND_URL` so the JavaScript knows where to POST.

### Key JavaScript functions (`chat_page.html`)

| Function | Purpose |
|----------|---------|
| `sendMessage()` | Reads textarea, POSTs to `/chat`, renders reply or error bubble |
| `addMessage(role, text)` | Creates a styled message bubble and appends it |
| `addTypingIndicator()` | Animated dots shown while awaiting the backend |
| `extractPdfText(file)` | Reads an uploaded PDF as text for context |

### Service-to-service communication

```
Browser  ──GET /──►  frontend:8000  (Jinja2 renders HTML)
Browser  ──POST /chat──►  backend:8001  (JSON API called directly from JS)
```

Inside the Docker network `app-net`, the frontend's `BACKEND_URL` resolves to `http://backend:8001` via Docker's internal DNS. On the host, port `8001` is also forwarded so `curl` tests work directly.

---

## Data / Assumptions

### Message JSON shape

```json
{ "message": "<user text>", "pdf_text": "<optional plain text from PDF>" }
```

### Assumptions

- PDFs are read as plain text by the browser's `FileReader`. Scanned/image-only PDFs will send garbled or empty text; a production system would use `pdfplumber` or a similar library on the backend.
- PDF text is hard-truncated at **8 000 characters** on the backend before being passed to Claude.
- The application is **stateless** — each request is a single-turn call; conversation history is not maintained between messages.
- `ANTHROPIC_API_KEY` must be set before starting the backend; the service starts regardless but every `/chat` call returns HTTP 401 if the key is absent or invalid.

### Data flow

```
User types message
  → JS collects message + PDF text (if any)
  → POST /chat { message, pdf_text }  →  backend:8001
  → backend builds system prompt (with optional PDF context)
  → Anthropic Claude API called (claude-sonnet-4-20250514, max_tokens=1024)
  → { response }  ←  backend
  → JS renders reply bubble in the browser
```

---

## Testing

### Frontend tests (manual)

| Test | Steps | Expected result |
|------|-------|----------------|
| Send a message | Type text, press Enter | Reply bubble appears |
| Shift+Enter newline | Press Shift+Enter | New line in textarea (no send) |
| Attach PDF | Click "Attach PDF", choose file | Filename shown; text sent with next message |
| Remove PDF | Click "✕ remove" | File cleared; no PDF context in subsequent messages |
| Backend unreachable | Stop backend, send message | Error bubble: "Could not reach backend" |
| Empty send | Press Enter with blank input | Nothing happens |

### Backend tests (curl — works on Linux, macOS, Windows with Git Bash or WSL)

```bash
# Health check
curl http://localhost:8001/health

# Normal chat
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"What is 2+2?\", \"pdf_text\": \"\"}"

# Empty message → 400
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"\", \"pdf_text\": \"\"}"
```

### Verifying inter-service networking inside Docker

```bash
docker exec week3_frontend python -c \
  "import urllib.request; print(urllib.request.urlopen('http://backend:8001/health').read())"
```

Expected output: `b'{"status":"ok"}'`

---

## Limitations

- **No conversation history**: every message is a fresh single-turn call; Claude has no memory of previous turns in the same chat session.
- **No authentication**: all endpoints are open to any client with network access.
- **Naive PDF handling**: text is extracted in the browser; scanned PDFs produce no useful text.
- **No streaming**: the entire Claude response is buffered before display — long replies feel slow.
- **No persistent storage**: chat history is lost on page refresh.
- **PDF size cap**: text is truncated at 8 000 chars; proper RAG / chunking would be needed for long documents.
- **Single model hard-coded**: `claude-sonnet-4-20250514` is fixed in `backend/src/app.py`.

---

## Architecture Reflection

### Design Choices

The project deliberately separates the **frontend** and **backend** into two independent containers, following a microservices pattern. Each service has a single responsibility, can be deployed or scaled independently, and fails in isolation without taking down the other.

**FastAPI** was chosen for both services because it is fast to prototype with, natively async, and generates interactive OpenAPI docs automatically at `/docs` — useful for manual backend testing.

**Jinja2** server-side rendering keeps the frontend dependency footprint minimal: no Node.js build step, no bundler, no framework — just Python and HTML. The trade-off is a less reactive UI compared to a SPA framework.

**Docker Compose** provides straightforward local orchestration. The `depends_on: condition: service_healthy` directive ensures the frontend only starts once the backend health-check passes, preventing race-condition startup failures.

### Trade-offs

| Prioritised | Traded off |
|-------------|------------|
| Ease of local setup (single `docker compose up`) | Performance (no async streaming, no connection pooling) |
| Minimal dependencies (no Node.js, no DB) | Feature richness (no history, no auth) |
| Platform independence (uv, pure Python scripts) | Native tooling shortcuts (no shell scripts, no Makefile) |
| Exact version pinning (`uv.lock`, `pyproject.toml`) | Automatic security updates |

### Improvements

Given more time, the following would be prioritised:

1. **Streaming responses** — use Claude's streaming API with Server-Sent Events so the reply appears token-by-token.
2. **Conversation history** — pass prior turns in the `messages` array so Claude has session context.
3. **Proper PDF extraction** — use `pdfplumber` on the backend with per-page chunking for reliable text extraction from all PDF types.
4. **Database persistence** — store chat sessions in SQLite or PostgreSQL to survive page refreshes.
5. **Authentication** — add JWT or session-based auth to isolate each user's conversations.
6. **Cloud deployment** — publish images to Docker Hub and deploy via Railway or Fly.io using the existing Dockerfiles.
