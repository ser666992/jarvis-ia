"""
config/settings.py
====================
Configuração centralizada do Ultron.

Fonte única: `config/config.json`, criado automaticamente a partir de
`config.example.json` na primeira execução. Se existir
`config/config.yaml` **e** a biblioteca opcional `pyyaml` estiver
instalada, o YAML tem prioridade sobre o JSON — isso é só uma
conveniência para quem preferir editar YAML; nunca é obrigatório (o
Ultron roda só com a stdlib `json`).

Qualquer chave pode ser sobrescrita por variável de ambiente, no
formato `JARVIS_<CAMINHO_EM_MAIUSCULO_COM_UNDERSCORE>`, por exemplo:

    JARVIS_IA_PROVEDORES_OPENAI_API_KEY=sk-...

sobrescreve `config["ia"]["provedores"]["openai"]["api_key"]`.

Uso:
    from config.settings import get_settings
    settings = get_settings()
    settings.get("ia.provedores.openai.api_key")
    settings.is_module_enabled("voz")
"""

import copy
import json
import os
import threading

CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
EXAMPLE_PATH = os.path.join(CONFIG_DIR, "config.example.json")
JSON_PATH = os.path.join(CONFIG_DIR, "config.json")
YAML_PATH = os.path.join(CONFIG_DIR, "config.yaml")

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def _load_default() -> dict:
    with open(EXAMPLE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _deep_merge(base: dict, override: dict) -> dict:
    """Mescla `override` em cima de `base`, preservando chaves default
    ausentes em `override` -- assim, novas versões do Ultron podem
    adicionar chaves de config sem quebrar um config.json antigo do
    usuário."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Settings:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        if HAS_YAML and os.path.isfile(YAML_PATH):
            with open(YAML_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return _deep_merge(_load_default(), data)

        if not os.path.isfile(JSON_PATH):
            default = _load_default()
            self._write_json(default)
            return default

        try:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = _load_default()
        return _deep_merge(_load_default(), data)

    def _write_json(self, data: dict):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def reload(self):
        with self._lock:
            self._data = self._load()

    def save(self):
        """Persiste o estado atual em config/config.json (mesmo que a
        fonte original tenha sido YAML -- o YAML só é lido, nunca
        escrito automaticamente)."""
        with self._lock:
            self._write_json(self._data)

    def get(self, path: str, default=None):
        env_name = "JARVIS_" + path.upper().replace(".", "_")
        if env_name in os.environ:
            return os.environ[env_name]
        node = self._data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, path: str, value):
        parts = path.split(".")
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def is_module_enabled(self, module_name: str) -> bool:
        value = self.get(f"modulos.{module_name}", True)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "sim", "yes", "on")
        return bool(value)

    def get_provider_config(self, provider_name: str) -> dict:
        """Config de um provedor de IA (`ia.provedores.<nome>`), com
        `api_key`/`base_url`/`modelo` sobrescritos por variável de
        ambiente quando presente."""
        cfg = dict(self.get(f"ia.provedores.{provider_name}", {}) or {})
        env_prefix = f"JARVIS_IA_PROVEDORES_{provider_name.upper()}_"
        for key in ("api_key", "base_url", "modelo"):
            env_val = os.environ.get(env_prefix + key.upper())
            if env_val is not None:
                cfg[key] = env_val
        # Segredos no Credential Manager têm prioridade sobre o JSON.
        # Falha do cofre nunca impede configurações antigas de funcionar.
        try:
            from seguranca.vault import get_secret
            vaulted = get_secret(f"ia.{provider_name}.api_key")
            if vaulted:
                cfg["api_key"] = vaulted
        except Exception:
            pass
        return cfg

    @property
    def data(self) -> dict:
        return self._data


_settings_instance = None
_settings_lock = threading.Lock()


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        with _settings_lock:
            if _settings_instance is None:
                _settings_instance = Settings()
    return _settings_instance
