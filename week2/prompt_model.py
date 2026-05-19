import os
import json
import urllib.request
from google import genai
from google.genai import errors

# Make sure you set your API key in your terminal before running!
# export GEMINI_API_KEY="your_api_key_here"

def prompt_model(model: str, prompt: str) -> str:
    try:
        if "gemini" in model.lower():
            # Handle Google Gemini
            client = genai.Client() # Automatically picks up GEMINI_API_KEY from environment
            response = client.models.generate_content(
                model=model,
                contents=prompt
            )
            return response.text
        else:
            # Handle Local Ollama
            url = "http://127.0.0.1:11434/api/generate"
            data = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }
            req = urllib.request.Request(url, json.dumps(data).encode('utf-8'), {'Content-Type': 'application/json'})
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode())
                return result['response']
                
    except Exception as e:
        return f"[Error] Something went wrong: {str(e)}"

# Main function to test it via command line arguments (Bonus)
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        model_name = sys.argv[1]
        user_prompt = sys.argv[2]
        print("\n--- RESPONSE ---\n")
        print(prompt_model(model_name, user_prompt))
    else:
        print("Usage: uv run prompt_model.py <model_name> '<prompt>'")