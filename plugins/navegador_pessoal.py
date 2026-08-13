"""
plugins/navegador_pessoal.py
===============================
Abre o SEU navegador real (Chrome/Brave/Edge) já logado nas suas contas
-- ver automacao/navegador_pessoal.py pra como (e pros limites honestos).

Comandos:
    "abre o meu navegador"            -> abre seu navegador logado
    "abre o meu gmail"               -> atalho pro Gmail já logado
    "abre o meu youtube"
    "abre <site> no meu navegador"   -> abre um site qualquer logado
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

# Guarda o contexto aberto pra NÃO fechar quando handle() retorna (senão
# o navegador fecharia na hora) -- mesmo padrão de automacao/musica.py.
_sessao = {}

_ATALHOS = {
    "gmail": "https://mail.google.com",
    "email": "https://mail.google.com",
    "e-mail": "https://mail.google.com",
    "youtube": "https://www.youtube.com",
    "drive": "https://drive.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "instagram": "https://www.instagram.com",
    "gpt": "https://chat.openai.com",
    "chatgpt": "https://chat.openai.com",
    "maps": "https://maps.google.com",
    "calendario": "https://calendar.google.com",
    "calendário": "https://calendar.google.com",
}

# "abre o meu X" / "abre X no meu navegador" / "abre meu navegador"
_MEU_NAV_RE = re.compile(
    r"\babr[ea]\w*\s+(?:o\s+|a\s+)?meu\s+navegador\b|"
    r"\bnav[ea]g[ae]\w*\s+(?:logad[oa]|com\s+minhas?\s+contas?)\b",
    re.IGNORECASE,
)
_ABRE_MEU_X_RE = re.compile(r"\babr[ea]\w*\s+(?:o\s+|a\s+)?meu\s+(.+)", re.IGNORECASE)
_ABRE_X_NO_MEU_RE = re.compile(
    r"\babr[ea]\w*\s+(.+?)\s+no\s+meu\s+navegador\b", re.IGNORECASE
)


class NavegadorPessoalPlugin(BasePlugin):
    name = "navegador_pessoal"
    description = "Abre o seu navegador real (Chrome/Brave/Edge) já logado nas suas contas"
    triggers = [
        "abre o meu navegador", "abre meu navegador", "abre o meu gmail",
        "abre o meu email", "abre o meu youtube", "no meu navegador",
        "navega logado",
    ]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(
            _MEU_NAV_RE.search(t) or _ABRE_X_NO_MEU_RE.search(t)
            or (_ABRE_MEU_X_RE.search(t) and self._alvo_web(_ABRE_MEU_X_RE.search(t).group(1)))
        )

    def _alvo_web(self, termo: str):
        """Resolve 'meu gmail'/'meu youtube'/'meu <site>' -> URL, ou None
        se for claramente não-web (ex.: 'meu computador') -- aí deixa
        outro plugin tratar."""
        termo = termo.strip(" .!?").lower()
        if termo in _ATALHOS:
            return _ATALHOS[termo]
        # domínio explícito ("meu site exemplo.com")
        if re.search(r"\.[a-z]{2,}", termo):
            url = termo if termo.startswith("http") else f"https://{termo.split()[-1]}"
            return url
        return None

    def handle(self, text: str, context: dict):
        t = text.strip()

        # "abre X no meu navegador"
        m = _ABRE_X_NO_MEU_RE.search(t)
        if m:
            alvo = m.group(1).strip(" .!?")
            url = _ATALHOS.get(alvo.lower())
            if not url:
                if re.search(r"\.[a-z]{2,}", alvo):
                    url = alvo if alvo.startswith("http") else f"https://{alvo}"
                else:
                    url = f"https://www.google.com/search?q={alvo.replace(' ', '+')}"
            return self._abrir(url)

        # "abre o meu gmail/youtube/<site>"
        m = _ABRE_MEU_X_RE.search(t)
        if m:
            url = self._alvo_web(m.group(1))
            if url:
                return self._abrir(url)

        # "abre o meu navegador" (sem alvo)
        if _MEU_NAV_RE.search(t):
            return self._abrir("https://www.google.com")

        return None

    def _abrir(self, url: str):
        from automacao import navegador_pessoal
        if not navegador_pessoal.available():
            return Answer(
                "Pra usar seu navegador logado eu preciso do 'playwright' instalado "
                "(requirements-automacao.txt) + 'python -m playwright install chromium'.",
                Confidence.GUESS,
            )
        nome = navegador_pessoal.qual_navegador()
        if not nome:
            return Answer(
                "Não encontrei um perfil de Chrome/Brave/Edge neste PC pra reaproveitar suas contas.",
                Confidence.GUESS,
            )
        # Fecha uma sessão anterior antes de abrir outra.
        self._fechar()
        try:
            contexto, _ = navegador_pessoal.abrir_logado(url)
        except Exception as e:
            return Answer(f"Não consegui abrir seu {nome}: {e}", Confidence.GUESS)
        _sessao["contexto"] = contexto
        return Answer(
            f"Abri o {nome} com suas contas logadas em {url}. "
            "É a sua sessão de verdade -- o que você fizer aqui usa seus logins.",
            Confidence.CONFIRMED,
        )

    def _fechar(self):
        ctx = _sessao.pop("contexto", None)
        if ctx is None:
            return
        pw = getattr(ctx, "_ultron_pw", None)
        for fechar in (lambda: ctx.close(), lambda: pw and pw.stop()):
            try:
                fechar()
            except Exception:
                pass
