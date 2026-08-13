"""
ia/providers/openai_compatible.py
====================================
Provedor genérico para qualquer API compatível com o formato de chat
completions da OpenAI (`POST {base_url}/chat/completions`). Cobre:
OpenAI, Mistral, OpenRouter, DeepSeek, NVIDIA NIM/API Catalog, Ollama,
LM Studio, "OpenAI Compatible" genérico e "servidor próprio".
"""

import socket
from urllib.parse import urlparse

from ia.base import AIProvider
from ia.http_utils import post_json


class OpenAICompatibleProvider(AIProvider):
    def __init__(self, name: str, base_url: str, api_key: str = "", model: str = "",
                 kind: str = "remoto", auth_header: str = "Authorization"):
        self.name = name
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""
        self.kind = kind
        self.auth_header = auth_header or "Authorization"

    def available(self) -> bool:
        if not self.base_url:
            return False
        if self.kind == "local":
            # Servidor local (Ollama/LM Studio/próprio): um teste TCP
            # rápido (300ms) evita esperar ~4s por uma "conexão
            # recusada" via HTTP a cada mensagem não reconhecida,
            # quando nenhum servidor local está de pé.
            return self._local_server_reachable()
        return bool(self.api_key)

    def _local_server_reachable(self, timeout: float = 0.3) -> bool:
        try:
            parsed = urlparse(self.base_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def chat(self, messages: list, **kwargs) -> str:
        headers = {}
        if self.api_key:
            if self.auth_header.lower() == "authorization":
                headers["Authorization"] = f"Bearer {self.api_key}"
            else:
                headers[self.auth_header] = self.api_key

        payload = {
            "model": kwargs.get("model") or self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 1024),
        }

        ok, status, data = post_json(
            f"{self.base_url}/chat/completions", payload, headers=headers,
            timeout=kwargs.get("timeout", 30),
        )
        if not ok:
            raise RuntimeError(f"[{self.name}] erro HTTP {status}: {data.get('erro') or data}")
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"[{self.name}] resposta em formato inesperado: {data}") from e

    def describe(self) -> dict:
        d = super().describe()
        d["base_url"] = self.base_url
        d["modelo"] = self.model
        return d
