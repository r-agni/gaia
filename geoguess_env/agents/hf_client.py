"""
HuggingFace Inference API wrapper.
Uses the Messages API (compatible with Llama 3.1 Instruct).
"""
from __future__ import annotations

import httpx


class HFInferenceClient:
    BASE_URL = "https://api-inference.huggingface.co/models"

    def __init__(self, model_id: str, api_key: str):
        self.model_id = model_id
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: list[dict],
        max_new_tokens: int = 600,
        temperature: float = 0.7,
    ) -> str:
        """
        Chat completion via HF Messages API.
        messages format: [{"role": "system"|"user"|"assistant", "content": str}]
        """
        url = f"{self.BASE_URL}/{self.model_id}/v1/chat/completions"
        payload = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": max_new_tokens,
            "temperature": temperature,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(url, headers=self._headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def generate(
        self,
        prompt: str,
        max_new_tokens: int = 600,
        temperature: float = 0.7,
    ) -> str:
        """Raw text generation fallback."""
        url = f"{self.BASE_URL}/{self.model_id}"
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_new_tokens,
                "temperature": temperature,
                "return_full_text": False,
            },
        }
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(url, headers=self._headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data[0].get("generated_text", "")
            return str(data)
