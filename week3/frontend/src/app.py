import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="src/templates")

BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8001")


@app.get("/", response_class=HTMLResponse)
async def chat_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "chat_page.html",
        {"request": request, "backend_url": BACKEND_URL},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
