"""
plugins/reminders.py
=======================
Lembretes com horário: "me lembre que tenho treino às 18h", "me avise
em 10 minutos que o bolo está pronto" -- agenda uma notificação (som +
mensagem) para o horário certo, via automacao/reminders.py.

Diferente de "lembre que X é Y" (plugins/memory_commands.py, que só
guarda um fato, sem horário): este plugin só assume o comando quando
consegue extrair uma expressão de tempo reconhecível da frase. Sem
isso, devolve None e o texto segue para os outros plugins -- é por
isso que "lembre que minha cor é azul" continua caindo em
memory_commands normalmente.

O verbo aceita várias formas naturais -- "me lembre", "lembra" (sem
"me"), "lembre-me", "pode me lembrar", "me avise", "notifique" -- em
vez de exigir um prefixo exato, porque conversa real varia demais pra
depender de bater uma frase fixa.
"""

import re
from datetime import datetime, timedelta

from automacao.reminders import cancel_reminder, create_reminder, list_pending, parse_datetime_from_text
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_TRIGGER_RE = re.compile(
    r"(?:me\s+)?(?:lembr(?:e|a|ar)|avis(?:e|a|ar)|notifiqu(?:e)|notific(?:a|ar))"
    r"(?:-me|-se)?\s+(?:que\s+)?(.+)",
    re.IGNORECASE,
)
# Recorrência: "a cada 1 hora", "a cada 30 minutos" -- diferente de um
# horário fixo, isso faz o lembrete repetir indefinidamente (ver
# automacao/reminders.py:_fire_reminder) até ser cancelado.
_INTERVAL_RE = re.compile(r"a cada\s+(\d+)\s*(minutos?|horas?)\b", re.IGNORECASE)
_CANCEL_RE = re.compile(
    r"\b(?:para|pare)\s+de\s+me\s+lembrar\s+(?:de\s+)?(.+)|"
    r"\bcancel[ae]\w*\s+(?:o\s+)?lembrete\s+(?:de\s+)?(.+)",
    re.IGNORECASE,
)


class RemindersPlugin(BasePlugin):
    name = "reminders"
    description = "Agenda lembretes com horário e avisa (som + mensagem) na hora certa"

    def matches(self, text: str) -> bool:
        t = text.lower().strip()
        return "meus lembretes" in t or bool(_TRIGGER_RE.search(t)) or bool(_CANCEL_RE.search(t))

    def handle(self, text: str, context: dict):
        user_id = context["user_id"]
        t = text.strip()
        tl = t.lower()

        if "meus lembretes" in tl:
            pendentes = list_pending(user_id)
            if not pendentes:
                return Answer("Você não tem lembretes pendentes.", Confidence.CONFIRMED)
            linhas = []
            for r in pendentes:
                quando = datetime.fromisoformat(r["quando"]).strftime("%d/%m às %H:%M")
                if r.get("intervalo_segundos"):
                    linhas.append(f"- {r['mensagem']} (recorrente, próximo em {quando})")
                else:
                    linhas.append(f"- {r['mensagem']} ({quando})")
            return Answer("Seus lembretes pendentes:\n" + "\n".join(linhas), Confidence.CONFIRMED)

        # Cancelar precisa vir ANTES do gatilho genérico de criar lembrete:
        # "para de me lembrar de beber água" também contém "lembrar", então
        # bateria com _TRIGGER_RE e seria tratado (errado) como um pedido
        # de lembrete novo se checado depois.
        m_cancel = _CANCEL_RE.search(t)
        if m_cancel:
            alvo = (m_cancel.group(1) or m_cancel.group(2) or "").strip(" .!")
            if not alvo:
                return Answer("Cancelar qual lembrete? Diga uma palavra da mensagem original.", Confidence.GUESS)
            n = cancel_reminder(user_id, alvo)
            if n:
                return Answer(f'Cancelei {n} lembrete(s) relacionado(s) a "{alvo}".', Confidence.CONFIRMED)
            return Answer(f'Não encontrei nenhum lembrete pendente relacionado a "{alvo}".', Confidence.GUESS)

        m = _TRIGGER_RE.search(t)
        if not m:
            return None
        resto = m.group(1).strip(" .!")

        m_intervalo = _INTERVAL_RE.search(resto)
        if m_intervalo:
            valor = int(m_intervalo.group(1))
            unidade = m_intervalo.group(2).lower()
            intervalo_segundos = valor * 60 if "min" in unidade else valor * 3600
            mensagem = _INTERVAL_RE.sub("", resto).strip(" .,!")
            if mensagem.lower().startswith("que "):
                mensagem = mensagem[4:].strip()
            if mensagem.lower().startswith("de "):
                mensagem = mensagem[3:].strip()
            mensagem = mensagem or "lembrete"
            primeiro_disparo = datetime.now() + timedelta(seconds=intervalo_segundos)
            create_reminder(user_id, mensagem, primeiro_disparo, intervalo_segundos=intervalo_segundos)
            unidade_label = "minuto" if "min" in unidade else "hora"
            plural = "s" if valor != 1 else ""
            return Answer(
                f'Combinado! Vou te lembrar de "{mensagem}" a cada {valor} {unidade_label}{plural}, '
                'até você me pedir pra parar (ex.: "para de me lembrar de beber água").',
                Confidence.CONFIRMED,
            )

        when, mensagem = parse_datetime_from_text(resto)
        if when is None:
            return None

        mensagem = mensagem.strip(" .,!")
        # Em frases como "me avisa em 5 minutos que o café vai ficar
        # pronto", o "que" vem depois da expressão de tempo, não logo
        # após o verbo -- parse_datetime_from_text só remove a
        # expressão de tempo em si, então um "que" solto pode sobrar
        # no início da mensagem.
        if mensagem.lower().startswith("que "):
            mensagem = mensagem[4:].strip()
        # Mesmo motivo do "que" acima: em "me lembre DE tomar remédio
        # às 20h", o "de" fica colado na mensagem depois que
        # parse_datetime_from_text tira só a expressão de horário --
        # sem isso, o lembrete salvava (e a notificação disparava)
        # com o texto literal "de tomar remédio" em vez de "tomar
        # remédio". Faltava aqui (já existia no ramo recorrente acima).
        if mensagem.lower().startswith("de "):
            mensagem = mensagem[3:].strip()
        mensagem = mensagem or "lembrete"
        create_reminder(user_id, mensagem, when)

        return Answer(
            f'Combinado! Vou te lembrar de "{mensagem}" em {when.strftime("%d/%m às %H:%M")}.',
            Confidence.CONFIRMED,
        )
