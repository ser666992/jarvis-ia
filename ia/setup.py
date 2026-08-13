"""
ia/setup.py
=============
Assistente interativo de configuração de provedores de IA -- chamado
por `main.py` no início do programa se nenhum provedor remoto estiver
configurado ainda, e também disponível a qualquer momento via
`/configurarapi` no chat.

Aceita QUALQUER provedor já suportado por `ia/providers/registry.py`
(OpenAI, Anthropic, Gemini, Mistral, OpenRouter, DeepSeek, NVIDIA,
Ollama, LM Studio, API compatível genérica, servidor próprio) --
inclusive a NVIDIA (NIM / API Catalog), que usa o mesmo fluxo
compatível com OpenAI dos demais.

Nunca salva uma chave/URL sem antes VALIDAR de verdade: `test_provider()`
faz uma chamada mínima real ao provedor escolhido (poucos tokens) e só
`save_provider()` grava em `config/config.json` se a chamada funcionou.
Isso evita configurar silenciosamente uma API key inválida/errada.
"""

from config.settings import get_settings
from ia.providers.anthropic_provider import AnthropicProvider
from ia.providers.gemini_provider import GeminiProvider
from ia.providers.openai_compatible import OpenAICompatibleProvider
from ia.providers.registry import PROVIDER_SPECS

# Rótulos amigáveis para exibir no assistente de configuração.
PROVIDER_LABELS = {
    "openai": "OpenAI (GPT)",
    "anthropic": "Anthropic (Claude)",
    "gemini": "Google Gemini",
    "mistral": "Mistral",
    "openrouter": "OpenRouter",
    "deepseek": "DeepSeek",
    "nvidia": "NVIDIA (NIM / API Catalog)",
    "ollama": "Ollama (servidor local)",
    "lm_studio": "LM Studio (servidor local)",
    "openai_compatible": "Outra API compatível com OpenAI (genérica)",
    "servidor_proprio": "Servidor próprio",
}

PROVIDER_ORDER = list(PROVIDER_SPECS.keys())

# Provedores com endpoint fixo (não fazem parte do fluxo genérico
# OpenAICompatibleProvider) -- não faz sentido pedir "URL base" deles.
_FIXED_ENDPOINT_PROVIDERS = ("anthropic", "gemini")


def list_providers() -> list:
    """[(nome, rótulo, precisa_de_chave, url_padrao), ...] na ordem de exibição."""
    result = []
    for name in PROVIDER_ORDER:
        spec = PROVIDER_SPECS[name]
        result.append((name, PROVIDER_LABELS.get(name, name), spec["kind"] == "remoto", spec["base_url"]))
    return result


def _build_provider(name: str, api_key: str, base_url: str, model: str):
    spec = PROVIDER_SPECS[name]
    if name == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model or spec["default_model"])
    if name == "gemini":
        return GeminiProvider(api_key=api_key, model=model or spec["default_model"])
    return OpenAICompatibleProvider(
        name=name,
        base_url=base_url or spec["base_url"],
        api_key=api_key,
        model=model or spec["default_model"],
        kind=spec["kind"],
    )


def test_provider(name: str, api_key: str = "", base_url: str = "", model: str = "") -> tuple:
    """Faz uma chamada mínima real de teste ao provedor. Retorna
    (ok: bool, mensagem: str) -- nunca levanta exceção."""
    if name not in PROVIDER_SPECS:
        return False, f"Provedor desconhecido: {name}"

    spec = PROVIDER_SPECS[name]
    if spec["kind"] == "remoto" and not api_key:
        return False, "Este provedor exige uma API key."
    if name not in _FIXED_ENDPOINT_PROVIDERS and not (base_url or spec["base_url"]):
        return False, "Este provedor exige uma URL base."

    provider = _build_provider(name, api_key, base_url, model)
    try:
        resposta = provider.chat(
            [
                {"role": "system", "content": "Responda apenas com a palavra ok."},
                {"role": "user", "content": "teste de conexão"},
            ],
            max_tokens=10,
            timeout=15,
        )
        if resposta:
            return True, "conexão validada com sucesso."
        return False, "o provedor respondeu vazio -- confira o nome do modelo configurado."
    except Exception as e:
        return False, str(e)


def save_provider(name: str, api_key: str = "", base_url: str = "", model: str = ""):
    settings = get_settings()
    if api_key:
        settings.set(f"ia.provedores.{name}.api_key", api_key)
    if base_url:
        settings.set(f"ia.provedores.{name}.base_url", base_url)
    if model:
        settings.set(f"ia.provedores.{name}.modelo", model)
    settings.save()


def any_remote_provider_configured() -> bool:
    """True se já existe pelo menos um provedor pronto para uso (API
    key configurada para algum remoto, ou URL customizada para um
    local) -- usado para decidir se o assistente de configuração deve
    aparecer no início do programa."""
    settings = get_settings()
    for name, spec in PROVIDER_SPECS.items():
        cfg = settings.get_provider_config(name)
        if spec["kind"] == "remoto" and cfg.get("api_key"):
            return True
        if spec["kind"] == "local" and name != "ollama" and name != "lm_studio" and cfg.get("base_url"):
            # ollama/lm_studio já vêm com uma URL padrão (localhost) mesmo
            # sem o usuário ter configurado nada -- só contam como
            # "configurado" outros servidores locais explicitamente apontados.
            return True
    return False
