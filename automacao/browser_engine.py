"""
automacao/browser_engine.py
==============================
Detecta se o Brave está instalado e, se estiver, deixa
automacao/logins_web.py e automacao/instagram_auto.py preferirem ele
como motor de navegador em vez do Chromium que o Playwright baixa
sozinho (`python -m playwright install chromium`) -- Brave é baseado
em Chromium e fala o mesmo protocolo de automação (CDP), então o
Playwright consegue controlá-lo perfeitamente bem apontando
`executable_path` pro executável do Brave, mesmo sem um canal
("channel") oficial dedicado a ele (Playwright só documenta canais
oficiais pro Chrome/Edge, não pro Brave).

IMPORTANTE -- o que isso NÃO faz: não reaproveita o SEU perfil pessoal
do Brave (login, histórico, extensões, abas abertas). O perfil de
automação continua sendo um perfil PRÓPRIO do Ultron, numa pasta
separada em data/ -- só troca qual EXECUTÁVEL renderiza as páginas.
Reaproveitar diretamente o seu perfil do dia a dia não seria seguro
(trava se o Brave já estiver aberto usando aquele mesmo perfil, e
mistura sessão de automação com sua navegação real).
"""

import os
import sys

_CAMINHOS_BRAVE_WINDOWS = (
    os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    os.path.expandvars(r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"),
)
_CAMINHOS_BRAVE_MACOS = (
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
)
_CAMINHOS_BRAVE_LINUX = (
    "/usr/bin/brave-browser",
    "/usr/bin/brave",
    "/snap/bin/brave",
)


def caminho_brave() -> str:
    """Retorna o caminho do executável do Brave se estiver instalado,
    ou None -- quem chama cai pro Chromium embutido do Playwright
    quando None (nunca trava por causa disso)."""
    if sys.platform == "win32":
        candidatos = _CAMINHOS_BRAVE_WINDOWS
    elif sys.platform == "darwin":
        candidatos = _CAMINHOS_BRAVE_MACOS
    else:
        candidatos = _CAMINHOS_BRAVE_LINUX
    for caminho in candidatos:
        if os.path.isfile(caminho):
            return caminho
    return None


def kwargs_launch(preferir_brave: bool = None) -> dict:
    """Monta os kwargs extras pra `chromium.launch_persistent_context()`
    -- inclui `executable_path` do Brave se ele estiver instalado e a
    preferência estiver ligada; dict vazio (Chromium padrão do
    Playwright) caso contrário. `preferir_brave=None` lê o config
    (`automacao.preferir_brave`, `true` por padrão) -- passe
    explicitamente True/False só se quiser ignorar o config."""
    if preferir_brave is None:
        from config.settings import get_settings
        preferir_brave = bool(get_settings().get("automacao.preferir_brave", True))
    if not preferir_brave:
        return {}
    caminho = caminho_brave()
    return {"executable_path": caminho} if caminho else {}
