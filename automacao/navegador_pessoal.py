"""
automacao/navegador_pessoal.py
=================================
"Usar o MESMO navegador que o meu, com as mesmas contas/emails logados":
abre o SEU perfil real do Chrome/Brave/Edge via Playwright, então o
Ultron já cai logado em tudo que você usa (Gmail, YouTube, etc.) em vez
de um perfil de automação vazio.

Diferença crucial pra automacao/navegador.py e browser_engine.py: aqueles
usam um perfil PRÓPRIO do Ultron (separado, sem seus logins). Aqui é o
seu perfil DE VERDADE (`user-data-dir` real do navegador), pra
reaproveitar suas sessões.

TRÊS RESTRIÇÕES HONESTAS, todas tratadas aqui:
1. O Chrome/Brave/Edge TRAVA o perfil enquanto está aberto -- o Playwright
   não consegue abrir o MESMO `user-data-dir` que uma janela já aberta
   está usando (dá erro "ProcessSingleton"/"profile in use"). Por isso,
   com o navegador ABERTO, trabalhamos sobre uma CÓPIA do perfil (copia
   cookies/logins), que funciona mesmo assim e NUNCA corrompe seu perfil
   real.
2. Cookies recém-criados (ex.: você acabou de logar) às vezes ficam só
   NA MEMÓRIA do navegador aberto por um tempo antes de serem gravados
   no arquivo Cookies em disco -- copiar o arquivo nesse meio-tempo pode
   perder a sessão mais fresca (bug real encontrado: usuário já logado
   no Instagram no Brave aberto, mas a cópia não pegou a sessão). Por
   isso, quando o navegador está FECHADO, usamos a pasta REAL direto
   (`usar_perfil_real`, automático) -- sem cópia, sem essa limitação,
   sempre pega a sessão mais atual. Com o navegador aberto, a cópia
   continua sendo o único jeito (não dá pra abrir a pasta real), então
   uma sessão criada há pouco pode não aparecer -- fechar o navegador e
   pedir de novo garante pegar certo.
3. Só copiamos os arquivos de sessão/login necessários (Cookies -- que
   mora em Network/Cookies nas versões atuais do Chromium, não mais
   direto em Default/Cookies --, Login Data, Local State, Preferences),
   não o histórico/cache inteiro -- mais rápido e menos invasivo.

Isso NÃO burla 2FA nem "rouba" senha nenhuma: reaproveita os COOKIES de
sessão que já estão no seu próprio computador, no seu próprio perfil --
exatamente o que aconteceria se você mesmo abrisse o navegador.
"""

import os
import shutil
import sys

from logs.logger import get_logger

log = get_logger("automacao")

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# (nome amigável, subpasta do user-data sob a raiz do SO). A ordem é a
# preferência: Brave primeiro (o projeto já favorece ele), depois Chrome,
# depois Edge.
_NAVEGADORES_WINDOWS = (
    ("Brave", r"BraveSoftware\Brave-Browser\User Data"),
    ("Chrome", r"Google\Chrome\User Data"),
    ("Edge", r"Microsoft\Edge\User Data"),
)


def available() -> bool:
    return HAS_PLAYWRIGHT


def _raiz_user_data(subpasta: str) -> str:
    if sys.platform == "win32":
        return os.path.join(os.environ.get("LOCALAPPDATA", ""), subpasta)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~/Library/Application Support"), subpasta)
    return os.path.join(os.path.expanduser("~/.config"), subpasta)


def detectar_perfil():
    """Retorna (nome_navegador, caminho_user_data) do primeiro navegador
    instalado com um perfil de verdade, ou (None, None)."""
    if sys.platform == "win32":
        candidatos = _NAVEGADORES_WINDOWS
    else:
        # macOS/Linux: só os nomes mudam de subpasta; mantemos simples e
        # cobrimos o caso mais comum (Chrome) -- Brave/Edge no desktop do
        # usuário aqui é Windows, então priorizamos isso.
        candidatos = (("Chrome", "google-chrome"), ("Brave", "BraveSoftware/Brave-Browser"))
    for nome, sub in candidatos:
        caminho = _raiz_user_data(sub)
        if os.path.isdir(caminho) and os.path.isdir(os.path.join(caminho, "Default")):
            return nome, caminho
    return None, None


_PROCESSOS_NAVEGADOR = {
    "Brave": ("brave.exe", "brave"),
    "Chrome": ("chrome.exe", "chrome", "google-chrome"),
    "Edge": ("msedge.exe", "msedge"),
}


def navegador_esta_aberto(nome_navegador: str) -> bool:
    """True se o navegador detectado tem processo(s) rodando agora --
    decide se dá pra usar a pasta real direto (fechado, sem risco de
    'profile in use') ou se precisa da cópia (aberto). Best-effort: se
    psutil não estiver disponível, assume 'aberto' (mais seguro -- usa
    a cópia em vez de arriscar travar o perfil real)."""
    alvos = _PROCESSOS_NAVEGADOR.get(nome_navegador, ())
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            nome_proc = (p.info.get("name") or "").lower()
            if any(nome_proc == alvo.lower() for alvo in alvos):
                return True
        return False
    except Exception:
        return True


# Arquivos/pastas que carregam a SESSÃO logada (cookies + tokens). Copiar
# só isso deixa o Ultron logado sem arrastar histórico/cache/senhas em
# texto -- 'Login Data' é o cofre criptografado do próprio navegador, que
# só descriptografa na mesma máquina/usuário (não é senha em texto).
_ARQUIVOS_SESSAO = ("Cookies", "Login Data", "Preferences", "Secure Preferences")
_ARQUIVOS_RAIZ = ("Local State",)
_PASTAS_SESSAO = ("Network",)


def _perfil_copia_dir() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    caminho = os.path.join(base, "data", "perfil_navegador_ultron")
    os.makedirs(caminho, exist_ok=True)
    return caminho


def _copiar_sessao(user_data_real: str, destino: str):
    """Copia só os arquivos de sessão/login do perfil 'Default' real pro
    'Default' da cópia. Best-effort por arquivo: um bloqueado (navegador
    aberto pode manter o Cookies travado) é pulado, não aborta tudo."""
    origem_default = os.path.join(user_data_real, "Default")
    destino_default = os.path.join(destino, "Default")
    os.makedirs(os.path.join(destino_default, "Network"), exist_ok=True)

    for nome in _ARQUIVOS_RAIZ:
        _copiar_arquivo(os.path.join(user_data_real, nome), os.path.join(destino, nome))
    for nome in _ARQUIVOS_SESSAO:
        _copiar_arquivo(os.path.join(origem_default, nome), os.path.join(destino_default, nome))
    for pasta in _PASTAS_SESSAO:
        _copiar_pasta(os.path.join(origem_default, pasta), os.path.join(destino_default, pasta))


def _copiar_arquivo(origem: str, destino: str):
    try:
        if os.path.isfile(origem):
            shutil.copy2(origem, destino)
    except Exception as e:
        log.warning("navegador_pessoal: não copiei %s (%s) -- seguindo", os.path.basename(origem), e)


def _copiar_pasta(origem: str, destino: str):
    """Copia arquivo por arquivo (não shutil.copytree inteiro) -- um
    ÚNICO arquivo travado (o navegador aberto pode manter Network/Cookies
    com lock momentâneo) não pode abortar a cópia dos outros arquivos da
    pasta. copytree pararia tudo no primeiro erro; assim, cada arquivo
    tem sua própria chance."""
    if not os.path.isdir(origem):
        return
    os.makedirs(destino, exist_ok=True)
    for nome in os.listdir(origem):
        caminho_origem = os.path.join(origem, nome)
        caminho_destino = os.path.join(destino, nome)
        if os.path.isdir(caminho_origem):
            _copiar_pasta(caminho_origem, caminho_destino)
        else:
            _copiar_arquivo(caminho_origem, caminho_destino)


def _executable_path(nome_navegador: str):
    """Executável real do navegador detectado -- reaproveita
    browser_engine pro Brave; Chrome/Edge têm caminhos padrão."""
    if nome_navegador == "Brave":
        from automacao.browser_engine import caminho_brave
        return caminho_brave()
    if sys.platform != "win32":
        return None
    candidatos = {
        "Chrome": (
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        ),
        "Edge": (
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        ),
    }.get(nome_navegador, ())
    for c in candidatos:
        if os.path.isfile(c):
            return c
    return None


def abrir_logado(
    url: str = "https://www.google.com",
    usar_perfil_real: bool = None,
    pasta_copia: str = None,
    esconder_automacao: bool = False,
):
    """Abre o navegador do usuário JÁ LOGADO nas contas dele, em `url`.
    Retorna (contexto, pagina, usou_perfil_real) de um Playwright
    persistente -- quem chama é dono de fechar (context.close()).
    Levanta RuntimeError com uma mensagem clara se não der.

    usar_perfil_real=None (padrão, RECOMENDADO): decide sozinho -- usa a
    pasta REAL direto se o navegador estiver FECHADO agora (garante
    pegar a sessão mais atual, sem nenhuma limitação de cópia), ou cai
    pra cópia se estiver aberto (única opção possível nesse caso, mas
    uma sessão bem recente pode não ter sido gravada em disco ainda --
    ver limitação 2 no topo do arquivo).
    usar_perfil_real=True/False: força um dos dois modos, ignorando a
    detecção automática.

    pasta_copia: destino alternativo pra cópia da sessão (ex.: um site
    específico querendo sua própria cópia isolada, em vez da cópia
    genérica compartilhada) -- None usa a cópia padrão (_perfil_copia_dir).

    esconder_automacao: aplica os mesmos truques anti-detecção de
    automacao/instagram_auto.py (esconde `navigator.webdriver` e a flag
    `--enable-automation`) -- sites com proteção anti-bot (Meta, Google)
    podem bloquear/mostrar captcha em branco sem isso, mesmo usando um
    perfil logado de verdade."""
    if not HAS_PLAYWRIGHT:
        raise RuntimeError(
            "Instale 'playwright' e rode 'python -m playwright install chromium' "
            "pra eu usar seu navegador."
        )
    nome, user_data_real = detectar_perfil()
    if not user_data_real:
        raise RuntimeError(
            "Não encontrei um perfil de Chrome/Brave/Edge neste computador pra reaproveitar."
        )

    if usar_perfil_real is None:
        usar_perfil_real = not navegador_esta_aberto(nome)

    if usar_perfil_real:
        user_data_dir = user_data_real
    else:
        user_data_dir = pasta_copia or _perfil_copia_dir()
        os.makedirs(user_data_dir, exist_ok=True)
        _copiar_sessao(user_data_real, user_data_dir)

    executable = _executable_path(nome)
    pw = sync_playwright().start()
    args = ["--no-first-run", "--no-default-browser-check"]
    launch_kwargs = {"headless": False, "args": args}
    if esconder_automacao:
        args.append("--disable-blink-features=AutomationControlled")
        launch_kwargs["ignore_default_args"] = ["--enable-automation"]
    if executable:
        launch_kwargs["executable_path"] = executable
    try:
        contexto = pw.chromium.launch_persistent_context(user_data_dir, **launch_kwargs)
    except Exception as e:
        pw.stop()
        raise RuntimeError(
            f"Não consegui abrir seu perfil do {nome}: {e}. "
            "Se pediu o perfil real, feche o navegador e tente de novo."
        )
    if esconder_automacao:
        try:
            contexto.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
        except Exception:
            pass
    pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
    try:
        pagina.goto(url, wait_until="domcontentloaded", timeout=20000)
    except Exception:
        pass  # abriu; a página específica pode carregar devagar, não é fatal
    contexto._ultron_pw = pw  # guarda o handle pra fechar limpo depois
    # Guarda se usou o perfil real ou a cópia -- quem chama pode usar isso
    # pra explicar ao usuário por que uma sessão não apareceu (ver
    # instagram_auto.py:conectar_instagram()).
    contexto._usou_perfil_real = usar_perfil_real
    return contexto, pagina


def qual_navegador() -> str:
    """Nome do navegador que seria usado, ou '' se nenhum -- pra
    mensagens de chat honestas ('vou usar seu Brave logado')."""
    nome, _ = detectar_perfil()
    return nome or ""


def caminho_navegador() -> str:
    """Executável do navegador detectado, sem expor detalhes internos."""
    nome, _ = detectar_perfil()
    return _executable_path(nome) if nome else ""
