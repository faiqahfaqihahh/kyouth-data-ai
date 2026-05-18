"""
prompt_model.py

Calls either a local Ollama model or a Google Gemini model depending on the
model name provided.  Ollama models: llama3.1, phi3, deepseek-r1:1.5b
Gemini models : gemini-2.5-flash, gemini-2.5-flash-lite, gemini-3-flash-preview

Usage:
    uv run prompt_model.py <model> "<prompt>"
Example:
    uv run prompt_model.py llama3.1 "tell me one malaysian joke"
    uv run prompt_model.py gemini-2.5-flash "tell me one malaysian joke"
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()  # reads .env for GOOGLE_API_KEY

# ── model routing ────────────────────────────────────────────────────────────
OLLAMA_MODELS = {"llama3.1", "phi3", "deepseek-r1:1.5b"}
GEMINI_MODELS  = {
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
}


def _call_ollama(model: str, prompt: str) -> str:
    """Send a prompt to a locally running Ollama model via HTTP and return the response text.
    Uses /api/generate which works reliably across all Ollama versions.
    """
    try:
        import requests
        response = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=300,
        )
        response.raise_for_status()
        return response.json()["response"]
    except Exception as e:
        return f"[Ollama Error] {e}"


def _call_gemini(model: str, prompt: str) -> str:
    """Send a prompt to a Google Gemini model and return the response text."""
    try:
        from google import genai
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return "[Gemini Error] GOOGLE_API_KEY not set in environment / .env file"
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"[Gemini Error] {e}"


def prompt_model(model: str, prompt: str) -> str:
    """
    Prompt an AI model and return its text response.

    Parameters
    ----------
    model  : str  - model name, e.g. "llama3.1" or "gemini-2.5-flash"
    prompt : str  - the text prompt to send

    Returns
    -------
    str  - the model's response, or an error message string (never raises)
    """
    if not model or not prompt:
        return "[Error] model and prompt must both be non-empty strings"

    if model in OLLAMA_MODELS:
        return _call_ollama(model, prompt)

    if model in GEMINI_MODELS:
        return _call_gemini(model, prompt)

    # Unknown model - try Ollama first (lets you use bonus extra models), then error
    print(f"[Warning] '{model}' is not in the known model list. Trying Ollama...",
          file=sys.stderr)
    result = _call_ollama(model, prompt)
    if result.startswith("[Ollama Error]"):
        return f"[Error] Unknown model '{model}'. Known models: {OLLAMA_MODELS | GEMINI_MODELS}"
    return result


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    # Bonus: read model + prompt from CLI arguments
    if len(sys.argv) >= 3:
        model_arg  = sys.argv[1]
        prompt_arg = " ".join(sys.argv[2:])
    else:
        # Fallback defaults so you can test quickly without arguments
        model_arg  = "llama3.1"
        prompt_arg = "Tell me one Malaysian joke"

    response = prompt_model(model_arg, prompt_arg)
    print("\n--- RESPONSE ---\n")
    print(response)


if __name__ == "__main__":
    main()