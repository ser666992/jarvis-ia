from core.plugin_manager import BasePlugin
from core.confidence import Answer, Confidence
import re

class FerramentaDeDepuração(BasePlugin):
    name = "depuração_rápida"
    description = "Ferramenta para ajudar a depurar código rapidamente"
    triggers = ["depurar código", "erro na tela"]

    def handle(self, text: str, context: dict):
        # Verifica se o usuário está mencionando um erro específico
        if "possivel_erro_na_tela" in text.lower():
            # Oferece ajuda para depurar o erro
            return Answer("Posso ajudar a depurar o erro. Qual é o código que está dando erro?", Confidence.RELIABLE_SOURCE)
        
        # Se o usuário não mencionou um erro específico, oferece uma ferramenta de depuração geral
        elif re.search(r"depurar código|erro na tela", text.lower()):
            # Oferece uma ferramenta de depuração geral
            return Answer("Posso ajudar a depurar o código. Qual é o tipo de erro que está ocorrendo?", Confidence.RELIABLE_SOURCE)
        
        # Se o usuário não está mencionando um erro ou depuração, não responde
        else:
            return None