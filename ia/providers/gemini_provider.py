"""
ia/providers/gemini_provider.py
==================================
Provedor Google Gemini via urllib -- REST `generateContent`.
"""

from ia.base import AIProvider
from ia.http_utils import post_json

DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider(AIProvider):
    name = "gemini"
    kind = "remoto"

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key or ""
        self.model = model or DEFAULT_MODEL

    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: list, **kwargs) -> str:
        model = kwargs.get("model") or self.model
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={self.api_key}"
        )

        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        contents = []
        for m in messages:
            if m["role"] == "system":
                continue
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        payload = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": kwargs.get("max_tokens", 1024)},
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}

        ok, status, data = post_json(url, payload, timeout=kwargs.get("timeout", 30))
        if not ok:
            raise RuntimeError(f"[gemini] erro HTTP {status}: {data.get('erro') or data}")
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"[gemini] resposta em formato inesperado: {data}") from e
