"""
linguagem/interpretador.py
=============================
Interpretador "tree-walking" da UltronScript: percorre a AST
(linguagem/ast_nodes.py) e executa direto, sem compilar pra bytecode --
mais simples de entender e depurar, ao custo de ser mais lento que uma
VM de verdade (irrelevante pro tamanho de programa que essa linguagem
é feita pra rodar).

Limites de segurança (_max_passos/_max_segundos): um "enquanto"/"para"
mal escrito vira loop infinito com muita facilidade -- sem um teto, um
programa UltronScript travaria a thread que o chamou (a mesma que
processa o chat) pra sempre. Estourar qualquer um dos dois aborta a
execução com ErroExecucao, nunca trava o processo.
"""

import time as _time


class ErroExecucao(Exception):
    pass


class _RetornoSinal(Exception):
    def __init__(self, valor):
        self.valor = valor


class _QuebraSinal(Exception):
    """Sinaliza 'quebra;' -- só _exec_EnquantoInstrucao deveria capturar
    isso; se escapar até o topo (quebra fora de qualquer loop) ou
    atravessar uma chamada de função, é um erro de programa, não um
    controle de fluxo válido (ver FuncaoUltronScript.chamar e
    Interpretador.executar)."""


class _ContinuaSinal(Exception):
    """Sinaliza 'continua;' -- mesma lógica de _QuebraSinal acima."""


class Ambiente:
    def __init__(self, pai=None):
        self.valores = {}
        self.pai = pai

    def definir(self, nome, valor):
        self.valores[nome] = valor

    def obter(self, nome):
        if nome in self.valores:
            return self.valores[nome]
        if self.pai is not None:
            return self.pai.obter(nome)
        raise ErroExecucao(f"Variável não definida: '{nome}'")

    def atribuir(self, nome, valor):
        if nome in self.valores:
            self.valores[nome] = valor
            return
        if self.pai is not None:
            self.pai.atribuir(nome, valor)
            return
        raise ErroExecucao(f"Variável não definida: '{nome}'")


class FuncaoJarvisScript:
    def __init__(self, declaracao, closure):
        self.declaracao = declaracao
        self.closure = closure

    def chamar(self, interpretador, argumentos):
        ambiente = Ambiente(self.closure)
        for nome, valor in zip(self.declaracao.parametros, argumentos):
            ambiente.definir(nome, valor)
        try:
            interpretador._executar_bloco(self.declaracao.corpo, ambiente)
        except _RetornoSinal as retorno:
            return retorno.valor
        except (_QuebraSinal, _ContinuaSinal):
            # Sem isso, um 'quebra'/'continua' dentro de uma função
            # chamada de dentro de um loop escaparia da função e
            # acabaria interrompendo o loop de QUEM CHAMOU a função --
            # comportamento surpreendente que nenhuma linguagem de
            # verdade permite (quebra/continua nunca atravessa a
            # fronteira de uma chamada de função).
            raise ErroExecucao("'quebra'/'continua' não pode atravessar uma chamada de função.")
        return None


def _eh_verdadeiro(valor) -> bool:
    if valor is None:
        return False
    if isinstance(valor, bool):
        return valor
    return True


def _formatar(valor) -> str:
    if valor is None:
        return "nulo"
    if isinstance(valor, bool):
        return "verdadeiro" if valor else "falso"
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if isinstance(valor, list):
        return "[" + ", ".join(_formatar(v) for v in valor) + "]"
    return str(valor)


class Interpretador:
    def __init__(self, max_passos: int = 200_000, max_segundos: float = 5.0):
        self.globais = Ambiente()
        self.saida = []
        self._passos = 0
        self._max_passos = max_passos
        self._max_segundos = max_segundos
        self._inicio = None
        self._instalar_builtins()

    def _instalar_builtins(self):
        self.globais.definir("len", lambda args: len(args[0]))
        self.globais.definir("str", lambda args: _formatar(args[0]))
        self.globais.definir("num", lambda args: float(args[0]) if "." in str(args[0]) else int(args[0]))
        self.globais.definir("tempo", lambda args: _time.time())

    def executar(self, instrucoes) -> str:
        self._inicio = _time.time()
        for instrucao in instrucoes:
            try:
                self._executar(instrucao, self.globais)
            except (_QuebraSinal, _ContinuaSinal):
                raise ErroExecucao("'quebra'/'continua' usado fora de um 'enquanto'/'para'.")
        return "\n".join(self.saida)

    def _checar_limites(self):
        self._passos += 1
        if self._passos > self._max_passos:
            raise ErroExecucao("Programa excedeu o número máximo de passos (possível loop infinito).")
        if _time.time() - self._inicio > self._max_segundos:
            raise ErroExecucao("Programa excedeu o tempo máximo de execução.")

    def _executar(self, instrucao, ambiente):
        self._checar_limites()
        metodo = getattr(self, f"_exec_{type(instrucao).__name__}")
        return metodo(instrucao, ambiente)

    def _executar_bloco(self, instrucoes, ambiente):
        for instrucao in instrucoes:
            self._executar(instrucao, ambiente)

    def _exec_ExpressaoInstrucao(self, instrucao, ambiente):
        self._avaliar(instrucao.expressao, ambiente)

    def _exec_ImprimeInstrucao(self, instrucao, ambiente):
        valor = self._avaliar(instrucao.expressao, ambiente)
        self.saida.append(_formatar(valor))

    def _exec_VarInstrucao(self, instrucao, ambiente):
        valor = None
        if instrucao.inicializador is not None:
            valor = self._avaliar(instrucao.inicializador, ambiente)
        ambiente.definir(instrucao.nome, valor)

    def _exec_BlocoInstrucao(self, instrucao, ambiente):
        self._executar_bloco(instrucao.instrucoes, Ambiente(ambiente))

    def _exec_SeInstrucao(self, instrucao, ambiente):
        if _eh_verdadeiro(self._avaliar(instrucao.condicao, ambiente)):
            self._executar(instrucao.ramo_entao, ambiente)
        elif instrucao.ramo_senao is not None:
            self._executar(instrucao.ramo_senao, ambiente)

    def _exec_EnquantoInstrucao(self, instrucao, ambiente):
        while _eh_verdadeiro(self._avaliar(instrucao.condicao, ambiente)):
            self._checar_limites()
            try:
                self._executar(instrucao.corpo, ambiente)
            except _QuebraSinal:
                break
            except _ContinuaSinal:
                continue

    def _exec_ParaInstrucao(self, instrucao, ambiente):
        # Escopo próprio pro inicializador, igual um bloco faria --
        # assim "para (var i = 0; ...)" não vaza `i` pro escopo de fora.
        ambiente_para = Ambiente(ambiente)
        if instrucao.inicializador is not None:
            self._executar(instrucao.inicializador, ambiente_para)
        while _eh_verdadeiro(self._avaliar(instrucao.condicao, ambiente_para)):
            self._checar_limites()
            try:
                self._executar(instrucao.corpo, ambiente_para)
            except _QuebraSinal:
                break
            except _ContinuaSinal:
                pass  # cai direto pro incremento abaixo -- mesmo comportamento de um 'continue' de verdade
            if instrucao.incremento is not None:
                self._avaliar(instrucao.incremento, ambiente_para)

    def _exec_FuncInstrucao(self, instrucao, ambiente):
        ambiente.definir(instrucao.nome, FuncaoJarvisScript(instrucao, ambiente))

    def _exec_RetornaInstrucao(self, instrucao, ambiente):
        valor = None
        if instrucao.valor is not None:
            valor = self._avaliar(instrucao.valor, ambiente)
        raise _RetornoSinal(valor)

    def _exec_QuebraInstrucao(self, instrucao, ambiente):
        raise _QuebraSinal()

    def _exec_ContinuaInstrucao(self, instrucao, ambiente):
        raise _ContinuaSinal()

    # ---------- expressões ----------
    def _avaliar(self, expressao, ambiente):
        metodo = getattr(self, f"_aval_{type(expressao).__name__}")
        return metodo(expressao, ambiente)

    def _aval_Literal(self, expressao, ambiente):
        return expressao.valor

    def _aval_ListaLiteral(self, expressao, ambiente):
        return [self._avaliar(e, ambiente) for e in expressao.elementos]

    def _aval_Variavel(self, expressao, ambiente):
        return ambiente.obter(expressao.nome)

    def _aval_Atribuicao(self, expressao, ambiente):
        valor = self._avaliar(expressao.valor, ambiente)
        ambiente.atribuir(expressao.nome, valor)
        return valor

    def _aval_AtribuicaoIndexada(self, expressao, ambiente):
        alvo = self._avaliar(expressao.alvo, ambiente)
        indice = self._avaliar(expressao.indice, ambiente)
        valor = self._avaliar(expressao.valor, ambiente)
        if not isinstance(alvo, list):
            raise ErroExecucao("Só é possível atribuir por índice numa lista.")
        try:
            alvo[int(indice)] = valor
        except (IndexError, TypeError) as e:
            raise ErroExecucao(f"Erro ao atribuir por índice: {e}")
        return valor

    def _aval_Unario(self, expressao, ambiente):
        direita = self._avaliar(expressao.direita, ambiente)
        if expressao.operador == "MENOS":
            return -direita
        if expressao.operador in ("NAO", "NAO_SIMBOLO"):
            return not _eh_verdadeiro(direita)
        raise ErroExecucao(f"Operador unário desconhecido: {expressao.operador}")

    def _aval_Logico(self, expressao, ambiente):
        esquerda = self._avaliar(expressao.esquerda, ambiente)
        if expressao.operador == "OU":
            if _eh_verdadeiro(esquerda):
                return esquerda
        else:  # E
            if not _eh_verdadeiro(esquerda):
                return esquerda
        return self._avaliar(expressao.direita, ambiente)

    def _aval_Binario(self, expressao, ambiente):
        esquerda = self._avaliar(expressao.esquerda, ambiente)
        direita = self._avaliar(expressao.direita, ambiente)
        op = expressao.operador
        try:
            if op == "MAIS":
                return esquerda + direita
            if op == "MENOS":
                return esquerda - direita
            if op == "VEZES":
                return esquerda * direita
            if op == "DIVIDE":
                return esquerda / direita
            if op == "PORCENTO":
                return esquerda % direita
            if op == "MENOR":
                return esquerda < direita
            if op == "MENOR_IGUAL":
                return esquerda <= direita
            if op == "MAIOR":
                return esquerda > direita
            if op == "MAIOR_IGUAL":
                return esquerda >= direita
            if op == "IGUAL_IGUAL":
                return esquerda == direita
            if op == "DIFERENTE":
                return esquerda != direita
        except (TypeError, ZeroDivisionError) as e:
            raise ErroExecucao(f"Erro na operação '{op}': {e}")
        raise ErroExecucao(f"Operador binário desconhecido: {op}")

    def _aval_Chamada(self, expressao, ambiente):
        callee = self._avaliar(expressao.callee, ambiente)
        argumentos = [self._avaliar(a, ambiente) for a in expressao.argumentos]
        if isinstance(callee, FuncaoJarvisScript):
            return callee.chamar(self, argumentos)
        if callable(callee):
            return callee(argumentos)
        raise ErroExecucao("Só é possível chamar funções.")

    def _aval_Indexacao(self, expressao, ambiente):
        alvo = self._avaliar(expressao.alvo, ambiente)
        indice = self._avaliar(expressao.indice, ambiente)
        try:
            return alvo[int(indice)]
        except (IndexError, TypeError) as e:
            raise ErroExecucao(f"Erro ao indexar: {e}")
