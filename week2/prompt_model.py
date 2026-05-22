import sys
import subprocess
import os
from dotenv import load_dotenv
from google import genai

def main():
    if len(sys.argv) < 3:
        print("Usage: uv run prompt_model.py <model> <prompt>")
        sys.exit(1)

    model = sys.argv[1]
    prompt = sys.argv[2]

    # Local Ollama models
    if model.startswith("llama") or model.startswith("phi") or model.startswith("deepseek"):
        try:
            result = subprocess.run(
                ["ollama", "run", model],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            # ollama prints errors to stderr and exits with a non-zero code
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                print(f"Ollama error (exit code {result.returncode}): {error_msg}")
                sys.exit(1)

            if not result.stdout.strip():
                print("Ollama returned an empty response. The model may have crashed.")
                sys.exit(1)

            print("\n--- RESPONSE ---\n")
            print(result.stdout.strip())

        except FileNotFoundError:
            print("Error: 'ollama' command not found. Is Ollama installed and in your PATH?")
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error running Ollama: {e}")
            sys.exit(1)

    # Gemini cloud models
    else:
        try:
            load_dotenv()
            api_key = os.getenv("GOOGLE_API_KEY")

            if not api_key:
                print("Error: GOOGLE_API_KEY not found in environment or .env file.")
                sys.exit(1)

            client = genai.Client(api_key=api_key)

            response = client.models.generate_content(
                model=model,
                contents=prompt
            )
            print("\n--- RESPONSE ---\n")
            print(response.text.strip())

        except Exception as e:
            print(f"Gemini error: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()