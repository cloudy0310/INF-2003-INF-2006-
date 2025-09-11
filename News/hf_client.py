# hf_client.py
import os, time, requests
from typing import Dict, Any, Optional

HF_API_URL = "https://api-inference.huggingface.co/models"
DEFAULT_MODEL = "mistralai/Mistral-7B-Instruct-v0.2"

class HFTextGen:
    def __init__(self, api_token: Optional[str] = None, model: str = DEFAULT_MODEL, timeout_s: int = 20):
        self.api_token = api_token or os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")
        if not self.api_token:
            raise RuntimeError("Missing HF token. Set env var HF_TOKEN or HUGGINGFACEHUB_API_TOKEN.")
        self.model = model
        self.timeout_s = timeout_s
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {self.api_token}"})

    def generate(self, prompt: str, max_new_tokens: int = 300, temperature: float = 0.2, top_p: float = 0.9, retries: int = 2) -> str:
        url = f"{HF_API_URL}/{self.model}"
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_new_tokens,
                "temperature": temperature,
                "top_p": top_p,
                # truncate long inputs instead of failing:
                "truncate": 4096,
                "return_full_text": False
            },
            "options": {"wait_for_model": True}
        }

        for attempt in range(retries + 1):
            try:
                resp = self._session.post(url, json=payload, timeout=self.timeout_s)
                if resp.status_code == 200:
                    data = resp.json()
                    # HF returns a list[{"generated_text": "..."}] or a dict with "generated_text"
                    if isinstance(data, list) and data and "generated_text" in data[0]:
                        return data[0]["generated_text"].strip()
                    if isinstance(data, dict) and "generated_text" in data:
                        return data["generated_text"].strip()
                    # Some models return {"error": "..."} even with 200 (rare)
                    if isinstance(data, dict) and "error" in data:
                        raise RuntimeError(data["error"])
                    raise RuntimeError(f"Unexpected HF response: {str(data)[:200]}")
                # Handle model loading / rate limits / 5xx
                if resp.status_code in (503, 529) and attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"HF error {resp.status_code}: {resp.text[:200]}")
            except requests.RequestException as e:
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise e
