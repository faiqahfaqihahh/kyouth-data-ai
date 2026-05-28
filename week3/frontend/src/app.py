import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

# Initialize tracking environment configuration
load_dotenv()

app = FastAPI()

# Fallback defaults to local docker container networking domain if not explicitly provided
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8001")

templates = Jinja2Templates(directory="src/templates")

@app.get("/", response_class=HTMLResponse)
def landing_page(request: Request):
    """Landing page explaining the AI pipeline."""
    return templates.TemplateResponse(
        request=request,
        name="landing.html"
    )

@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request):
    """Main chat application interface."""
    return templates.TemplateResponse(
        request=request,
        name="chat_page.html",
        context={"backend_url": BACKEND_URL}
    )
