"""
linguagem/lexer.py
=====================
Análise léxica da UltronScript (ver linguagem/README.md pra sintaxe e
exemplos): transforma o texto fonte numa lista de tokens.
"""

from dataclasses import dataclass

PALAVRAS_CHAVE = {
    "var", "func", "se", "senao", "enquanto", "para", "retorna",
    "imprime", "verdadeiro", "falso", "nulo", "e", "ou", "nao",
    "quebra", "continua",
}


@dataclass
class Token:
    tipo: str
    lexema: str
    literal: object
    linha: int


class ErroLexico(Exception):
    pass


class Lexer:
    def __init__(self, fonte: str):
        self.fonte = fonte
        self.tokens = []
        self.inicio = 0
        self.atual = 0
        self.linha = 1

    def _fim(self) -> bool:
        return self.atual >= len(self.fonte)

    def _avancar(self) -> str:
        c = self.fonte[self.atual]
        self.atual += 1
        return c

    def _proximo_igual(self, esperado: str) -> bool:
        if self._fim() or self.fonte[self.atual] != esperado:
            return False
        self.atual += 1
        return True

    def _olhar(self) -> str:
        return "" if self._fim() else self.fonte[self.atual]

    def _olhar_seguinte(self) -> str:
        return "" if self.atual + 1 >= len(self.fonte) else self.fonte[self.atual + 1]

    def _adicionar(self, tipo: str, literal=None):
        lexema = self.fonte[self.inicio:self.atual]
        self.tokens.append(Token(tipo, lexema, literal, self.linha))

    def tokenizar(self):
        while not self._fim():
            self.inicio = self.atual
            self._escanear_token()
        self.tokens.append(Token("EOF", "", None, self.linha))
        return self.tokens

    def _escanear_token(self):
        c = self._avancar()
        simples = {
            "(": "PAREN_ESQ", ")": "PAREN_DIR", "{": "CHAVE_ESQ", "}": "CHAVE_DIR",
            "[": "COLCH_ESQ", "]": "COLCH_DIR", ",": "VIRGULA", ";": "PONTO_VIRGULA",
            "%": "PORCENTO",
        }
        if c in simples:
            self._adicionar(simples[c])
        elif c == "+":
            self._adicionar("MAIS_IGUAL" if self._proximo_igual("=") else "MAIS")
        elif c == "-":
            self._adicionar("MENOS_IGUAL" if self._proximo_igual("=") else "MENOS")
        elif c == "*":
            self._adicionar("VEZES_IGUAL" if self._proximo_igual("=") else "VEZES")
        elif c == "/":
            if self._olhar() == "/":
                while self._olhar() != "\n" and not self._fim():
                    self._avancar()
            elif self._proximo_igual("="):
                self._adicionar("DIVIDE_IGUAL")
            else:
                self._adicionar("DIVIDE")
        elif c == "#":
            while self._olhar() != "\n" and not self._fim():
                self._avancar()
        elif c == "!":
            self._adicionar("DIFERENTE" if self._proximo_igual("=") else "NAO_SIMBOLO")
        elif c == "=":
            self._adicionar("IGUAL_IGUAL" if self._proximo_igual("=") else "IGUAL")
        elif c == "<":
            self._adicionar("MENOR_IGUAL" if self._proximo_igual("=") else "MENOR")
        elif c == ">":
            self._adicionar("MAIOR_IGUAL" if self._proximo_igual("=") else "MAIOR")
        elif c in " \r\t":
            pass
        elif c == "\n":
            self.linha += 1
        elif c == '"':
            self._string()
        elif c.isdigit():
            self._numero()
        elif c.isalpha() or c == "_":
            self._identificador()
        else:
            raise ErroLexico(f"Caractere inesperado '{c}' na linha {self.linha}")

    def _string(self):
        while self._olhar() != '"' and not self._fim():
            if self._olhar() == "\n":
                self.linha += 1
            self._avancar()
        if self._fim():
            raise ErroLexico(f"String não terminada na linha {self.linha}")
        self._avancar()  # fecha aspas
        valor = self.fonte[self.inicio + 1:self.atual - 1]
        self._adicionar("STRING", valor)

    def _numero(self):
        while self._olhar().isdigit():
            self._avancar()
        eh_float = False
        if self._olhar() == "." and self._olhar_seguinte().isdigit():
            eh_float = True
            self._avancar()
            while self._olhar().isdigit():
                self._avancar()
        texto = self.fonte[self.inicio:self.atual]
        self._adicionar("NUMERO", float(texto) if eh_float else int(texto))

    def _identificador(self):
        while self._olhar().isalnum() or self._olhar() == "_":
            self._avancar()
        texto = self.fonte[self.inicio:self.atual]
        tipo = texto.upper() if texto in PALAVRAS_CHAVE else "IDENT"
        self._adicionar(tipo)
