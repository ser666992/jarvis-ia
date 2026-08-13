"""
plugins/observation.py
=========================
Ultron "vendo" o que o usuário está fazendo (jogando, estudando,
trabalhando) e comentando sobre isso -- via visao/observe.py (janela
em foco + processo + texto visível na tela via OCR, tudo opcional e
degradando graciosamente) combinado com o estágio de IA (ia/manager.py)
para gerar um comentário natural e breve.

A detecção da intenção usa um par de regex (verbo de "olhar" + alvo
"tela"/"o que eu estou fazendo"/"jogando"/"estudando") em vez de uma
lista fixa de frases -- conversa real varia demais ("vê minha tela",
"olha pra minha tela", "consegue ver o que eu tô fazendo?", "me vê
jogando"...) pra depender de bater uma frase exata. Ver _classify().

Comandos reconhecidos (exemplos, não frases exatas):
    "veja o que eu estou fazendo" / "olha minha tela" / "consegue ver
    o que eu to fazendo?" -> um comentário único, agora
    "fique de olho no que eu estou fazendo" / "observe a todo momento"
    / "comenta aleatoriamente sobre o que eu tô vendo" / "a cada 10
    minutos" -> comentários recorrentes
    "pare de me observar" / "para de olhar"  -> cancela os recorrentes

Sem um intervalo explícito ("a cada N minutos"), os comentários
recorrentes disparam em intervalos ALEATÓRIOS (entre 3 e 7 minutos) em
vez de um tique-taque fixo -- fica mais parecido com alguém comentando
espontaneamente de vez em quando do que um cronômetro robótico. Com um
intervalo explícito, esse é respeitado à risca.

Sem nenhum provedor de IA configurado, cai para um comentário
simples baseado em palavras-chave da janela/processo em foco -- nunca
trava por falta de IA, só fica menos elaborado.
"""

import random
import re

from automacao import tasks
from automacao.notify import notify
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin
from core.timeline import registrar
from visao.observe import describe_activity

# "pare/para" + "de" + (opcional "me") + o verbo -- exige o "de" no
# meio pra não disparar em frases soltas tipo "para de estudar, vamos
# ver um filme" (tem "para" e "ver" mas não "para de ver").
_STOP_RE = re.compile(r"\b(pare|para)\s+de\s+(me\s+)?(observ\w*|olh\w*|ver|acompanh\w*)", re.IGNORECASE)

# Verbo de "olhar/observar/comentar", em várias conjugações e formas
# de pedido ("consegue ver", "pode ver") -- "comenta sobre minha tela"
# é tão válido quanto "olha minha tela", não precisa dizer "veja"
# explicitamente pra pedir um comentário.
_ACTION_RE = re.compile(
    # Cada stem termina em \w* pra cobrir gerúndio/infinitivo/conjugação
    # (ex.: "olh[ae]\w*" casa "olha", "olhar" E "olhando" -- o \b no
    # final do grupo garante a fronteira certa mesmo com o \w* guloso).
    # Sem o \w*, "olh[ae]" sozinho só casava até a próxima letra e o \b
    # falhava pra qualquer forma com mais letras depois (gerúndio,
    # infinitivo), deixando frases muito comuns tipo "fica observando
    # minha tela"/"da uma olhada"/"voce ta vendo minha tela" sem
    # reconhecer NENHUM verbo de ação -- e a intenção inteira falhava.
    r"\b(ver|vendo|v[eê]|veja|vejo|olh[ae]\w*|observ[ae]\w*|"
    r"acompanh[ae]\w*|repar[ae]\w*|coment[ae]\w*|"
    r"entend[ae]\w*|"
    r"consegue\s+(?:ver|olhar)|pode\s+ver)\b",
    re.IGNORECASE,
)

# O que está sendo observado: a tela, a atividade, ou uma referência a
# "o que eu estou/tô fazendo" / jogando / estudando / trabalhando / um
# vídeo que esteja passando na tela.
_TARGET_RE = re.compile(
    r"(minha tela|minha atividade|meu jogo|jogando|estudando|trabalhando|fazendo|"
    r"v[ií]deo|"
    r"o que (eu\s+)?(estou|to|t[oô])\b)",
    re.IGNORECASE,
)

# "em tempo real" -- pedido explícito de acompanhamento mais frequente
# (intervalo curto + só comenta quando algo muda de verdade, ver
# _tick()) em vez do intervalo aleatório padrão de minutos.
_REALTIME_RE = re.compile(r"tempo real", re.IGNORECASE)
_REALTIME_INTERVAL = 20  # segundos

# "de olho" ("fique/fica de olho") é sinal inequívoco de observação
# recorrente por si só -- ao contrário dos marcadores "fracos" abaixo
# (frases comuns que só devem contar como "isso é recorrente" quando
# JÁ combinadas com verbo+alvo de observação, pra não disparar em
# frases soltas tipo "sempre que eu erro, tento de novo").
_STRONG_RECURRING_RE = re.compile(r"\bde olho\b", re.IGNORECASE)
_WEAK_RECURRING_PHRASES = (
    "de tempos em tempos", "toda hora", "periodicamente", "sempre que",
    "constantemente", "o tempo todo", "a todo momento", "o tempo inteiro",
    "sem parar", "aleatori", "tempo real",
)
_INTERVAL_RE = re.compile(r"a cada\s+(\d+)\s*min(?:uto)?s?", re.IGNORECASE)
_RANDOM_INTERVAL_RANGE = (180, 420)  # 3 a 7 minutos

_JOGO_PALAVRAS = (
    "steam", "epic games", "valorant", "league of legends", "leagueclient",
    "counter-strike", "csgo", "cs2", "minecraft", "fortnite", "gta",
    "dota", "overwatch", "roblox", "among us", "apex legends",
)
_ESTUDO_PALAVRAS = (
    "word", "excel", "powerpoint", "pdf", "code", "visual studio",
    "pycharm", "notion", "anki", "duolingo", "coursera", "moodle",
    "google docs", "wikipedia", "overleaf", "jupyter",
)


def _classify(text: str):
    """Retorna 'stop', 'start' (recorrente), 'once', ou None (não é um
    pedido de observação -- deixa o texto seguir pra outros plugins).

    Exige verbo de observação + alvo (ex.: "ver" + "minha tela") OU a
    frase "de olho" pra sequer considerar a mensagem -- os outros
    marcadores de recorrência ("sempre que", "o tempo todo" etc.) só
    contam quando um desses dois já estiver presente, senão frases
    soltas do dia a dia (ex.: "sempre que eu erro, tento de novo")
    disparariam o plugin por engano."""
    t = text.lower().strip()

    if _STOP_RE.search(t):
        return "stop"

    tem_acao = bool(_ACTION_RE.search(t))
    tem_alvo = bool(_TARGET_RE.search(t))
    tem_de_olho = bool(_STRONG_RECURRING_RE.search(t))
    tem_intervalo = bool(_INTERVAL_RE.search(t))

    # Evidência mínima de que a frase é sobre observação: verbo+alvo
    # explícitos, "de olho" sozinho, ou verbo+intervalo ("observe a
    # cada 10 minutos", sem precisar repetir "minha tela").
    sinal_suficiente = (tem_acao and tem_alvo) or tem_de_olho or (tem_acao and tem_intervalo)
    if not sinal_suficiente:
        return None

    is_recurring = (
        tem_de_olho or tem_intervalo
        or any(p in t for p in _WEAK_RECURRING_PHRASES)
    )
    return "start" if is_recurring else "once"


def _parse_interval_seconds(text: str):
    """Retorna o intervalo em segundos se o usuário pediu um explícito
    ("a cada 10 minutos"), ou None se não pediu -- nesse caso quem
    chama deve usar um intervalo aleatório (ver _random_interval())."""
    m = _INTERVAL_RE.search(text)
    if not m:
        return None
    return max(60, int(m.group(1)) * 60)


def _random_interval() -> float:
    return random.uniform(*_RANDOM_INTERVAL_RANGE)


def _fallback_comment(info: dict) -> str:
    alvo = " ".join(filter(None, [info.get("janela"), info.get("processo")])).lower()
    if not alvo:
        return "Não consegui identificar o que está em foco na sua tela agora."
    if any(p in alvo for p in _JOGO_PALAVRAS):
        return f"Te vi jogando por aí ({info.get('janela') or info.get('processo')}) -- boa sorte na partida!"
    if any(p in alvo for p in _ESTUDO_PALAVRAS):
        return f"Parece que você está estudando/trabalhando em {info.get('janela') or info.get('processo')}. Bora com foco!"
    return f"Percebi que você está em \"{info.get('janela') or info.get('processo')}\" agora."


def _build_prompt(info: dict) -> str:
    linhas = ["Dê uma olhada no que eu pareço estar fazendo no computador agora:"]
    linhas.append(f"- Janela em foco: {info.get('janela') or 'não identificada'}")
    if info.get("processo"):
        linhas.append(f"- Processo: {info['processo']}")
    if info.get("texto_tela"):
        linhas.append(f"- Texto visível na tela: {info['texto_tela']}")
    linhas.append(
        "\nComente de forma breve (1-2 frases), natural e amigável sobre o que "
        "parece que estou fazendo -- jogando, estudando ou trabalhando -- como "
        "se estivesse acompanhando de leve, sem ser intrusivo."
    )
    return "\n".join(linhas)


def comment_on_activity(ia_manager, history=None, info=None) -> str:
    if info is None:
        info = describe_activity()
    if ia_manager is not None:
        try:
            _, resposta = ia_manager.chat(_build_prompt(info), history=history or [])
        except Exception:
            resposta = None
        if resposta:
            return resposta
    return _fallback_comment(info)


class ObservationPlugin(BasePlugin):
    name = "observation"
    description = "Observa a janela/atividade em foco e comenta sobre o que você parece estar fazendo"

    def matches(self, text: str) -> bool:
        return _classify(text) is not None

    def handle(self, text: str, context: dict):
        kind = _classify(text)
        if kind is None:
            return None

        user_id = context["user_id"]
        ia_manager = context.get("ia_manager")
        routine_name = f"observacao_{user_id}"

        if kind == "stop":
            if tasks.cancel_routine(routine_name):
                return Answer("Ok, parei de observar.", Confidence.CONFIRMED)
            return Answer("Eu não estava observando nada no momento.", Confidence.CONFIRMED)

        if kind == "start":
            interval_fixo = _parse_interval_seconds(text)
            memory = context["memory"]

            if _REALTIME_RE.search(text):
                # "Tempo real": intervalo curto, e só comenta quando a
                # janela/texto na tela realmente muda desde o último
                # tick -- fica bem mais "ao vivo" que o modo padrão sem
                # virar um tique-taque irritante a cada 20s.
                estado = {"ultima_assinatura": None}

                def _tick():
                    info = describe_activity()
                    assinatura = (info.get("janela"), info.get("texto_tela"))
                    if assinatura == estado["ultima_assinatura"]:
                        return
                    estado["ultima_assinatura"] = assinatura
                    comentario = comment_on_activity(ia_manager, memory.get_history(user_id, limit=10), info=info)
                    notify("Ultron", comentario)
                    registrar("comentario_tela", comentario[:150])

                tasks.schedule_recurring(routine_name, _REALTIME_INTERVAL, _tick)
                return Answer(
                    f"Combinado, vou acompanhar sua tela em tempo real (verificando a cada "
                    f"{_REALTIME_INTERVAL}s) e só comento quando algo mudar de verdade -- "
                    'novo vídeo, nova janela, texto novo na tela. Diga "pare de me observar" '
                    "quando quiser parar. (Isso ainda lê texto/janela, não é análise de "
                    "imagem/vídeo de verdade -- ver limitação no README.)",
                    Confidence.CONFIRMED,
                )

            def _tick():
                comentario = comment_on_activity(ia_manager, memory.get_history(user_id, limit=10))
                notify("Ultron", comentario)
                registrar("comentario_tela", comentario[:150])

            if interval_fixo:
                tasks.schedule_recurring(routine_name, interval_fixo, _tick)
                descricao = f"a cada {interval_fixo // 60} minuto(s)"
            else:
                tasks.schedule_recurring(routine_name, _random_interval, _tick)
                lo, hi = _RANDOM_INTERVAL_RANGE
                descricao = f"de vez em quando, em intervalos aleatórios (entre {lo // 60} e {hi // 60} minutos)"

            return Answer(
                f"Combinado, vou dar uma olhada {descricao} e comentar sobre o que "
                "você parece estar fazendo. Diga 'pare de me observar' quando quiser parar.",
                Confidence.CONFIRMED,
            )

        comentario = comment_on_activity(ia_manager, context["history"])
        confidence = Confidence.RELIABLE_SOURCE if ia_manager is not None else Confidence.GUESS
        return Answer(comentario, confidence)
