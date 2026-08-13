# Jarvis — Assistente Pessoal em Python

Um assistente pessoal local, modular e expansível, em Python. O
núcleo (chat, memória permanente, perfil de usuário, sistema de
plugins, busca de conhecimento, controle básico e seguro do
computador, motor de **conversa natural**) roda 100% com a biblioteca
padrão do Python + SQLite — **sem nenhuma dependência obrigatória e
sem nenhuma API externa obrigatória** (veja a seção "Sistema de
conversa natural" mais abaixo para o que isso significa na prática).

Em volta desse núcleo, o projeto tem uma arquitetura modular de
módulos **opcionais** — IA (múltiplos provedores + modelo local),
voz, visão computacional, automação, dispositivos (Android/BLE/
Serial/MQTT/SSH), monitoramento de sistema/GPU, segurança, logs e
atualizações — cada um ativável/desativável em `config/config.json`,
e que degrada graciosamente quando a dependência de uma lib opcional
não está instalada. Veja a seção **"Arquitetura modular"** logo
abaixo para o mapa completo.

## Como rodar

**Sem terminal, com um clique** (Windows): dê duplo-clique em `Iniciar
Jarvis.vbs` (na raiz do projeto) -- abre a interface gráfica direto,
sem nenhuma janela de CMD/PowerShell aparecendo (usa `pythonw.exe`,
que roda sem console, com a janela oculta desde o início). Também já
existe um atalho **"Jarvis"** na sua Área de Trabalho apontando pra
esse arquivo. Se algo der errado e nada abrir, rode
`iniciar_jarvis_com_console.bat` (mesma pasta) pra ver a mensagem de
erro de verdade -- o `.vbs` não mostra nada na tela em caso de falha,
por isso o `.bat` existe como alternativa de diagnóstico.

Ou, pelo terminal:

```bash
python main.py
```

Por padrão isso abre a **interface gráfica** (`gui/`): fundo preto, um
núcleo de nêutrons que estabiliza anéis magnéticos quando ocioso e pulsa
mais rápido enquanto o Neutron processa uma resposta, e um chat com as
respostas — da base de conhecimento, plugins (inclusive abrir
programas) ou IA externa. Requer `requirements-gui.txt`
(`pip install -r requirements-gui.txt`, instala o PySide6); sem essa
dependência instalada, o Jarvis avisa e cai sozinho para o modo texto
no terminal, sem travar.

**Abertura cinematográfica** (`gui/intro.py`): na primeira vez que a
GUI abre, matéria luminosa entra em colapso e forma uma estrela de
nêutrons com anéis magnéticos. Em seguida o Neutron verifica a
assinatura do operador. Se ninguém está registrado, ele pede seu nome,
você digita, e ele guarda —
`geral.usuario_padrao` no config, o mesmo id de sessão da memória. Da
próxima vez ele te reconhece ("que bom revê-lo") e vai direto pra
interface. Pule a qualquer momento com **Esc**, ou desligue de vez com
`"geral.intro_animada": false` em `config.json`. Tudo desenhado com
QPainter (sem vídeo/imagem externa), e qualquer falha na intro cai
sozinha pro fluxo simples, sem impedir o Jarvis de abrir.

A GUI também fala as respostas em voz alta (botão "Voz" no topo liga/
desliga) — usa o mesmo motor de síntese do modo `--voz`
(`requirements-voz.txt`, `pyttsx3`); sem essa dependência instalada, o
botão simplesmente não produz áudio (o chat continua funcionando
normalmente).

Para forçar o modo texto no terminal mesmo com a GUI instalada:

```bash
python main.py --texto
```

O núcleo (chat, memória, base de conhecimento, plugins, config, logs,
provedores de IA via urllib, backup, atualização, detecção de
hardware) usa só a biblioteca padrão do Python 3.8+ — `requirements.txt`
não lista nenhuma dependência obrigatória (rodar
`pip install -r requirements.txt` roda instantaneamente, sem instalar
nada). Cada módulo novo tem seu próprio arquivo de dependências
opcionais (`requirements-gui.txt`, `requirements-ia.txt`,
`requirements-voz.txt`, `requirements-visao.txt`,
`requirements-automacao.txt`, `requirements-dispositivos.txt`,
`requirements-sistema.txt`, `requirements-seguranca.txt`) — instale só
o que for usar, por exemplo:

```bash
pip install -r requirements-sistema.txt   # psutil: uso de CPU/RAM, processos, GPU
```

Ou tudo de uma vez com `pip install -r requirements-full.txt`. Veja a
seção "Arquitetura modular" mais abaixo para o que cada um destrava.

Na primeira vez que rodar sem nenhum provedor de IA configurado, o
Jarvis pergunta se você quer configurar um agora — aceita **qualquer**
provedor (OpenAI, Anthropic, Gemini, Mistral, OpenRouter, DeepSeek,
**NVIDIA**, Ollama, LM Studio, API compatível genérica, servidor
próprio) e **valida a chave/URL de verdade** (chamada real de teste)
antes de salvar, então uma chave errada nunca é gravada silenciosamente.
Isso é 100% opcional — responder "não" não pergunta de novo depois, e
o Jarvis já funciona sem nenhuma IA externa. Para configurar (ou
trocar) depois, use `/configurarapi` no chat. Detalhes em
[`ia/README.md`](ia/README.md).

No chat, digite normalmente. Por padrão, as respostas do Jarvis
aparecem depois de uma pequena pausa simulando "digitando..." (dá um
compasso mais parecido com conversa real, em vez de uma resposta
instantânea de questionário). Se preferir respostas imediatas, rode
com a variável de ambiente `JARVIS_SEM_DELAY=1`:

```bash
JARVIS_SEM_DELAY=1 python main.py
```

Para conversar por voz em vez de texto (requer `requirements-voz.txt`
instalado e microfone — ver seção "Arquitetura modular"):

```bash
python main.py --voz
```

Por padrão o modo voz usa **palavra de ativação** (`voz.ativar_wakeword`
em `config.json`, ligado por padrão): diga "jarvis" seguido do pedido
numa respiração só ("jarvis, que horas são") ou "jarvis" sozinho e o
pedido logo em seguida — sem precisar reiniciar o modo voz a cada
frase. Mais de uma palavra de ativação é aceita ao mesmo tempo
(`voz.palavras_chave`, lista, ex. `["jarvis", "ark"]` -- qualquer uma
delas ativa). A voz de resposta pode ficar mais grave/mecânica
(`personalidade.voz_robotica`, ligado por padrão) usando prosódia
nativa do SAPI5 (Windows) — não é clonagem de nenhuma voz de terceiros,
só ajuste de tom/velocidade da própria API, combinado com preferir uma
voz MASCULINA entre as já instaladas no Windows (tom grave numa voz
grave de base soa mais parecido com uma IA "vilanesca" do que o mesmo
tom aplicado a uma voz aguda -- se não houver voz masculina instalada
no idioma, usa a que houver). Tom configurável em
`personalidade.tom_voz_robotica` (-9 por padrão, escala -10 a 10 do
próprio SAPI5). Veja também "personalidade ultron" na tabela de
comandos abaixo.

Velocidade da fala é configurável (`voz.velocidade_fala`, 205 por
padrão -- mais rápida que o default comum do `pyttsx3`, ~175-200):
diga "fala mais rápido" / "fala mais devagar" a qualquer momento pra
ajustar, ou "velocidade normal da fala" pra voltar ao padrão. Vale
tanto pro modo de voz quanto pro botão 🔊 da GUI/app do celular.

**Personalidade "ultron"** (`"ativa a personalidade ultron"` /
`"personalidade padrão"`): não é só um system prompt diferente pra IA
-- as respostas prontas do motor de conversa (saudação, piada, "como
você está", agradecimento, etc., ver `core/conversation.py`) também
mudam de tom quando o estilo está ativo (frio, calculista,
ironicamente superior, sempre com humor seco em vez de deboche cruel
de verdade). A única exceção deliberada: respostas de acolhimento
emocional (quando você diz que está triste/estressado/bravo) **não**
mudam de tom em nenhum estilo -- a personalidade tempera o "como" de
quase tudo, menos disso.

Comandos especiais:

| Comando        | Efeito                                  |
|-----------------|------------------------------------------|
| `/historico`    | mostra últimas mensagens salvas          |
| `/plugins`      | lista plugins carregados                 |
| `/recarregar`   | recarrega plugins sem reiniciar          |
| `/aprendizado`  | mostra o resumo do que o Jarvis aprendeu |
| `/consolidar`   | força a consolidação de assuntos frequentes em conhecimento |
| `/baseconhecimento` | mostra estatísticas da base de conhecimento curada |
| `/modulos`      | status de cada módulo (ia, voz, visao, automacao, dispositivos, sistema, seguranca, logs, atualizacoes) |
| `/sistema`      | hardware detectado (CPU/GPU) e uso atual de recursos |
| `/backup`       | força um backup manual do banco de dados |
| `/atualizacoes` | checa se há atualizações disponíveis (via git) |
| `/logs`         | mostra as últimas linhas do log |
| `/sair`         | encerra                                  |

## Testes automatizados

```bash
pip install -r requirements-dev.txt
pytest
```

Cobre os plugins mais sensíveis a regressão silenciosa/segurança:
login em sites (garante que senha digitada no chat NUNCA é aceita),
Modo Autônomo (CRUD de objetivos + o "gate" de ociosidade do `_tick`) e
Instagram (o fallback pra ADB sem fio quando a fonte principal de
notificação não tem nada -- foi assim que uma regressão real foi pega
numa sessão de manutenção). `tests/conftest.py` isola cada teste do
ambiente real: banco de dados, `config.json` e o cofre de credenciais
do Windows são todos substituídos por versões temporárias/falsas --
nenhum teste escreve no seu `data/jarvis.db` real nem no Credential
Locker de verdade.

## Exemplos de frases que funcionam

```
meu nome é Pedro
lembre que minha cor favorita é azul
qual minha cor favorita
o que é fotossíntese
quem foi Albert Einstein
que horas são
data de hoje
uso de cpu
uso de memoria
espaço em disco
status do sistema
abra youtube
meus fatos
aprenda que o Brasil é um país da América do Sul
o que você aprendeu

me lembre que eu tenho treino às 18h
me avise em 10 minutos que o bolo está pronto
meus lembretes

veja o que eu estou fazendo e comente
fique de olho no que eu estou fazendo (a cada 10 minutos)
pare de me observar
assuntos frequentes
consolide o que aprendeu
relacione 1 com 2: ambos sobre o mesmo tema
o que está relacionado a 1
resumo do aprendizado

oi, tudo bem?
estou meio estressado com o trabalho hoje
conte uma piada
você é uma pessoa real?
obrigado pela ajuda
tchau

pareia o celular 192.168.0.10:39451 482913
conecta no celular 192.168.0.10:37451
celulares conectados
abre o whatsapp no celular
vê a bateria do meu celular
o que está aberto no celular
tira um print do celular
aumenta o volume do celular
liga a lanterna do celular
cadê meu celular
espaço no celular
minhas mensagens do instagram
sugere uma resposta pro instagram
desconecta o celular

aumenta o volume
diminui o volume
muta o som
aumenta o brilho
brilho em 50%
tira um print da tela
feche o notepad
feche o notepad, confirmo

ative a personalidade ultron
modo normal
```

## Estrutura

```
jarvis/
├── main.py                  # interface gráfica (padrão), texto (--texto) ou voz (--voz)
├── gui/                      # interface gráfica opcional (PySide6): fundo preto, "Núcleo" de partículas, chat
│                              # + intro.py: abertura cinematográfica (partículas -> cérebro -> logo -> registro do operador)
│                              # + reactor.py: o Núcleo (esfera de ~520 partículas que gira/respira, cresce ao trabalhar, muda de cor ao aprender, ejeta partículas ao pesquisar)
├── core/
│   ├── jarvis.py             # orquestrador central
│   ├── memory.py             # memória permanente (SQLite)
│   ├── knowledge.py          # sistema de APRENDIZADO (conhecimento próprio)
│   ├── knowledge_base.py     # BASE DE CONHECIMENTO curada por categorias fixas
│   ├── confidence.py         # sistema de níveis de confiança
│   ├── conversation.py       # motor de CONVERSA NATURAL (small talk, humor, variação)
│   ├── plugin_manager.py     # carregamento dinâmico de plugins
│   ├── module_manager.py     # status agregado de todos os módulos (/modulos)
│   ├── database.py           # helper SQLite genérico, reusado pelos módulos novos
│   ├── personality.py        # persona do Jarvis (tom, system prompt para IA -- inclui estilo "ultron")
│   ├── skill_forge.py        # gera habilidades/programas/jogos/correções com IA -- nunca ativa sozinho
│   ├── timeline.py           # junta eventos registrados pelos módulos numa linha do tempo cronológica
│   ├── estado_interno.py     # energia/humor simulados (não é consciência real) que temperam o tom das respostas
│   └── intencao.py           # classificação silenciosa pergunta/comando/conversa (nunca aparece na resposta)
├── linguagem/                 # JarvisScript: linguagem de programação própria (léxico/parser/interpretador)
├── config/                   # configuração centralizada (config.json)
├── ia/                       # provedores de IA (OpenAI, Anthropic, Gemini, NVIDIA, Ollama, ...) + modelo local
├── voz/                      # reconhecimento e síntese de voz, palavra de ativação, voz robótica (SAPI5)
├── visao/                    # câmera, OCR, reconhecimento facial, objetos, gestos, tela, observe.py (janela/atividade em foco)
│                              # + screen.py:record_screen() e video_edit.py (gravação/edição de vídeo da tela)
├── automacao/                # abrir/fechar apps, arquivos, rotinas, observar pastas, lembretes (+recorrentes), notificações, media_keys.py
│                              # + janelas.py, logins_web.py, auto_melhoria.py, aprendizado_autonomo.py, instagram_auto.py, navegador.py
│                              # + habitos.py, instalador_apps.py, gemeo_digital.py, sonhos.py, aprendizado_programa.py, macros.py, escuta_ativa.py
├── dispositivos/             # Android (adb, Wi-Fi/sem cabo), Bluetooth LE, Serial, MQTT, SSH
├── visao_continua/           # Módulo novo: visão CONTÍNUA da tela em segundo plano (ver README próprio)
├── controle_pc/              # Módulo novo: API interna de controle do PC -- mouse/teclado, elementos de UI,
│                              # janelas, arquivos, comandos de sistema, processos (ver README próprio)
├── sistema/                  # hardware (CPU/GPU/CUDA), monitoramento de recursos, display.py (brilho)
├── seguranca/                # autenticação, criptografia, permissões, backup
├── logs/                     # logging centralizado (logs/jarvis.log)
├── atualizacoes/             # versão e checagem de atualização (git)
├── plugins/
│   ├── memory_commands.py     # "lembre que...", perfil, fatos
│   ├── categorized_memory.py  # memória categorizada: projetos, hábitos, preferências...
│   ├── learning.py            # "aprenda que...", assuntos frequentes, relações
│   ├── knowledge_base.py      # gerencia a base de conhecimento por categorias
│   ├── knowledge_search.py    # busca na Wikipedia
│   ├── observation.py         # "veja o que eu estou fazendo e comente" / observação recorrente
│   ├── reminders.py           # "me lembre que ... às HH:MM" (notificação com som na hora certa)
│   ├── device_control.py      # conecta/controla o celular Android por Wi-Fi: apps, bateria, print
│   ├── instagram.py           # sugere resposta pras mensagens do Instagram (nunca envia sozinho)
│   ├── skill_forge.py         # "aprenda a...", "cria uma habilidade/programa/jogo..." (com aprovação/confirmação)
│   ├── logins_web.py          # "loga no <site>" (senha nunca digitada no chat, ver seção própria)
│   ├── video_creation.py      # "grava minha tela por Xs", corta/acelera vídeo
│   ├── navegador.py           # "pesquisa na internet sobre X" (lê páginas de verdade, só leitura)
│   ├── professor.py           # "me ensina sobre X" / "me testa sobre X"
│   ├── timeline.py            # "linha do tempo" / "o que aconteceu ontem"
│   ├── aprendizado_programa.py # "observa como eu uso o X" -- aprende a descrever o uso, não a repetir
│   ├── habitos.py              # "quais são meus hábitos" (uso de apps no PC)
│   ├── instalador_apps.py      # "instala o vlc" / "baixa o spotify" (via winget)
│   ├── gemeo_digital.py        # testa organização de pasta numa cópia antes de aplicar de verdade
│   ├── macros.py               # "cria uma macro ...", "roda a macro ...", "agenda a macro ... a cada Xmin"
│   ├── visao_continua.py       # "liga/desliga a visão contínua", "o que está acontecendo na minha tela"
│   ├── controle_pc.py          # "executa o comando ... no terminal, confirmo", "organiza minhas janelas", "clica em..."
│   ├── escuta_ativa.py         # "escuta essa conversa por N minutos", "para de escutar", "o que você ouviu"
│   ├── investigador.py         # "investiga o arquivo ...", "descubra tudo sobre https://..."
│   ├── atualizacoes.py         # "tem atualização nova", "atualiza o jarvis, confirmo"
│   ├── autonomia.py            # "aprende algo novo", "inventa uma habilidade" (dispara a autonomia na hora)
│   ├── intencoes.py            # "meta: lançar meu jogo esse mês" -> vira checklist rastreável
│   ├── curiosidade.py          # "notou algo?" -> tendências/anomalias reais (disco enchendo, erro recorrente)
│   ├── consciencia.py          # "diagnóstico" -> estado técnico real (memória, uptime, plugins, IA, erros do dia)
│   ├── consciencia_codigo.py   # "o que quebra se eu mexer em X" -> mapa de dependências do próprio código
│   ├── linguagem_propria.py    # "roda em jarvisscript: ..." / "o que é jarvisscript"
│   └── system_control.py      # abrir/fechar apps, volume, brilho, print da tela, janelas, personalidade
└── data/
    ├── jarvis.db              # criado automaticamente (SQLite)
    └── backups/                # backups automáticos/manuais do banco
```

Cada módulo novo (`config/`, `ia/`, `voz/`, `visao/`, `automacao/`,
`dispositivos/`, `sistema/`, `seguranca/`, `logs/`, `atualizacoes/`)
tem seu próprio `README.md` com detalhes, dependências opcionais e
exemplos de uso — veja a seção seguinte para o mapa geral.

## Arquitetura modular

Filosofia do projeto, aplicada a todo módulo novo: **nenhuma
dependência é obrigatória**, **nenhuma API é obrigatória**, **tudo
funciona offline sempre que possível**, e **todo módulo pode ser
ligado/desligado** em `config/config.json` → `modulos`. Sem a
dependência opcional de um módulo instalada, ele reporta isso
claramente (em vez de travar o programa) — mesmo padrão que o plugin
`system_control.py` já usava com `psutil`.

| Módulo | Cobre | Dependências opcionais |
|---|---|---|
| [`config/`](config/README.md) | configuração central (`config.json`), API keys, idioma, hardware, voz, plugins | nenhuma (`pyyaml` só se quiser usar YAML) |
| [`ia/`](ia/README.md) | OpenAI, Anthropic, Gemini, Mistral, OpenRouter, DeepSeek, NVIDIA (NIM/API Catalog), Ollama, LM Studio, servidor próprio, e fallback para modelo local | nenhuma para provedores via API (usa `urllib`); `transformers`+`torch` ou `llama-cpp-python` para modelo local |
| [`voz/`](voz/README.md) | reconhecimento de voz, wake word, síntese de voz, conversa contínua | `vosk`/`faster-whisper`/`SpeechRecognition`, `pyttsx3`, `sounddevice` |
| [`visao/`](visao/README.md) | webcam, reconhecimento facial, detecção de objetos (YOLO), gestos, OCR, leitura/gravação de tela | `opencv-python`, `pytesseract`, `ultralytics`, `mediapipe`, `mss` |
| [`automacao/`](automacao/README.md) | abrir/fechar programas, organizar/buscar/renomear arquivos, backup em zip, rotinas, observar pastas | nenhuma no núcleo; `watchdog` melhora a observação de pastas |
| [`dispositivos/`](dispositivos/README.md) | Android (`adb`), Bluetooth LE, Serial (Arduino/ESP32), MQTT (IoT), SSH | `adb` no PATH, `bleak`, `pyserial`, `paho-mqtt`, `paramiko` (ou `ssh` do sistema) |
| [`sistema/`](sistema/README.md) | detecção de CPU/GPU/CUDA/stack NVIDIA, monitoramento de recursos, processos/serviços | `psutil`, `torch` ou `pynvml` (GPU) |
| [`seguranca/`](seguranca/README.md) | autenticação local (PIN/senha), criptografia de segredos, modo administrador, backup automático | `cryptography` (senão cai para ofuscação, não criptografia real) |
| [`logs/`](logs/README.md) | logging centralizado, rotativo, por módulo | nenhuma |
| [`atualizacoes/`](atualizacoes/README.md) | versão atual, checagem de atualização via git (nunca faz pull sozinho) | `git` no PATH |

Todos ligados em `config/config.json` → `modulos.<nome>` (`true`/`false`).
Veja o status real de cada um a qualquer momento com `/modulos` no chat.

### Suporte à NVIDIA

- **Detecção de GPU**: `sistema.detect_gpu()` tenta `torch.cuda` →
  `pynvml` → `nvidia-smi`, nessa ordem; sem GPU NVIDIA, usa CPU
  automaticamente.
- **NVIDIA NIM / API Catalog**: funciona como qualquer outro provedor
  de IA compatível com a API da OpenAI — só precisa de uma
  `NVIDIA_API_KEY` em `ia.provedores.nvidia`, sem SDK nenhum (ver
  `ia/README.md`).
- **CUDA Toolkit, cuDNN, TensorRT, Triton, NeMo, Riva**: detectados
  (presença, não uso) por `sistema.detect_nvidia_stack()`, e reportados
  em `/modulos`/`/sistema`. Rodar esse stack de verdade exige os
  instaladores oficiais da NVIDIA (fora do `pip`) e hardware
  compatível — fora do escopo deste projeto orquestrar sozinho, mas os
  pontos de integração estão documentados em `requirements-nvidia.txt`.

### Provedores de IA suportados

Nenhum é obrigatório; o Jarvis detecta automaticamente quais estão
configurados (`config.json` ou variável de ambiente) e cai para modelo
local, e por fim para o comportamento 100% baseado em regras que já
existia, se nada estiver disponível: **OpenAI**, **Anthropic**,
**Google Gemini**, **Mistral**, **OpenRouter**, **DeepSeek**,
**NVIDIA** (NIM/API Catalog), **Ollama**, **LM Studio**, qualquer
**API compatível com OpenAI**, ou um **servidor próprio**. Detalhes em
[`ia/README.md`](ia/README.md).

## O que cada requisito do pedido original significa aqui, na prática

Sendo direto sobre o que está implementado de verdade, sem inflar:

- **Memória permanente** ✅ — Tudo (conversas, fatos, perfil, conhecimento
  aprendido) é salvo em SQLite (`data/jarvis.db`). Fecha o programa, abre
  de novo, e o Jarvis continua lembrando.
- **Aprendizado contínuo** ✅ — Implementado em duas camadas
  complementares:
  1. **Memória de fatos sobre o usuário** (`lembre que X é Y`,
     `core/memory.py`) — dados sobre quem fala com o Jarvis.
  2. **Sistema de aprendizado / conhecimento próprio**
     (`core/knowledge.py`, plugin `learning.py`) — conhecimento geral,
     com data, fonte, categoria e confiança em cada item; detecta
     assuntos frequentes nas conversas (mesmo sem comando explícito);
     consolida assuntos recorrentes em conhecimento próprio; e
     relaciona itens entre si (manual ou automaticamente, por
     palavras-chave compartilhadas). Veja a seção "Sistema de
     aprendizado" mais abaixo para detalhes.
  **Isso não é treinar uma rede neural** — é aprendizado por
  acumulação e relação de dados estruturados, que é como a maioria
  dos assistentes "que aprendem com você" funciona na prática.
- **Interface de chat** ✅ — Loop de chat via terminal em `main.py`.
- **Sistema de plugins** ✅ — Qualquer arquivo `.py` em `/plugins` que
  defina uma classe herdando de `BasePlugin` é carregado automaticamente.
  Testado e validado com hot-reload.
- **Controle do computador** ⚠️ — Implementado como um conjunto de
  comandos **seguros**: abrir sites, ver hora/data, uso de CPU/RAM,
  espaço em disco, listar processos. Não implementei (por segurança)
  execução de comandos arbitrários, encerramento de processos ou
  qualquer coisa destrutiva/irreversível. Se quiser estender isso,
  recomendo sempre pedir confirmação explícita do usuário antes de
  qualquer ação que modifique o sistema.
- **Busca de conhecimento** ✅ — Consulta a API pública da Wikipedia
  (pt.wikipedia.org). Sem necessidade de chave de API.
- **Histórico completo** ✅ — Toda mensagem (sua e do Jarvis) é
  persistida com timestamp; veja com `/historico`.
- **Perfil do usuário** ✅ — Nome e dados extras ficam guardados por
  `user_id`, permitindo múltiplos usuários na mesma base.
- **Evolução constante** ⚠️ — No sentido de "a base de conhecimento e
  capacidades crescem com o tempo" (mais fatos memorizados, mais
  plugins instalados), sim. No sentido de "o modelo de IA em si se
  retreina sozinho", não — isso exigiria infraestrutura de ML bem
  mais pesada (coleta de dados, pipeline de treinamento, GPU, etc.)
  e não é o que este tipo de projeto local costuma fazer.

## Sistema de aprendizado (conhecimento próprio)

Além da memória de fatos sobre o usuário, o Jarvis tem uma camada
dedicada a **aprender e construir conhecimento geral**, separada do
"quem é você" — implementada em `core/knowledge.py` e exposta no chat
por `plugins/learning.py`.

Os 4 pilares pedidos, e onde cada um vive no código:

1. **Salvar novas informações** → `Knowledge.learn()`. Toda informação
   aprendida recebe, sempre, os 4 metadados abaixo — não há como salvar
   algo sem eles:
   - **Data** (`created_at`): quando foi aprendida pela primeira vez.
   - **Fonte** (`source`): de onde veio (`"usuário"`, `"wikipedia"`,
     um nome que o próprio usuário indicar, etc.).
   - **Categoria** (`category`): `fact`, `concept`, `topic`,
     `definition`, `user_provided` ou `inference`.
   - **Confiança** (`confidence`): um dos níveis fixos de
     `core/confidence.py` (100/90/70/50/30/10).

2. **Detectar assuntos frequentes** → `Knowledge.observe_text()` é
   chamado automaticamente a cada mensagem processada pelo Jarvis
   (`core/jarvis.py:process`), extraindo palavras-chave e contando
   quantas vezes cada uma aparece nas conversas
   (`topic_mentions`). `detect_frequent_topics()` lista o que mais se
   repete. Isso roda **em segundo plano**, sem precisar de comando
   explícito — é aprendizado passivo de verdade.

3. **Construir conhecimento próprio** → `Knowledge.consolidate()`
   examina os assuntos frequentes e, para cada um mencionado três
   vezes ou mais, cria (ou reforça) um item de conhecimento na
   categoria `concept`, com a fonte registrada como "observação de N
   menções em conversa" e confiança calculada a partir do número de
   menções. Ou seja: o Jarvis não espera ser instruído — ele percebe,
   pela repetição, o que parece importante, e sintetiza isso como
   conhecimento próprio. Rode com o comando `/consolidar` ou a frase
   "consolide o que aprendeu".

4. **Relacionar informações** → duas formas:
   - **Manual**: `relate(from_id, to_id, relation)` / frase
     `"relacione 3 com 7: motivo"`.
   - **Automática**: `auto_relate_by_keywords()` roda a cada novo item
     aprendido e cria ligações com itens existentes que compartilhem
     duas ou mais palavras-chave relevantes — assim a base cresce como
     uma rede (grafo), não como uma lista solta. Veja as relações de
     um item com `"o que está relacionado a <id>"`.

Como a confiança evolui automaticamente: cada vez que a **mesma**
informação é aprendida de novo (`learn()` chamado com conteúdo
idêntico), o contador de menções sobe e a confiança é recalculada:

| Menções | Confiança          |
|---------|---------------------|
| 1       | 70 (Encontrada apenas uma vez) |
| 2       | 90 (Fonte confiável) |
| 3+      | 100 (Confirmada várias vezes) |

### Comandos disponíveis no chat

```
aprenda que o Brasil é um país da América do Sul
aprenda que python é uma linguagem de programação, fonte: documentação oficial

o que você aprendeu
o que você aprendeu sobre python

assuntos frequentes
consolide o que aprendeu

relacione 3 com 7: ambos tratam de bancos de dados
o que está relacionado a 3

grafo de conhecimento
resumo do aprendizado

esqueça o conhecimento 5
```

Também: respostas vindas da busca na Wikipedia (`knowledge_search`)
são absorvidas automaticamente na base de conhecimento, já com
`source="wikipedia"`, `category="definition"` e a confiança que o
plugin de busca retornou — sem precisar repetir a informação com
`"aprenda que ..."`.

### Usando programaticamente (`core/knowledge.py`)

```python
from core.knowledge import Knowledge

k = Knowledge()

# Salvar (cria ou reforça se o mesmo conteúdo já existir)
item = k.learn("user1", "SQLite é um banco de dados leve",
               source="usuário", category="fact")

# Registrar menção a um assunto (chamado automaticamente em todo
# process() do Jarvis, mas pode ser usado manualmente também)
k.observe_topic("user1", "sqlite")
k.observe_text("user1", "texto livre qualquer, vira palavras-chave")

# Detectar o que se repete
k.detect_frequent_topics("user1", min_mentions=3)

# Consolidar assuntos frequentes em conhecimento próprio
k.consolidate("user1", min_mentions=3)

# Relacionar dois itens (manual) ou deixar o sistema relacionar
# automaticamente por palavras-chave compartilhadas
k.relate("user1", item["id"], outro_item["id"], relation="usa")
k.auto_relate_by_keywords("user1", item["id"])

# Navegar a rede de conhecimento
k.related_to(item["id"])
k.knowledge_graph("user1")

# Resumo pronto para exibir ou injetar como contexto
k.learning_summary("user1")
```

## Base de conhecimento curada (categorias fixas)

Além do conhecimento aprendido organicamente (seção anterior), o
Jarvis tem uma **base de conhecimento de referência**, com categorias
fixas e predefinidas — implementada em `core/knowledge_base.py` e
exposta no chat por `plugins/knowledge_base.py`:

- Programação
- História
- Geografia
- Ciências
- Matemática
- Jogos
- Tecnologia

Tentar usar outra categoria levanta `ValueError` com a lista de
categorias válidas (mesmo padrão de `MEMORY_CATEGORIES` em
`core/memory.py`), para a base não se encher de rótulos inconsistentes.

A base já vem com alguns itens de exemplo (seed) em cada categoria na
primeira execução, para haver algo para consultar desde o início.

### Regra central: a IA pesquisa nessa base antes de responder

Isso é aplicado em `core/jarvis.py:process()`, no método
`_query_knowledge_base_first()`, que roda **antes** de qualquer plugin
(inclusive antes da busca na Wikipedia). O fluxo é:

1. Mensagem chega → o Jarvis identifica se parece uma pergunta
   (contém marcadores como "o que é", "quem foi", "qual", "como
   funciona", termina com "?", etc.) e não é um comando de gestão da
   própria base (esses ficam por conta do plugin).
2. Se parecer uma pergunta, consulta `KnowledgeBase.search()` —
   tentando tanto a frase inteira quanto o termo extraído (ex.: "o que
   é um NPC" → tenta "o que é um NPC" e depois "um NPC"), tolerante a
   acentuação (buscar "fotossintese" encontra "Fotossíntese").
3. **Se encontrar algo relevante**, a resposta vem dali, com a
   confiança própria daquele item e indicando a categoria — sem
   precisar buscar na Wikipedia ou cair no fallback.
4. **Só se a base não tiver nada** é que o fluxo segue normalmente
   para os outros plugins (`knowledge_search` na Wikipedia, etc.) e,
   por fim, para o fallback.

Ou seja: a base de conhecimento curada tem **prioridade** sobre
qualquer outra fonte de resposta.

### Comandos disponíveis no chat

```
adicione na base de programação: O que é um loop | Estrutura que repete um bloco de código.
adicione na base de jogos: O que é um NPC | Personagem não controlado pelo jogador.

liste a base de história
liste a base de tecnologia

busque na base sobre teorema de pitágoras

remova da base de jogos: O que é um NPC

quais categorias
estatísticas da base
```

E, automaticamente, qualquer pergunta com cara de pergunta ("o que é
...", "quem foi ...", termina com "?") já consulta a base primeiro,
sem precisar de nenhum comando especial — é só perguntar normalmente.

### Usando programaticamente (`core/knowledge_base.py`)

```python
from core.knowledge_base import KnowledgeBase

kb = KnowledgeBase()

# Adicionar (cria ou atualiza se já existir o mesmo título na categoria)
kb.add_entry("tecnologia", "O que é uma API",
             "Interface que permite comunicação entre sistemas.",
             source="usuário")

# Pesquisar (tolerante a acento, e essa é a função usada pelo núcleo
# do Jarvis antes de responder qualquer pergunta)
kb.search("fotossintese")
kb.best_match("teorema de pitagoras")

# Listar tudo de uma categoria
kb.list_by_category("historia")

# Remover
kb.remove_entry("jogos", "O que é um NPC")

# Estatísticas por categoria
kb.stats()
```

### Por que esta base é separada de `core/knowledge.py`

`core/knowledge.py` guarda conhecimento **aprendido organicamente**
nas conversas (fatos ditos pelo usuário, assuntos frequentes,
conceitos consolidados por repetição) — ele cresce e evolui sozinho.
`core/knowledge_base.py` é uma base **de referência**, com categorias
fixas de assunto, pensada para ser consultada com prioridade antes de
qualquer resposta — mais parecida com uma enciclopédia interna
organizada por tema do que com memória de conversa. Os dois sistemas
coexistem e não se sobrepõem: a base curada responde primeiro quando
tem o que precisa; quando não tem, o restante do pipeline (incluindo o
aprendizado orgânico) segue seu fluxo normal.

## Sistema de confiança

Toda resposta factual do Jarvis carrega um nível de confiança explícito
internamente, mas **por padrão o bloco de texto não aparece** — o
usuário só vê a resposta (`personalidade.mostrar_confianca` em
`config.json`, `false` por padrão). Peça "mostra a confiança" (ou
"esconde a confiança" para voltar) e o `plugins/system_control.py`
alterna isso em tempo real. Com o bloco ligado, o formato é:

```
Resposta:
A capital da França é Paris.

Confiança:
100% (Confirmada várias vezes)
```

Níveis fixos (definidos em `core/confidence.py`):

| Nível | Significado                          |
|-------|----------------------------------------|
| 100   | Informação confirmada várias vezes     |
| 90    | Informação obtida de fonte confiável   |
| 70    | Informação encontrada apenas uma vez   |
| 50    | Informação inferida                    |
| 30    | Possível resposta                      |
| 10    | Palpite                                |

Como cada plugin atual usa isso, na prática:

- **system_control** (hora, data, CPU, disco etc.) → **100**, porque lê
  direto do sistema operacional — não há incerteza.
- **knowledge_search** (Wikipedia) → **70**, porque é uma única fonte
  consultada, sem cruzamento com outra fonte para confirmar.
- **memory_commands**: salvar/apagar um fato → **100** (é uma operação
  do próprio sistema, sempre certa); recuperar um fato → **70** (foi
  dito uma única vez pelo usuário e nunca reconfirmado).
- **fallback** (quando nenhum plugin sabe responder) → **10**, ou
  **100** para saudações/ajuda (são respostas fixas do sistema).

### Como declarar confiança em um plugin novo

```python
from core.plugin_manager import BasePlugin
from core.confidence import Answer, Confidence

class MeuPlugin(BasePlugin):
    name = "meu_plugin"
    triggers = ["palavra-chave"]

    def handle(self, text, context):
        return Answer("minha resposta", Confidence.RELIABLE_SOURCE)  # 90
```

Se um plugin retornar uma string pura (formato antigo, sem `Answer`),
o sistema continua funcionando por compatibilidade, mas assume
confiança **10 (Palpite)** automaticamente, já que o plugin não
declarou o nível.

## Modo de comando direto ("/") e outros ajustes de resposta

### Comando direto com "/"

Quando o texto começa com `/`, o Jarvis entra em **modo de comando
direto**: a barra é removida e o texto vai *só* para o dispatch de
plugins (`core/plugin_manager.py`) — a base de conhecimento curada, a
conversa natural e a IA (`ia/manager.py`) são todas puladas. Se algum
plugin souber executar o comando, ele executa; se nenhum souber, o
Jarvis avisa explicitamente "Não conheço o comando ..." em vez de
tentar adivinhar uma resposta.

Isso existe para casos em que o pedido é claramente uma AÇÃO ("abre o
youtube", "fecha o chrome", "instala o vlc") e não uma pergunta — sem
o "/", frases assim já são tratadas pelos plugins certos na maioria
das vezes, mas se algum provedor de IA estiver configurado e a frase
não casar com nenhum plugin, ela pode acabar caindo na IA (que
responde em texto, mas não *executa* nada). Prefixando com "/" você
garante que a mensagem SÓ é tratada como comando.

Convenção recomendada: quem DIGITA a mensagem usa "/" na frente de comandos ("/abrir youtube");
quem FALA (voz/wake word) continua falando naturalmente, sem barra —
a entrada de voz nunca produz uma barra, então ela sempre passa pelo
fluxo completo (plugins → conversa → IA → fallback), que já entende
frases naturais.

```
/abrir youtube          -> executa se algum plugin souber (dispositivos/automação)
/fechar chrome          -> idem
/comando_que_nao_existe -> Não conheço o comando "/comando_que_nao_existe". ...
oi                      -> sem barra, cai na conversa natural normalmente
```

### Esconder qual provedor de IA respondeu

Por padrão (`personalidade.mostrar_provedor_ia`, `false`), quando a
resposta vem da IA (`ia/manager.py`) o Jarvis mostra só o texto — sem
indicar se foi NVIDIA, OpenAI, Ollama etc. Diga "mostra o provedor da
ia"/"esconde o provedor da ia" para alternar (`plugins/system_control.py`).
Com o modo "mostrar" ligado, o rodapé `(nvidia | resposta gerada por
IA)` volta a aparecer — útil para depuração.

### Executar sem pedir confirmação

Ações destrutivas-adjacentes (fechar um programa, instalar um app,
rodar código gerado, aplicar de verdade uma organização de pasta etc.)
pedem uma palavra de confirmação ("confirmo") na mesma frase, por
padrão (`seguranca.exigir_confirmacao_acoes_destrutivas`, `true`). Diga
"não peça confirmação" para desligar essa exigência globalmente — a
partir daí, o mesmo comando ("fecha o chrome", "instala o vlc" etc.)
executa direto, sem precisar da palavra "confirmo". Diga "peça
confirmação" a qualquer momento para voltar a exigi-la. A lógica fica
centralizada em `seguranca.permissions.confirmado_pela_frase_ou_config()`,
usada por todos os plugins que já pediam confirmação
(`system_control.py`, `skill_forge.py`, `instalador_apps.py`,
`gemeo_digital.py`).

### Raciocínio interno: "isso é uma pergunta ou um comando?" (nunca aparece pro usuário)

Além do modo "/" (que exige a barra explicitamente), `core/intencao.py`
faz uma classificação silenciosa de toda frase SEM barra que nenhum
plugin/base de conhecimento reconheceu: "pergunta", "comando" ou
"conversa" -- puramente heurística (marcadores de pergunta + uma lista
curta e deliberadamente conservadora de verbos de ação inequívocos como
"abre"/"fecha"/"muta"/"instala"), nunca é mostrada na resposta, e só
existe pra decidir o que fazer em seguida.

Se a frase "tem cara de comando" (ex.: "liga a impressora") e nenhum
plugin soube executar, o Jarvis avisa que não conhece o comando em vez
de deixar a conversa/IA responderem com um texto que parece ter feito
algo mas não executou nada de verdade -- a mesma garantia do modo "/",
só que automática. Qualquer coisa ambígua ou claramente criativa/
informacional ("cria uma história sobre...", "faz um resumo de...",
"como funciona X") continua caindo na conversa/IA normalmente -- a
lista de verbos é intencionalmente curta pra nunca bloquear um pedido
legítimo (ver a docstring de `core/intencao.py` pro raciocínio completo
de por que "cria"/"faz"/"escreve" ficam de fora de propósito).

## Macros: várias ações em sequência, sob um nome

`automacao/macros.py` + `plugins/macros.py`: `"cria uma macro boa
noite: fecha o chrome, muta o som, diminui o brilho"` salva uma
sequência de comandos JÁ EXISTENTES sob um nome; `"roda a macro boa
noite"` executa todos em ordem, um após o outro. Cada passo roda no
modo de comando direto (`"/"`, ver acima) -- então toda regra de
segurança de sempre (confirmação pra ações destrutivas, etc.) continua
valendo passo a passo; um passo que precisa de confirmação simplesmente
pede confirmação em vez de executar, exatamente como pediria se você
tivesse digitado aquele passo sozinho.

Isto NÃO é "a IA decide sozinha o que fazer no PC sem limite nenhum" --
uma macro só contém comandos que o próprio usuário escreveu ao criá-la;
agendar (abaixo) só decide QUANDO os mesmos passos já aprovados rodam,
nunca O QUE roda.

```
cria uma macro boa noite: fecha o chrome, muta o som, diminui o brilho
roda a macro boa noite
minhas macros
apaga a macro boa noite

agenda a macro boa noite a cada 60 minutos   -- roda sozinha, sem precisar pedir
cancela o agendamento da macro boa noite
```

Agendamentos sobrevivem a reinícios (`automacao/macros.py:retomar_agendamentos()`,
chamado no startup do Jarvis, mesma ideia de `automacao/reminders.py:reschedule_pending()`).

## Visão contínua da tela e controle inteligente do PC

Dois módulos novos, cada um com README próprio detalhado
(`visao_continua/README.md`, `controle_pc/README.md`) -- resumo aqui.

**Visão contínua** (`visao_continua/`, desligado por padrão --
`"liga a visão contínua"` pra ativar): mantém um estado estruturado
sempre atualizado do que está na tela -- janela/processo em foco,
texto (OCR), botões/menus/caixas de diálogo (via UI Automation do
Windows), se o programa está travado (`IsHungAppWindow`), e eventos
detectados (programa aberto/fechado, possível erro/atualização/
download concluído). Roda em segundo plano com checagem de eficiência
em duas camadas: só reprocessa (OCR + UI) quando um screenshot
reduzido indica mudança de verdade, ou quando processos abrem/fecham
-- do contrário, pula o trabalho caro. Alimenta silenciosamente o
contexto da IA (mesmo mecanismo de `core/estado_interno.py`) e expõe
`visao_continua.estado_atual()`/`historico()` pra qualquer outro
código consultar. **Assistência proativa opt-in**
(`personalidade.assistencia_proativa`, desligado por padrão): quando
ligado, e só quando a visão contínua já detectou sozinha um possível
erro na tela, o Jarvis pede pra IA uma explicação curta + próximo
passo e avisa por notificação, sem precisar que você pergunte --
notifica uma vez por erro (não fica repetindo pro mesmo erro parado na
tela).

**Controle do PC** (`controle_pc/`): API interna pro cérebro do Jarvis
pedir ações -- mouse/teclado, localizar e clicar num elemento por
nome (UI Automation) ou imagem, organizar janelas em grade/cascata,
ler/escrever arquivo, rodar comando de sistema, listar/encerrar
processo travado. Reaproveita `automacao.apps`/`automacao.janelas`/
`sistema.processes` onde eles já cobrem o pedido, só acrescenta o que
faltava. Ações reversíveis (mover mouse, clicar, ler arquivo) não
exigem confirmação; ações destrutivas (rodar comando, escrever
arquivo, fechar programa, encerrar processo) exigem `confirmed=True`
-- o MESMO `seguranca.permissions` de sempre, inclusive o toggle
"não peça confirmação" já existente.

```
liga a visão contínua
o que está acontecendo na minha tela
desliga a visão contínua

executa o comando dir no terminal, confirmo
organiza minhas janelas
clica no botão Salvar
```

**Escuta acompanhada com tempo limitado** (`automacao/escuta_ativa.py`):
a alternativa responsável a um modo de escuta contínua sempre ligado
(recusado nesta conversa por captar terceiros sem consentimento e não
ter um fim natural) -- aqui a escuta só começa com um comando
explícito, dizendo por quanto tempo, com um teto de segurança
(`escuta_ativa.duracao_maxima_minutos`, 30 por padrão) mesmo se
pedirem mais, avisa quando começa/termina, e a transcrição só vive na
memória do processo (nunca salva em disco) até a próxima sessão ou até
pedir pra esquecer.

```
escuta essa conversa por 10 minutos
para de escutar
o que você ouviu
esquece o que você ouviu
```

Dois bugs reais encontrados e corrigidos durante o desenvolvimento
(detalhados nos READMEs de cada módulo): um conflito de threading COM
que fazia a visão contínua "ligar" sem nunca produzir observação
nenhuma (import de `pywinauto` cedo demais), e um falso positivo em
`clicar_elemento` onde um painel de texto (não um botão) "encontrava a
si mesmo" ao ser pesquisado por uma palavra que aparecia no texto
exibido.

## Sistema de conversa natural (sem IA externa)

Implementado em `core/conversation.py`, ligado ao núcleo em
`core/jarvis.py`. **Não usa nenhuma API, nenhum LLM, nenhuma rede
neural** — é Python puro com `re` e `random`, igual ao resto do
projeto. A diferença em relação a um plugin de comando comum (que
casa uma frase fixa com uma ação fixa) é o que tenta tornar isto uma
conversa "de verdade" em vez de um roteiro decorado:

- **Várias respostas por intenção, nunca repetidas em sequência.** Cada
  categoria (saudação, despedida, agradecimento, piada, etc.) tem um
  banco de frases diferentes; o motor evita repetir a mesma frase duas
  vezes seguidas para o mesmo usuário, sempre que há alternativa.
- **Detecção de humor.** Frases como "estou meio estressado com o
  trabalho" ou "tô exausta" são reconhecidas (com tolerância a
  intensificadores no meio — "meio", "um pouco", "muito" — e a
  variações com/sem acento) e respondidas com empatia, não com "não
  entendi". O motor também guarda esse humor *durante a sessão atual*
  e pode voltar nisso depois, numa próxima saudação ("e aí, melhorou
  um pouco aquilo que você comentou?").
- **Referências para trás.** Em algumas respostas, o motor busca um
  projeto ou hábito que você já salvou (`core/memory.py`, memória
  categorizada) e devolve uma pergunta sobre aquilo — é isso que dá a
  sensação de "ele lembra de mim" em vez de responder e esquecer.
- **Consciência de tempo.** Sabe se é a primeira mensagem de todas
  (saudação de apresentação, diferente de uma saudação comum), se faz
  tempo desde a última troca (> 3h: "que bom te ver de novo!"), e
  respeita o período do dia que *você* mencionou ("boa tarde") em vez
  de impor o horário do sistema por cima.
- **Honesto sobre o que é.** Perguntado diretamente ("você é uma
  pessoa real?", "você tem sentimentos?"), o Jarvis responde a
  verdade: é um programa local. A meta aqui é a conversa fluir
  naturalmente, não fingir ser humano.

Categorias reconhecidas: saudação, despedida, agradecimento, elogio,
frustração/crítica ao Jarvis, perguntas sobre a identidade dele,
pedido de piada, "como você está", humor/sentimento expresso pelo
usuário, e respostas curtas tipo "kkk"/"rs"/"top".

### Onde isto entra no fluxo de resposta

```
1. Base de conhecimento curada      (pergunta factual)
2. Plugins de comando                ("lembre que...", "que horas são")
3. Motor de conversa natural         (saudação, humor, piada...)  <- esta seção
4. Fallback final                    (ajuda, ou "não sei o que fazer com isso")
```

Comandos explícitos sempre têm prioridade — "lembre que estou
estressado" continua sendo tratado como memória (plugin
`memory_commands`), não como expressão de humor, porque o motor de
conversa só é consultado depois que nenhum plugin soube responder.

### Por que a resposta não tem o bloco "Resposta:/Confiança:" aqui

Respostas factuais (base de conhecimento, plugins, fallback) saem
formatadas como:

```
Resposta:
<texto>

Confiança:
<nível>%
```

porque ali "confiança" tem sentido real: a informação pode ter vindo
de uma fonte, ser inferida, ser um palpite, etc. Já small talk
("oi", "tudo bem?", "obrigado") não tem esse tipo de incerteza — e
mostrar o bloco ali só faria a conversa parecer um questionário em
vez de uma conversa. Por isso `Answer` tem um campo `formal`
(`core/confidence.py`): o motor de conversa devolve `formal=False` e
`format()` retorna só o texto puro.

## Jarvis criando código sozinho: habilidades, programas e auto-melhoria

Três capacidades relacionadas, todas construídas em cima da mesma regra
de segurança: **código gerado por IA nunca entra em uso sem aprovação
humana explícita** -- um plugin tem o mesmo acesso ao sistema que o
resto do Jarvis (arquivos, processos, seu celular via ADB), então
código com bug, alucinado ou diferente do pedido nunca deveria rodar
sem alguém revisar primeiro.

### 1. Habilidades novas (plugins escritos pelo próprio Jarvis)

```
"aprenda a converter moedas" / "cria uma habilidade que me diz o clima"
```

Gera um plugin novo (`core/skill_forge.py` + `ia/manager.py`) e salva
em `plugins/pendentes/<nome>.py` -- uma pasta que `core/plugin_manager.py`
NUNCA varre, então o rascunho nunca entra em uso sozinho. Você:

- revisa o arquivo (o Jarvis te diz o caminho),
- aprova com `"aprova a habilidade <nome>"` -- move pra `plugins/` de
  verdade e recarrega os plugins na hora, sem reiniciar o Jarvis, ou
- rejeita com `"rejeita a habilidade <nome>"` -- só apaga o rascunho.

`"quais habilidades estão pendentes"` lista o que está esperando revisão.

### 2. Programas (scripts avulsos, sob demanda)

```
"cria um programa que organiza meus arquivos por data"
```

Mesma ideia, mas gera um script autocontido em
`data/programas_gerados/<nome>.py` em vez de um plugin -- não entra no
pipeline do Jarvis, só fica salvo. Rodar também exige confirmação
explícita (mesmo gate de `seguranca.permissions` usado por "fechar um
programa"):

```
"roda o programa <nome>, confirmo"
```

`"quais programas você criou"` lista os já gerados.

### 3. Controle de outros programas (janelas + login em sites)

Controle de janela (`automacao/janelas.py`, requer `pygetwindow`):

```
"minimiza o chrome" / "maximiza o spotify" / "restaura o discord" /
"foca no vscode" / "traz o discord pra frente"
```

Login automático em sites salvos (`automacao/logins_web.py`, requer
`keyring` + `playwright`, ver requirements-automacao.txt):

```
"loga no github"
"logins salvos"
"remove o login do github"
```

**A senha NUNCA é digitada no chat.** `core/jarvis.py` grava toda
mensagem no histórico de conversa antes de qualquer plugin rodar, então
uma senha no texto já ficaria em texto puro no banco (e nos backups
automáticos) antes de qualquer código poder impedir isso. Por isso
cadastrar um login é sempre por um caminho separado, que nunca passa
pelo chat: `python -m automacao.logins_web` no terminal (usa
`getpass`, sem eco na tela) ou o comando **"salvar login"** na
interface gráfica (abre um diálogo à parte, com campo de senha
mascarado -- intercetado antes de chegar no chat/`Jarvis.process()`,
nunca um botão). A senha em si fica só no cofre de
credenciais do próprio Windows (Credential Locker/DPAPI, via
`keyring`) -- nunca em `config.json`, nunca em `data/jarvis.db`.

### 4. Auto-melhoria, aprender sozinho e "sonhar" habilidades (em segundo plano)

Três rotinas autônomas rodam enquanto o Jarvis fica aberto:

- **Auto-melhoria** (`automacao/auto_melhoria.py`, `personalidade.auto_melhoria`,
  4h): verifica se o mesmo pedido caiu no fallback ("não sei fazer
  isso") pelo menos 3 vezes -- e se sim, gera sozinho um rascunho de
  habilidade pra aquele pedido e **avisa por notificação**.
- **Aprender tecnologia sozinho** (`automacao/aprendizado_autonomo.py`,
  `personalidade.aprender_tecnologia`, 24h): pesquisa um tópico novo
  (linguagem de programação ou tecnologia, ou um dos seus projetos
  salvos) na Wikipedia/IA e salva na base de conhecimento orgânico.
- **"Sonhar" habilidades** (`automacao/sonhos.py`, `personalidade.sonhos`,
  2h): inventa E TESTA sozinho uma habilidade nova (carrega e chama
  `handle()` com uma mensagem de teste antes de apresentar), e avisa.

Todas **avisam por notificação** e **nunca ativam nada sozinhas** --
uma habilidade gerada é sempre um rascunho esperando "aprova a
habilidade ...". Cada uma tem sua flag `false` em `config.json` se
preferir desligar.

**Importante -- a primeira rodada acontece logo, não daqui a horas.**
Antes, o primeiro aprendizado só rodava 24h depois de abrir o Jarvis e
a primeira "ideia sonhada" 2h depois -- ou seja, numa sessão normal de
minutos, nada autônomo jamais acontecia (era o "ele não cria nem
aprende nada sozinho"). Agora o primeiro aprendizado roda ~5 min depois
de abrir e a primeira ideia ~10 min depois, e daí seguem no intervalo
configurado.

**E dá pra disparar na hora, sem esperar** (`plugins/autonomia.py`):

```
"aprende algo novo" / "aprende algo na internet"   -> aprende um tópico agora e te mostra
"inventa uma habilidade" / "sonha uma habilidade"  -> inventa+testa uma habilidade agora (rascunho, pra aprovar)
```

("cria uma habilidade **que** faz X" continua sendo o item 1 -- com um
pedido específico; aqui é o pedido GENÉRICO de "cria/aprende algo
sozinho", sem você dizer o quê.)

### 5. Sistema de Intenção (objetivo → checklist rastreável)

`automacao/intencoes.py`: em vez de dar um comando por vez, você declara
um OBJETIVO grande e o Jarvis o quebra sozinho (via IA) num checklist de
passos concretos, salva, e acompanha o progresso.

```
"meta: lançar meu jogo esse mês"   -> vira um plano de 4-12 passos
"minhas metas"                     -> lista com progresso (2/11 feitos, etc.)
"conclui o passo 3 da meta 1"      -> marca e avança
"apaga a meta 1"
```

Honesto sobre o escopo: o Jarvis **planeja e acompanha** -- ele não
executa "criar trailer"/"preparar marketing" sozinho (não tem essas
capacidades, e fazer sem revisão seria arriscado). O valor é transformar
um objetivo vago numa lista clara e rastreável que sobrevive a reinícios.

### 6. Sistema de Curiosidade / Previsão (o que o Jarvis notou)

`sistema/curiosidade.py`: procura padrões e anomalias REAIS nos dados
que o Jarvis já coleta -- uso de hardware ao longo do tempo (coletado
de leve em segundo plano) e a linha do tempo de eventos.

```
"notou algo?" / "tem algo estranho?" / "previsão do sistema"
```

Reporta coisas como "no ritmo atual o disco encheria em ~X dias", "a RAM
está consistentemente alta", "esse erro apareceu N vezes essa semana",
"a maioria desses problemas caiu numa quinta". Também avisa sozinho por
notificação quando algo de gravidade alta aparece (disco quase cheio).
Honesto: é extrapolação estatística de dados reais, **não** previsão
mágica de bugs/travamentos -- e precisa de dados acumulados ao longo do
tempo pra ter o que dizer. Configurável em `sistema.curiosidade`.

O **sistema de sonhos** (item 4) foi atualizado pra puxar inspiração
dos seus objetivos ativos (Sistema de Intenção) e dessas curiosidades
detectadas -- então as habilidades que ele inventa sozinho tendem a ser
relevantes ao que você está tentando fazer, em vez de puramente
aleatórias.

### 7. Atualização do próprio Jarvis (checa sozinho, aplica só com confirmação)

`atualizacoes/updater.py`: a cada `atualizacoes.intervalo_horas` (padrão
24h, config `atualizacoes.verificar_automaticamente`, `true` por
padrão), checa se há commits novos no repositório remoto (`git fetch
--dry-run` -- só leitura) e **avisa por notificação** quando encontra
algo, uma vez por commit (não fica repetindo o mesmo aviso). Mesma
regra de sempre: nunca aplica nada sozinho --

```
"tem atualização nova" / "verifica atualização do jarvis"
"atualiza o jarvis, confirmo"
```

só o segundo comando roda `git pull` de verdade, e só com "confirmo"
na frase (ou com a confirmação global desligada, ver `seguranca`).
Requer que o projeto seja um repositório git com um remoto configurado
-- sem isso, a checagem simplesmente não encontra nada pra avisar, sem
travar nada.

## Mais autonomia: tela em tempo real, celular, Instagram, acesso remoto, vídeos/jogos, navegação

### Motor de Missões

O Neutron possui missões persistentes que dividem um objetivo em comandos
reais, executam um passo por vez, guardam evidências e retomam após
reiniciar. Ações de alto risco ficam paradas até a aprovação do passo
específico. Quando `missoes.executar_automaticamente` está ativo, missões
prontas avançam enquanto o computador está ocioso.

```text
nova missão: preparar meu ambiente de trabalho
minhas missões
executa missão 1
aprova passo 2 da missão 1
pausa missão 1
retoma missão 1
```

Mais uma leva de capacidades, quase todas construídas em cima do que já
existia (skill_forge, tasks.schedule_recurring, timeline, Playwright).

**Entender tela/vídeo "em tempo real"** -- `"entende o vídeo em tempo
real"` / `"acompanha meu jogo em tempo real"` (plugins/observation.py):
verifica a cada 20s (em vez do intervalo aleatório de minutos do modo
normal) e só comenta quando a janela ou o texto na tela realmente muda.
Honestidade: continua sendo janela+OCR (visao/observe.py), não análise
de imagem/vídeo de verdade -- os provedores de IA configurados
(ia/manager.py) não têm entrada de imagem ligada ainda.

**Corrigir erros automaticamente**: quando um plugin quebra em tempo de
execução, ou um programa gerado falha ao rodar, o Jarvis já gera
sozinho um rascunho de correção (`core/skill_forge.py:gerar_correcao_*`)
e oferece pra você aprovar -- nunca aplica sozinho (mesma regra dos
rascunhos de habilidade). No máximo uma tentativa por plugin por sessão,
pra não gastar chamada de IA repetida num plugin que continua quebrado.

**Celular monitorado sozinho**: `"monitora a bateria do celular"`
(plugins/device_control.py) fica de olho a cada 15 min e avisa sozinho
se cair a 20% ou menos sem estar carregando -- `"para de monitorar a
bateria"` cancela.

**Conecta a conta do Instagram**: `"conecta minha conta do instagram"`
(ou variações naturais como `"loga no instagram"`, `"entra no
instagram"`, `"acessa o instagram"`, `"faz login no instagram"` --
todas reconhecidas) abre a página de login DE VERDADE do Instagram
numa aba, mesmo princípio do login com o Google: você digita sua
senha/2FA direto com o Instagram, o Jarvis nunca vê nem guarda essa
senha. A sessão fica salva (`data/instagram_browser_profile/`) para as
próximas vezes -- ler mensagens, e responder sozinho se o envio
automático (abaixo) estiver ligado.

**Instagram com envio automático (opcional, desligado por padrão)**:
`"ativa o envio automático do instagram"` liga um modo que lê e
responde mensagens sozinho, **sem revisão sua** -- diferente do padrão
do projeto (só sugestão). Isso é uma troca de segurança real: viola os
Termos de Uso do Instagram (risco de banimento) e a pessoa do outro
lado não sabe que fala com um bot. Só existe porque foi pedido
explicitamente sabendo do risco. Redutores de risco em
`automacao/instagram_auto.py`: sessão de navegador persistente (evita
logins repetidos), atraso "humano" antes de enviar, limite diário de
envios (`instagram.limite_envios_por_dia`, 15 por padrão), e toda
mensagem enviada fica registrada na timeline pra auditoria. Desligue
com `"desativa o envio automático do instagram"` a qualquer momento.

**Cria vídeos** (gravação + edição da tela, `visao/screen.py` +
`visao/video_edit.py` + `plugins/video_creation.py`): `"grava minha
tela por 20 segundos"` (bloqueia o Jarvis durante a gravação, teto de
120s), depois `"corta o vídeo <nome> de 5 a 15 segundos"` ou `"acelera
o vídeo <nome> em 2x"`. Requer `mss` + `opencv-python`
(requirements-visao.txt).

**Cria jogos completos a partir só de um tema**: `"cria um jogo sobre
piratas espaciais"` -- sem precisar descrever mecânica nenhuma,
`core/skill_forge.py` gera em DUAS etapas: primeiro pede pra IA
inventar um design completo (título, lore/história, mecânica,
condições de vitória/derrota, 2-4 níveis com dificuldade crescente) só
a partir do tema, depois implementa esse design inteiro como jogo
jogável de verdade (todos os níveis, tela de abertura com a lore, telas
de vitória/derrota). Por padrão em 2D (Pygame, sem baixar nenhum asset
externo, só formas desenhadas); peça `"cria um jogo em 3d sobre..."`
pra gerar em 3D de verdade (câmera navegável, entidades com posição
x/y/z) via `ursina` (opcional, requirements-jogos.txt -- download bem
maior que o pygame). O design gerado fica salvo ao lado do jogo
(`<nome>.design.json`), pra ler a lore sem precisar abrir o código.
Mesma regra de programas: gera em `data/programas_gerados/`, roda com
`"roda o programa <nome>, confirmo"`.

**Navega sozinho na internet**: `"pesquisa na internet sobre X"`
(`automacao/navegador.py`) pesquisa no DuckDuckGo, abre de verdade até
3 páginas de resultado, lê o conteúdo, e pede pra IA resumir/responder
citando a fonte -- diferente de `knowledge_search.py` (só Wikipedia).
Deliberadamente **somente leitura e sob demanda**: nunca preenche
formulário, nunca loga em nada, nunca compra nada, e só roda quando
você pede -- não é um robô vasculhando a internet sem parar em segundo
plano.

**Linha do tempo de tudo que aconteceu no PC**: `"linha do tempo"` /
`"o que aconteceu ontem"` / `"o que aconteceu essa semana"`
(`core/timeline.py` + `plugins/timeline.py`) junta os eventos que os
módulos de automação já registram (abrir/fechar programa, lembretes,
habilidades criadas/aprovadas, janelas controladas, logins usados,
vídeos gravados, correções automáticas, pesquisas na internet...) numa
lista cronológica. De propósito NÃO mostra cada mensagem de chat --
só os eventos que os módulos decidiram valer a pena registrar.

**Lembretes recorrentes**: além de "às 18h" (uma vez), agora também
`"me lembra de beber água a cada 1 hora"` -- repete indefinidamente até
você dizer `"para de me lembrar de beber água"` (`automacao/reminders.py`).

**Professor particular**: `"me ensina sobre recursão"` / `"quero
aprender sobre APIs"` / `"me dá uma aula sobre economia"`
(`plugins/professor.py`) explica do zero, com um system prompt próprio
de professor paciente (não a persona configurada do Jarvis). `"me
testa sobre X"` gera uma pergunta -- responda com `"resposta: ..."`
pra ele corrigir.

**Aprende tecnologia nova sozinho**: a cada 24h (config
`personalidade.aprender_tecnologia_intervalo_horas`), pesquisa um
tópico -- prioridade pros seus "projetos" salvos na memória
categorizada, senão uma lista rotativa de tecnologias -- via Wikipedia
(ou a IA como alternativa) e salva no conhecimento orgânico
(`core/knowledge.py`, mesmo mecanismo de "aprenda que X"). Avisa por
notificação o que aprendeu. Desligue com
`"personalidade.aprender_tecnologia": false`.

## Interface, conta do Google, hábitos, linguagem própria e mais autonomia

### Central avançada do Neutron

O botão **Central** abre painéis de diagnóstico, atividades, memória,
integrações, habilidades, privacidade, agenda, projetos, segurança e
desempenho. A central também oferece memória temporária, checkpoints,
permissões por grupo, cofre de API keys, métricas de provedores,
simulação de automações, auditoria estática e rollback de plugins.

Atalhos na janela principal: `Ctrl+Space` foca o chat, `Esc` cancela a
operação atual e `Ctrl+Shift+C` abre a Central. Pesquisas web removem
linhas com padrões comuns de prompt injection antes de entregar o
conteúdo à IA, e provedores/plugins com falhas repetidas entram
temporariamente em circuit breaker para evitar loops.

Mais uma leva grande de capacidades. Como sempre: nada que toque o
sistema de verdade roda sem aprovação/confirmação explícita.

**Interface mais bonita** (PC): `gui/app.py`/`gui/neutron_core.py`
ganharam gradientes, glow (`QGraphicsDropShadowEffect`), interpolação
suave de energia no núcleo, bolhas de chat com cor por remetente e
scrollbar customizada. O núcleo visual tem estados próprios para ouvir,
pensar, aprender e pesquisar; o chat pisca a borda sutilmente a cada
mensagem nova, e "Jarvis está pensando..." anima as reticências em vez
de ficar estático. O antigo app Android foi removido do projeto.

**Voz também na GUI do PC**: além do modo de voz
"de verdade" (`python main.py --voz`, ver `voz/README.md`), agora dá
pra falar com o Jarvis pelo botão 🎤 na GUI, reaproveitando
`voz/stt.py`, incluindo a detecção de silêncio. A entrada por voz
sempre vira uma mensagem natural (nunca
prefixada com "/") -- mesma convenção do modo de comando direto.

**Login com a conta do Google**: `"conecta minha conta do google"`
(`automacao/logins_web.py`) abre a página de login DE VERDADE do
Google numa aba do navegador -- você digita sua senha/2FA direto com o
Google, o Jarvis nunca vê nem guarda essa senha (não é OAuth, é reuso
de uma sessão de navegador persistente). Depois disso, `"entra no
<site> com o google"` clica no botão "Continuar com o Google" de
qualquer site, usando essa mesma sessão -- sem precisar salvar uma
senha separada pra cada um.

**Bug corrigido -- "Jarvis esquecendo o usuário"**: `main.py` e
`gui/app.py` perguntavam o nome de usuário a cada execução, caindo
pro literal `"default_user"` se você só apertasse ENTER -- então
digitar o nome numa sessão e só apertar ENTER na próxima criava um
perfil/memória SEPARADO a cada vez. Agora o último nome usado fica
salvo (`config.json` -> `geral.usuario_padrao`) e é sugerido como
padrão, então ENTER continua com o MESMO usuário em vez de reiniciar
do zero.

**Observa como você usa um programa, e aprende**: `"observa como eu
uso o excel"` (`plugins/aprendizado_programa.py`) tira capturas
periódicas (janela + texto na tela) enquanto você trabalha; `"para de
aprender o excel"` encerra e pede pra IA resumir o fluxo num "como
usar", salvo na base de conhecimento. Não é automação/replay -- Jarvis
aprende a DESCREVER o que viu, não a clicar sozinho nos mesmos lugares.

**Analisa hábitos no PC e no celular**: `"quais são meus hábitos no
pc"` / `"...no celular"` (`automacao/habitos.py`) amostra o app/janela
em primeiro plano a cada poucos minutos (5min PC, 15min celular) e
responde com uma contagem de verdade dos apps mais usados -- não um
palpite.

**Aprende linguagens de programação sozinho**: o mesmo sistema de
"aprender tecnologia sozinho" agora intercala tecnologias gerais com
uma lista de linguagens de programação (Rust, Go, Kotlin, TypeScript,
Swift, Elixir, Zig, Julia, Haskell, Lua...), usando um prompt mais
aprofundado (sintaxe + exemplo de código) pra cada linguagem.

**JarvisScript -- linguagem de programação própria**: `linguagem/` tem
um léxico, parser recursivo descendente e interpretador "tree-walking"
escritos do zero (variáveis, funções com closures, `se`/`enquanto`/
`para`, listas, tratamento de erro de verdade, teto de passos/tempo
contra loop infinito). 100% sandboxed -- sem acesso a arquivo, rede ou
Python de fora. `"roda em jarvisscript: <código>"` executa; `"o que é
jarvisscript"` explica a sintaxe. Ver `linguagem/README.md`.

**Baixa/instala programas só pelo nome**: `"instala o vlc"` / `"baixa
o spotify"` (`automacao/instalador_apps.py`) usa o `winget` (Windows
Package Manager, o mesmo por trás da tela de instalação de apps do
Windows) -- exige confirmação, igual fechar um programa.
`"procura o pacote do X"` lista candidatos sem instalar nada.

**Gêmeo digital**: `"testa organizar a pasta <caminho> num gêmeo
digital"` (`automacao/gemeo_digital.py`) copia a pasta, aplica a
organização por tipo NA CÓPIA, e mostra o que teria mudado -- só
depois disso `"aplica de verdade a organização da pasta..., confirmo"`
roda de verdade no original. Honestidade: simular o computador/celular
inteiro não é possível -- isto simula o efeito de UMA operação
específica numa cópia real dos arquivos.

**Sistema de "sonhos"**: a cada ~2h (config
`personalidade.sonhos_intervalo_horas`), Jarvis inventa E TESTA sozinho
uma habilidade nova (usando `core/skill_forge.py`, com um prompt mais
livre/criativo que "aprender tecnologia") -- carrega a habilidade de
verdade e chama `handle()` com uma mensagem de teste antes de
apresentar; se quebrar no autoteste, descarta silenciosamente sem te
incomodar. Nunca ativa nada sem sua aprovação -- mesma regra de sempre.

**Estado interno simulado (energia/humor)**: `core/estado_interno.py`
mantém uma energia (100 no início do dia, cai um pouco a cada mensagem,
piso em 20) e um humor sorteado dentro de uma faixa coerente com a
energia -- influencia sutilmente o TOM das respostas da IA. Isto NÃO é
consciência real (isso não existe, não dá pra construir) -- é só mais
uma variável de contexto, e o Jarvis é sempre honesto sobre isso ser
simulado quando perguntado diretamente (às vezes aparece na resposta
de "como você está").

**Sobre "achar contas do Instagram/Instagram de alguém só com o
nome"**: decidi não construir uma ferramenta dedicada de busca de
pessoas. Um buscador de pessoas genérico (nome -> perfis em várias
redes) é o tipo de ferramenta que também habilita stalking/perseguição
contra alguém que não consentiu, e não tem como eu verificar a
legitimidade do uso caso a caso. O que já existe (`plugins/navegador.py`,
`"pesquisa na internet sobre X"`) já cobre o uso legítimo -- achar sua
própria conta esquecida, ou confirmar um perfil de alguém que já te
passou o nome/@.

### Limitações honestas (sem inflar)

- Isto continua sendo **casamento de padrões com variação**, não
  geração de linguagem livre — o Jarvis não vai improvisar uma
  resposta nova para algo fora dos padrões cadastrados aqui (nesse
  caso, cai no fallback normal).
- A detecção de intenção é por palavras-chave/regex, então frases
  ambíguas que por acaso contenham um gatilho (ex.: uma pergunta sobre
  outro assunto que contenha "como vai") podem ser interpretadas como
  small talk em vez de cair no plugin certo. É a mesma limitação que
  já existe nos outros plugins do projeto, baseados no mesmo
  mecanismo de triggers.
- O humor guardado em `_last_mood` é só de memória RAM da sessão atual
  (processo em execução) — reiniciar o `main.py` o reseta. Isso é
  intencional (ver comentário no topo de `core/conversation.py`), mas
  se quiser persistir entre sessões, dá pra estender salvando em
  `memory.save_memory(user_id, "important_conversation", ...)`.
- Quer plugar um LLM real (incluindo a API da Anthropic) para
  conversas mais ricas e abertas? O ponto de extensão é o mesmo de
  sempre: `Jarvis._fallback_response()` em `core/jarvis.py`, chamado
  quando nem a base de conhecimento, nem os plugins, nem este motor de
  conversa souberam responder.

## Memória permanente categorizada e priorizada

Além da memória de fatos livres (`lembre que...`), o Jarvis tem uma
camada de memória **categorizada** e **priorizada**, pensada para guardar
o que realmente importa sobre o usuário ao longo do tempo:

| Categoria                  | Exemplo de uso                                      | Prioridade padrão |
|------------------------------|------------------------------------------------------|:---:|
| `name` (nome)                 | tratado via perfil (`meu nome é ...`)                | 100 |
| `important_conversation` (conversa importante) | decisões, combinados, contexto relevante | 90  |
| `project` (projeto)            | projetos em andamento e seus detalhes                | 70  |
| `preference` (preferência)     | gostos, configurações preferidas                     | 60  |
| `habit` (hábito)               | rotinas e padrões de comportamento                    | 50  |

A prioridade é um número de 0 a 100: quanto maior, mais relevante o
item é considerado quando o Jarvis monta um resumo de contexto. Você
pode usar a prioridade padrão da categoria ou definir a sua.

### Comandos disponíveis no chat

```
salve o projeto Jarvis: assistente pessoal em Python com plugins
salve a preferência tema escuro: prefiro interface escura sempre
salve o hábito acordar cedo: desperto às 6h todos os dias
salve a conversa importante decisao arquitetura: vamos usar SQLite

atualize a preferência tema escuro: ativar por padrão sempre

busque sobre Jarvis

liste meus projetos
liste minhas preferências
liste meus hábitos

remova o hábito acordar cedo

minha memória          (mostra tudo, ordenado por prioridade)
```

### Usando programaticamente (`core/memory.py`)

```python
from core.memory import Memory

m = Memory()

# Salvar (cria ou faz upsert se já existir)
m.save_memory("user1", "project", "site pessoal", "portfolio em React", priority=80)

# Atualizar (só falha se o item não existir ainda)
m.update_memory("user1", "project", "site pessoal", content="portfolio em React com blog")

# Buscar um item específico
m.get_memory("user1", "project", "site pessoal")

# Buscar por texto (em título e conteúdo, em qualquer categoria ou só uma)
m.search_memory("user1", "react")
m.search_memory("user1", "react", category="project")

# Listar tudo de uma categoria, já ordenado por prioridade
m.list_memory("user1", category="project")

# Remover
m.remove_memory("user1", "project", "site pessoal")

# Repriorizar um item já existente
m.set_priority("user1", "habit", "exercicio", 95)

# Resumo pronto para contexto (ex: injetar num prompt de LLM)
m.get_context_summary("user1")
```

As categorias válidas são fixas: `name`, `preference`, `project`,
`important_conversation`, `habit`. Tentar usar outra levanta `ValueError`
com a lista de categorias aceitas — isso é intencional, para não deixar
a memória se encher de categorias inconsistentes (`"projeto"` vs
`"projetos"` vs `"Project"`, etc.).

### Por que SQLite e não JSON puro

Ambos foram considerados aceitáveis no pedido original. Optei por
SQLite (já usado no resto do projeto) por três motivos práticos:
busca por texto e filtros (`WHERE category=...`) sem precisar carregar
o arquivo inteiro na memória; updates atômicos com `UNIQUE` constraint
evitando duplicatas silenciosas; e leitura/escrita concorrente seguras
o bastante para um assistente local. Se preferir JSON simples (por
exemplo, para inspecionar/editar manualmente os dados em texto), é
possível trocar o backend sem alterar a interface pública de `Memory`
— me avisa se quiser essa variante.

### Plugin novo (exemplo mínimo)

```python
# plugins/meu_plugin.py
from core.plugin_manager import BasePlugin

class MeuPlugin(BasePlugin):
    name = "meu_plugin"
    description = "O que ele faz"
    triggers = ["palavra-chave"]

    def handle(self, text, context):
        # context tem: memory, user_id, history
        return "minha resposta"
```

Salve o arquivo em `/plugins` e rode `/recarregar` no chat (ou reinicie).

### Ligar a um LLM real para respostas mais inteligentes

O método `Jarvis._fallback_response()` em `core/jarvis.py` é o ponto
de extensão ideal: é chamado sempre que nenhum plugin souber responder.
Você pode substituí-lo por uma chamada à API da Anthropic (ou outra)
passando o histórico de `context["history"]` como contexto da conversa.
