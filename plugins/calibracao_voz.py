"""
plugins/calibracao_voz.py
============================
"Calibra o microfone": teste guiado que grava alguns segundos da sua
fala natural e ajusta `voz.silencio_para_parar_segundos` pro jeito que
VOCÊ fala -- em vez do palpite genérico (0.6s por padrão) que corta
frases de quem fala mais devagar ou pausa mais no meio ("cortando
minhas frases no meio" -- sintoma real que motivou isto: o valor
genérico não sobrevive a uma pausa de respiração/pensamento no meio de
uma frase mais longa).

Ver voz/stt.py:SpeechToText.calibrar_microfone() pra como a medição
funciona (mede a maior PAUSA INTERNA da fala, não a pausa final).
Também ajusta `voz.sensibilidade_barge_in` (calibrada junto, na mesma
gravação -- ver docstring de calibrar_microfone()), guarda o chão de
ruído medido (`voz.ruido_ambiente_calibrado`, usado depois por
voz/loop.py:_checar_mudanca_de_ambiente pra notar se o ambiente mudou)
e marca `voz.microfone_calibrado=True` (evita que
voz/loop.py:_calibrar_se_necessario rode o assistente de novo na
próxima vez que o modo de voz iniciar).

Comandos:
    "calibra o microfone" / "testa o microfone" / "calibra minha voz"
    "ajusta o microfone pra minha voz"
"""

import re

from automacao.notify import notify
from core.confidence import Answer, Confidence
from core.personality import NOME
from core.plugin_manager import BasePlugin

_RE = re.compile(
    r"\bcalibr[ae]\w*\s+.*\b(microfone|voz)\b|"
    r"\btest[ae]\w*\s+.*\bmicrofone\b|"
    r"\bajust[ae]\w*\s+.*\bmicrofone\b.*\b(minha\s+voz|voz)\b",
    re.IGNORECASE,
)


class CalibracaoVozPlugin(BasePlugin):
    name = "calibracao_voz"
    description = "Testa o microfone e calibra o tempo de silêncio pro jeito que você fala (menos corte no meio de frases)"
    triggers = ["calibra o microfone", "testa o microfone", "calibra minha voz", "calibra o meu microfone"]

    def matches(self, text: str) -> bool:
        return bool(_RE.search(text.strip()))

    def handle(self, text: str, context: dict):
        from voz.stt import SpeechToText
        stt = SpeechToText()
        if not stt.available():
            return Answer(
                "Nenhum motor de voz disponível pra eu testar o microfone (instale 'vosk' ou "
                "'faster-whisper' + 'sounddevice', ver requirements-voz.txt).",
                Confidence.GUESS,
            )

        # Aviso IMEDIATO (som + notificação) -- a gravação começa logo em
        # seguida, então a pessoa precisa saber AGORA que é hora de falar,
        # não só quando a resposta (que só vem depois da gravação inteira)
        # aparecer no chat.
        notify(
            NOME,
            'Calibrando o microfone -- fale uma frase natural e um pouco '
            'longa AGORA, com alguma pausa no meio (ex.: "estou testando o '
            'microfone... isso aqui deveria funcionar bem").',
            sound=True,
        )

        try:
            resultado = stt.calibrar_microfone()
        except Exception as e:
            return Answer(f"Não consegui calibrar o microfone: {e}", Confidence.GUESS)

        from config.settings import get_settings
        settings = get_settings()
        settings.set("voz.silencio_para_parar_segundos", resultado["silencio_recomendado_segundos"])
        settings.set("voz.sensibilidade_barge_in", resultado["sensibilidade_barge_in_recomendada"])
        settings.set("voz.ruido_ambiente_calibrado", resultado["ruido_ambiente_rms"])
        settings.set("voz.microfone_calibrado", True)
        settings.save()

        linhas = [
            f'Calibrado! Ajustei o tempo de silêncio pra {resultado["silencio_recomendado_segundos"]}s '
            f'(sua maior pausa no meio da frase foi de {resultado["maior_pausa_interna_segundos"]}s) -- '
            "isso deve cortar bem menos no meio das suas frases. Também ajustei a sensibilidade "
            f'de interrupção (barge-in) pro seu volume de voz ({resultado["sensibilidade_barge_in_recomendada"]}).',
        ]
        if resultado["aviso"]:
            linhas.append(resultado["aviso"])
        linhas.append('Pode rodar "calibra o microfone" de novo a qualquer momento se mudar de ambiente.')
        return Answer("\n".join(linhas), Confidence.CONFIRMED)
