"""
automacao/instagram_auto.py
==============================
Envio automático de respostas no Instagram Direct -- SEM revisão sua.

Isso é uma mudança deliberada em relação ao padrão do projeto
(plugins/instagram.py, que só sugere): o usuário foi avisado
explicitamente que automação não-oficial viola os Termos de Uso do
Instagram (risco real de banimento da conta) e que quem recebe a
mensagem não vai saber que está falando com um bot -- e confirmou que
quer isso mesmo assim. Ver plugins/instagram.py para os comandos que
ligam/desligam isso.

Redutores de risco (não eliminam o risco, só reduzem):
- **Desligado por padrão**, mesmo depois dessa confirmação -- precisa
  de um comando explícito ("ativa o envio automático do instagram")
  pra realmente começar a mandar sozinho.
- **Sessão persistente** (Playwright `launch_persistent_context`, perfil
  salvo em data/instagram_browser_profile/): evita logins repetidos,
  que são um dos padrões mais associados a detecção de bot.
- **Atraso humano** antes de enviar (alguns segundos aleatórios), em
  vez de responder instantaneamente.
- **Limite diário de envios** (config `instagram.limite_envios_por_dia`,
  padrão 15) -- passou do limite, para de mandar sozinho e avisa que
  as próximas mensagens precisam de revisão manual.
- **Log de auditoria**: toda mensagem enviada sozinho fica registrada
  na timeline (core/timeline.py, evento "instagram_enviado") com o
  texto exato mandado, pra você conseguir conferir depois.
- Nunca reprocessa a mesma mensagem duas vezes (marca como
  "instagram_processada" na timeline antes de seguir pra próxima).

Fonte das notificações -- BUG REAL corrigido: `_tick()` só lia
`automacao/notification_inbox.py` (alimentada pelo app companion do
celular via `POST /notify`). O app e o servidor HTTP foram removidos
do projeto (não existem mais), então esse inbox nunca mais é
preenchido -- `_tick()` rodava pra sempre sem achar nada, SEM avisar
(pior tipo de falha: parecia que só não tinha mensagem nova, quando na
verdade a fonte de dados tinha sumido). Agora `_tick()` cai pro ADB sem
fio (`dispositivos.adb.list_notifications()`) quando o inbox está
vazio -- mesmo fallback que `plugins/instagram.py` já usava pra "minhas
mensagens do instagram" (que continuava funcionando por ADB), só que
`_tick()`/envio automático não tinha esse fallback.
"""

import random
import json
import os
import re
import socket
import subprocess
import time
from urllib.request import urlopen

from automacao.notification_inbox import mensagens_de as inbox_mensagens_de
from automacao import tasks
from automacao.notify import notify
from core.personality import NOME
from core.timeline import registrar
from dispositivos import adb
from logs.logger import get_logger

log = get_logger("automacao")

_INSTAGRAM_PKG = "com.instagram.android"
_LIMITE_DIARIO_PADRAO = 15
_INTERVALO_POLL = 30  # segundos

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

_perfil_dir = None
_sessao = {}  # mantém playwright/browser/page vivos entre ticks
MODO_DEDICADO = "dedicado"
MODO_NAVEGADOR = "navegador"
_processo_login = None
_ultima_tentativa_reconexao = 0.0
_INTERVALO_RECONEXAO = 300


def available() -> bool:
    return HAS_PLAYWRIGHT


def _system_prompt_sugestao(contexto_extra: str) -> str:
    from config.settings import get_settings
    perfil = get_settings().get("instagram.perfil_resposta", "casual")
    estilos = {
        "casual": "casual, natural e breve",
        "profissional": "profissional, claro e cordial",
        "atendimento": "acolhedor, objetivo e focado em resolver a solicitação",
        "vendas": "consultivo, útil e sem pressão; faça no máximo uma pergunta",
        "amigos": "próximo, descontraído e espontâneo",
    }
    base = (
        f"Você está ajudando a redigir uma resposta de Instagram Direct em nome do "
        f"usuário -- você NÃO é o {NOME} respondendo aqui, é a própria voz dele. Tom "
        f"{estilos.get(perfil, estilos['casual'])}, como uma mensagem de verdade entre pessoas -- nunca "
        "se identifique como assistente ou IA, e não adicione nada além da resposta "
        "em si (sem 'aqui está uma sugestão:' ou aspas)."
    )
    if contexto_extra:
        base += f"\n\nContexto sobre o usuário (pra imitar melhor o estilo dele):\n{contexto_extra}"
    return base


def _garantir_pagina(modo=None):
    pagina_existente = _sessao.get("page")
    if pagina_existente is not None:
        try:
            if not pagina_existente.is_closed():
                return pagina_existente
        except Exception:
            pass
        # A janela foi fechada ou a sessão ficou inválida. Não devolva
        # uma Page morta em todas as tentativas seguintes.
        _sessao.clear()
    if not HAS_PLAYWRIGHT:
        raise RuntimeError(
            "Instale 'playwright' (requirements-automacao.txt) e rode "
            "'python -m playwright install chromium' pra eu conseguir usar o Instagram."
        )

    from config.settings import get_settings
    # Pedido explícito do usuário (2026-07-06): conectar pelo Brave do
    # dia a dia dele, reaproveitando a sessão JÁ LOGADA -- em vez de
    # exigir um login novo num perfil isolado. "instagram.usar_perfil_proprio"
    # (false por padrão agora) é a válvula de escape pra voltar ao perfil
    # isolado antigo se isso causar algum problema.
    if modo is None:
        modo = get_settings().get("instagram.modo_conexao", MODO_DEDICADO)
    if modo == MODO_NAVEGADOR:
        try:
            pagina = _garantir_pagina_perfil_pessoal()
            if pagina is not None:
                return pagina
        except Exception as e:
            log.warning(
                "instagram_auto: falha usando o navegador pessoal (%s) -- caindo pro perfil "
                "isolado.", e,
            )
    return _garantir_pagina_perfil_isolado()


def _garantir_pagina_perfil_pessoal():
    """Reaproveita o navegador do dia a dia (Brave/Chrome/Edge) -- se
    você já está logado no Instagram nele, o Jarvis cai direto na caixa
    de entrada, sem pedir login de novo. Cópia isolada (não mexe no seu
    perfil real, funciona com o navegador aberto) numa pasta PRÓPRIA
    (não a cópia genérica de navegador_pessoal.py), pra manter a sessão
    do Instagram estável entre uma chamada e outra."""
    import os
    from automacao import navegador_pessoal
    if not navegador_pessoal.available() or not navegador_pessoal.qual_navegador():
        return None
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pasta_copia = os.path.join(base_dir, "data", "instagram_perfil_pessoal_copia")
    contexto, pagina = navegador_pessoal.abrir_logado(
        "https://www.instagram.com/", pasta_copia=pasta_copia, esconder_automacao=True,
    )
    _sessao["pw"] = getattr(contexto, "_ultron_pw", None)
    _sessao["contexto"] = contexto
    _sessao["page"] = pagina
    return pagina


def _garantir_pagina_perfil_isolado():
    """Caminho antigo: perfil Playwright PRÓPRIO do Instagram (não o
    navegador do dia a dia), exigindo login manual na primeira vez.
    Mantido como fallback (config `instagram.usar_perfil_proprio: true`,
    ou se o navegador pessoal não estiver disponível)."""
    global _perfil_dir
    if _perfil_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _perfil_dir = os.path.join(base_dir, "data", "instagram_browser_profile")
        os.makedirs(_perfil_dir, exist_ok=True)

    from automacao.browser_engine import kwargs_launch
    from config.settings import get_settings
    pw = sync_playwright().start()
    # O login manual novo abre um navegador comum com depuração local.
    # Se ele ainda estiver aberto, apenas anexamos à sessão já autenticada.
    porta_cdp = int(get_settings().get("instagram.cdp_port", 0) or 0)
    if porta_cdp:
        try:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{porta_cdp}")
            contexto = browser.contexts[0]
            pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
            _sessao.update({"pw": pw, "browser": browser, "contexto": contexto, "page": pagina})
            return pagina
        except Exception:
            pass
    # Diferente de logins_web.py: aqui a preferência por Brave é
    # DESLIGADA por padrão (instagram.preferir_brave, false), mesmo com
    # automacao.preferir_brave=true globalmente. Motivo: reCAPTCHA do
    # Instagram/Google ficou em branco ao logar via Brave (relatado de
    # verdade) -- provavelmente o Shields/proteção de fingerprint do
    # Brave interferindo na renderização do reCAPTCHA. Chromium puro não
    # tem esse problema. Configurável -- "instagram.preferir_brave": true
    # em config.json volta a usar o Brave se quiser tentar de novo.
    preferir_brave = bool(get_settings().get("instagram.preferir_brave", False))
    # Anti-detecção: o captcha da Meta fica em branco/bloqueia quando
    # detecta um navegador AUTOMATIZADO (Playwright expõe
    # `navigator.webdriver=true` e a flag `--enable-automation`, que os
    # sistemas anti-bot do Instagram leem). Esconder esses sinais faz o
    # captcha renderizar e reduz MUITO a chance de ele aparecer -- não
    # elimina (a Meta luta contra automação de propósito), mas é a
    # diferença entre "captcha em branco impossível" e "captcha normal
    # que você resolve na mão".
    contexto = pw.chromium.launch_persistent_context(
        _perfil_dir,
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
        **kwargs_launch(preferir_brave=preferir_brave),
    )
    try:
        # Zera navigator.webdriver antes de qualquer página carregar --
        # complemento do arg acima, pega os checks feitos via JS.
        contexto.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    except Exception:
        pass
    pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
    _sessao["pw"] = pw
    _sessao["contexto"] = contexto
    _sessao["page"] = pagina
    return pagina


def _estado_autenticacao(pagina) -> str:
    """Retorna um estado estável sem depender do idioma da página."""
    pagina.goto("https://www.instagram.com/direct/inbox/", wait_until="domcontentloaded", timeout=20000)
    url = (pagina.url or "").lower()
    if "/challenge" in url or "/checkpoint" in url:
        return "verificacao"
    if "/accounts/login" in url or "/accounts/signup" in url:
        return "desconectado"
    if "/direct/" in url:
        return "conectado"
    return "carregando"


def _estado_url(url: str) -> str:
    url = (url or "").lower()
    if "/challenge" in url or "/checkpoint" in url:
        return "verificacao"
    if "/accounts/login" in url or "/accounts/signup" in url:
        return "desconectado"
    if "instagram.com/direct" in url or (
            "instagram.com/" in url and "/accounts/" not in url):
        return "conectado"
    return "carregando"


def _paginas_cdp():
    from config.settings import get_settings
    porta = int(get_settings().get("instagram.cdp_port", 0) or 0)
    if not porta:
        return []
    try:
        with urlopen(f"http://127.0.0.1:{porta}/json", timeout=1.5) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except Exception:
        return []


_TEMPO_PREVIEW_RE = re.compile(
    r"^(?:agora|now|\d+\s*(?:s|min|m|h|d|sem|w))$", re.IGNORECASE)
_PREVIEW_ENVIADO_RE = re.compile(
    r"^(?:você|voce|you)\s*:|^(?:você|voce|you)\s+(?:enviou|sent)\b",
    re.IGNORECASE)


def _extrair_preview_botao(texto: str):
    linhas = [x.strip() for x in (texto or "").splitlines()
              if x.strip() and x.strip() not in ("·",)]
    if len(linhas) < 3 or not _TEMPO_PREVIEW_RE.match(linhas[-1]):
        return None
    titulo, preview = linhas[0], linhas[1]
    return {
        "titulo": titulo,
        "texto": preview,
        "quando": linhas[-1],
        "recebida": not bool(_PREVIEW_ENVIADO_RE.search(preview)),
        "fonte": "web",
    }


def mensagens_web(apenas_nao_lidas: bool = False, percorrer_lista: bool = False,
                  max_conversas: int = 200) -> list:
    """Lê previews do Direct pela sessão web conectada, sem usar senha.

    Seletores por classes não são usados porque o Instagram troca seus
    nomes constantemente. Os itens de conversa são botões acessíveis
    cujo texto termina com um tempo relativo.
    """
    from config.settings import get_settings
    if not HAS_PLAYWRIGHT:
        return []
    porta = int(get_settings().get("instagram.cdp_port", 0) or 0)
    if not porta or not _paginas_cdp():
        return []
    pw = sync_playwright().start()
    pagina = None
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
        contexto = browser.contexts[0]
        pagina = contexto.new_page()
        pagina.goto(
            "https://www.instagram.com/direct/inbox/",
            wait_until="domcontentloaded", timeout=30000)
        pagina.wait_for_timeout(3500)
        if _estado_url(pagina.url) != "conectado":
            return []
        mensagens, vistos, anterior = [], set(), None
        for _ in range(80):
            primeira_linha = None
            botoes = pagina.get_by_role("button")
            for indice in range(botoes.count()):
                botao = botoes.nth(indice)
                item = _extrair_preview_botao(botao.inner_text())
                if not item:
                    continue
                primeira_linha = primeira_linha or botao
                estado = botao.evaluate("""e => ({
                    forte: [...e.querySelectorAll('span')].some(
                        x => Number.parseInt(getComputedStyle(x).fontWeight || '400') >= 600),
                    ponto: [...e.querySelectorAll('div')].some(
                        x => getComputedStyle(x).backgroundColor === 'rgb(0, 149, 246)')
                })""")
                item["nao_lida"] = bool(estado.get("forte") or estado.get("ponto"))
                chave = item["titulo"].strip().casefold()
                if chave not in vistos and (not apenas_nao_lidas or item["nao_lida"]):
                    vistos.add(chave)
                    mensagens.append(item)
            if (not percorrer_lista or len(mensagens) >= max_conversas
                    or primeira_linha is None):
                break
            primeira_linha.evaluate("""e => {
                let n=e.parentElement;
                while(n && n.scrollHeight <= n.clientHeight) n=n.parentElement;
                if(n) n.dataset.neutronInboxScroller='1';
            }""")
            scroller = pagina.locator('[data-neutron-inbox-scroller="1"]')
            if not scroller.count():
                break
            estado_scroll = scroller.first.evaluate(
                "e=>({top:e.scrollTop,height:e.scrollHeight,client:e.clientHeight})")
            assinatura = (estado_scroll["top"], estado_scroll["height"])
            if (assinatura == anterior or estado_scroll["top"] + estado_scroll["client"]
                    >= estado_scroll["height"] - 2):
                break
            anterior = assinatura
            scroller.first.evaluate(
                "e=>e.scrollTop+=Math.max(300,e.clientHeight*.8)")
            pagina.wait_for_timeout(600)
        return mensagens
    except Exception as e:
        log.warning("instagram_auto: falha ao ler Direct web: %s", e)
        return []
    finally:
        if pagina is not None:
            try:
                pagina.close()
            except Exception:
                pass
        try:
            pw.stop()
        except Exception:
            pass


def _pagina_da_conversa(contexto, destinatario: str):
    """Reutiliza uma conversa aberta quando o cabeçalho identifica o contato."""
    alvo = destinatario.strip().casefold()
    for pagina in contexto.pages:
        if "/direct/t/" not in pagina.url:
            continue
        try:
            textos = pagina.get_by_text(destinatario, exact=True)
            if textos.count() and alvo in pagina.locator("body").inner_text().casefold():
                return pagina
        except Exception:
            continue
    return None


def _localizar_conversa_no_inbox(pagina, destinatario: str):
    """Procura uma conversa inclusive nas linhas virtualizadas da lateral."""
    alvo = destinatario.strip().casefold()
    anterior = None
    for _ in range(60):
        botoes = pagina.get_by_role("button")
        primeira_linha = None
        for indice in range(botoes.count()):
            candidato = botoes.nth(indice)
            try:
                preview = _extrair_preview_botao(candidato.inner_text())
            except Exception:
                continue
            if not preview:
                continue
            primeira_linha = primeira_linha or candidato
            if preview["titulo"].strip().casefold() == alvo:
                return candidato
        if primeira_linha is None:
            pagina.wait_for_timeout(600)
            continue
        primeira_linha.evaluate("""e => {
            let n=e.parentElement;
            while(n && n.scrollHeight <= n.clientHeight) n=n.parentElement;
            if(n) n.dataset.neutronInboxScroller='1';
        }""")
        scroller = pagina.locator('[data-neutron-inbox-scroller="1"]')
        if not scroller.count():
            break
        estado = scroller.first.evaluate(
            "e=>({top:e.scrollTop,height:e.scrollHeight,client:e.clientHeight})")
        assinatura = (estado["top"], estado["height"])
        if assinatura == anterior or estado["top"] + estado["client"] >= estado["height"] - 2:
            break
        anterior = assinatura
        scroller.first.evaluate("e=>e.scrollTop+=Math.max(300,e.clientHeight*.8)")
        pagina.wait_for_timeout(650)
    return None


def coletar_conversa_web(destinatario: str, max_mensagens: int = 1000) -> list:
    """Coleta texto da conversa, rotulado como usuário/contato.

    Áudios, imagens e posts sem transcrição textual são ignorados. O
    histórico é rolado para cima até estabilizar ou atingir o limite.
    """
    from config.settings import get_settings
    if not HAS_PLAYWRIGHT:
        return []
    porta = int(get_settings().get("instagram.cdp_port", 0) or 0)
    if not porta or not _paginas_cdp():
        return []
    pw = sync_playwright().start()
    pagina = None
    pagina_criada = False
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
        contexto = browser.contexts[0]
        pagina = _pagina_da_conversa(contexto, destinatario)
        if pagina is None:
            pagina = contexto.new_page()
            pagina_criada = True
            pagina.goto("https://www.instagram.com/direct/inbox/",
                        wait_until="domcontentloaded", timeout=30000)
            pagina.wait_for_timeout(3500)
            row = _localizar_conversa_no_inbox(pagina, destinatario)
            if row is None:
                # O Direct ocasionalmente entrega a lateral vazia na primeira carga.
                pagina.reload(wait_until="domcontentloaded", timeout=30000)
                pagina.wait_for_timeout(3500)
                row = _localizar_conversa_no_inbox(pagina, destinatario)
            if row is None:
                raise RuntimeError("conversa não encontrada no Direct")
            row.click(timeout=12000, force=True)
            pagina.wait_for_url(re.compile(r".*/direct/t/.*"), timeout=15000)
            pagina.wait_for_timeout(2000)

        groups = pagina.locator('[role="group"]')
        if not groups.count():
            return []
        # Classes/estilos inline nem sempre expõem o scroller. Descobre
        # pelo primeiro ancestral realmente rolável via JavaScript.
        groups.first.evaluate("""e => {
            let n=e.parentElement;
            while(n && n.scrollHeight <= n.clientHeight) n=n.parentElement;
            if(n) n.dataset.neutronMessageScroller='1';
        }""")
        scroll = pagina.locator('[data-neutron-message-scroller="1"]')
        if scroll.count():
            previous = -1
            for _ in range(40):
                height = scroll.first.evaluate("e=>e.scrollHeight")
                scroll.first.evaluate("e=>e.scrollTop=0")
                pagina.wait_for_timeout(500)
                if height == previous or groups.count() >= max_mensagens:
                    break
                previous = height

        result, seen = [], set()
        for index in range(groups.count()):
            group = groups.nth(index)
            text = group.inner_text().strip()
            if not text or "Ver transcrição" in text or re.fullmatch(r"[\d:.\s]+", text):
                continue
            presentations = group.locator('[role="presentation"]')
            if not presentations.count():
                continue
            bubble = presentations.first.bounding_box()
            container = group.bounding_box()
            if not bubble or not container:
                continue
            author = "eu" if bubble["x"] + bubble["width"] / 2 > (
                container["x"] + container["width"] / 2) else "contato"
            clean = " ".join(x.strip() for x in text.splitlines() if x.strip())
            key = (author, clean)
            if key not in seen:
                seen.add(key)
                result.append({"autor": author, "texto": clean})
        return result[-max_mensagens:]
    except Exception as e:
        log.warning("instagram_auto: falha ao coletar conversa de %s: %s", destinatario, e)
        return []
    finally:
        if pagina is not None and pagina_criada:
            try:
                pagina.close()
            except Exception:
                pass
        try:
            pw.stop()
        except Exception:
            pass


def analisar_perfil_contato(jarvis, contato: str, mensagens: list) -> dict:
    """Resume estilo e dinâmica sem armazenar a conversa bruta."""
    if not mensagens:
        raise ValueError(f"Não encontrei texto suficiente na conversa com {contato}.")
    amostra = "\n".join(
        f"{'EU' if m['autor'] == 'eu' else 'CONTATO'}: {m['texto']}"
        for m in mensagens[-300:])[-30000:]
    prompt = (
        "Analise como EU costumo conversar com este contato. Não diagnostique personalidade, "
        "não invente fatos e não copie segredos. Responda apenas JSON válido com as chaves "
        '"tom", "tamanho", "vocabulario", "emojis", "dinamica", "assuntos", "evitar". '
        "Descreva como adaptar futuras respostas mantendo minha voz, em frases curtas.\n\n"
        f"Contato: {contato}\n{amostra}")
    _, response = jarvis.ia_manager.chat(prompt, history=[], max_tokens=600)
    raw = (response or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    profile = json.loads(raw)
    if not isinstance(profile, dict):
        raise ValueError("A IA não devolveu um perfil válido.")
    allowed = ("tom", "tamanho", "vocabulario", "emojis",
               "dinamica", "assuntos", "evitar")
    profile = {
        key: str(profile.get(key, "")).strip()[:500]
        for key in allowed
    }
    from core.instagram_profiles import save
    return save(jarvis.user_id, contato, profile, len(mensagens))


def analisar_conversas_visiveis(jarvis, max_contatos: int = 20) -> list:
    if jarvis.ia_manager is None:
        raise RuntimeError("É necessário um provedor de IA para analisar os estilos.")
    contacts = [
        m["titulo"] for m in mensagens_web(
            percorrer_lista=True, max_conversas=max_contatos
        )[:max_contatos]
    ]
    results = []
    for contact in contacts:
        messages = coletar_conversa_web(contact)
        try:
            profile = analisar_perfil_contato(jarvis, contact, messages)
            results.append({"contato": contact, "mensagens": len(messages),
                            "sucesso": True, "perfil": profile["profile"]})
        except Exception as e:
            results.append({"contato": contact, "mensagens": len(messages),
                            "sucesso": False, "erro": str(e)})
    return results
def _porta_local_livre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _porta_processo_dedicado() -> int:
    """No Windows, recupera a porta CDP da janela dedicada já aberta."""
    if os.name != "nt":
        return 0
    perfil = os.path.join("data", "instagram_browser_profile").lower()
    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -match '^(brave|chrome|msedge)\\.exe$' -and "
        f"$_.CommandLine -like '*{perfil.replace(chr(92), '*')}*' -and "
        "$_.CommandLine -match '--remote-debugging-port=(\\d+)' } | "
        "ForEach-Object { if ($_.CommandLine -match "
        "'--remote-debugging-port=(\\d+)') { $Matches[1]; break } }"
    )
    try:
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        texto = resultado.stdout.strip().splitlines()
        return int(texto[0].strip()) if texto else 0
    except Exception:
        return 0


def _abrir_login_normal() -> None:
    """Abre o login num navegador comum; o Playwright só anexa depois."""
    global _perfil_dir, _processo_login
    from automacao import navegador_pessoal
    from config.settings import get_settings
    porta_existente = _porta_processo_dedicado()
    if porta_existente:
        get_settings().set("instagram.cdp_port", porta_existente)
        get_settings().save()
        return
    executavel = navegador_pessoal.caminho_navegador()
    if not executavel:
        raise RuntimeError("Não encontrei Chrome, Brave ou Edge instalado.")
    if _perfil_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _perfil_dir = os.path.join(base_dir, "data", "instagram_browser_profile")
        os.makedirs(_perfil_dir, exist_ok=True)
    porta = _porta_local_livre()
    args = [
        executavel,
        f"--remote-debugging-port={porta}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={_perfil_dir}",
        "--no-first-run",
        "https://www.instagram.com/accounts/login/",
    ]
    _processo_login = subprocess.Popen(args)
    # Só publica a porta depois que o navegador realmente a abriu. Se o
    # Chromium reutilizar um processo existente, não deixa uma porta falsa
    # gravada na configuração.
    for _ in range(20):
        try:
            with urlopen(f"http://127.0.0.1:{porta}/json", timeout=0.3):
                get_settings().set("instagram.cdp_port", porta)
                get_settings().save()
                return
        except Exception:
            time.sleep(0.25)
    porta_existente = _porta_processo_dedicado()
    if porta_existente:
        get_settings().set("instagram.cdp_port", porta_existente)
        get_settings().save()


def _esta_logado(pagina) -> bool:
    return _estado_autenticacao(pagina) == "conectado"


def instagram_conectado() -> bool:
    """Confirma a sessão atual no próprio Instagram."""
    try:
        return _esta_logado(_garantir_pagina())
    except Exception as e:
        log.warning("instagram_auto: falha ao verificar conexão: %s", e)
        return False


def conectar_instagram(modo=None) -> str:
    """Conecta ao Instagram reaproveitando o navegador do dia a dia
    (Brave/Chrome/Edge) -- pedido explícito do usuário (2026-07-06): se
    você já está logado no Instagram nesse navegador, o Jarvis cai numa
    cópia dessa sessão e já entra direto, sem pedir login de novo. Se
    não houver sessão ativa (ou o navegador pessoal não estiver
    disponível), abre a página de login DE VERDADE do Instagram -- você
    digita usuário/senha/2FA direto com o Instagram, o Jarvis nunca vê
    nem guarda essa senha (mesmo princípio de
    automacao/logins_web.py:conectar_google()). Uma vez logado, a sessão
    persiste pras próximas vezes (ler mensagens, e responder sozinho se
    instagram.envio_automatico estiver ligado)."""
    from config.settings import get_settings
    modo = modo or get_settings().get("instagram.modo_conexao", MODO_DEDICADO)
    if modo not in (MODO_DEDICADO, MODO_NAVEGADOR):
        raise ValueError("Modo de conexão do Instagram inválido.")
    get_settings().set("instagram.modo_conexao", modo)
    get_settings().set("instagram.usar_perfil_proprio", modo == MODO_DEDICADO)
    get_settings().save()
    if modo == MODO_DEDICADO:
        fechar_sessao()
        _abrir_login_normal()
        return (
            "Abri o Instagram em um navegador normal, sem automação na tela de login. "
            "Digite sua senha e conclua o 2FA diretamente nele; o Neutron apenas verificará "
            "quando a sessão estiver pronta."
        )
    pagina = _garantir_pagina(modo)
    if _esta_logado(pagina):
        registrar("instagram_conectado", "")
        return (
            "Já estou conectado -- reaproveitei a sessão logada do seu navegador do dia a dia, "
            "então nem precisou de login. Posso ler suas mensagens, e responder sozinho também, "
            "se você ligar o envio automático."
        )
    pagina.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded", timeout=20000)
    dica_navegador_aberto = ""
    if getattr(pagina.context, "_usou_perfil_real", True) is False:
        # Não achou login numa CÓPIA do perfil (navegador estava aberto) --
        # bem possível que você esteja logado de verdade, só que a sessão
        # mais recente ainda não tinha sido gravada em disco no momento da
        # cópia (ver navegador_pessoal.py). Fechar o navegador e pedir de
        # novo usa a pasta real direto, sem essa limitação.
        dica_navegador_aberto = (
            " Se você já está logado no Instagram no seu navegador, tente fechá-lo e "
            'pedir "conecta minha conta do instagram" de novo -- com ele fechado eu uso '
            "o perfil real direto, sem risco de perder uma sessão recém-criada."
        )
    return (
        "Abri a página de login do Instagram numa aba -- faça login você mesmo (usuário, "
        "senha, verificação em duas etapas) direto com o Instagram; eu não vejo nem guardo "
        "sua senha. A sessão fica salva pra próxima vez. Depois de logar, posso ler suas "
        "mensagens, e responder sozinho também, se você ligar o envio automático."
        ' Depois de concluir o login/2FA, diga "verifica conexão do instagram" '
        "para eu confirmar que a sessão foi autenticada."
        + dica_navegador_aberto
    )


def estado_conexao() -> str:
    """Estado simplificado usado pelo assistente visual de conexão."""
    if not available():
        return "indisponivel"
    paginas = _paginas_cdp()
    if paginas:
        estados = [_estado_url(item.get("url", "")) for item in paginas]
        for prioridade in ("verificacao", "conectado", "desconectado", "carregando"):
            if prioridade in estados:
                return prioridade
    try:
        return _estado_autenticacao(_garantir_pagina())
    except Exception as e:
        log.warning("instagram_auto: falha ao obter estado da conexão: %s", e)
        return "erro"


def fechar_sessao() -> None:
    """Fecha a janela controlada sem apagar cookies ou a sessão salva."""
    contexto = _sessao.get("contexto")
    pw = _sessao.get("pw")
    _sessao.clear()
    try:
        if contexto is not None:
            contexto.close()
    finally:
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                pass


def enviar_resposta(destinatario: str, texto: str) -> None:
    """Abre a conversa com `destinatario` no Instagram Direct e envia
    `texto` -- sem confirmação, chamado só pelo tick automático (ver
    _tick) quando instagram.envio_automatico estiver ligado. Exige que
    a sessão já esteja autenticada via conectar_instagram() -- nunca
    guarda nem digita a senha por conta própria."""
    from config.settings import get_settings
    porta = int(get_settings().get("instagram.cdp_port", 0) or 0)
    if not porta or not _paginas_cdp():
        raise RuntimeError("A janela conectada do Instagram não está aberta.")
    pw = sync_playwright().start()
    pagina = None
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
        pagina = browser.contexts[0].new_page()
        pagina.goto(
            "https://www.instagram.com/direct/inbox/",
            wait_until="domcontentloaded", timeout=30000)
        pagina.wait_for_timeout(2500)
        if _estado_url(pagina.url) != "conectado":
            raise RuntimeError("A sessão do Instagram expirou; conecte novamente.")

        # O nome pode aparecer em stories e sugestões. Restringir a
        # botões cujo texto começa pelo destinatário seleciona a linha
        # da conversa, evitando abrir outro elemento homônimo.
        padrao = re.compile(rf"^{re.escape(destinatario)}(?:\n|$)")
        conversa = pagina.get_by_role("button", name=padrao).first
        conversa.wait_for(timeout=12000)
        conversa.click()
        caixa_texto = pagina.locator(
            'div[contenteditable="true"][role="textbox"], '
            'textarea[placeholder], div[contenteditable="true"][aria-label]').last
        caixa_texto.wait_for(timeout=12000)
        time.sleep(random.uniform(1.5, 4.0))
        caixa_texto.fill(texto)
        caixa_texto.press("Enter")
        time.sleep(1.0)
    finally:
        if pagina is not None:
            try:
                pagina.close()
            except Exception:
                pass
        try:
            pw.stop()
        except Exception:
            pass


def _limite_diario(jarvis) -> int:
    return int(jarvis.settings.get("instagram.limite_envios_por_dia", _LIMITE_DIARIO_PADRAO))


def _envios_nas_ultimas_24h(memory) -> int:
    """Usa events_by_type() (filtra por tipo DIRETO no SQL), não
    recent_events(limit=N) -- este último pega os últimos N eventos de
    QUALQUER tipo (todos os módulos escrevem na mesma tabela), então um
    dia ativo de visao_continua/habitos/macros podia empurrar eventos
    de "instagram_enviado" antigos pra fora da janela e SUBCONTAR os
    envios do dia, deixando o limite diário furar."""
    from datetime import datetime, timedelta
    desde = datetime.now() - timedelta(hours=24)
    eventos = memory.events_by_type("instagram_enviado", since=desde.isoformat(), limit=1000)
    return len(eventos)


def _ja_processada(memory, chave: str) -> bool:
    """Mesmo motivo de _envios_nas_ultimas_24h: filtra por tipo direto
    no SQL, pra "instagram_processada" nunca ficar invisível atrás de
    eventos de outros módulos e fazer a mesma mensagem ser reprocessada/
    reenviada sozinha."""
    eventos = memory.events_by_type("instagram_processada", limit=2000)
    return any(ev.get("description") == chave for ev in eventos)


def _mensagens_pendentes() -> list:
    """App companion (POST /notify) foi removido do projeto -- o inbox
    em memória (`notification_inbox`) nunca mais é alimentado por ele.
    Cai pro ADB sem fio (mesmo fallback de plugins/instagram.py) quando
    o inbox estiver vazio, em vez de silenciosamente nunca achar nada."""
    # A sessão web é a fonte principal. Para não responder conversas
    # antigas ao ativar a automação, só entram previews não lidos cuja
    # última mensagem veio da outra pessoa.
    previews_web = mensagens_web()
    da_web = [
        m for m in previews_web
        if m.get("recebida") and m.get("nao_lida")
    ]
    # Algumas versões do Direct não expõem mais negrito/ponto azul no
    # HTML acessível. Nesse caso, confiar só em `nao_lida` faz a rotina
    # ignorar todas as mensagens para sempre. O registro
    # instagram_processada continua impedindo reenvio duplicado.
    if not da_web and previews_web and not any(
            m.get("nao_lida") for m in previews_web):
        da_web = [m for m in previews_web if m.get("recebida")]
    if da_web:
        return da_web
    do_inbox = inbox_mensagens_de(_INSTAGRAM_PKG)
    if do_inbox:
        return do_inbox
    if not adb.available() or not adb.list_devices():
        return []
    try:
        notifs = adb.list_notifications(package=_INSTAGRAM_PKG)
    except Exception as e:
        log.warning("instagram_auto: falha ao ler notificações via ADB: %s", e)
        return []
    return [n for n in notifs if n.get("texto")]


def _garantir_sessao_automatica(jarvis) -> bool:
    """Recupera a sessão do navegador se ela foi fechada durante o uso."""
    global _ultima_tentativa_reconexao
    if _paginas_cdp():
        return True
    if jarvis.settings.get(
            "instagram.modo_conexao", MODO_DEDICADO) != MODO_DEDICADO:
        return False
    agora = time.monotonic()
    if agora - _ultima_tentativa_reconexao < _INTERVALO_RECONEXAO:
        return False
    _ultima_tentativa_reconexao = agora
    try:
        _abrir_login_normal()
        for _ in range(20):
            if _paginas_cdp():
                log.info("instagram_auto: sessão do navegador reconectada")
                return True
            time.sleep(0.25)
    except Exception as e:
        log.warning("instagram_auto: falha ao reconectar navegador: %s", e)
    notify(
        NOME,
        "O Instagram automático está ligado, mas a sessão do navegador não está "
        "disponível. Abra a janela do Instagram e confirme o login.",
    )
    return False


def _tick(jarvis):
    if jarvis is None:
        log.warning("instagram_auto: rotina recebeu contexto vazio; não foi executada")
        return
    if not jarvis.settings.get("instagram.envio_automatico", False):
        return
    if jarvis.ia_manager is None:
        return
    if not _garantir_sessao_automatica(jarvis):
        return

    mensagens = _mensagens_pendentes()
    for msg in mensagens:
        texto = msg.get("texto")
        titulo = msg.get("titulo") or "alguém"
        if not texto:
            continue
        chave = f"{titulo}::{texto}"
        if _ja_processada(jarvis.memory, chave):
            continue

        if _envios_nas_ultimas_24h(jarvis.memory) >= _limite_diario(jarvis):
            registrar("instagram_processada", chave)
            notify(
                NOME,
                "Atingi o limite diário de respostas automáticas no Instagram -- "
                f'a mensagem de "{titulo}" ficou sem resposta automática, revise manualmente.',
            )
            continue

        contexto_extra = jarvis.memory.get_context_summary(jarvis.user_id)
        try:
            from core.instagram_profiles import prompt_for
            perfil_contato = prompt_for(jarvis.user_id, titulo)
            if perfil_contato:
                contexto_extra += (
                    f"\n\nEstilo específico desta conversa com {titulo}:\n{perfil_contato}")
        except Exception:
            pass
        try:
            _, sugestao = jarvis.ia_manager.chat(
                f'Mensagem recebida no Instagram de "{titulo}": "{texto}"',
                history=[], system_prompt=_system_prompt_sugestao(contexto_extra),
            )
        except Exception as e:
            log.warning("instagram_auto: falha ao gerar sugestão: %s", e)
            continue
        if not sugestao:
            continue

        try:
            enviar_resposta(titulo, sugestao.strip())
        except Exception as e:
            log.warning("instagram_auto: falha ao enviar resposta: %s", e)
            notify(NOME, f'Tentei responder "{titulo}" no Instagram sozinho, mas falhou: {e}')
            continue

        # Só marca depois que o envio terminou. Antes, uma falha
        # transitória no navegador tornava a mensagem invisível para
        # todas as tentativas seguintes.
        registrar("instagram_processada", chave)
        registrar("instagram_enviado", f'{titulo}: "{sugestao.strip()[:80]}"')
        notify(f"{NOME} (Instagram automático)", f'Respondi "{titulo}" sozinho: "{sugestao.strip()[:120]}"')


def iniciar(jarvis):
    """Chamado no startup do Jarvis -- só agenda o polling se
    instagram.envio_automatico já estiver true (ligado numa sessão
    anterior). Ativar pela primeira vez (plugins/instagram.py) também
    agenda na hora, sem precisar reiniciar."""
    if not jarvis.settings.is_module_enabled("automacao"):
        return
    if not jarvis.settings.get("instagram.envio_automatico", False):
        return
    if (jarvis.settings.get("instagram.modo_conexao", MODO_DEDICADO) == MODO_DEDICADO
            and not _paginas_cdp()):
        try:
            _abrir_login_normal()
            # O navegador é externo; aguarda apenas a porta local ficar
            # pronta. A sessão persistida normalmente já está autenticada.
            for _ in range(16):
                if _paginas_cdp():
                    break
                time.sleep(0.25)
        except Exception as e:
            log.warning("instagram_auto: não consegui reabrir a sessão no startup: %s", e)
    tasks.schedule_recurring("instagram_auto", _INTERVALO_POLL, _tick, jarvis)
