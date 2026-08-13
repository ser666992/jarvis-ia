"""
ia/manager.py
===============
AIManager: detecta quais provedores de IA estão configurados (config
+ variáveis de ambiente), tenta cada um em ordem até um responder, e
cai para o modelo local (`ia/local_model.py`) se nenhum provedor
remoto estiver disponível. Se nem isso estiver disponível, `chat()`
retorna `(None, None)` -- o núcleo do Ultron (`core/jarvis.py`) segue
então para seu próprio fallback (ajuda / "não sei").

Plugins podem registrar provedores extras (novas IAs) sem tocar neste
arquivo:

    from ia.manager import AIManager
    AIManager.register_provider(MeuProvider(...))
"""

from config.settings import get_settings
from core.personality import build_system_prompt
from ia.local_model import LocalModelProvider
from ia.providers.anthropic_provider import AnthropicProvider
from ia.providers.gemini_provider import GeminiProvider
from ia.providers.openai_compatible import OpenAICompatibleProvider
from ia.providers.registry import PROVIDER_SPECS
from logs.logger import get_logger
import time

log = get_logger("ia")

_extra_providers = []


class AIManager:
    @classmethod
    def register_provider(cls, provider):
        """Ponto de extensão para plugins adicionarem uma nova IA."""
        _extra_providers.append(provider)

    def __init__(self):
        self.settings = get_settings()
        self._providers = None

    def _build_providers(self) -> list:
        providers = []
        order = self.settings.get("ia.ordem_provedores", list(PROVIDER_SPECS.keys()))

        for name in order:
            spec = PROVIDER_SPECS.get(name)
            if not spec:
                continue
            cfg = self.settings.get_provider_config(name)

            if name == "anthropic":
                providers.append(AnthropicProvider(api_key=cfg.get("api_key", ""), model=cfg.get("modelo", "")))
                continue
            if name == "gemini":
                providers.append(GeminiProvider(api_key=cfg.get("api_key", ""), model=cfg.get("modelo", "")))
                continue

            base_url = cfg.get("base_url") or spec["base_url"]
            model = cfg.get("modelo") or spec["default_model"]
            providers.append(OpenAICompatibleProvider(
                name=name, base_url=base_url, api_key=cfg.get("api_key", ""),
                model=model, kind=spec["kind"], auth_header=cfg.get("auth_header", "Authorization"),
            ))

        providers.extend(_extra_providers)

        if self.settings.get("ia.modelo_local.ativar", True):
            providers.append(LocalModelProvider(
                model_name=self.settings.get("ia.modelo_local.nome_modelo", ""),
                gguf_path=self.settings.get("ia.modelo_local.caminho_gguf", ""),
            ))

        return providers

    @property
    def providers(self) -> list:
        if self._providers is None:
            self._providers = self._build_providers()
        return self._providers

    def refresh(self):
        """Descarta a lista de provedores já construída (com as chaves/URLs
        que estavam configuradas na hora em que `.providers` foi acessado
        pela primeira vez), forçando reconstruir na próxima chamada.

        Necessário depois de configurar/trocar um provedor EM UMA SESSÃO
        JÁ EM ANDAMENTO (ex.: comando "/configurarapi" no modo texto,
        chamado com o `Jarvis`/`AIManager` já construído) -- sem isso, a
        chave nova era salva certinho em config.json, mas o
        `AIManager` continuava respondendo com a lista antiga (cacheada
        na primeira mensagem processada, antes da chave existir), e a
        IA recém-configurada só passava a funcionar depois de reiniciar
        o processo. Bug real encontrado em auditoria."""
        self._providers = None

    def available_providers(self) -> list:
        result = []
        for p in self.providers:
            try:
                if p.available():
                    result.append(p)
            except Exception as e:
                log.warning("erro ao checar disponibilidade de %s: %s", p.name, e)
        return result

    def chat(self, text: str, history: list = None, extra_context: str = "",
              timeout: int = 60, max_tokens: int = 512, system_prompt: str = None):
        """Retorna (nome_do_provedor, texto_da_resposta) ou (None, None)
        se nenhum provedor conseguiu responder.

        `timeout`/`max_tokens` têm um teto mais folgado que a chamada de
        teste do assistente de configuração (ia/setup.py, que usa poucos
        tokens e timeout curto de propósito): uma resposta de chat de
        verdade, principalmente em modelos grandes hospedados (ex.: os
        70B da NVIDIA), pode legitimamente levar mais que 30s para gerar
        uma resposta completa -- 30s era curto demais e causava falhas
        por timeout mesmo com uma API key válida.

        `system_prompt`: sobrescreve o prompt de sistema padrão (persona
        do Ultron -- ver core/personality.py). Uso: tarefas onde a IA
        não deve responder COMO o Ultron, mas gerar texto em nome do
        usuário (ex.: sugestão de resposta de mensagem -- ver
        plugins/instagram.py) -- nesses casos a persona configurada do
        Ultron (inclusive o estilo "ultron") não deveria vazar pro
        texto gerado."""
        if system_prompt is None:
            estilo = self.settings.get("personalidade.estilo", "padrao")
            system_prompt = build_system_prompt(extra_context, estilo=estilo)
        messages = [{"role": "system", "content": system_prompt}]
        for h in (history or [])[-10:]:
            role = "assistant" if h.get("role") == "jarvis" else "user"
            messages.append({"role": role, "content": h["content"]})
        messages.append({"role": "user", "content": text})

        for provider in self.available_providers():
            from core import resilience
            if not resilience.allowed(f"provider:{provider.name}"):
                continue
            inicio = time.monotonic()
            try:
                response = provider.chat(messages, timeout=timeout, max_tokens=max_tokens)
                if response:
                    resilience.success(f"provider:{provider.name}")
                    try:
                        from core.advanced import record_provider_metric
                        record_provider_metric(provider.name, True, (time.monotonic() - inicio) * 1000)
                    except Exception:
                        pass
                    return provider.name, response.strip()
                resilience.failure(f"provider:{provider.name}")
                try:
                    from core.advanced import record_provider_metric
                    record_provider_metric(
                        provider.name, False, (time.monotonic() - inicio) * 1000,
                        "resposta vazia",
                    )
                except Exception:
                    pass
            except Exception as e:
                resilience.failure(f"provider:{provider.name}")
                try:
                    from core.advanced import record_provider_metric
                    record_provider_metric(
                        provider.name, False, (time.monotonic() - inicio) * 1000, str(e))
                except Exception:
                    pass
                log.warning("provedor %s falhou: %s", provider.name, e)
                continue

        return None, None

    def status(self) -> dict:
        available = self.available_providers()
        return {
            "disponivel": bool(available),
            "motivo": (
                f"provedor(es) prontos: {', '.join(p.name for p in available)}" if available else
                "nenhum provedor de IA configurado e nenhum modelo local disponível"
            ),
            "detalhes": {"provedores": [p.describe() for p in self.providers]},
        }
