"""
core/plugin_manager.py
=======================
Sistema de plugins do Ultron.

Cada plugin é um arquivo .py dentro de /plugins que define uma classe
herdando de BasePlugin. O gerenciador carrega todos automaticamente.

Um plugin declara:
- name: nome do plugin
- triggers: lista de palavras/padrões que ativam o plugin
- handle(text, context) -> Answer | str | None : processa o comando

handle() pode retornar:
- uma Answer(text, confidence) -> recomendado, deixa a confiança explícita
- uma string simples -> mantido por compatibilidade; nesse caso o
  PluginManager assume confiança GUESS (10), pois o plugin não declarou
  o nível explicitamente
- None -> o plugin não soube responder; o Ultron segue para o próximo
  candidato (ou fallback)

Se handle() lançar uma exceção, dispatch() tenta gerar sozinho um
rascunho de correção (core/skill_forge.py) e já oferece a aprovação
junto da mensagem de erro -- nunca aplica a correção sem você dizer
"aprova a habilidade <nome>" (ver PluginManager._erro_com_correcao).
"""

import os
import importlib.util
import inspect
import traceback

from core.confidence import Answer, Confidence

_PERMISSION_PLUGIN_GROUPS = {
    "permissoes.internet": {
        "navegador", "navegador_pessoal", "investigador", "observador_internet",
        "atualizacoes", "instalador_apps",
    },
    "permissoes.controle_pc": {
        "controle_pc", "system_control", "clicar_texto", "musica",
        "aprendizado_programa", "macros",
    },
    "permissoes.instagram": {"instagram"},
    "permissoes.dispositivos": {"device_control"},
}


class BasePlugin:
    name = "base"
    description = "Plugin base"
    triggers = []  # palavras-chave que ativam este plugin

    def matches(self, text: str) -> bool:
        text_low = text.lower()
        return any(trigger in text_low for trigger in self.triggers)

    def handle(self, text: str, context: dict):
        """Deve retornar uma Answer (texto + confiança), uma string simples,
        ou None se não souber lidar com o pedido."""
        raise NotImplementedError


class PluginManager:
    def __init__(self, plugins_dir: str):
        self.plugins_dir = plugins_dir
        self.plugins = []
        self._tentativas_correcao = set()
        self.load_plugins()

    def load_plugins(self):
        self.plugins = []
        if not os.path.isdir(self.plugins_dir):
            return

        for filename in sorted(os.listdir(self.plugins_dir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            path = os.path.join(self.plugins_dir, filename)
            module_name = f"jarvis_plugin_{filename[:-3]}"

            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except Exception as e:
                print(f"[PluginManager] Falha ao carregar {filename}: {e}")
                continue

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                    try:
                        instance = obj()
                        instance._jarvis_source_path = path
                        self.plugins.append(instance)
                    except Exception as e:
                        print(f"[PluginManager] Falha ao instanciar {obj}: {e}")

    def list_plugins(self):
        return [(p.name, p.description) for p in self.plugins]

    def dispatch(self, text: str, context: dict):
        """
        Percorre os plugins; o primeiro que casar com os triggers
        e retornar uma resposta não-nula 'ganha'.

        Retorna (plugin_name, Answer) ou (None, None) se nenhum
        plugin soube responder.
        """
        try:
            from config.settings import get_settings
            settings = get_settings()
            desativados = set(settings.get("plugins.desativados", []) or [])
            for permission, names in _PERMISSION_PLUGIN_GROUPS.items():
                if not settings.get(permission, True):
                    desativados.update(names)
        except Exception:
            desativados = set()
        for plugin in self.plugins:
            if plugin.name in desativados:
                continue
            from core import resilience
            if not resilience.allowed(f"plugin:{plugin.name}"):
                continue
            try:
                corresponde = plugin.matches(text)
            except Exception as e:
                # matches() quebrando não deve derrubar o dispatch inteiro
                # (isso pararia TODOS os plugins seguintes de serem
                # tentados, não só o quebrado) -- trata como "não bateu" e
                # segue pro próximo, igual já acontece pra handle().
                print(f"[PluginManager] Plugin '{plugin.name}' quebrou em matches(): {e}")
                continue

            if corresponde:
                try:
                    result = plugin.handle(text, context)
                except Exception as e:
                    resilience.failure(f"plugin:{plugin.name}")
                    result = Answer(self._erro_com_correcao(plugin, e, context), Confidence.GUESS)
                else:
                    resilience.success(f"plugin:{plugin.name}")

                if result is None:
                    continue

                if isinstance(result, str):
                    # Compatibilidade: plugin antigo retornou string pura.
                    # Sem declaração explícita de confiança -> nível mínimo (palpite).
                    result = Answer(result, Confidence.GUESS)

                return plugin.name, result
        return None, None

    def _erro_com_correcao(self, plugin, exc: Exception, context: dict) -> str:
        """Quando um plugin quebra em tempo real, tenta gerar sozinho
        um rascunho de correção (core/skill_forge.py) e já oferece pra
        aprovação -- nunca aplica a correção sozinho (mesma regra de
        plugins/skill_forge.py). No máximo uma tentativa de correção
        por plugin por sessão, pra não gastar chamadas de IA repetidas
        se o mesmo plugin quebrado for acionado várias vezes seguidas."""
        base = f"[Erro no plugin {plugin.name}]: {exc}"
        caminho = getattr(plugin, "_jarvis_source_path", None)
        ia_manager = context.get("ia_manager")
        if not caminho or ia_manager is None or plugin.name in self._tentativas_correcao:
            return base
        self._tentativas_correcao.add(plugin.name)
        try:
            from core import skill_forge
            resultado = skill_forge.gerar_correcao_habilidade(ia_manager, caminho, traceback.format_exc())
        except Exception:
            return base
        return (
            f"{base}\n\nGerei uma correção pra isso: rascunho \"{resultado['slug']}\" "
            f'({resultado["caminho"]}). Diga "aprova a habilidade {resultado["slug"]}" pra '
            f'aplicar, ou "rejeita a habilidade {resultado["slug"]}" pra ignorar.'
        )
