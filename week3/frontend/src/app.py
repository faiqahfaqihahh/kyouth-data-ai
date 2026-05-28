import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

app = FastAPI() # [cite: 24]

# Point Jinja2 to your templates directory
templates = Jinja2Templates(directory="src/templates")

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    # Pass the context explicitly as a separate parameter 
    # to maintain strict compatibility with Python 3.14 string hashing
    return templates.TemplateResponse(
        request=request,
        name="chat_page.html",
        context={"backend_url": "http://localhost:8000"}
    )
