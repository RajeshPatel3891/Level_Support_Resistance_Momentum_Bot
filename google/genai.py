import os
import requests

class Client:
    def __init__(self, api_key=None, **kwargs):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")

    @property
    def models(self):
        return Models(self.api_key)

class Models:
    def __init__(self, api_key):
        self.api_key = api_key

    def generate_content(self, model=None, contents=None, **kwargs):
        model_name = model or "gemini-flash-latest"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": self.api_key
        }
        
        if isinstance(contents, str):
            payload = {"contents": [{"parts": [{"text": contents}]}]}
        elif isinstance(contents, list):
            payload = {"contents": contents}
        else:
            payload = {"contents": [{"parts": [{"text": str(contents)}]}]}

        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            return ResponseWrapper(response.json())
        raise RuntimeError(f"Gemini REST Error {response.status_code}: {response.text}")

class ResponseWrapper:
    def __init__(self, data):
        self._data = data
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            self.text = parts[0].get("text", "") if parts else ""
        else:
            self.text = ""
