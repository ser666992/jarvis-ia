"""
linguagem/
============
UltronScript: a linguagem de programação PRÓPRIA do Ultron -- léxico
(lexer.py) -> sintaxe (parser.py, ast_nodes.py) -> execução
(interpretador.py). Pequena mas real: variáveis, funções, se/enquanto/
para, listas, e alguns builtins (imprime, len, str, num, tempo).

100% sandboxed por construção -- não tem NENHUM jeito de ler/escrever
arquivo, acessar rede, ou chamar código Python arbitrário: só os
builtins que este módulo decide expor. Rodar um programa UltronScript
nunca é uma ação destrutiva, mesmo que o código venha de uma fonte não
confiável (ex.: gerado por IA) -- ver core/skill_forge.py pra código
Python de verdade, que aí sim exige aprovação/confirmação.

Ver linguagem/README.md pra sintaxe completa e exemplos.

Uso:
    from linguagem import executar
    saida, erro = executar('imprime "olá mundo";')
"""

from linguagem.interpretador import ErroExecucao, Interpretador
from linguagem.lexer import ErroLexico, Lexer
from linguagem.parser import ErroSintaxe, Parser


def executar(codigo: str, max_segundos: float = 5.0):
    """Roda um programa UltronScript. Retorna (saida: str, erro: str|None)
    -- erro é None se rodou até o fim sem problema."""
    interpretador = Interpretador(max_segundos=max_segundos)
    try:
        tokens = Lexer(codigo).tokenizar()
        instrucoes = Parser(tokens).parse()
    except (ErroLexico, ErroSintaxe) as e:
        return "", str(e)
    try:
        saida = interpretador.executar(instrucoes)
        return saida, None
    except ErroExecucao as e:
        return "\n".join(interpretador.saida), str(e)
