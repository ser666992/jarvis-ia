"""
core/module_manager.py
========================
Registro central de módulos do Ultron. Cada módulo de topo (`ia`,
`voz`, `visao`, `automacao`, `dispositivos`, `sistema`, `seguranca`,
`logs`, `atualizacoes`) expõe uma função `status()` no seu
`__init__.py`, retornando:

    {"disponivel": bool, "motivo": str, "detalhes": {...}}

`disponivel=True` significa "as dependências necessárias estão
presentes", não necessariamente "está configurado" (ex.: `ia` pode
estar tecnicamente disponível mas sem nenhum provedor configurado
ainda).

O ModuleManager cruza isso com `config.modulos.<nome>` (ligado/
desligado pelo usuário) para dar o status final de cada módulo, usado
pelo comando `/modulos` no chat (ver main.py).
"""

import importlib

from config.settings import get_settings

MODULE_NAMES = (
    "ia", "voz", "visao", "automacao", "dispositivos",
    "sistema", "seguranca", "logs", "atualizacoes",
)


class ModuleManager:
    def __init__(self):
        self.settings = get_settings()

    def status_all(self) -> dict:
        return {name: self.status(name) for name in MODULE_NAMES}

    def status(self, name: str) -> dict:
        enabled_by_config = self.settings.is_module_enabled(name)
        if not enabled_by_config:
            return {
                "ativado_por_config": False,
                "disponivel": False,
                "motivo": f"desativado em config/config.json (modulos.{name})",
                "detalhes": {},
            }

        try:
            mod = importlib.import_module(name)
        except Exception as e:
            return {
                "ativado_por_config": True,
                "disponivel": False,
                "motivo": f"falha ao importar o módulo: {e}",
                "detalhes": {},
            }

        status_fn = getattr(mod, "status", None)
        if not callable(status_fn):
            return {
                "ativado_por_config": True,
                "disponivel": True,
                "motivo": "módulo carregado (sem relatório detalhado de status)",
                "detalhes": {},
            }

        try:
            result = dict(status_fn() or {})
        except Exception as e:
            return {
                "ativado_por_config": True,
                "disponivel": False,
                "motivo": f"erro ao consultar status: {e}",
                "detalhes": {},
            }

        result.setdefault("disponivel", False)
        result.setdefault("motivo", "")
        result.setdefault("detalhes", {})
        result["ativado_por_config"] = True
        return result

    def report_text(self) -> str:
        lines = []
        for name in MODULE_NAMES:
            st = self.status(name)
            if not st["ativado_por_config"]:
                marker = "desligado"
            elif st["disponivel"]:
                marker = "ok"
            else:
                marker = "indisponivel"
            lines.append(f"[{marker:11}] {name:14} {st['motivo']}")
        return "\n".join(lines)
