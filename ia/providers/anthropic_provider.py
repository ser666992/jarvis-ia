"""
ia/providers/anthropic_provider.py
=====================================
Provedor Anthropic (API da Claude) via urllib -- "Messages API",
diferente do padrão OpenAI-compatible (header `x-api-key` + campo
"system" separado da lista de mensagens).
"""

from ia.base import AIProvider
from ia.http_utils import post_json

DEFAULT_MODEL = "claude-sonnet-5"
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicProvider(AIProvider):
    name = "anthropic"
    kind = "remoto"

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key or ""
        self.model = model or DEFAULT_MODEL

    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: list, **kwargs) -> str:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        conversation = [m for m in messages if m["role"] != "system"]

        payload = {
            "model": kwargs.get("model") or self.model,
            "max_tokens": kwargs.get("max_tokens", 1024),
            "messages": conversation,
        }
        if system:
            payload["system"] = system

        headers = {"x-api-key": self.api_key, "anthropic-version": API_VERSION}
        ok, status, data = post_json(API_URL, payload, headers=headers, timeout=kwargs.get("timeout", 30))
        if not ok:
            raise RuntimeError(f"[anthropic] erro HTTP {status}: {data.get('erro') or data}")
        try:
            return "".join(block.get("text", "") for block in data["content"])
        except (KeyError, TypeError) as e:
            raise RuntimeError(f"[anthropic] resposta em formato inesperado: {data}") from e
