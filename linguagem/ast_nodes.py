"""
linguagem/ast_nodes.py
=========================
Nós da árvore sintática (AST) da UltronScript -- classes simples de
dados, sem lógica; quem interpreta é linguagem/interpretador.py.
"""


class Expressao:
    pass


class Literal(Expressao):
    def __init__(self, valor):
        self.valor = valor


class ListaLiteral(Expressao):
    def __init__(self, elementos):
        self.elementos = elementos


class Variavel(Expressao):
    def __init__(self, nome):
        self.nome = nome


class Atribuicao(Expressao):
    def __init__(self, nome, valor):
        self.nome = nome
        self.valor = valor


class AtribuicaoIndexada(Expressao):
    """`alvo[indice] = valor` (e o desaçucaramento de `alvo[indice] +=
    valor` etc.) -- diferente de Atribuicao, que só reatribui uma
    variável inteira, esta muta um elemento existente de uma lista."""
    def __init__(self, alvo, indice, valor):
        self.alvo = alvo
        self.indice = indice
        self.valor = valor


class Unario(Expressao):
    def __init__(self, operador, direita):
        self.operador = operador
        self.direita = direita


class Binario(Expressao):
    def __init__(self, esquerda, operador, direita):
        self.esquerda = esquerda
        self.operador = operador
        self.direita = direita


class Logico(Expressao):
    def __init__(self, esquerda, operador, direita):
        self.esquerda = esquerda
        self.operador = operador
        self.direita = direita


class Chamada(Expressao):
    def __init__(self, callee, argumentos):
        self.callee = callee
        self.argumentos = argumentos


class Indexacao(Expressao):
    def __init__(self, alvo, indice):
        self.alvo = alvo
        self.indice = indice


class Instrucao:
    pass


class ExpressaoInstrucao(Instrucao):
    def __init__(self, expressao):
        self.expressao = expressao


class ImprimeInstrucao(Instrucao):
    def __init__(self, expressao):
        self.expressao = expressao


class VarInstrucao(Instrucao):
    def __init__(self, nome, inicializador):
        self.nome = nome
        self.inicializador = inicializador


class BlocoInstrucao(Instrucao):
    def __init__(self, instrucoes):
        self.instrucoes = instrucoes


class SeInstrucao(Instrucao):
    def __init__(self, condicao, ramo_entao, ramo_senao):
        self.condicao = condicao
        self.ramo_entao = ramo_entao
        self.ramo_senao = ramo_senao


class EnquantoInstrucao(Instrucao):
    def __init__(self, condicao, corpo):
        self.condicao = condicao
        self.corpo = corpo


class ParaInstrucao(Instrucao):
    """`para (init; cond; incr) corpo`. Tem nó próprio em vez de ser
    desaçucarado em EnquantoInstrucao (como era antes) porque
    'continua' precisa rodar o incremento antes de reavaliar a
    condição -- se o incremento fosse só a última instrução dentro do
    mesmo bloco do corpo (a forma antiga de desaçucarar), 'continua'
    pularia o incremento junto com o resto do corpo, e o loop nunca
    avançaria (loop infinito)."""
    def __init__(self, inicializador, condicao, incremento, corpo):
        self.inicializador = inicializador
        self.condicao = condicao
        self.incremento = incremento
        self.corpo = corpo


class FuncInstrucao(Instrucao):
    def __init__(self, nome, parametros, corpo):
        self.nome = nome
        self.parametros = parametros
        self.corpo = corpo


class RetornaInstrucao(Instrucao):
    def __init__(self, valor):
        self.valor = valor


class QuebraInstrucao(Instrucao):
    """`quebra;` -- sai do 'enquanto'/'para' mais interno na hora."""
    pass


class ContinuaInstrucao(Instrucao):
    """`continua;` -- pula pro início da próxima repetição do
    'enquanto'/'para' mais interno, sem rodar o resto do corpo."""
    pass
