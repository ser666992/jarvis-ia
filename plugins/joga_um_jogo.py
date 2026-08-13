from core.plugin_manager import BasePlugin
from core.confidence import Answer, Confidence
import random

class JogoDoGalo(BasePlugin):
    name = "jogo_do_galo"
    description = "Jogo do Galo"
    triggers = ["jogo do galo", "jogar galo"]

    def handle(self, text: str, context: dict):
        if "jogar" in text:
            self.jogo = [" " for _ in range(9)]
            self.jogador_atual = "X"
            return Answer("Vamos jogar! Eu irei atualizar o tabuleiro.\n" + self.imprimir_tabuleiro(), Confidence.CONFIRMED)
        elif "fazer jogada" in text or "jogar em" in text:
            posicao = self.obter_posicao(text)
            if posicao is not None:
                if self.jogo[posicao] == " ":
                    self.jogo[posicao] = self.jogador_atual
                    if self.checar_vitoria():
                        return Answer(self.imprimir_tabuleiro() + "\n" + self.jogador_atual + " venceu!", Confidence.CONFIRMED)
                    self.jogador_atual = "O" if self.jogador_atual == "X" else "X"
                    return Answer(self.imprimir_tabuleiro(), Confidence.RELIABLE_SOURCE)
                else:
                    return Answer("Posição ocupada. Tente novamente.", Confidence.Possible)
            else:
                return Answer("Posição inválida. Tente novamente.", Confidence.Possible)
        elif "sair" in text:
            return Answer("Fim do jogo!", Confidence.CONFIRMED)
        return None

    def imprimir_tabuleiro(self):
        return f"{self.jogo[0]} | {self.jogo[1]} | {self.jogo[2]}\n---------\n{self.jogo[3]} | {self.jogo[4]} | {self.jogo[5]}\n---------\n{self.jogo[6]} | {self.jogo[7]} | {self.jogo[8]}"

    def obter_posicao(self, text):
        posicoes = ["canto superior esquerdo", "canto superior direito", "canto superior meio", "canto meio esquerdo", "canto meio", "canto meio direito", "canto inferior esquerdo", "canto inferior direito", "canto inferior meio"]
        for i, posicao in enumerate(posicoes):
            if posicao in text:
                return i
        return None

    def checar_vitoria(self):
        vitorias = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
        for vitoria in vitorias:
            if self.jogo[vitoria[0]] == self.jogo[vitoria[1]] == self.jogo[vitoria[2]] != " ":
                return True
        return False