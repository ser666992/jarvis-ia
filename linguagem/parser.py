"""
linguagem/parser.py
======================
Parser recursivo descendente da UltronScript: tokens (linguagem/lexer.py)
-> árvore sintática (linguagem/ast_nodes.py). Segue a precedência
clássica de expressões (atribuição < ou < e < igualdade < comparação <
termo < fator < unário < chamada < primário) -- mesmo esquema usado por
praticamente todo interpretador recursivo descendente (ver "Crafting
Interpreters", de onde esse desenho vem).

"para (init; cond; incr) corpo" tem nó próprio (ParaInstrucao) em vez
de ser desaçucarado em "enquanto" -- ver o comentário em
ast_nodes.ParaInstrucao pra entender por quê (tem a ver com "continua"
precisar rodar o incremento antes de reavaliar a condição). Já os
operadores compostos (`+=`, `-=`, `*=`, `/=`) continuam sendo açúcar
sintático de verdade: viram `alvo = alvo <op> valor` já aqui no parser
(ver `_atribuicao`/`_construir_atribuicao`), então o interpretador só
conhece atribuição simples e indexada.
"""

from linguagem import ast_nodes as no


class ErroSintaxe(Exception):
    pass


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.atual = 0

    # ---------- utilidades ----------
    def _verifica(self, *tipos) -> bool:
        return not self._fim() and self._token_atual().tipo in tipos

    def _fim(self) -> bool:
        return self._token_atual().tipo == "EOF"

    def _token_atual(self):
        return self.tokens[self.atual]

    def _anterior(self):
        return self.tokens[self.atual - 1]

    def _avancar(self):
        if not self._fim():
            self.atual += 1
        return self._anterior()

    def _combina(self, *tipos) -> bool:
        if self._verifica(*tipos):
            self._avancar()
            return True
        return False

    def _espera(self, tipo, mensagem):
        if self._verifica(tipo):
            return self._avancar()
        atual = self._token_atual()
        raise ErroSintaxe(f"{mensagem} (linha {atual.linha}, achei '{atual.lexema}')")

    # ---------- programa ----------
    def parse(self):
        instrucoes = []
        while not self._fim():
            instrucoes.append(self._declaracao())
        return instrucoes

    def _declaracao(self):
        if self._combina("VAR"):
            return self._decl_var()
        if self._combina("FUNC"):
            return self._decl_func()
        return self._instrucao()

    def _decl_var(self):
        nome = self._espera("IDENT", "Esperava um nome de variável").lexema
        inicializador = None
        if self._combina("IGUAL"):
            inicializador = self._expressao()
        self._espera("PONTO_VIRGULA", "Esperava ';' depois da declaração de variável")
        return no.VarInstrucao(nome, inicializador)

    def _decl_func(self):
        nome = self._espera("IDENT", "Esperava um nome de função").lexema
        self._espera("PAREN_ESQ", "Esperava '(' depois do nome da função")
        parametros = []
        if not self._verifica("PAREN_DIR"):
            parametros.append(self._espera("IDENT", "Esperava nome de parâmetro").lexema)
            while self._combina("VIRGULA"):
                parametros.append(self._espera("IDENT", "Esperava nome de parâmetro").lexema)
        self._espera("PAREN_DIR", "Esperava ')' depois dos parâmetros")
        self._espera("CHAVE_ESQ", "Esperava '{' antes do corpo da função")
        corpo = self._bloco()
        return no.FuncInstrucao(nome, parametros, corpo)

    def _instrucao(self):
        if self._combina("SE"):
            return self._instrucao_se()
        if self._combina("ENQUANTO"):
            return self._instrucao_enquanto()
        if self._combina("PARA"):
            return self._instrucao_para()
        if self._combina("RETORNA"):
            return self._instrucao_retorna()
        if self._combina("QUEBRA"):
            self._espera("PONTO_VIRGULA", "Esperava ';' depois de 'quebra'")
            return no.QuebraInstrucao()
        if self._combina("CONTINUA"):
            self._espera("PONTO_VIRGULA", "Esperava ';' depois de 'continua'")
            return no.ContinuaInstrucao()
        if self._combina("IMPRIME"):
            return self._instrucao_imprime()
        if self._combina("CHAVE_ESQ"):
            return no.BlocoInstrucao(self._bloco())
        return self._instrucao_expressao()

    def _bloco(self):
        instrucoes = []
        while not self._verifica("CHAVE_DIR") and not self._fim():
            instrucoes.append(self._declaracao())
        self._espera("CHAVE_DIR", "Esperava '}' no final do bloco")
        return instrucoes

    def _instrucao_se(self):
        self._espera("PAREN_ESQ", "Esperava '(' depois de 'se'")
        condicao = self._expressao()
        self._espera("PAREN_DIR", "Esperava ')' depois da condição")
        ramo_entao = self._instrucao()
        ramo_senao = None
        if self._combina("SENAO"):
            ramo_senao = self._instrucao()
        return no.SeInstrucao(condicao, ramo_entao, ramo_senao)

    def _instrucao_enquanto(self):
        self._espera("PAREN_ESQ", "Esperava '(' depois de 'enquanto'")
        condicao = self._expressao()
        self._espera("PAREN_DIR", "Esperava ')' depois da condição")
        corpo = self._instrucao()
        return no.EnquantoInstrucao(condicao, corpo)

    def _instrucao_para(self):
        self._espera("PAREN_ESQ", "Esperava '(' depois de 'para'")
        if self._combina("PONTO_VIRGULA"):
            inicializador = None
        elif self._combina("VAR"):
            inicializador = self._decl_var()
        else:
            inicializador = self._instrucao_expressao()

        condicao = None
        if not self._verifica("PONTO_VIRGULA"):
            condicao = self._expressao()
        self._espera("PONTO_VIRGULA", "Esperava ';' depois da condição do 'para'")

        incremento = None
        if not self._verifica("PAREN_DIR"):
            incremento = self._expressao()
        self._espera("PAREN_DIR", "Esperava ')' depois das cláusulas do 'para'")

        corpo = self._instrucao()
        if condicao is None:
            condicao = no.Literal(True)
        return no.ParaInstrucao(inicializador, condicao, incremento, corpo)

    def _instrucao_retorna(self):
        valor = None
        if not self._verifica("PONTO_VIRGULA"):
            valor = self._expressao()
        self._espera("PONTO_VIRGULA", "Esperava ';' depois do 'retorna'")
        return no.RetornaInstrucao(valor)

    def _instrucao_imprime(self):
        valor = self._expressao()
        self._espera("PONTO_VIRGULA", "Esperava ';' depois do 'imprime'")
        return no.ImprimeInstrucao(valor)

    def _instrucao_expressao(self):
        expr = self._expressao()
        self._espera("PONTO_VIRGULA", "Esperava ';' depois da expressão")
        return no.ExpressaoInstrucao(expr)

    # ---------- expressões (precedência crescente) ----------
    def _expressao(self):
        return self._atribuicao()

    _COMPOSTOS_PARA_BINARIO = {
        "MAIS_IGUAL": "MAIS", "MENOS_IGUAL": "MENOS",
        "VEZES_IGUAL": "VEZES", "DIVIDE_IGUAL": "DIVIDE",
    }

    def _atribuicao(self):
        expr = self._logico_ou()
        if self._combina("IGUAL"):
            valor = self._atribuicao()
            return self._construir_atribuicao(expr, valor)
        if self._combina("MAIS_IGUAL", "MENOS_IGUAL", "VEZES_IGUAL", "DIVIDE_IGUAL"):
            # `alvo += valor` é açúcar sintático pra `alvo = alvo + valor` --
            # desaçucarado aqui mesmo no parser, então o interpretador nem
            # precisa saber que operador composto existe (mesma filosofia
            # já usada pra desaçucarar "para" em "enquanto").
            operador_binario = self._COMPOSTOS_PARA_BINARIO[self._anterior().tipo]
            incremento = self._atribuicao()
            novo_valor = no.Binario(expr, operador_binario, incremento)
            return self._construir_atribuicao(expr, novo_valor)
        return expr

    def _construir_atribuicao(self, expr, valor):
        if isinstance(expr, no.Variavel):
            return no.Atribuicao(expr.nome, valor)
        if isinstance(expr, no.Indexacao):
            return no.AtribuicaoIndexada(expr.alvo, expr.indice, valor)
        raise ErroSintaxe("Alvo de atribuição inválido")

    def _logico_ou(self):
        expr = self._logico_e()
        while self._combina("OU"):
            operador = self._anterior().tipo
            direita = self._logico_e()
            expr = no.Logico(expr, operador, direita)
        return expr

    def _logico_e(self):
        expr = self._igualdade()
        while self._combina("E"):
            operador = self._anterior().tipo
            direita = self._igualdade()
            expr = no.Logico(expr, operador, direita)
        return expr

    def _igualdade(self):
        expr = self._comparacao()
        while self._combina("IGUAL_IGUAL", "DIFERENTE"):
            operador = self._anterior().tipo
            direita = self._comparacao()
            expr = no.Binario(expr, operador, direita)
        return expr

    def _comparacao(self):
        expr = self._termo()
        while self._combina("MENOR", "MENOR_IGUAL", "MAIOR", "MAIOR_IGUAL"):
            operador = self._anterior().tipo
            direita = self._termo()
            expr = no.Binario(expr, operador, direita)
        return expr

    def _termo(self):
        expr = self._fator()
        while self._combina("MAIS", "MENOS"):
            operador = self._anterior().tipo
            direita = self._fator()
            expr = no.Binario(expr, operador, direita)
        return expr

    def _fator(self):
        expr = self._unario()
        while self._combina("VEZES", "DIVIDE", "PORCENTO"):
            operador = self._anterior().tipo
            direita = self._unario()
            expr = no.Binario(expr, operador, direita)
        return expr

    def _unario(self):
        if self._combina("NAO", "NAO_SIMBOLO", "MENOS"):
            operador = self._anterior().tipo
            direita = self._unario()
            return no.Unario(operador, direita)
        return self._chamada()

    def _chamada(self):
        expr = self._primario()
        while True:
            if self._combina("PAREN_ESQ"):
                argumentos = []
                if not self._verifica("PAREN_DIR"):
                    argumentos.append(self._expressao())
                    while self._combina("VIRGULA"):
                        argumentos.append(self._expressao())
                self._espera("PAREN_DIR", "Esperava ')' depois dos argumentos")
                expr = no.Chamada(expr, argumentos)
            elif self._combina("COLCH_ESQ"):
                indice = self._expressao()
                self._espera("COLCH_DIR", "Esperava ']' depois do índice")
                expr = no.Indexacao(expr, indice)
            else:
                break
        return expr

    def _primario(self):
        if self._combina("NUMERO", "STRING"):
            return no.Literal(self._anterior().literal)
        if self._combina("VERDADEIRO"):
            return no.Literal(True)
        if self._combina("FALSO"):
            return no.Literal(False)
        if self._combina("NULO"):
            return no.Literal(None)
        if self._combina("IDENT"):
            return no.Variavel(self._anterior().lexema)
        if self._combina("PAREN_ESQ"):
            expr = self._expressao()
            self._espera("PAREN_DIR", "Esperava ')' depois da expressão")
            return expr
        if self._combina("COLCH_ESQ"):
            elementos = []
            if not self._verifica("COLCH_DIR"):
                elementos.append(self._expressao())
                while self._combina("VIRGULA"):
                    elementos.append(self._expressao())
            self._espera("COLCH_DIR", "Esperava ']' no final da lista")
            return no.ListaLiteral(elementos)
        atual = self._token_atual()
        raise ErroSintaxe(f"Esperava uma expressão (linha {atual.linha}, achei '{atual.lexema}')")
