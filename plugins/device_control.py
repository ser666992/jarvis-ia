"""
plugins/device_control.py
============================
Controla o celular Android via ADB sem fio (dispositivos/adb.py) --
sempre dentro da mesma rede local, nunca expõe nada na internet.

Como conectar (só necessário uma vez, ou toda vez que a depuração sem
fio for desligada/religada):
    1. No celular: Configurações > Opções do desenvolvedor > Depuração
       sem fio > Parear dispositivo com código.
    2. "pareia o celular <ip>:<porta> <código>" -- IP, porta e código
       de 6 dígitos aparecem na tela de pareamento do celular.
    3. "conecta no celular <ip>:<porta>" -- a porta da tela principal
       de Depuração sem fio (diferente da porta de pareamento, e muda
       toda vez que a depuração sem fio é desligada e religada).

Comandos:
    "conecta no celular <ip>[:porta]" / "pareia o celular <ip>:<porta> <código>"
    "desconecta o celular" / "celulares conectados"
    "abre o whatsapp no celular" / "abre <app> no celular"
    "vê a bateria do celular" / "bateria do celular"
    "tira um print do celular" / "screenshot do celular"
    "monitora a bateria do celular" / "para de monitorar a bateria"
"""

import datetime
import os
import re

from automacao import tasks
from automacao.notify import notify
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin
from core.timeline import registrar
from dispositivos import adb

_IP_PORT_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})(?::(\d{1,5}))?")
_CODE_RE = re.compile(r"\b(\d{6})\b")

_CONNECT_RE = re.compile(r"\bconect[ae]r?\s+(?:no|com o|ao|o)?\s*celular", re.IGNORECASE)
_PAIR_RE = re.compile(r"pare(?:ia|ar)\s+(?:o\s+)?celular", re.IGNORECASE)
_DISCONNECT_RE = re.compile(r"desconect[ae]r?\s+(?:o\s+)?celular", re.IGNORECASE)
_LIST_RE = re.compile(r"(celulares|dispositivos|aparelhos)\s+conectados", re.IGNORECASE)
_OPEN_APP_RE = re.compile(r"abr(?:[ae]|ir)\s+(?:o\s+|a\s+)?(.+?)\s+no\s+celular", re.IGNORECASE)
# "bateria" e "celular" em qualquer ordem ("vê a bateria do celular",
# "celular com quanto de bateria", "quanto de bateria tem o celular").
_BATTERY_RE = re.compile(
    r"\bbateria\b.*\bcelular\b|\bcelular\b.*\bbateria\b", re.IGNORECASE
)
# "print"/"screenshot"/"captura" + "celular" em qualquer ordem --
# checado ANTES do print de tela genérico do system_control.py (este
# plugin carrega primeiro, em ordem alfabética: device < system).
_SCREENSHOT_RE = re.compile(
    r"\b(print|screenshot|captura[r]?)\b.*\bcelular\b|\bcelular\b.*\b(print|screenshot|captura)\b",
    re.IGNORECASE,
)

# Monitoramento autônomo de bateria: "controla o celular sozinho" --
# em vez de só responder quando perguntado, fica de olho na bateria em
# segundo plano e avisa sozinho quando ela fica baixa.
_MONITOR_BATTERY_RE = re.compile(
    r"\b(monitor[ae]\w*|fica\w*\s+de\s+olho|avis[ae]\w*)\b.*\bbateria\b.*\bcelular\b",
    re.IGNORECASE,
)
_STOP_MONITOR_BATTERY_RE = re.compile(
    r"\bpar[ae]\w*\s+de\s+monitorar\s+a\s+bateria\b", re.IGNORECASE
)
_LIMIAR_BATERIA_BAIXA = 20  # %
_INTERVALO_MONITOR_BATERIA = 900  # 15 minutos

_SEM_ADB = (
    "Não consegui falar com o celular por ADB. Diga 'pareia o celular <ip>:<porta> <código>' "
    "pra conectar primeiro (Opções do desenvolvedor > Depuração sem fio, no celular)."
)


class DeviceControlPlugin(BasePlugin):
    name = "device_control"
    description = "Controla o celular Android via ADB sem fio"

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(
            _PAIR_RE.search(t) or _CONNECT_RE.search(t) or _DISCONNECT_RE.search(t)
            or _LIST_RE.search(t) or _OPEN_APP_RE.search(t) or _BATTERY_RE.search(t)
            or _SCREENSHOT_RE.search(t)
            or _MONITOR_BATTERY_RE.search(t) or _STOP_MONITOR_BATTERY_RE.search(t)
        )

    def handle(self, text: str, context: dict):
        t = text.strip()

        if _STOP_MONITOR_BATTERY_RE.search(t):
            return self._parar_monitorar_bateria(context)
        if _MONITOR_BATTERY_RE.search(t):
            return self._monitorar_bateria(context)

        # Todos os comandos daqui pra baixo exigem o binário ADB instalado.
        if _PAIR_RE.search(t) or _CONNECT_RE.search(t) or _DISCONNECT_RE.search(t) or _LIST_RE.search(t):
            if not adb.available():
                return Answer(
                    "Preciso do 'adb' (Android SDK Platform Tools) instalado e no PATH pra "
                    "isso -- veja dispositivos/README.md.",
                    Confidence.GUESS,
                )
            if _PAIR_RE.search(t):
                return self._pair(t)
            if _CONNECT_RE.search(t):
                return self._connect(t)
            if _DISCONNECT_RE.search(t):
                return self._disconnect()
            return self._list()

        if _BATTERY_RE.search(t):
            return self._battery()
        if _SCREENSHOT_RE.search(t):
            return self._screenshot()
        m = _OPEN_APP_RE.search(t)
        if m:
            return self._open_app(m.group(1).strip(" .!"))

        return None

    def _pair(self, t):
        ips = _IP_PORT_RE.findall(t)
        codigo_m = _CODE_RE.search(t)
        if not ips or not ips[0][1] or not codigo_m:
            return Answer(
                "Pra parear, me diga o IP:porta de pareamento e o código de 6 dígitos que "
                "aparecem em Opções do desenvolvedor > Depuração sem fio > Parear dispositivo "
                "com código, no celular. Ex.: 'pareia o celular 192.168.0.10:39451 482913'.",
                Confidence.GUESS,
            )
        ip, porta = ips[0]
        try:
            saida = adb.pair(ip, int(porta), codigo_m.group(1))
        except Exception as e:
            return Answer(f"Falha ao parear: {e}", Confidence.GUESS)
        ok = "successfully paired" in saida.lower()
        return Answer(saida or "Pareado.", Confidence.CONFIRMED if ok else Confidence.GUESS)

    def _connect(self, t):
        ips = _IP_PORT_RE.findall(t)
        if not ips:
            return Answer(
                "Preciso do IP do celular pra conectar. Ex.: 'conecta no celular 192.168.0.10:37451' "
                "(a porta aparece na tela de Depuração sem fio e muda toda vez que ela é religada).",
                Confidence.GUESS,
            )
        ip, porta = ips[0]
        porta = int(porta) if porta else 5555
        try:
            saida = adb.connect(ip, porta)
        except Exception as e:
            return Answer(f"Falha ao conectar: {e}", Confidence.GUESS)
        ok = "connected" in saida.lower()
        return Answer(saida or "Conectado.", Confidence.CONFIRMED if ok else Confidence.GUESS)

    def _disconnect(self):
        try:
            saida = adb.disconnect()
        except Exception as e:
            return Answer(f"Falha ao desconectar: {e}", Confidence.GUESS)
        return Answer(saida or "Desconectado.", Confidence.CONFIRMED)

    def _list(self):
        try:
            dispositivos = adb.list_devices()
        except Exception as e:
            return Answer(f"Falha ao listar dispositivos: {e}", Confidence.GUESS)
        if not dispositivos:
            return Answer(
                "Nenhum celular conectado por ADB agora. Diga 'pareia o celular <ip>:<porta> "
                "<código>' pra conectar pela primeira vez.",
                Confidence.CONFIRMED,
            )
        return Answer("Conectado(s) por ADB: " + ", ".join(dispositivos), Confidence.CONFIRMED)

    def _open_app(self, nome):
        if not (adb.available() and adb.list_devices()):
            return Answer(_SEM_ADB, Confidence.GUESS)
        try:
            pacote = adb.open_app(nome)
            return Answer(f'Abri "{nome}" no celular ({pacote}).', Confidence.CONFIRMED)
        except Exception as e:
            return Answer(str(e), Confidence.GUESS)

    def _nivel_bateria(self):
        """(nivel, carregando) via ADB, ou (None, None) sem dispositivo conectado --
        compartilhado por `_battery()` e o monitoramento em segundo plano."""
        if not (adb.available() and adb.list_devices()):
            return None, None
        try:
            info = adb.battery_level()
            return info["nivel_percentual"], info["carregando"]
        except Exception:
            return None, None

    def _battery(self):
        nivel, carregando = self._nivel_bateria()
        if nivel is None:
            return Answer(_SEM_ADB, Confidence.GUESS)
        status = "carregando" if carregando else "na bateria"
        return Answer(f"O celular está com {nivel}% de bateria ({status}).", Confidence.CONFIRMED)

    def _screenshot(self):
        if not adb.available() or not adb.list_devices():
            return Answer(_SEM_ADB, Confidence.GUESS)
        pasta = os.path.join("data", "screenshots")
        os.makedirs(pasta, exist_ok=True)
        nome = f"celular_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        caminho = os.path.join(pasta, nome)
        try:
            adb.screenshot(caminho)
        except Exception as e:
            return Answer(f"Falha ao capturar a tela do celular: {e}", Confidence.GUESS)
        return Answer(f"Print do celular salvo em {caminho}.", Confidence.CONFIRMED)

    def _monitorar_bateria(self, context):
        user_id = context["user_id"]
        routine_name = f"bateria_celular_{user_id}"
        estado = {"ja_avisado": False}

        def _tick():
            nivel, carregando = self._nivel_bateria()
            if nivel is None:
                return
            if nivel <= _LIMIAR_BATERIA_BAIXA and not carregando and not estado["ja_avisado"]:
                estado["ja_avisado"] = True
                notify("Jarvis", f"A bateria do seu celular está em {nivel}% -- considere carregar.")
                registrar("bateria_celular_baixa", f"{nivel}%")
            elif nivel > _LIMIAR_BATERIA_BAIXA + 10:
                # Só reseta o aviso depois de subir um pouco além do limiar,
                # pra não ficar oscilando aviso/sem-aviso perto do limiar.
                estado["ja_avisado"] = False

        tasks.schedule_recurring(routine_name, _INTERVALO_MONITOR_BATERIA, _tick)
        return Answer(
            f"Combinado, vou checar a bateria do celular a cada {_INTERVALO_MONITOR_BATERIA // 60} "
            f"minutos e te aviso sozinho se ela cair a {_LIMIAR_BATERIA_BAIXA}% ou menos sem estar "
            'carregando. Diga "para de monitorar a bateria" quando quiser parar.',
            Confidence.CONFIRMED,
        )

    def _parar_monitorar_bateria(self, context):
        user_id = context["user_id"]
        routine_name = f"bateria_celular_{user_id}"
        if tasks.cancel_routine(routine_name):
            return Answer("Ok, parei de monitorar a bateria do celular.", Confidence.CONFIRMED)
        return Answer("Eu não estava monitorando a bateria do celular.", Confidence.CONFIRMED)
