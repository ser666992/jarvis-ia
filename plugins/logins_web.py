"""
plugins/logins_web.py
========================
Lado de CHAT do login automático em sites (automacao/logins_web.py):
"loga no github", "logins salvos", "remove o login do github".

Este plugin NUNCA aceita usuário/senha dentro do texto do chat -- só
conhece o nome do site. Motivo: `core/jarvis.py:process()` grava toda
mensagem seguidamente no histórico de conversa ANTES de qualquer
plugin rodar, então uma senha digitada no chat já ficaria salva em
texto puro no banco (e nos backups automáticos) mesmo que este plugin
recusasse processá-la. Por isso salvar/atualizar uma credencial só
acontece por um caminho separado, que nunca passa pelo chat:
    - CLI: `python -m automacao.logins_web`
    - GUI: comando "salvar login" (não é mais um botão -- ver
      gui/app.py:_on_send(), que intercepta ANTES de mandar pro chat/
      `Jarvis.process()` e abre o mesmo diálogo com o campo de senha
      mascarado; a senha nunca é digitada no chat).
Se alguém pedir pra salvar um login aqui (fora da GUI, ex.: modo texto/
voz puro), o plugin recusa educadamente e explica isso, em vez de
tentar interpretar a senha do texto.

"conecta minha conta do google" abre a página de login DE VERDADE do
Google numa aba -- você digita sua senha/2FA direto com o Google, o
Jarvis nunca vê nem guarda essa senha (não é OAuth, é reuso da mesma
sessão de navegador). Depois disso, "entra no <site> com o google"
tenta clicar no botão "Continuar com o Google" daquele site, usando
essa mesma sessão -- sem precisar salvar uma senha separada.

Comandos:
    "loga no github" / "faz login no github" / "entra no site github"
    "conecta minha conta do google" / "entra no notion.so com o google"
    "logins salvos" / "quais logins você tem"
    "remove o login do github" / "esquece o login do github"
    "fecha o navegador do login do github"
"""

import re

from automacao import logins_web
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

SAVE_INTENT_RE = re.compile(
    r"\b(salv[ae]|guard[ae]|cadastr[ae])\w*\s+.*\blogin\b|\bnovo\s+login\b|\blogin\b.*\bsenha\b",
    re.IGNORECASE,
)
_LOGIN_RE = re.compile(
    r"\blog[ae]\w*\s+(?:no|na|em)\s+(.+)|"
    r"\bfa[çcz]\w*\s+login\s+(?:no|na|em)\s+(.+)|"
    r"\bentr[ae]\w*\s+(?:no|na)\s+site\s+(?:d[eo]\s+)?(.+)",
    re.IGNORECASE,
)
_CONNECT_GOOGLE_RE = re.compile(
    r"\bconecta\w*\s+.*\bconta\b.*\bgoogle\b|\bconecta\w*\s+.*\bgoogle\b", re.IGNORECASE
)
_LOGIN_GOOGLE_RE = re.compile(r"\b(?:loga|entra)\w*\s+(?:no|na|em)\s+(\S+).*\bgoogle\b", re.IGNORECASE)
_LIST_RE = re.compile(r"\blogins?\s+salv[oa]s?\b|\bquais\s+logins\b|\blist[ae]\w*\s+.*\blogins?\b", re.IGNORECASE)
_REMOVE_RE = re.compile(r"\b(remov[ae]|apag[ae]|esque[çc]\w*)\w*\s+.*\blogin\b\s+d[eo]\s+(.+)", re.IGNORECASE)
_CLOSE_SESSION_RE = re.compile(r"\bfech\w*\s+.*\bnavegador\b.*\blogin\b\s+d[eo]\s+(.+)", re.IGNORECASE)

_TRIGGERS = [
    "loga no", "loga na", "faz login", "fazer login", "entra no site",
    "logins salvos", "quais logins", "lista os logins", "logins gerados",
    "remove o login", "apaga o login", "esquece o login",
    "fecha o navegador", "salva o login", "guarda o login", "cadastra o login",
    "novo login",
]


def _extrair_site(resto: str) -> str:
    alvo = resto.strip(" ,.!?")
    alvo = re.sub(r"^(o|a|do|da|de)\s+", "", alvo, flags=re.IGNORECASE).strip()
    return alvo.lower()


class LoginsWebPlugin(BasePlugin):
    name = "logins_web"
    description = "Login automático em sites salvos (senha guardada com segurança, nunca pelo chat)"
    triggers = _TRIGGERS

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(
            SAVE_INTENT_RE.search(t) or _CLOSE_SESSION_RE.search(t) or _REMOVE_RE.search(t)
            or _LIST_RE.search(t) or _CONNECT_GOOGLE_RE.search(t) or _LOGIN_GOOGLE_RE.search(t)
            or _LOGIN_RE.search(t)
        )

    def handle(self, text: str, context: dict):
        t = text.strip()

        if _CONNECT_GOOGLE_RE.search(t):
            return self._conectar_google()

        m = _LOGIN_GOOGLE_RE.search(t)
        if m:
            return self._logar_com_google(_extrair_site(m.group(1)))

        if SAVE_INTENT_RE.search(t):
            return Answer(
                "Por segurança, não guardo login/senha digitados no chat -- ficariam "
                "salvos em texto puro no histórico de conversa. Pra cadastrar um login: "
                "na interface gráfica, diga 'salvar login' (abre um diálogo à parte, com "
                "o campo de senha oculto, que nunca passa pelo chat); no terminal, rode "
                "'python -m automacao.logins_web' (a senha não aparece na tela). Depois "
                "disso, é só dizer 'loga no <site>' aqui que eu cuido do resto.",
                Confidence.GUESS,
            )

        m = _CLOSE_SESSION_RE.search(t)
        if m:
            return self._fechar_sessao(_extrair_site(m.group(1)))

        m = _REMOVE_RE.search(t)
        if m:
            return self._remover(_extrair_site(m.group(2)))

        if _LIST_RE.search(t):
            return self._listar()

        m = _LOGIN_RE.search(t)
        if m:
            site = next((g for g in m.groups() if g), None)
            return self._logar(_extrair_site(site))

        return None

    def _logar(self, site: str):
        if not site:
            return Answer("Logar em qual site?", Confidence.GUESS)
        if not logins_web.available():
            return Answer(
                "Instale 'keyring' e 'playwright' (requirements-automacao.txt), e rode "
                "'python -m playwright install chromium', pra eu conseguir logar em sites.",
                Confidence.GUESS,
            )
        try:
            mensagem = logins_web.login(site)
        except (ValueError, RuntimeError) as e:
            return Answer(str(e), Confidence.GUESS)
        except Exception as e:
            return Answer(f"Não consegui logar em \"{site}\": {e}", Confidence.GUESS)
        return Answer(mensagem, Confidence.GUESS)

    def _listar(self):
        logins = logins_web.listar_logins()
        if not logins:
            return Answer("Nenhum login salvo ainda.", Confidence.CONFIRMED)
        lista = "\n".join(f'- {l["site"]} ({l["usuario"]}) -> {l["url"]}' for l in logins)
        return Answer(f"Logins salvos:\n{lista}", Confidence.CONFIRMED)

    def _remover(self, site: str):
        if not site:
            return Answer("Remover o login de qual site?", Confidence.GUESS)
        if logins_web.remover_login(site):
            return Answer(f'Removi o login salvo de "{site}".', Confidence.CONFIRMED)
        return Answer(f'Não achei nenhum login salvo pra "{site}".', Confidence.GUESS)

    def _conectar_google(self):
        if not logins_web.available():
            return Answer(
                "Instale 'keyring' e 'playwright' (requirements-automacao.txt), e rode "
                "'python -m playwright install chromium', pra eu conseguir conectar sua conta do Google.",
                Confidence.GUESS,
            )
        try:
            mensagem = logins_web.conectar_google()
        except Exception as e:
            return Answer(f"Não consegui abrir o login do Google: {e}", Confidence.GUESS)
        return Answer(mensagem, Confidence.CONFIRMED)

    def _logar_com_google(self, site: str):
        if not site:
            return Answer("Entrar com o Google em qual site?", Confidence.GUESS)
        if not logins_web.available():
            return Answer(
                "Instale 'keyring' e 'playwright' (requirements-automacao.txt), e rode "
                "'python -m playwright install chromium', pra eu conseguir fazer isso.",
                Confidence.GUESS,
            )
        url = site if site.startswith("http") else f"https://{site}"
        try:
            mensagem = logins_web.entrar_com_google(site, url)
        except RuntimeError as e:
            return Answer(str(e), Confidence.GUESS)
        except Exception as e:
            return Answer(f'Não consegui entrar em "{site}" com o Google: {e}', Confidence.GUESS)
        return Answer(mensagem, Confidence.GUESS)

    def _fechar_sessao(self, site: str):
        if not site:
            return Answer("Fechar o navegador de qual login?", Confidence.GUESS)
        if logins_web.fechar_sessao(site):
            return Answer(f'Fechei o navegador da sessão de login de "{site}".', Confidence.CONFIRMED)
        return Answer(f'Não havia nenhum navegador aberto pro login de "{site}".', Confidence.GUESS)
