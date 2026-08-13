"""
plugins/jogos.py
===================
Lado de chat do "Aprendiz de jogos" (jogos/) -- Jarvis aprende a jogar
observando você e depois se aperfeiçoa sozinho. Ver jogos/__init__.py
pra arquitetura completa e as limitações honestas (não é RL de
verdade, não vai jogar bem, cada jogo precisa da própria demonstração).

IMPORTANTE (evita colisão real): os verbos usados aqui são de
propósito **aprende**/**joga**/**melhora**/**esquece** (nunca "cria"),
porque plugins/skill_forge.py já responde a "cria um jogo que..."
(gerar CÓDIGO de um jogo do zero -- feature totalmente diferente:
programar um jogo novo, não aprender a jogar um já existente) e
plugins/autonomia.py já responde a "aprende algo novo"/"aprenda algo
sozinho" (rotina de aprendizado autônomo genérico, sem relação com
jogos). Os regexes daqui exigem "a jogar" logo depois de
"aprende"/"ensinar", o que nenhum desses dois outros padrões cobre --
testado com despacho ao vivo (ver tests/test_plugins_jogos.py) pra
confirmar que "cria um jogo sobre gatos" continua indo pro skill_forge
e "aprende algo novo" continua indo pra autonomia.

Comandos:
    "aprende a jogar F1" / "vou te ensinar a jogar Roblox"
    "para de gravar"
    "joga F1 sozinho" / "joga F1 agora"
    "para de jogar"
    "isso foi bom" / "isso foi ruim" (só COM auto-jogo ativo)
    "melhora o que você aprendeu sobre F1"
    "como você está indo no F1"
    "esquece o que você aprendeu sobre F1"
"""

import re

import jogos
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin
from seguranca.permissions import PermissionDenied, check_destructive_action

_RE_APRENDER = re.compile(
    r"\baprend[ae]\w*\s+a\s+jogar\s+(.+?)\s*[.!]?$|"
    r"\bvou\s+te\s+ensinar\s+a\s+jogar\s+(.+?)\s*[.!]?$",
    re.IGNORECASE,
)
_RE_PARAR_GRAVACAO = re.compile(r"\b(?:para|pare|chega)\s+de\s+grav(?:ar|ação)\b", re.IGNORECASE)
_RE_JOGAR_SOZINHO = re.compile(r"\bjog[ae]\w*\s+(.+?)\s+(?:sozinho|sozinha|agora)\b", re.IGNORECASE)
_RE_PARAR_JOGO = re.compile(r"\bpara\s+de\s+jogar\b", re.IGNORECASE)
_RE_FEEDBACK_BOM = re.compile(r"\bisso\s+foi\s+bom\b|^bo[ma]\b\s*[.!]?$", re.IGNORECASE)
_RE_FEEDBACK_RUIM = re.compile(r"\bisso\s+foi\s+ruim\b|\bn[ãa]o,?\s+assim\s+n[ãa]o\b|^ruim\b\s*[.!]?$", re.IGNORECASE)
_RE_MELHORAR = re.compile(
    r"\bmelhor[ae]\w*\s+o\s+que\s+(?:você|voce)\s+aprendeu\s+(?:sobre|de|do|da)\s+(.+?)\s*[.!]?$",
    re.IGNORECASE,
)
_RE_STATUS = re.compile(
    r"\bcomo\s+(?:você|voce)\s+est[áa]\s+indo\s+(?:no|na|com|em)\s+(.+?)\s*[.!?]?$",
    re.IGNORECASE,
)
_RE_ESQUECER = re.compile(
    r"\besquece\w*\s+o\s+que\s+(?:você|voce)\s+aprendeu\s+sobre\s+(.+?)\s*[.!]?$",
    re.IGNORECASE,
)


class JogosPlugin(BasePlugin):
    name = "jogos"
    description = "Aprende a jogar um jogo observando você e melhora sozinho jogando de novo"
    triggers = [
        "aprende a jogar", "vou te ensinar a jogar", "para de gravar",
        "joga sozinho", "para de jogar", "como você está indo",
    ]

    def matches(self, text: str) -> bool:
        t = text.strip()
        if (
            _RE_APRENDER.search(t) or _RE_PARAR_GRAVACAO.search(t) or _RE_JOGAR_SOZINHO.search(t)
            or _RE_PARAR_JOGO.search(t) or _RE_MELHORAR.search(t) or _RE_STATUS.search(t)
            or _RE_ESQUECER.search(t)
        ):
            return True
        # Palavras de feedback ("bom"/"ruim") são curtas e genéricas demais
        # pra interceptar SEMPRE -- só valem enquanto uma sessão de
        # auto-jogo está rolando de verdade.
        if jogos.jogo_ativo() and (_RE_FEEDBACK_BOM.search(t) or _RE_FEEDBACK_RUIM.search(t)):
            return True
        return False

    def handle(self, text: str, context: dict):
        t = text.strip()

        m = _RE_APRENDER.search(t)
        if m:
            nome_jogo = (m.group(1) or m.group(2)).strip(" .!?")
            return self._iniciar_gravacao(nome_jogo)

        if _RE_PARAR_GRAVACAO.search(t):
            return self._parar_gravacao()

        m = _RE_JOGAR_SOZINHO.search(t)
        if m:
            return self._jogar_sozinho(m.group(1).strip(" .!?"))

        if _RE_PARAR_JOGO.search(t):
            return self._parar_jogo()

        if jogos.jogo_ativo():
            if _RE_FEEDBACK_BOM.search(t):
                jogos.registrar_feedback(bom=True)
                return Answer("Anotado -- isso conta a favor na hora de refinar o aprendizado.", Confidence.CONFIRMED)
            if _RE_FEEDBACK_RUIM.search(t):
                jogos.registrar_feedback(bom=False)
                return Answer("Anotado -- vou excluir esse trecho na hora de refinar o aprendizado.", Confidence.CONFIRMED)

        m = _RE_MELHORAR.search(t)
        if m:
            return self._melhorar(m.group(1).strip(" .!?"))

        m = _RE_STATUS.search(t)
        if m:
            return self._status(m.group(1).strip(" .!?"))

        m = _RE_ESQUECER.search(t)
        if m:
            confirmado = "confirmo" in t.lower()
            return self._esquecer(m.group(1).strip(" .!?"), confirmado)

        return None

    def _iniciar_gravacao(self, nome_jogo: str):
        try:
            resultado = jogos.iniciar_gravacao(nome_jogo)
        except RuntimeError as e:
            return Answer(str(e), Confidence.GUESS)
        return Answer(
            f'Beleza, tô observando -- pode jogar "{nome_jogo}" normalmente '
            f'(até {resultado["duracao_minutos"]:.0f} min). Diga "para de gravar" quando terminar.',
            Confidence.CONFIRMED,
        )

    def _parar_gravacao(self):
        resultado = jogos.parar_gravacao()
        if not resultado["parou"]:
            return Answer("Não havia nenhuma gravação em andamento.", Confidence.GUESS)
        if resultado["n_quadros"] == 0:
            return Answer("Gravação encerrada, mas não capturei nenhum quadro -- nada pra treinar ainda.", Confidence.GUESS)

        nome_jogo = resultado["nome_jogo"]
        try:
            treino = jogos.treinar_por_imitacao(nome_jogo)
        except RuntimeError as e:
            return Answer(f'Gravei {resultado["n_quadros"]} quadro(s), mas não consegui treinar: {e}', Confidence.GUESS)
        return Answer(
            f'Gravei {resultado["n_quadros"]} quadro(s) e treinei uma primeira versão '
            f'({treino["epocas"]} época(s), perda {treino["perda_final"]}). '
            f'Diga "joga {nome_jogo} sozinho" pra ver o resultado.',
            Confidence.CONFIRMED,
        )

    def _jogar_sozinho(self, nome_jogo: str):
        try:
            resultado = jogos.iniciar_jogo_sozinho(nome_jogo)
        except RuntimeError as e:
            return Answer(str(e), Confidence.GUESS)
        aviso_roblox = (
            ' Aviso: automação em experiências do Roblox pode violar os Termos de Serviço da '
            "plataforma -- o risco de banimento de conta é seu."
            if "roblox" in nome_jogo.lower() else ""
        )
        return Answer(
            f'Jogando "{nome_jogo}" sozinho por até {resultado["duracao_minutos"]:.0f} min -- '
            'diga "para de jogar" a qualquer momento, ou "isso foi bom"/"isso foi ruim" '
            "pra eu aprender com o que você achou." + aviso_roblox,
            Confidence.CONFIRMED,
        )

    def _parar_jogo(self):
        resultado = jogos.parar_jogo()
        if not resultado["parou"]:
            return Answer("Não havia nenhuma sessão de auto-jogo em andamento.", Confidence.GUESS)
        return Answer(
            f'Parei -- joguei {resultado["n_quadros"]} quadro(s) em {resultado["n_episodios"]} episódio(s). '
            'Diga "melhora o que você aprendeu sobre..." quando quiser que eu refine com isso.',
            Confidence.CONFIRMED,
        )

    def _melhorar(self, nome_jogo: str):
        try:
            resultado = jogos.retreinar_com_sessoes(nome_jogo)
        except RuntimeError as e:
            return Answer(str(e), Confidence.GUESS)
        return Answer(
            f'Refinei o aprendizado de "{nome_jogo}" com o que rolou nas sessões de auto-jogo '
            f'({resultado["n_amostras"]} amostra(s), perda {resultado["perda_final"]}).',
            Confidence.CONFIRMED,
        )

    def _status(self, nome_jogo: str):
        info = jogos.status(nome_jogo)
        if info["n_demonstracoes"] == 0 and info["n_sessoes"] == 0:
            return Answer(f'Ainda não sei nada sobre "{nome_jogo}" -- diga "aprende a jogar {nome_jogo}" pra começar.', Confidence.GUESS)
        linhas = [
            f'Sobre "{nome_jogo}":',
            f'- {info["n_demonstracoes"]} demonstração/ões gravada(s)',
            f'- {info["n_sessoes"]} sessão/ões de auto-jogo',
            f'- política treinada: {"sim" if info["tem_politica_treinada"] else "não"}',
        ]
        if info["duracao_media_episodio_quadros"] is not None:
            linhas.append(f'- duração média de episódio: {info["duracao_media_episodio_quadros"]} quadros')
        if info["tendencia"]:
            linhas.append(f'- tendência: {info["tendencia"]}')
        linhas.append(
            "(lembrando: isso mede duração/repetição, não entendimento real do jogo -- ver limitações em jogos/__init__.py)"
        )
        return Answer("\n".join(linhas), Confidence.CONFIRMED)

    def _esquecer(self, nome_jogo: str, confirmado: bool):
        try:
            check_destructive_action(f'apagar tudo que aprendi sobre "{nome_jogo}"', confirmed=confirmado)
        except PermissionDenied as e:
            return Answer(str(e), Confidence.GUESS)
        apagou = jogos.apagar_jogo(nome_jogo)
        if not apagou:
            return Answer(f'Não tinha nada guardado sobre "{nome_jogo}".', Confidence.GUESS)
        return Answer(f'Esqueci tudo que tinha aprendido sobre "{nome_jogo}".', Confidence.CONFIRMED)
