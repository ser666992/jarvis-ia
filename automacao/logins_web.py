"""
automacao/logins_web.py
==========================
Login automático em sites (ex.: "loga no github"), guardando a
credencial com segurança:

- A SENHA nunca é escrita em texto puro em lugar nenhum -- fica só no
  cofre de credenciais do próprio Windows (Credential Locker/DPAPI),
  acessado via `keyring`. Nem em config.json, nem em data/jarvis.db,
  nem em log nenhum.
- Site/URL/usuário (não-secreto) ficam numa tabela própria em
  data/jarvis.db, só pra saber pra quem pedir a senha no keyring.

IMPORTANTE -- por que salvar login NUNCA acontece via texto de chat:
`core/jarvis.py:process()` grava toda mensagem do usuário no histórico
de conversa (core/memory.py) ANTES de qualquer plugin rodar. Se a senha
viesse dentro da própria mensagem de chat (“salva o login do site X,
senha 123”), ela já teria sido gravada em texto puro no banco (e nos
backups automáticos) antes de qualquer código aqui poder impedir isso.
Por isso `salvar_login()` só é chamado por um caminho SEPARADO do chat:
    - CLI: `python -m automacao.logins_web` (usa `getpass`, sem eco na tela)
    - GUI: diálogo próprio com campo de senha mascarado (gui/app.py)
plugins/logins_web.py (o lado de chat) só conhece o SITE (nome), nunca
a senha -- e recusa explicitamente se alguém tentar mandar uma senha
pelo chat, explicando por que.

Automação do preenchimento do formulário via Playwright (opcional --
requer `pip install playwright` + `python -m playwright install
chromium`, ver requirements-automacao.txt). Todas as sessões
compartilham UM ÚNICO contexto de navegador PERSISTENTE (perfil salvo
em data/logins_browser_profile/, cookies sobrevivem entre chamadas) --
cada site abre em sua própria aba dentro desse mesmo contexto. Isso é
o que permite "conectar a conta do Google" (conectar_google(), abre a
página de login de verdade do Google -- você digita sua senha/2FA
direto com o Google, o Ultron nunca vê nem guarda essa senha) e depois
usar essa MESMA sessão pra sites com "Continuar com o Google"
(entrar_com_google()), sem precisar salvar uma senha separada pra cada
um. O navegador abre visível (não headless) e as abas ficam abertas
depois do login, pra você poder ver o resultado e resolver qualquer
2FA/captcha -- feche com "fecha o navegador do login do <site>".
"""

import os

from core.database import get_database
from core.timeline import registrar
from logs.logger import get_logger

log = get_logger("automacao")

try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

_KEYRING_SERVICE = "jarvis_login"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS automacao_logins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    usuario TEXT NOT NULL,
    criado_em TEXT NOT NULL
);
"""

_sessao = {}          # "pw" / "contexto" -- contexto de navegador PERSISTENTE, compartilhado
_paginas_abertas = {}  # site -> Page (uma aba por site, mesmo contexto/cookies)

_GOOGLE_BUTTON_SELECTORS = (
    'button:has-text("Continue with Google")',
    'button:has-text("Continuar com o Google")',
    'div[role="button"]:has-text("Google")',
    'a:has-text("Sign in with Google")',
    'a:has-text("Continuar com o Google")',
)


def available() -> bool:
    return HAS_KEYRING and HAS_PLAYWRIGHT


def _perfil_dir() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    caminho = os.path.join(base_dir, "data", "logins_browser_profile")
    os.makedirs(caminho, exist_ok=True)
    return caminho


def _garantir_contexto():
    if "contexto" in _sessao:
        return _sessao["contexto"]
    if not HAS_PLAYWRIGHT:
        raise RuntimeError(
            "Instale 'playwright' (requirements-automacao.txt) e rode "
            "'python -m playwright install chromium' pra eu conseguir usar o navegador."
        )
    from automacao.browser_engine import kwargs_launch
    pw = sync_playwright().start()
    # Se o Brave estiver instalado, usa ele em vez do Chromium do
    # Playwright (mesmo perfil de automação próprio do Jarvis, só troca
    # o executável -- ver automacao/browser_engine.py).
    contexto = pw.chromium.launch_persistent_context(_perfil_dir(), headless=False, **kwargs_launch())
    _sessao["pw"] = pw
    _sessao["contexto"] = contexto
    return contexto


def conectar_google() -> str:
    """Abre a página de login DE VERDADE do Google numa aba -- você
    digita usuário/senha/2FA direto com o Google, o Ultron nunca vê
    nem guarda essa senha. Depois disso, sites com "Continuar com o
    Google" conseguem usar essa mesma sessão (ver entrar_com_google)."""
    contexto = _garantir_contexto()
    pagina = contexto.new_page()
    try:
        pagina.goto("https://accounts.google.com/", wait_until="domcontentloaded", timeout=20000)
    except Exception:
        pagina.close()
        raise
    _paginas_abertas["google"] = pagina
    registrar("google_conectado", "")
    return (
        "Abri a página de login do Google numa aba -- faça login você mesmo (usuário, senha, "
        "verificação em duas etapas) direto com o Google; eu não vejo nem guardo sua senha do "
        "Google. Depois de logar, sites com \"Continuar com o Google\" vão conseguir usar essa "
        "mesma sessão (\"entra no <site> com o google\")."
    )


def entrar_com_google(site: str, url: str) -> str:
    """Abre `url` numa aba (mesmo contexto/cookies de conectar_google)
    e clica no botão "Continuar com o Google", se houver um."""
    contexto = _garantir_contexto()
    pagina = contexto.new_page()
    try:
        pagina.goto(url, wait_until="domcontentloaded", timeout=20000)
        for seletor in _GOOGLE_BUTTON_SELECTORS:
            alvo = pagina.locator(seletor).first
            if alvo.count() > 0:
                alvo.click(timeout=5000)
                pagina.wait_for_timeout(3000)
                _paginas_abertas[site] = pagina
                registrar("login_usado", f"google:{site}")
                return (
                    f'Cliquei em "Continuar com o Google" em {url} -- confira a aba (pode pedir uma '
                    "confirmação extra na primeira vez)."
                )
        pagina.close()
        raise RuntimeError(
            f"Não achei um botão de login com o Google em {url}. Se o site tiver login normal, "
            f'use "loga no {site}" depois de salvar a credencial.'
        )
    except Exception:
        if not pagina.is_closed():
            pagina.close()
        raise


def _ensure_schema():
    get_database().executescript(_SCHEMA)


def salvar_login(site: str, url: str, usuario: str, senha: str) -> dict:
    """Salva/atualiza uma credencial. Chamado SÓ pelo CLI (__main__
    deste módulo) ou por um diálogo seguro da GUI -- nunca a partir de
    texto de chat (ver aviso no topo do arquivo)."""
    if not HAS_KEYRING:
        raise RuntimeError("Instale 'keyring' (requirements-automacao.txt) para eu guardar logins com segurança.")
    _ensure_schema()
    from datetime import datetime
    site = site.strip().lower()
    get_database().execute("""
        INSERT INTO automacao_logins (site, url, usuario, criado_em)
        VALUES (?,?,?,?)
        ON CONFLICT(site) DO UPDATE SET url=excluded.url, usuario=excluded.usuario
    """, (site, url.strip(), usuario.strip(), datetime.now().isoformat()))
    keyring.set_password(_KEYRING_SERVICE, site, senha)
    log.info("login salvo para o site '%s' (senha só no keyring do SO)", site)
    registrar("login_salvo", site)
    return listar_login(site)


def listar_logins() -> list:
    _ensure_schema()
    return get_database().query("SELECT site, url, usuario, criado_em FROM automacao_logins ORDER BY site")


def listar_login(site: str) -> dict | None:
    _ensure_schema()
    return get_database().query_one(
        "SELECT site, url, usuario, criado_em FROM automacao_logins WHERE site=?", (site.strip().lower(),)
    )


def remover_login(site: str) -> bool:
    _ensure_schema()
    site = site.strip().lower()
    existente = listar_login(site)
    if not existente:
        return False
    get_database().execute("DELETE FROM automacao_logins WHERE site=?", (site,))
    if HAS_KEYRING:
        try:
            keyring.delete_password(_KEYRING_SERVICE, site)
        except Exception:
            pass
    return True


def login(site: str) -> str:
    """Abre o navegador, preenche usuário+senha no primeiro formulário
    de login encontrado, e envia. Retorna uma mensagem descrevendo o
    que foi feito -- não dá pra confirmar de fora se o login realmente
    passou (pode haver 2FA/captcha), por isso o navegador fica aberto
    visível pra você conferir."""
    if not HAS_PLAYWRIGHT:
        raise RuntimeError(
            "Instale 'playwright' (requirements-automacao.txt) e rode "
            "'python -m playwright install chromium' pra eu conseguir logar em sites."
        )
    site = site.strip().lower()
    dados = listar_login(site)
    if not dados:
        raise ValueError(f"Não tenho nenhum login salvo pra '{site}'. Salve um primeiro (veja o README de automacao/).")
    if not HAS_KEYRING:
        raise RuntimeError("Instale 'keyring' (requirements-automacao.txt) para eu recuperar a senha salva.")
    senha = keyring.get_password(_KEYRING_SERVICE, site)
    if senha is None:
        raise ValueError(f"A senha de '{site}' não está mais no cofre do sistema. Salve o login de novo.")

    contexto = _garantir_contexto()
    pagina = contexto.new_page()
    try:
        pagina.goto(dados["url"], wait_until="domcontentloaded", timeout=20000)

        senha_input = pagina.locator('input[type="password"]').first
        senha_input.wait_for(timeout=10000)

        usuario_input = pagina.locator(
            'input[type="email"], input[autocomplete="username"], '
            'input[type="text"][name*="user" i], input[type="text"][name*="email" i], '
            'input[type="text"][name*="login" i]'
        ).first
        if usuario_input.count() > 0:
            usuario_input.fill(dados["usuario"])

        senha_input.fill(senha)
        senha_input.press("Enter")
        pagina.wait_for_timeout(2000)
    except Exception:
        pagina.close()
        raise

    _paginas_abertas[site] = pagina
    registrar("login_usado", site)
    return (
        f"Abri uma aba e preenchi o login de \"{site}\" com o usuário salvo. "
        "Dá uma conferida -- deixei a aba aberta caso precise de 2FA ou algo assim. "
        f'Diga "fecha o navegador do login do {site}" quando terminar.'
    )


def fechar_sessao(site: str) -> bool:
    site = site.strip().lower()
    pagina = _paginas_abertas.pop(site, None)
    if not pagina:
        return False
    try:
        pagina.close()
    except Exception:
        pass
    return True


def _cli():
    import getpass
    print("Salvar um login (a senha NÃO aparece na tela e vai só pro cofre do Windows).")
    site = input("Site (nome curto, ex.: github): ").strip()
    url = input("URL da página de login (ex.: https://github.com/login): ").strip()
    usuario = input("Usuário/e-mail: ").strip()
    senha = getpass.getpass("Senha: ")
    if not (site and url and usuario and senha):
        print("Todos os campos são obrigatórios. Cancelado.")
        return
    salvar_login(site, url, usuario, senha)
    print(f"Login de '{site}' salvo. No Ultron, diga 'loga no {site}' quando quiser usar.")


if __name__ == "__main__":
    _cli()
