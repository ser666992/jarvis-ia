"""
automacao/escuta_ativa.py
============================
Sessão de escuta acompanhada, com tempo limitado -- a alternativa
responsável ao "modo de escuta contínua" sempre ligado que foi pedido
nesta conversa e recusado (ambient listening sem escopo definido capta
terceiros sem consentimento deles, e nunca tem um fim natural). Aqui:

  - A escuta só começa com um comando EXPLÍCITO do usuário, dizendo por
    quanto tempo ("escuta essa conversa por 10 minutos") -- nunca liga
    sozinha.
  - Teto de segurança (`escuta_ativa.duracao_maxima_minutos`, 30 por
    padrão) -- mesmo se pedirem mais, a sessão nunca passa disso.
  - Avisa (som + mensagem, `automacao.notify`) quando a escuta começa e
    quando termina -- nunca escuta silenciosamente sem indicar.
  - Pode ser encerrada a qualquer momento ("para de escutar").
  - Nada é persistido em disco/banco -- a transcrição vive só na
    memória do processo, e é apagada assim que uma NOVA sessão começa
    (ver `iniciar()`) ou explicitamente via `descartar()`. Reiniciar o
    Ultron também apaga (não sobrevive ao processo).

Diferente de `voz/loop.py` (VoiceLoop): lá é um comando de cada vez, o
Ultron processa e age sobre cada frase. Aqui é só captura/transcrição
contínua por um tempo determinado -- o usuário revisa depois ("o que
você ouviu") ou pede pra agir sobre o que foi dito; o Ultron não reage
sozinho a cada frase durante a sessão.

Implementado como uma thread dedicada (não via `automacao.tasks`,
pensado pra ticks CURTOS e baratos) porque aqui cada "passo" já é, por
natureza, uma gravação bloqueante de alguns segundos -- é o comportamento
desejado (escuta contínua), não um tick que deveria ser rápido.
"""

import threading
import time

from logs.logger import get_logger

log = get_logger("automacao")

_DURACAO_TRECHO_SEGUNDOS = 6.0  # janela de gravação por iteração -- também o atraso máx. pra "para de escutar" surtir efeito

_estado = {
    "ativa": False,
    "inicio": None,
    "fim_previsto": None,
    "transcricao": [],  # [{"timestamp": float, "texto": str}]
    "_parar_evento": None,
    "_thread": None,
}


def _duracao_maxima_minutos() -> float:
    from config.settings import get_settings
    return float(get_settings().get("escuta_ativa.duracao_maxima_minutos", 30.0))


def _formatar_duracao(minutos: float) -> str:
    if minutos < 1:
        return f"{minutos * 60:.0f} segundo(s)"
    return f"{minutos:.0f} minuto(s)"


def ativa() -> bool:
    return bool(_estado["ativa"])


def iniciar(duracao_minutos: float) -> dict:
    """Inicia uma sessão de escuta de até `duracao_minutos` (limitado
    por `escuta_ativa.duracao_maxima_minutos`). Levanta RuntimeError se
    já houver uma sessão ativa, ou se não houver motor de voz
    disponível."""
    if ativa():
        raise RuntimeError('Já existe uma escuta em andamento -- diga "para de escutar" antes de iniciar outra.')

    from voz.stt import SpeechToText
    stt = SpeechToText()
    if not stt.available():
        raise RuntimeError(
            "Nenhum motor de reconhecimento de voz disponível (instale 'vosk', "
            "'faster-whisper' ou 'SpeechRecognition' + 'sounddevice', ver requirements-voz.txt)."
        )

    duracao_minutos = max(0.5, min(float(duracao_minutos), _duracao_maxima_minutos()))
    _estado["transcricao"] = []  # nova sessão descarta a transcrição da anterior
    _estado["inicio"] = time.time()
    _estado["fim_previsto"] = _estado["inicio"] + duracao_minutos * 60
    _estado["_parar_evento"] = threading.Event()
    _estado["ativa"] = True

    from automacao.notify import notify
    notify(
        "Escuta ativa",
        f'Ouvindo por até {_formatar_duracao(duracao_minutos)}. Diga "para de escutar" a qualquer momento pra encerrar antes.',
    )

    thread = threading.Thread(target=_loop_escuta, args=(stt, _estado["_parar_evento"]), daemon=True)
    _estado["_thread"] = thread
    thread.start()
    return {"duracao_minutos": duracao_minutos, "fim_previsto": _estado["fim_previsto"]}


def _loop_escuta(stt, parar_evento):
    while not parar_evento.is_set() and time.time() < _estado["fim_previsto"]:
        try:
            resultado = stt.listen_and_transcribe_detalhado(duration_seconds=_DURACAO_TRECHO_SEGUNDOS)
        except Exception as e:
            log.warning("falha ao transcrever durante escuta ativa: %s", e)
            continue
        texto = (resultado.get("texto") or "").strip()
        if texto and resultado.get("confiavel", True):
            _estado["transcricao"].append({"timestamp": time.time(), "texto": texto})
    _estado["ativa"] = False
    from automacao.notify import notify
    notify("Escuta ativa", "Sessão de escuta encerrada.")


def parar() -> dict:
    """Encerra a sessão em andamento (se houver). Pode levar até
    `_DURACAO_TRECHO_SEGUNDOS` pra surtir efeito de verdade -- a
    thread só checa o pedido de parada entre uma gravação e outra,
    nunca no meio de uma gravação já em curso."""
    if not ativa():
        return {"parou": False, "transcricao": []}
    _estado["_parar_evento"].set()
    thread = _estado.get("_thread")
    if thread:
        thread.join(timeout=_DURACAO_TRECHO_SEGUNDOS + 5.0)
    return {"parou": True, "transcricao": list(_estado["transcricao"])}


def transcricao_atual() -> list:
    return list(_estado["transcricao"])


def tempo_restante_segundos() -> float:
    if not ativa() or not _estado["fim_previsto"]:
        return 0.0
    return max(0.0, _estado["fim_previsto"] - time.time())


def descartar():
    """Apaga a transcrição guardada em memória (da sessão atual ou da
    última encerrada) -- pedido explícito do usuário de "esquecer" o
    que foi ouvido antes do fim natural da retenção (próxima sessão)."""
    _estado["transcricao"] = []
