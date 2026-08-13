# visao_continua/ — Visão contínua da tela (Módulo 1)

Módulo novo, adicionado sem alterar a arquitetura existente: mantém um
**estado estruturado sempre atualizado** do que está acontecendo na
tela, rodando em segundo plano. Diferente de dois recursos que já
existiam e continuam do jeito que estavam:

- `visao/observe.py` — um retrato pontual, sob demanda (uma função que
  você chama e recebe o estado NAQUELE instante).
- `plugins/observation.py` — você pede um comentário falado sobre o
  que parece que está fazendo, de vez em quando ou em tempo real.

Este módulo é diferente dos dois: mantém uma **memória contínua**
(últimas N observações) e um **estado consultável a qualquer momento**
por qualquer outra parte do Jarvis — inclusive alimentando
silenciosamente o contexto que a IA recebe (ver
`core/jarvis.py:_query_ia()`), sem precisar de nenhum comando do
usuário para isso acontecer.

## Desligado por padrão

`visao_continua.ativa` começa `false`. Diferente da maioria dos outros
módulos automáticos deste projeto (que assumem "provavelmente
inofensivo, ligado por padrão"), vigiar a tela o tempo todo é sensível
por natureza — mesmo sendo só a SUA tela, no seu computador, ela pode
mostrar senhas sendo digitadas, conversas privadas, dados financeiros.
Ligue explicitamente com `"liga a visão contínua"` (mesmo padrão
opt-in de `instagram.envio_automatico`).

## Como funciona (eficiência)

A cada tick (`visao_continua.intervalo_segundos`, 3s por padrão):

1. **Checagens baratas, sempre**: um novo screenshot reduzido a uma
   miniatura (~64×36, só slicing em numpy, sem biblioteca de
   redimensionamento) comparado ao anterior, e a lista de processos
   rodando (`psutil`, já rápido por natureza).
2. **Só roda a parte cara quando vale a pena**: OCR + enumeração de
   elementos de UI (via UI Automation, `pywinauto`) só acontecem se a
   miniatura mudou mais que `visao_continua.limiar_mudanca` (12.0 por
   padrão) OU se algum processo abriu/fechou. Sem isso, um monitor
   "contínuo" reprocessaria a mesma tela parada dezenas de vezes por
   minuto à toa.

Identificar botões/menus/caixas de diálogo usa a árvore de
acessibilidade que o próprio Windows já expõe (UI Automation via
`pywinauto`) em vez de tentar "ver" isso a partir de pixels — muito
mais barato e muito mais confiável do que treinar/rodar um modelo de
detecção de objetos pra essa finalidade.

"Programa travado" usa `IsHungAppWindow` (API do próprio Windows feita
exatamente pra isso) em vez de tentar inferir isso comparando pixels
(tela parada ≠ travado; vídeo tocando ≠ não travado).

## Assistência proativa (opt-in)

Desligado por padrão (`personalidade.assistencia_proativa`, `false`).
Quando ligado, e só quando a visão contínua já detectou sozinha o
evento `"possivel_erro_na_tela"` (ver limitação honesta abaixo -- é
casamento de palavra-chave, não compreensão de verdade), o Jarvis pede
pra IA configurada uma explicação curta do que o erro provavelmente
significa e um próximo passo, e avisa por notificação -- sem precisar
que você pergunte "o que está acontecendo". Notifica **uma vez por
erro** (assinatura = janela + trecho do texto visível): um erro que
continua parado na tela, junto de qualquer outra mudança visual
(cursor piscando, animação), não reavisa repetidamente. Sem nenhum
provedor de IA configurado, cai para uma mensagem genérica ("notei
algo que parece um erro em X") em vez de travar ou ficar em silêncio.

## Comandos

```
liga a visão contínua
desliga a visão contínua
o que está acontecendo na minha tela / o que você está vendo agora
```

## Uso programático

```python
import visao_continua

visao_continua.ligar()
visao_continua.estado_atual()
# {"janela": ..., "processo": ..., "texto_tela": ..., "elementos": [...],
#  "travada": False, "eventos": [...], "timestamp": ...}

visao_continua.historico(5)          # últimas 5 observações
visao_continua.descrever_para_prompt()  # resumo curto pra injetar em prompt de IA
visao_continua.parar()
```

## Limitações honestas

- Detecção de erro/atualização/download concluído é **casamento de
  palavra-chave** (pt/en) contra o texto/elementos vistos na tela — não
  é compreensão de linguagem de verdade. Pode ter falso positivo
  (a palavra aparece sem ser o evento real) e falso negativo (o evento
  aconteceu, mas o texto não bateu com nenhuma palavra-chave
  conhecida).
- OCR (`texto_tela`) continua exigindo `pytesseract` + o binário
  Tesseract instalado (ver `requirements-visao.txt`) — sem isso, esse
  campo vem sempre `None`, e o resto do módulo funciona normalmente.
- Enumeração de elementos de UI (`pywinauto`) só funciona no Windows,
  e só pra aplicações que expõem sua árvore de acessibilidade
  corretamente (a maioria dos apps modernos expõe; alguns jogos/apps
  com renderização customizada não expõem nada).
- O primeiro tick depois de detectar uma mudança pode levar 1-2
  segundos a mais que o intervalo configurado (enumerar dezenas de
  elementos de UI via chamadas COM tem esse custo) -- é esperado, e é
  exatamente o que a checagem barata evita fazer sem necessidade.
- Notificações do sistema (toasts do Windows) não são capturadas
  diretamente -- só são inferidas indiretamente via palavra-chave no
  texto/elementos da janela em foco, quando aparecem dentro dela.

## Bug real encontrado e corrigido durante o desenvolvimento

`pywinauto` inicializa COM (apartment threading) na hora do import.
Importar isso no nível do módulo (`monitor.py`), carregado durante
`core/jarvis.py:_startup_diagnostics()` (thread principal, junto de
outras libs que também mexem em COM, como `win32com`/Playwright),
causava `[WinError -2147417850] RPC_E_CHANGED_MODE` de verdade,
silenciosamente capturado pelo try/except do startup -- a visão
contínua "ligava" (sem erro visível pro usuário) mas nunca produzia
nenhuma observação. Corrigido adiando o `import pywinauto` pra dentro
da função que realmente usa (`_elementos_janela_foco`), que só roda
dentro do tick em segundo plano (thread própria).

## Melhorias de precisão/desempenho (segunda rodada)

- **Enumeração de UI mais rápida em janelas complexas**:
  `_elementos_janela_foco` chamava `janela.descendants()` SEM filtro,
  o que enumera e materializa (via UI Automation, uma chamada COM fora
  de processo por elemento) TODOS os descendentes antes de filtrar por
  tipo em Python -- em apps com árvore de UI grande (Chrome, VS Code,
  Electron em geral) isso significa milhares de chamadas COM pagas à
  toa, bem mais que o "1-2 segundos a mais" que este README já admitia.
  Agora cada tipo relevante é buscado com `descendants(control_type=...)`,
  que aplica o filtro no UI Automation nativo -- só os elementos que já
  batem o tipo cruzam a fronteira COM -- e o loop para assim que
  `_MAX_ELEMENTOS` é atingido, então tipos "caros" (ex.: `ListItem` numa
  lista grande) muitas vezes nem chegam a ser consultados.
- **Detecção de mudança de tela mais robusta**: a miniatura usada pra
  decidir "a tela mudou o suficiente pra valer o OCR/enumeração de UI"
  comparava só o canal azul (BGR) do screenshot -- uma mudança
  concentrada em vermelho/verde (ex.: um banner de aviso vermelho sobre
  um fundo já azulado) podia passar batido. Agora usa a média dos 3
  canais.
- **Palavras-chave de evento mais abrangentes**: as listas de
  erro/atualização/download tinham poucas variantes -- várias frases
  reais ("crashed", "not responding", "invalid", "update required"...)
  não batiam com nenhuma delas e o evento correspondente nunca era
  detectado. Ampliadas (continua sendo casamento de substring, não NLP
  de verdade -- ver limitação honesta acima).
- **OCR mais preciso** (ver `visao/ocr.py`): o texto lido da tela agora
  passa por um pré-processamento (escala de cinza + upscale 2x +
  binarização) antes do Tesseract, e a checagem de disponibilidade do
  Tesseract (que chama o binário via subprocesso) é cacheada -- antes
  rodava a cada tick em que a tela mudasse.
