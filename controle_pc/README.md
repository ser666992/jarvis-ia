# controle_pc/ — Controle inteligente do computador (Módulo 2)

Módulo novo, adicionado sem alterar a arquitetura existente: API
interna pro "cérebro" do Jarvis (plugins, skill_forge, uma futura
lógica de decisão) pedir ações no computador -- mouse/teclado, abrir/
fechar/alternar programas, localizar e interagir com elementos de
interface, organizar janelas, ler/escrever arquivos, rodar comandos do
sistema, monitorar e encerrar processos.

**Reaproveita, não duplica.** Onde uma capacidade já existia
(`automacao.apps` para abrir/fechar programa, `automacao.janelas` para
minimizar/maximizar/focar, `sistema.processes` para listar processos),
este pacote só chama esse código já existente. Só ACRESCENTA o que
faltava: mouse/teclado, localizar elemento por texto/imagem, organizar
janelas em grade/cascata, ler/escrever conteúdo de arquivo, rodar
comando do sistema.

## Regra de permissão (nada novo -- mesma de sempre)

- **Reversível → sem confirmação**: mover mouse, clicar, digitar,
  pressionar tecla, focar janela, organizar janelas, ler arquivo,
  listar pasta, listar processos. É entrada simulada ou leitura, mesma
  categoria de `automacao/janelas.py` (que já documenta esse
  raciocínio: a janela/processo continua existindo, só muda de
  estado/nada muda).
- **Destrutivo/irreversível → exige `confirmed=True`**: rodar comando
  de sistema, escrever/sobrescrever arquivo, fechar programa, encerrar
  processo travado. Usa o MESMO `seguranca.permissions` de sempre --
  inclusive o toggle global `"não peça confirmação"` já existente
  funciona aqui igual em qualquer outro lugar do Jarvis.

Rodar um comando de sistema é a ação mais poderosa deste pacote --
por isso exige confirmação **sempre**, sem lista de "comandos
seguros" que o Jarvis tentaria adivinhar sozinho.

## Comandos de chat

```
executa o comando <cmd> no terminal, confirmo
organiza minhas janelas / organiza as janelas em cascata
clica no botão <nome> / clica em <nome>
clica no texto <texto> / clica em <texto> na tela   (via OCR, ver plugins/clicar_texto.py)
modo economia de energia / modo desempenho máximo / modo equilibrado
qual o plano de energia atual
```

**"clica no texto ..." vs. "clica no botão ..."**: são dois mecanismos
DIFERENTES, escolhidos por gatilho explícito pra não colidir. Sem a
palavra "texto"/sufixo "na tela", continua indo pro elemento por nome
acessível (UI Automation, mais rápido/confiável quando o app expõe
isso). Com "texto"/"na tela", usa OCR (`visao.ocr.localizar_texto_na_tela`)
pra achar QUALQUER texto visível na tela e clicar nele -- útil quando o
app não expõe árvore de acessibilidade (jogos, apps que renderizam a
própria UI) ou o "elemento" é só texto dentro de uma imagem.

A maior parte da API (mover mouse, digitar texto, ler arquivo, listar
processos...) não tem comando de chat dedicado -- não faz sentido pra
esse nível de granularidade. Ela existe pra outro CÓDIGO chamar
(plugins, skill_forge, etc.), ver "Uso programático" abaixo.

## Uso programático

```python
import controle_pc

controle_pc.mover_mouse(500, 300)
controle_pc.clicar(500, 300)
controle_pc.digitar_texto("olá")
controle_pc.pressionar_tecla("ctrl+s")

controle_pc.localizar_elemento(texto="Salvar")     # -> {"x", "y", "retangulo", "nome"} ou None
controle_pc.clicar_elemento(texto="Salvar")        # localiza e clica -> bool

controle_pc.alternar_para("bloco de notas")
controle_pc.organizar_janelas(modo="grade")        # ou "cascata"

controle_pc.ler_arquivo("C:/caminho/arquivo.txt")
controle_pc.escrever_arquivo("C:/caminho/novo.txt", "conteúdo", confirmed=True)
controle_pc.listar_pasta("C:/caminho")

controle_pc.abrir_programa("notepad")
controle_pc.fechar_programa("notepad", confirmed=True)
controle_pc.executar_comando("dir", confirmed=True)   # -> {"stdout", "stderr", "returncode", "timeout"}
controle_pc.listar_processos(limite=20)
controle_pc.encerrar_processo_travado("nome_ou_pid", confirmed=True)

controle_pc.listar_planos()              # -> [{"guid", "nome", "ativo"}, ...]
controle_pc.plano_ativo()                # -> {"guid", "nome", "ativo": True}
controle_pc.ativar_plano("alto desempenho")  # aceita apelido em português ou o nome local de verdade
```

## Localizar elemento por texto: como funciona e o que já foi corrigido

Usa UI Automation (`pywinauto`) pra procurar, entre os elementos da
janela em foco, um cujo nome acessível contenha o texto pedido --
muito mais confiável que decorar coordenada de pixel (que muda a cada
resolução/tema/janela).

**Dois bugs reais encontrados em teste e corrigidos**, ambos com
"encontrei um elemento" quando não deveria:

1. **Busca vazia batia com qualquer coisa** -- toda string contém a
   string vazia, então buscar `""` "encontrava" o primeiro elemento
   clicável da janela. Corrigido: busca vazia é recusada antes de
   procurar.
2. **Elementos de tipo "Text" (texto estático, não clicável) podiam
   "encontrar a si mesmos"** -- um painel de terminal mostrando a
   palavra buscada em algum lugar do texto exibido batia como se fosse
   um botão, com coordenadas sem sentido (às vezes fora da tela
   visível). Corrigido restringindo a busca a tipos genuinamente
   clicáveis (`Button`, `MenuItem`, `Menu`, `ListItem`, `TabItem`,
   `Hyperlink`, `CheckBox`, `RadioButton`, `ComboBox`, `SplitButton`) --
   um "Text" nunca é algo que faça sentido clicar.

## Bug real encontrado e corrigido: conflito de threading COM

Mesmo problema documentado em `visao_continua/README.md`: importar
`pywinauto` cedo demais (nível de módulo) podia causar
`RPC_E_CHANGED_MODE` se outra lib já tivesse inicializado COM antes,
na mesma thread, de um jeito incompatível. Corrigido adiando o import
pra dentro de `_localizar_por_texto()`, só na hora que alguém realmente
pede pra localizar/clicar em algo por nome.

## Limitações honestas

- `localizar_elemento`/`clicar_elemento` (por texto) só funcionam no
  Windows e só pra apps que expõem árvore de acessibilidade -- mesma
  limitação de `visao_continua/`.
- `organizar_janelas` reposiciona TODAS as janelas visíveis -- não dá
  pra escolher só algumas ainda.
- `executar_comando` roda no shell do sistema (`cmd.exe` no Windows) --
  qualquer coisa que você faria manualmente no terminal, pra melhor ou
  pra pior. A confirmação existe exatamente por isso.
- Mouse/teclado simulados (`pyautogui`) não sabem o que a ação vai
  CAUSAR dentro do programa focado -- clicar/digitar é só entrada
  simulada, a mesma limitação de qualquer automação de UI.
- "clica no texto ..." (OCR) depende de o texto estar realmente visível
  E legível na tela no momento do comando -- texto minúsculo,
  contraste ruim ou fonte incomum reduz a precisão do OCR, mesma
  limitação de qualquer leitura de tela (ver visao/README.md).
- `controle_pc.energia` (plano de energia) só funciona no Windows
  (`powercfg`); resolve o plano por nome local OU apelido comum em
  português, mas planos totalmente customizados com nome muito
  diferente dos três padrão podem não bater em nenhum apelido --
  nesse caso, use o nome local exato retornado por `listar_planos()`.
