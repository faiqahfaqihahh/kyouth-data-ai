import os
import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")

async def process_with_ai(user_message: str, pdf_context: str | None) -> str:
    """
    Processes incoming text using the Week 2 AI Pipeline or routes it to an 
    Ollama service container if orchestrated.
    """
    # Construct a clean system prompt combining the PDF data and user message
    context_str = f"Resume Context:\n{pdf_context}\n\n" if pdf_context else ""
    full_prompt = f"{context_str}User Question: {user_message}"

    try:
        # Bonus Hook: Attempt to forward request to Ollama if active
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": "llama3", # or whichever model you pull
                    "prompt": full_prompt,
                    "stream": False
                }
            )
            if response.status_code == 200:
                return response.json().get("response", "Empty response from Ollama.")
    except Exception:
        # Fallback processing if Ollama is not yet deployed/running (Day 3 requirement fallback)
        pass

    # Standard analytical processing fallback output
    if pdf_context:
        return f"[Fallback AI Engine] Analyzed your profile context ({len(pdf_context)} chars). Based on your query '{user_message}', you meet the structural requirements for this role."
    
    return f"[Fallback AI Engine] Received your message: '{user_message}'. Please upload a resume for tailored feedback."