"""
core/confidence.py
====================
Sistema de níveis de confiança do Ultron.

Toda resposta do Ultron deve vir acompanhada de um nível de confiança,
que indica o quão sólida é a informação fornecida.

Níveis (fixos, não inventar valores intermediários):

    100 -> Informação confirmada várias vezes
     90 -> Informação obtida de fonte confiável
     70 -> Informação encontrada apenas uma vez
     50 -> Informação inferida
     30 -> Possível resposta
     10 -> Palpite

Uso básico:

    from core.confidence import Confidence

    Confidence.CONFIRMED       # 100
    Confidence.RELIABLE_SOURCE # 90
    Confidence.SINGLE_SOURCE   # 70
    Confidence.INFERRED        # 50
    Confidence.POSSIBLE        # 30
    Confidence.GUESS           # 10

Um plugin pode retornar uma resposta simples (string) — nesse caso o
núcleo assume confiança GUESS (10) por padrão, já que não foi
declarada explicitamente — ou retornar uma Answer(texto, confiança)
para ser explícito, o que é o recomendado.
"""

from dataclasses import dataclass


class Confidence:
    CONFIRMED = 100        # Informação confirmada várias vezes
    RELIABLE_SOURCE = 90   # Informação obtida de fonte confiável
    SINGLE_SOURCE = 70     # Informação encontrada apenas uma vez
    INFERRED = 50          # Informação inferida
    POSSIBLE = 30          # Possível resposta
    GUESS = 10             # Palpite

    LABELS = {
        100: "Confirmada várias vezes",
        90: "Fonte confiável",
        70: "Encontrada apenas uma vez",
        50: "Inferida",
        30: "Possível resposta",
        10: "Palpite",
    }

    VALID_LEVELS = (100, 90, 70, 50, 30, 10)

    @classmethod
    def normalize(cls, value: int) -> int:
        """Arredonda qualquer valor para o nível fixo mais próximo."""
        if value is None:
            return cls.GUESS
        return min(cls.VALID_LEVELS, key=lambda lvl: abs(lvl - value))

    @classmethod
    def label(cls, value: int) -> str:
        return cls.LABELS.get(cls.normalize(value), "Desconhecido")


@dataclass
class Answer:
    """
    Resposta estruturada: texto + nível de confiança.

    `formal` controla o formato de exibição:
    - True (padrão): mostra o bloco "Resposta:/Confiança:", adequado
      para respostas factuais (conhecimento, sistema, memória), onde
      saber o quão confiável é a informação importa de verdade.
    - False: mostra só o texto puro, sem bloco nenhum. Usado pelo
      motor de conversa natural (core/conversation.py) -- small talk
      ("oi", "tudo bem?", "obrigado") não tem "nível de confiança" no
      sentido factual, e exibir esse bloco ali só faria a conversa
      parecer um questionário em vez de uma conversa.
    """
    text: str
    confidence: int = Confidence.GUESS
    formal: bool = True

    def __post_init__(self):
        self.confidence = Confidence.normalize(self.confidence)

    def format(self, mostrar_confianca: bool = True) -> str:
        """`mostrar_confianca=False` (usado por core/jarvis.py, lendo
        `personalidade.mostrar_confianca` de config.json -- oculto por
        padrão) devolve só o texto puro, sem o bloco "Resposta:/
        Confiança:". O valor de `self.confidence` continua calculado e
        acessível via `self.confidence` de qualquer forma -- só a
        exibição textual é que fica de fora."""
        if not self.formal or not mostrar_confianca:
            return self.text
        return (
            f"Resposta:\n{self.text}\n\n"
            f"Confiança:\n{self.confidence}% ({Confidence.label(self.confidence)})"
        )
