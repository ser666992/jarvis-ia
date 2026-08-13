from core.plugin_manager import BasePlugin
from core.confidence import Answer, Confidence
import subprocess
import os

class AutomatizadorDeTarefa(BasePlugin):
    name = "automatizador_de_tarefa"
    description = "Automatiza uma tarefa repetitiva de abrir os aplicativos favoritos"
    triggers = ["abrir aplicativos favoritos"]

    def handle(self, text: str, context: dict):
        # Verifica se o usuário tem hábitos registrados
        if 'habits' in context and context['habits']:
            # Extrai os nomes dos aplicativos mais usados
            aplicativos_favoritos = [habit['name'] for habit in context['habits'] if habit['name'] in ['Neutron', 'Codex Diff - jarvis', 'Visual Studio Code']]
            
            # Abre os aplicativos favoritos
            for aplicativo in aplicativos_favoritos:
                if aplicativo == 'Neutron':
                    # Executa o comando para abrir o Neutron
                    subprocess.Popen(['neutron'])
                elif aplicativo == 'Codex Diff - jarvis':
                    # Executa o comando para abrir o Codex Diff - jarvis
                    subprocess.Popen(['codex-diff-jarvis'])
                elif aplicativo == 'Visual Studio Code':
                    # Executa o comando para abrir o Visual Studio Code
                    subprocess.Popen(['code'])
            
            # Retorna uma resposta
            return Answer("Aplicativos favoritos abertos com sucesso!", Confidence.CONFIRMED)
        else:
            # Retorna uma resposta se o usuário não tiver hábitos registrados
            return Answer("Não há hábitos registrados para automatizar tarefas.", Confidence.POSSIBLE)