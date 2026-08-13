"""
ia/providers/registry.py
===========================
Especificações de cada provedor de IA suportado nativamente: variável
de ambiente-padrão para a chave (documentação apenas -- a chave real é
lida de `config.json`/env específico do Ultron via
`Settings.get_provider_config`), URL base padrão, modelo padrão, e se
é local (não exige chave) ou remoto.
"""

PROVIDER_SPECS = {
    "openai": {
        "env_var": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "kind": "remoto",
    },
    "anthropic": {
        "env_var": "ANTHROPIC_API_KEY",
        # Endpoint fixo, tratado por ia/providers/anthropic_provider.py
        # (formato "Messages API", diferente do padrão OpenAI-compatible)
        # -- este base_url é só informativo/documentação.
        "base_url": "https://api.anthropic.com",
        "default_model": "claude-sonnet-5",
        "kind": "remoto",
    },
    "gemini": {
        "env_var": "GEMINI_API_KEY",
        # Endpoint fixo, tratado por ia/providers/gemini_provider.py
        # (REST generateContent) -- este base_url é só informativo.
        "base_url": "https://generativelanguage.googleapis.com",
        "default_model": "gemini-2.0-flash",
        "kind": "remoto",
    },
    "mistral": {
        "env_var": "MISTRAL_API_KEY",
        "base_url": "https://api.mistral.ai/v1",
        "default_model": "mistral-small-latest",
        "kind": "remoto",
    },
    "openrouter": {
        "env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "openrouter/auto",
        "kind": "remoto",
    },
    "deepseek": {
        "env_var": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "kind": "remoto",
    },
    "nvidia": {
        "env_var": "NVIDIA_API_KEY",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "default_model": "meta/llama-3.1-70b-instruct",
        "kind": "remoto",
    },
    "ollama": {
        "env_var": None,
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3.1",
        "kind": "local",
    },
    "lm_studio": {
        "env_var": None,
        "base_url": "http://localhost:1234/v1",
        "default_model": "local-model",
        "kind": "local",
    },
    "openai_compatible": {
        "env_var": None,
        "base_url": "",
        "default_model": "",
        "kind": "remoto",
    },
    "servidor_proprio": {
        "env_var": None,
        "base_url": "",
        "default_model": "",
        "kind": "local",
    },
}
