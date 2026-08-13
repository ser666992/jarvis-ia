# automacao/ — Automação de sistema e arquivos

O núcleo (abrir programas/sites, buscar e organizar arquivos, backup
em zip, agendamento) roda 100% com a stdlib — zero dependência
obrigatória. `watchdog` (opcional) só melhora a eficiência da
observação de pastas; sem ele, cai para polling.

## Módulos

- `apps.py` — abrir programas/URLs (sempre permitido); fechar um
  programa por nome é **ação destrutiva** e passa por
  `seguranca.check_destructive_action` (exige `confirmed=True`
  explícito de quem chama — nunca fecha nada sozinho).
- `files.py` — buscar arquivos por padrão, organizar uma pasta por
  tipo (move para subpastas — destrutivo, exige confirmação), renomear
  (destrutivo, exige confirmação), backup em `.zip` com timestamp (não
  destrutivo, não exige confirmação).
- `tasks.py` — rotinas/agendamento (`threading.Timer`), com registro
  em SQLite (`core/database.py`) para histórico.
- `watcher.py` — observa uma pasta e chama um callback em
  criação/edição/remoção de arquivo.
- `reminders.py` — lembretes com horário ("me lembre que ... às
  18h", uma vez) ou recorrentes ("me lembra de beber água a cada 1
  hora", repete indefinidamente até "para de me lembrar de ..."),
  agendados via `tasks.py` e persistidos em SQLite (sobrevivem
  a reinícios). Ver `plugins/reminders.py`.
- `notify.py` — notificação genérica (som + print + hooks pra avisos
  visuais, ex.: toast na GUI), usada por `reminders.py` e por
  `plugins/observation.py`.
- `media_keys.py` — volume/mudo via tecla de mídia simulada
  (`ctypes`/`user32.keybd_event`, zero dependência, só Windows).
- `janelas.py` — minimizar/maximizar/restaurar/focar janelas de outros
  programas por título (requer `pygetwindow`). Diferente de
  `apps.close_program` (mata o processo): aqui a janela continua
  existindo, só muda de estado — reversível na hora, não passa por
  `seguranca.permissions`. Ver `plugins/system_control.py`.
- `logins_web.py` — login automático em sites salvos (requer `keyring`
  + `playwright`). A senha só fica no cofre de credenciais do Windows
  (`keyring`, nunca em texto puro) — **cadastrar um login nunca
  acontece por texto de chat** (rode `python -m automacao.logins_web`
  ou diga "salvar login" na GUI, que abre um diálogo à parte antes de
  chegar no chat), só usar um login já salvo é que é feito por chat
  ("loga no github"). Ver `plugins/logins_web.py`.
- `browser_engine.py` — se o Brave estiver instalado, `logins_web.py`
  e `instagram_auto.py` usam ele em vez do Chromium baixado pelo
  Playwright (`automacao.preferir_brave`, `true` por padrão) -- Brave é
  baseado em Chromium e fala o mesmo protocolo de automação. Continua
  sendo um perfil de navegador PRÓPRIO do Jarvis (pasta separada em
  `data/`), não o seu perfil pessoal do Brave -- só troca qual
  executável renderiza as páginas.
- `auto_melhoria.py` — de tempos em tempos (config
  `personalidade.auto_melhoria_intervalo_horas`, 4h por padrão),
  verifica se o mesmo pedido caiu no fallback repetidas vezes e, se
  sim, gera sozinho um rascunho de habilidade pra ele (`core/skill_forge.py`)
  e notifica pra você aprovar — nunca ativa nada sem aprovação.
- `aprendizado_autonomo.py` — de tempos em tempos (config
  `personalidade.aprender_tecnologia_intervalo_horas`, 24h por padrão),
  pesquisa um tópico (projetos salvos na memória, ou uma lista rotativa
  de tecnologias) via Wikipedia/IA e salva no conhecimento orgânico
  (`core/knowledge.py`) — avisa por notificação o que aprendeu.
- `instagram_auto.py` — envio automático de respostas no Instagram
  Direct, **opcional e desligado por padrão** (`instagram.envio_automatico`).
  Diferente do resto do projeto (que só sugere), isso realmente
  responde sozinho, sem revisão — só existe porque foi pedido
  explicitamente sabendo do risco de banimento (viola os Termos de Uso
  do Instagram). Login via `conectar_instagram()` -- mesmo princípio do
  Google (ver `logins_web.py`): você faz login DE VERDADE no Instagram
  numa aba, o Jarvis nunca vê nem guarda sua senha, só reusa a sessão
  depois (perfil de navegador próprio, `data/instagram_browser_profile/`).
  Ver `plugins/instagram.py` pros comandos ("conecta minha conta do
  instagram", "loga no instagram", "entra no instagram", "acessa o
  instagram" -- todas variações reconhecidas pra abrir o mesmo login;
  liga/desliga o envio automático) e os redutores de risco
  (sessão persistente, atraso humano, limite diário, log de auditoria
  na timeline).
- `navegador.py` — pesquisa um termo na internet (DuckDuckGo), lê de
  verdade até 3 páginas de resultado e resume com a IA configurada.
  Somente leitura por design: nunca preenche formulário, nunca loga em
  nada, só roda sob demanda (nunca em segundo plano sem ser pedido).
- `aprendizado_programa.py` — tira capturas periódicas (janela + texto
  na tela) enquanto você usa um programa, e ao encerrar pede pra IA
  resumir o fluxo num "como usar", salvo no conhecimento orgânico.
  Não é automação/replay -- só aprende a DESCREVER o que viu. Ver
  `plugins/aprendizado_programa.py`.
- `habitos.py` — amostra o app/janela em primeiro plano no PC a cada
  poucos minutos (5min) e acumula em SQLite pra responder "quais são
  meus hábitos" com uma contagem de verdade.
- `instalador_apps.py` — instala programas por nome via `winget`
  (Windows Package Manager) -- ação destrutiva-adjacente, exige
  confirmação explícita igual fechar um programa.
- `gemeo_digital.py` — copia uma pasta, aplica `files.organize_by_type`
  NA CÓPIA, e devolve um relatório do que teria mudado -- só depois
  disso a operação real (com confirmação) roda no original.
- `sonhos.py` — de tempos em tempos (config
  `personalidade.sonhos_intervalo_horas`, 2h por padrão -- mais
  frequente e livre que `auto_melhoria.py`/`aprendizado_autonomo.py`),
  inventa E TESTA sozinho uma habilidade nova (carrega de verdade e
  chama `handle()` com uma mensagem de teste antes de apresentar) --
  nunca ativa nada sem aprovação.
- `escuta_ativa.py` — sessão de escuta acompanhada, com tempo limitado
  ("escuta essa conversa por 10 minutos"). A alternativa responsável a
  um modo de escuta contínua sempre ligado (recusado por natureza:
  ambient listening sem escopo definido capta terceiros sem
  consentimento e nunca tem um fim natural) -- aqui a escuta só começa
  com um comando explícito, tem um teto de segurança
  (`escuta_ativa.duracao_maxima_minutos`, 30 por padrão) mesmo se
  pedirem mais, avisa (som + mensagem) quando começa e quando termina,
  pode ser encerrada a qualquer momento ("para de escutar"), e a
  transcrição só vive na memória do processo (nunca salva em
  disco/banco) até uma nova sessão começar ou até "esquece o que você
  ouviu". Ver `plugins/escuta_ativa.py`.
- `macros.py` — sequências de comandos já existentes, salvas sob um
  nome ("cria uma macro boa noite: fecha o chrome, muta o som,
  diminui o brilho"), rodadas sob demanda ("roda a macro boa noite")
  ou agendadas ("agenda a macro boa noite a cada 30 minutos" --
  `tasks.schedule_recurring`, sobrevive a reinícios). Cada passo roda
  no modo de comando direto do Jarvis (`jarvis.process("/" + passo)`)
  -- continua passando por toda checagem de confirmação/segurança de
  sempre, passo a passo. Ver `plugins/macros.py`.

## Uso

```python
import automacao

automacao.apps.open_url("https://github.com")
automacao.apps.close_program("notepad", confirmed=True)

automacao.files.search_files(r"C:\Users\voce\Documents", "*.pdf")
automacao.files.organize_by_type(r"C:\Users\voce\Downloads", confirmed=True)
automacao.files.backup_folder(r"C:\Users\voce\Projetos\meu_app")

automacao.tasks.schedule_recurring("check_disco", 3600, minha_funcao)

watcher = automacao.watcher.FolderWatcher(r"C:\pasta", on_change=print)
watcher.start()

automacao.media_keys.volume_up()
automacao.notify.notify("Jarvis", "mensagem qualquer")
```

## Dependência opcional

```bash
pip install -r requirements-automacao.txt   # watchdog, pyautogui, keyboard, mouse, pynput, pygetwindow, keyring, playwright
python -m playwright install chromium       # só necessário pra usar logins_web.py
```

`pyautogui`/`keyboard`/`mouse`/`pynput` ficam disponíveis para plugins
que queiram automação de teclado/mouse mais avançada (não usadas
diretamente pelo núcleo, para manter o padrão "core sem dependência").
`pygetwindow` habilita `janelas.py`; `keyring`+`playwright` habilitam
`logins_web.py`, `instagram_auto.py` e `navegador.py` — sem eles, os
plugins correspondentes avisam o que falta instalar em vez de travar.

Jogos gerados por `core/skill_forge.py` ("cria um jogo que...") usam
Pygame -- `pip install -r requirements-jogos.txt` só é necessário pra
RODAR o jogo, não pra gerar/revisar o código.

`instalador_apps.py` usa o `winget`, que já vem instalado em Windows
10/11 atualizados (parte do "App Installer") -- não é um pacote Python,
nada pra instalar via pip.
