import urllib.request
import json

payload = {
    "message": "What skills am I missing?",
    "pdf_text": "Software Engineer with 5 years Python experience, FastAPI, Docker, Kubernetes. Expert in AWS, CI/CD pipelines."
}

req = urllib.request.Request(
    'http://127.0.0.1:8001/chat',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST'
)

try:
    response = urllib.request.urlopen(req)
    result = json.loads(response.read().decode())
    print("CHAT API TEST: PASS")
    print("Reply:", result.get('reply', 'No reply')[:150])
except Exception as e:
    print(f"CHAT API TEST: FAIL - {str(e)[:100]}")
