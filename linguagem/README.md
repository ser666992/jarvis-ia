# linguagem/ — JarvisScript

A linguagem de programação **própria** do Jarvis: pequena, mas real —
léxico, sintaxe e interpretador escritos do zero em Python puro (sem
nenhuma dependência, nem da stdlib além de `dataclasses`/`time`). Não é
uma "brincadeira de fachada": tem variáveis, funções (com closures),
`se`/`senao`, `enquanto`, `para` (com `quebra`/`continua`), listas
(com atribuição por índice), operadores compostos (`+=` etc.), e trata
erro de sintaxe/execução de verdade.

100% **sandboxed por construção** — não existe NENHUM jeito de ler/
escrever arquivo, acessar rede, importar módulo Python, ou fazer
qualquer coisa fora da própria linguagem. Rodar um programa JarvisScript
nunca é uma ação destrutiva, mesmo vindo de uma fonte não confiável.
Também tem teto de passos e de tempo (`Interpretador(max_passos=...,
max_segundos=...)`) — um `enquanto` infinito aborta sozinho em vez de
travar a thread que chamou.

Este documento tem duas partes: **como usar** a JarvisScript (seções
1-4) e **como QUALQUER linguagem de programação é construída**, usando
a JarvisScript como exemplo real e funcionando do início ao fim (seção
5 em diante) — pra quem quer entender o assunto de verdade, não só
usar o resultado pronto.

---

## 1. Sintaxe

```
var nome = "mundo";
imprime "olá, " + nome;

func soma(a, b) {
    retorna a + b;
}
imprime soma(2, 3);

var i = 0;
enquanto (i < 5) {
    imprime i;
    i = i + 1;
}

para (var j = 0; j < 3; j = j + 1) {
    imprime "j = " + str(j);
}

var lista = [1, 2, 3];
imprime lista[1];      # 2
imprime len(lista);    # 3
lista[0] = 99;         # atribuição por índice
lista[1] += 10;        # também funciona com operador composto

var contador = 0;
para (var k = 0; k < 10; k = k + 1) {
    se (k == 5) { quebra; }       # sai do laço na hora
    se (k % 2 == 0) { continua; } # pula pro próximo k sem rodar o resto do corpo
    contador += 1;
}

se (soma(2, 2) == 4) {
    imprime "matemática funciona";
} senao {
    imprime "algo muito errado aconteceu";
}
```

Palavras-chave: `var`, `func`, `se`/`senao`, `enquanto`, `para`,
`quebra`, `continua`, `retorna`, `imprime`, `verdadeiro`/`falso`,
`nulo`, `e`/`ou`/`nao`.

Operadores: `+ - * / %`, atribuição composta `+= -= *= /=`, comparação
`== != < > <= >=`, lógicos `e`/`ou`/`nao`. Comentários com `#` ou `//`.

Builtins disponíveis: `len(x)`, `str(x)`, `num(x)`, `tempo()`.

## 2. Arquitetura (visão rápida)

```
lexer.py         texto fonte -> lista de Token
ast_nodes.py      classes de nó da árvore sintática (sem lógica)
parser.py         tokens -> AST (recursivo descendente, "Crafting Interpreters"-style)
interpretador.py  percorre a AST e executa ("tree-walking")
```

Os operadores compostos (`+=`, `-=`, `*=`, `/=`) são desaçucarados
direto em `atribuicao`/`atribuicao_indexada` dentro do parser — o
interpretador nem sabe que operador composto existe, só atribuição
simples. Isso é uma técnica real de design de linguagem chamada
**dessaçucaramento** ("desugaring"): em vez de dar suporte nativo a
todo recurso na etapa de execução, você reescreve o recurso "com
açúcar" (mais confortável de escrever) em termos de um recurso mais
simples que já existe. Menos código pra manter, menos chance de bug.

`para (init; cond; incr) corpo` JÁ FOI desaçucarado em `enquanto`
desse jeito, mas deixou de ser -- teve nó próprio (`ParaInstrucao`)
adicionado de volta quando `quebra`/`continua` foram implementados,
porque desaçucaramento nem sempre é a escolha certa (ver seção 5.7,
"Armadilhas comuns", pro relato completo de por quê).

## 3. Uso programático

```python
from linguagem import executar

saida, erro = executar('imprime "oi";')
# saida == "oi", erro is None

saida, erro = executar('imprime 1 / 0;')
# erro == "Erro na operação 'DIVIDE': ..."
```

## 4. Uso pelo chat

```
roda em jarvisscript: var x = 10; imprime x * 2;
o que é jarvisscript
```
Ver `plugins/linguagem_propria.py`.

---

## 5. Como QUALQUER linguagem de programação é construída

Toda linguagem — de brinquedo como esta, ou de produção como Python,
Rust, Go — passa pelas MESMAS quatro etapas, nesta ordem. Elas são
independentes: você pode trocar a implementação de uma sem mexer nas
outras, contanto que a interface entre elas (o formato de dados que uma
etapa produz e a próxima consome) continue igual.

```
texto fonte
    │  1. GRAMÁTICA (decisão de design, não é código)
    ▼
   [Léxico / Lexer]           texto  -> tokens
    │
    ▼
   [Sintaxe / Parser]         tokens -> árvore sintática (AST)
    │
    ▼
   [Execução / Interpretador] AST    -> resultado (ou bytecode, se for compilada)
```

### 5.1 Etapa 0: Gramática -- decidir a sintaxe ANTES de escrever código

Antes de escrever uma linha de lexer ou parser, você precisa decidir
COMO a linguagem vai se parecer. Isso se escreve numa notação chamada
**BNF** ou **EBNF** (Backus-Naur Form / Extended BNF) — uma forma
compacta de descrever "uma expressão é isto, ou aquilo, ou aquilo
outro". A gramática completa da JarvisScript (o que `parser.py`
implementa, método por método):

```ebnf
programa      = declaracao* EOF ;

declaracao    = decl_var | decl_func | instrucao ;
decl_var      = "var" IDENT ("=" expressao)? ";" ;
decl_func     = "func" IDENT "(" parametros? ")" bloco ;
parametros    = IDENT ("," IDENT)* ;

instrucao     = expr_stmt | se_stmt | enquanto_stmt | para_stmt
              | quebra_stmt | continua_stmt
              | retorna_stmt | imprime_stmt | bloco ;
expr_stmt     = expressao ";" ;
se_stmt       = "se" "(" expressao ")" instrucao ("senao" instrucao)? ;
enquanto_stmt = "enquanto" "(" expressao ")" instrucao ;
para_stmt     = "para" "(" (decl_var | expr_stmt | ";") expressao? ";" expressao? ")" instrucao ;
quebra_stmt   = "quebra" ";" ;
continua_stmt = "continua" ";" ;
retorna_stmt  = "retorna" expressao? ";" ;
imprime_stmt  = "imprime" expressao ";" ;
bloco         = "{" declaracao* "}" ;

expressao     = atribuicao ;
atribuicao    = alvo_atribuivel ("=" | "+=" | "-=" | "*=" | "/=") atribuicao
              | logico_ou ;
alvo_atribuivel = IDENT | IDENT "[" expressao "]" ;
logico_ou     = logico_e ("ou" logico_e)* ;
logico_e      = igualdade ("e" igualdade)* ;
igualdade     = comparacao (("==" | "!=") comparacao)* ;
comparacao    = termo (("<" | "<=" | ">" | ">=") termo)* ;
termo         = fator (("+" | "-") fator)* ;
fator         = unario (("*" | "/" | "%") unario)* ;
unario        = ("nao" | "-") unario | chamada ;
chamada       = primario ( "(" argumentos? ")" | "[" expressao "]" )* ;
primario      = NUMERO | STRING | "verdadeiro" | "falso" | "nulo"
              | IDENT | "(" expressao ")" | lista ;
lista         = "[" (expressao ("," expressao)*)? "]" ;
```

(`alvo_atribuivel` é uma simplificação da gramática real: o parser não
decide "isto é um alvo atribuível" antecipadamente -- ele parseia
`logico_ou` normalmente e só DEPOIS, se encontrar `=`/`+=`/etc. em
seguida, verifica se o que já parseou é um `Variavel` ou `Indexacao`
válido, e rejeita com `ErroSintaxe` se não for. Ver `_construir_atribuicao`.)

Duas decisões de design importantes já aparecem aqui, e valem pra
qualquer linguagem que você for criar:

- **Precedência de operadores vira ordem de regras.** Note que
  `atribuicao` chama `logico_ou`, que chama `logico_e`, que chama
  `igualdade`... até `primario`. Cada nível só "enxerga" os operadores
  daquele nível — é assim que `2 + 3 * 4` vira `2 + (3 * 4)` e não
  `(2 + 3) * 4`: `fator` (que trata `*`) fica MAIS PERTO de `primario`
  (os valores) do que `termo` (que trata `+`), então o `*` "aperta"
  primeiro. Essa técnica se chama **precedence climbing** — é o jeito
  padrão de codificar prioridade de operador numa gramática recursiva.
- **Ambiguidade tem que ser resolvida na gramática, não no código.**
  Se duas regras pudessem casar a mesma entrada de jeitos diferentes, a
  linguagem seria ambígua — o parser não saberia qual escolher. A
  gramática acima é desenhada pra nunca ter essa dúvida.

### 5.2 Etapa 1: Léxico (Lexer) — texto vira tokens

Arquivo: `lexer.py`. Um **lexer** (também chamado *tokenizer* ou
*scanner*) lê o texto fonte caractere por caractere e agrupa em
**tokens** — a menor unidade com significado (um número, um nome de
variável, uma palavra-chave, um símbolo). Ele NÃO entende a estrutura
da linguagem ainda — só reconhece "isto aqui parece um número", "isto
aqui é a palavra 'se'", sem saber se faz sentido onde está.

```python
# lexer.py -- ideia central, resumida
class Token:
    tipo: str       # ex.: "NUMERO", "IDENT", "MAIS", "SE"
    lexema: str     # o texto original, ex.: "42"
    literal: object  # o valor já convertido, ex.: 42 (int)
    linha: int      # pra mensagens de erro apontarem o lugar certo

class Lexer:
    def tokenizar(self):
        while not self._fim():
            self._escanear_token()   # decide o tipo de UM token e avança
        ...
```

Pontos que valem pra qualquer lexer que você for escrever:

- **Máximo munch**: sempre consome o MAIOR token possível naquela
  posição. `<=` é um token só (`MENOR_IGUAL`), não dois tokens `<` e
  `=` — por isso `_proximo_igual()` espia o próximo caractere antes de
  decidir.
- **Palavras-chave são identificadores especiais**: o lexer lê
  `enquanto` como um identificador comum primeiro (letras/números), e
  SÓ DEPOIS confere se esse texto está na lista de palavras reservadas
  (`PALAVRAS_CHAVE`) — daí decide se o token é `ENQUANTO` ou `IDENT`.
  Fazer diferente (tentar casar palavra-chave letra por letra antes de
  identificador) deixa o lexer muito mais lento e complicado.
- **Comentários e espaços em branco são descartados aqui**, nunca
  chegam ao parser — por isso `parser.py` não precisa saber que `#` e
  `//` existem.

### 5.3 Etapa 2: Sintaxe (Parser) — tokens viram uma árvore (AST)

Arquivos: `parser.py` (a lógica) + `ast_nodes.py` (as "caixinhas" de
dados que representam cada pedaço do programa). Um **parser** lê a
sequência linear de tokens e monta uma estrutura em ÁRVORE — a **AST**
(*Abstract Syntax Tree*) — que representa como as partes do programa se
encaixam. `2 + 3 * 4` vira uma árvore onde a MULTIPLICAÇÃO fica mais
funda (calculada primeiro):

```
        Binario(+)
        /        \
   Literal(2)   Binario(*)
                /        \
           Literal(3)   Literal(4)
```

A técnica usada aqui — **recursivo descendente** (*recursive descent*)
— é a mais comum pra escrever um parser à mão: uma função Python PARA
CADA regra da gramática, e cada função chama a de baixo (mais
precedência) até achar algo concreto, subindo de volta montando os nós:

```python
# parser.py -- o mesmo esqueleto se repete pra cada nível de precedência
def _termo(self):
    expr = self._fator()                    # desce primeiro (mais prioridade)
    while self._combina("MAIS", "MENOS"):    # depois olha o nível dele mesmo
        operador = self._anterior().tipo
        direita = self._fator()
        expr = no.Binario(expr, operador, direita)
    return expr
```

Pontos que valem pra qualquer parser recursivo descendente:

- **Cada função de precedência SEMPRE chama a de baixo primeiro.** É
  isso que implementa a precedência de operadores decidida na
  gramática (seção 5.1) — sem precisar de nenhuma tabela de precedência
  numérica.
- **AST não tem lógica, só estrutura.** Olhe `ast_nodes.py`: são só
  classes com `__init__` guardando os pedaços (`Binario` guarda
  esquerda/operador/direita). Quem DECIDE o que `+` significa é o
  interpretador (etapa 3), não o nó da árvore.
- **Dessaçucaramento acontece aqui (quando faz sentido).**
  `_atribuicao()` reconhece `+=`/`-=`/`*=`/`/=` e monta direto um
  `Atribuicao`/`AtribuicaoIndexada` com um `Binario` por dentro (`i +=
  1` vira o mesmo nó que `i = i + 1` produziria) — o interpretador nem
  sabe que operador composto existe. Ver seção 2 pro caso em que
  dessaçucarar **parecia** a escolha certa (`para`) mas não era.
- **Erros de sintaxe viram exceção com a linha certa.** `_espera()`
  levanta `ErroSintaxe` com a linha do token errado assim que a
  gramática não bate — é assim que `executar('var x = 5')` (sem `;`)
  devolve uma mensagem apontando exatamente onde faltou o `;`.

### 5.4 Etapa 3: Execução (Interpretador) — a AST vira um resultado

Arquivo: `interpretador.py`. Aqui é onde a árvore da etapa 2
finalmente FAZ alguma coisa. A JarvisScript usa a abordagem mais
simples que existe — **tree-walking**: percorre a AST recursivamente,
executando cada nó conforme visita (o oposto de compilar pra bytecode
e rodar numa máquina virtual, que é mais rápido mas muito mais
trabalho de implementar).

```python
# interpretador.py -- um "case" por tipo de nó, com despacho por nome de classe
def _avaliar(self, expressao, ambiente):
    metodo = getattr(self, f"_aval_{type(expressao).__name__}")
    return metodo(expressao, ambiente)

def _aval_Binario(self, expressao, ambiente):
    esquerda = self._avaliar(expressao.esquerda, ambiente)
    direita = self._avaliar(expressao.direita, ambiente)
    if expressao.operador == "MAIS":
        return esquerda + direita
    ...
```

Conceitos-chave de qualquer interpretador tree-walking:

- **Ambiente (Environment) = onde as variáveis moram.** A classe
  `Ambiente` guarda um dicionário `valores` + uma referência pro
  `pai` (o ambiente de fora). Entrar num bloco `{ }` cria um `Ambiente`
  NOVO com o de fora como pai (`_exec_BlocoInstrucao`); procurar uma
  variável (`obter()`) sobe a cadeia de pais até achar ou dar erro.
  Isso é o que implementa **escopo**: uma variável criada dentro de um
  `se { }` desaparece ao sair do bloco, mas ainda enxerga variáveis de
  fora.
- **Função com closure = a função guarda o ambiente de quando foi
  DEFINIDA.** `FuncaoJarvisScript.__init__` guarda `closure` (o
  ambiente de quando o `func` foi declarado); ao CHAMAR a função,
  cria um ambiente novo com esse `closure` como pai, não o ambiente de
  quem está chamando. É isso que permite uma função enxergar variáveis
  do lugar onde foi criada, mesmo chamada de um lugar diferente.
- **`retorna` é implementado com uma exceção interna** (`_RetornoSinal`)
  — não é um erro de verdade, é só um jeito de "pular" fora de quantos
  blocos/laços forem necessários até voltar pra quem chamou a função,
  carregando o valor. Truque comum em interpretadores tree-walking.
- **Limites de segurança são responsabilidade do interpretador, não da
  gramática.** `_checar_limites()` conta passos e tempo decorrido a
  cada instrução/laço — sem isso, `enquanto (verdadeiro) { }` travaria
  a thread pra sempre. Qualquer linguagem que aceite código de fontes
  não 100% confiáveis (inclusive as suas próprias, geradas por IA)
  precisa disso.

### 5.5 Decisões de design que você precisa tomar pra criar a sua

Toda linguagem nova exige escolher uma posição em cada um destes eixos
— não tem resposta "certa", só trade-offs:

| Decisão | O que a JarvisScript escolheu | Alternativa |
|---|---|---|
| Tipagem | Dinâmica (tipo descoberto em tempo de execução) | Estática (tipo checado antes de rodar, precisa de uma etapa de análise semântica a mais) |
| Execução | Interpretada, tree-walking direto na AST | Compilada pra bytecode + máquina virtual (mais rápida, muito mais código) |
| Escopo | Léxico (a variável pertence a onde foi ESCRITA no código) | Dinâmico (pertence a quem CHAMOU) -- bem mais raro e geralmente confuso |
| Erros | Exceção Python interna, para a execução | "Recuperar" e continuar (mais complexo, raramente vale a pena numa linguagem pequena) |
| Acesso externo | Nenhum -- sandboxed 100% | Biblioteca padrão com arquivo/rede (exige pensar em segurança com cuidado) |

### 5.6 Exemplo guiado: adicionando um recurso novo (caso real, não hipotético)

Esta seção costumava descrever um `+=` hipotético. Ele foi implementado
de verdade desde então (junto de `quebra`/`continua` e atribuição por
índice), então agora dá pra mostrar o fluxo com o histórico real das
decisões tomadas -- inclusive uma que precisou ser desfeita.

1. **Gramática**: decidida primeiro, por escrito (seção 5.1):
   `atribuicao = alvo_atribuivel ("=" | "+=" | "-=" | "*=" | "/=") atribuicao | logico_ou`.
2. **Lexer**: `_escanear_token()` ganhou um `elif` pra cada operador
   composto (`+`, `-`, `*`, `/`), cada um espiando se o próximo
   caractere é `=` (mesma técnica de "máximo munch" que `<=`/`>=` já
   usavam) -- ver `lexer.py`.
3. **AST**: nenhum nó novo pra `+=` em si -- ele desaçucara em
   `Atribuicao`/`AtribuicaoIndexada` com um `Binario` por dentro. Só
   precisou de um nó novo (`AtribuicaoIndexada`) pra viabilizar
   `lista[i] = valor` funcionar em primeiro lugar (antes só existia
   atribuição a variável simples).
4. **Parser**: `_atribuicao()` ganhou um segundo `if` (depois do `=`
   já existente) pra combinar os 4 tokens compostos, mapear pro
   operador binário equivalente, e montar `Binario(alvo, op, valor)`
   dentro de uma atribuição normal -- ver `_construir_atribuicao`.
5. **Interpretador**: zero código novo pra `+=` em si (reusa
   `_aval_Atribuicao`/`_aval_AtribuicaoIndexada`/`_aval_Binario` que já
   existiam) -- exatamente o benefício de desaçucarar bem escolhido.
6. **Testar**: cobrir `+=`/`-=`/`*=`/`/=` em variável simples, em
   elemento de lista, e com string (concatenação) -- todos passaram de
   primeira.

Só que "quebra"/"continua" (mesmo processo, gramática → lexer → AST →
parser → interpretador com uma exceção Python interna, igual `retorna`
já fazia) revelou um problema em uma decisão de design ANTIGA, que
tinha sido tomada com boa razão na hora mas parou de valer: ver seção
5.7 pro relato completo.

### 5.7 Um caso real de dessaçucaramento que precisou ser desfeito

Antes de `quebra`/`continua` existirem, `para (init; cond; incr) corpo`
era desaçucarado 100% em `enquanto` (seção 2 explicava esse desenho, e
ele era correto NAQUELE momento -- sem nenhum jeito de pular pro
"próximo passo do laço" no meio do corpo, não importava que o corpo e
o incremento estivessem embrulhados juntos no mesmo bloco).

Ao implementar `continua`, o teste `continua pula iteracao` (uma soma
de `para` pulando um índice) travou -- estourou o teto de segurança de
passos (`ErroExecucao: excedeu o número máximo de passos`), sinal de
loop infinito. A causa: o desaçucaramento antigo montava o corpo do
`para` como `BlocoInstrucao([corpo_original, incremento])` -- UM bloco
só, com o incremento DENTRO dele, depois do corpo do usuário. Quando
`continua` lançava seu sinal de dentro do corpo original, a exceção
saía direto desse bloco combinado inteiro (pulando o incremento
também) até ser capturada lá em cima, em `_exec_EnquantoInstrucao` --
ou seja, a variável do laço nunca avançava, e a condição continuava
verdadeira pra sempre.

A correção foi desfazer o desaçucaramento: `para` ganhou um nó próprio
(`ParaInstrucao`, com `inicializador`/`condicao`/`incremento`/`corpo`
SEPARADOS) e um `_exec_ParaInstrucao` dedicado, que captura `continua`
ao redor SÓ do corpo -- e roda o incremento de qualquer jeito, capturado
ou não, antes de reavaliar a condição:

```python
def _exec_ParaInstrucao(self, instrucao, ambiente):
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
            pass  # cai direto pro incremento -- mesmo comportamento de um 'continue' de verdade
        if instrucao.incremento is not None:
            self._avaliar(instrucao.incremento, ambiente_para)
```

**A lição, que vale pra qualquer linguagem que você for construir**:
dessaçucaramento é uma ótima técnica, mas o resultado só continua
correto enquanto a linguagem não ganha um jeito de "pular" fora do meio
de uma estrutura (exceção, `goto`, `continue`, `break`...). Adicionar
controle de fluxo não-linear é o gatilho clássico pra revisitar
decisões de dessaçucaramento antigas -- e é exatamente por isso que
"Crafting Interpreters" (seção 5.9) trata `break`/`continue` como um
dos capítulos mais delicados do livro, não um exercício trivial de
"só adicionar mais um `if`".

### 5.8 Armadilhas comuns (que esta implementação já evitou -- ou já caiu e corrigiu)

- **Não validar novamente uma condição pra cada iteração de laço sem
  necessidade** -- `_exec_EnquantoInstrucao`/`_exec_ParaInstrucao`
  reavaliam a condição a cada volta, correto; um erro comum é cachear
  o valor da primeira vez.
- **Esquecer de checar limites DENTRO do laço**, só na entrada da
  função -- por isso `_checar_limites()` é chamado tanto em
  `_executar()` (a cada instrução) quanto explicitamente dentro do
  `while` de `_exec_EnquantoInstrucao`/`_exec_ParaInstrucao`.
- **Deixar escopo vazar** -- se `Ambiente` não criasse um filho novo a
  cada bloco (`_exec_BlocoInstrucao`) e a cada `para` (o
  `ambiente_para` de `_exec_ParaInstrucao`), uma variável declarada
  dentro de um `se { }` ou do inicializador de um `para` continuaria
  visível depois dele, o que é um bug clássico de implementação de
  escopo.
- **Misturar erro de sintaxe com erro de execução** -- são fases
  diferentes (parser vs. interpretador) por um motivo: erro de sintaxe
  significa "o programa nem é válido, não rodou nada"; erro de
  execução significa "o programa era válido, mas algo deu errado
  rodando" (divisão por zero, variável inexistente). Reportar os dois
  do mesmo jeito confunde quem está depurando.
- **Desaçucarar um laço "para" embrulhando corpo+incremento no mesmo
  bloco** -- parece inofensivo até a linguagem ganhar `continua`, que
  aí escapa do bloco inteiro (incremento junto) e trava a variável do
  laço pra sempre. Ver seção 5.7 pro relato completo -- é o exemplo
  mais concreto deste documento inteiro de "parecia certo, e era, até
  deixar de ser".
- **`quebra`/`continua` vazando pra fora de onde fazem sentido** -- sem
  capturar esses sinais também em `FuncaoJarvisScript.chamar()` (limite
  de chamada de função) e em `Interpretador.executar()` (nível mais
  externo do programa), um `quebra;` solto fora de qualquer laço, ou
  dentro de uma função chamada de dentro do laço de QUEM CHAMOU,
  produziria um comportamento surpreendente (ou uma exceção Python
  crua vazando) em vez de um erro claro.

### 5.9 Pra aprender mais (fora deste projeto)

- *Crafting Interpreters*, de Robert Nystrom (livro gratuito online) —
  é literalmente o desenho que esta implementação segue (linguagem
  "Lox" em vez de JarvisScript, em Java/C em vez de Python), explicado
  passo a passo com muito mais profundidade.
- *Writing An Interpreter In Go*, de Thorsten Ball — mesmo assunto,
  outra linguagem de implementação.

---

## Limitações honestas

- Sem tipos definidos pelo usuário (struct/classe) — só número, string,
  booleano, nulo e lista.
- Sem mapas/dicionários (chave -> valor) — só lista indexada por
  número. Ficou de fora de propósito: `{` já é usado pra bloco de
  código, então dar suporte a `{chave: valor}` como literal de mapa
  exigiria o parser decidir qual dos dois significados vale ao ver um
  `{` numa posição de expressão — resolvível (a maioria das linguagens
  reais resolve isso de algum jeito), mas é complexidade real, não
  proporcional ao que esta linguagem se propõe a ser.
- Sem strings com métodos (`.upper()` etc.) — use os builtins.
- Sem módulos/imports — cada programa é um arquivo só.
- É uma linguagem de brinquedo real, não uma linguagem de produção —
  não espere um ecossistema, só a satisfação de "o Jarvis tem uma
  linguagem própria de verdade, que eu posso rodar e testar", e agora
  também entender como foi construída de ponta a ponta.
