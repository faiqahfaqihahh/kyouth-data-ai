import os

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="AI Chat Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

_PDF_CHAR_LIMIT = 8_000


class ChatRequest(BaseModel):
    message: str
    pdf_text: str = ""


class ChatResponse(BaseModel):
    response: str


def build_system_prompt(pdf_text: str) -> str:
    base = "You are a helpful AI assistant. Be concise and clear."
    if pdf_text.strip():
        return (
            base
            + "\n\nThe user has provided the following document for context:\n"
            + "--- DOCUMENT START ---\n"
            + pdf_text[:_PDF_CHAR_LIMIT]
            + "\n--- DOCUMENT END ---"
        )
    return base


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=build_system_prompt(req.pdf_text),
            messages=[{"role": "user", "content": req.message}],
        )
        reply: str = message.content[0].text  # type: ignore[union-attr]
        return ChatResponse(response=reply)
    except anthropic.AuthenticationError as exc:
        raise HTTPException(
            status_code=401, detail="Invalid Anthropic API key."
        ) from exc
    except anthropic.RateLimitError as exc:
        raise HTTPException(
            status_code=429, detail="Rate limit reached. Try again shortly."
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
