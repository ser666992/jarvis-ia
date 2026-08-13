"""
voz/tts.py
============
Síntese de voz (texto -> fala). Usa `pyttsx3` (offline: SAPI5 no
Windows, NSSpeechSynthesizer no macOS, espeak no Linux) como motor
padrão -- nenhuma API externa envolvida.

Velocidade (`rate`, unidade "palavras por minuto" no estilo pyttsx3):
se não passada explicitamente, vem de `config.json` ->
`voz.velocidade_fala` (205 por padrão -- mais rápido que o default do
pyttsx3, ~175-200). Ajustável em tempo real por comando de chat
("fala mais rápido"/"fala mais devagar"/"velocidade normal da fala",
ver plugins/system_control.py).

Voz "robótica" (opcional, `robotic=True` ou config
`personalidade.voz_robotica`): no Windows, fala via SAPI5 direto
(`win32com`, parte do `pyttsx3[SAPI5]`/`pywin32` já instalado junto),
usando as tags de prosódia XML nativas da própria API (`<pitch>`,
`<rate>`) pra baixar o tom e deixar a fala mais grave e mecânica --
é um recurso padrão de engenharia de voz do Windows, não uma
imitação/clone de nenhuma voz específica de terceiros. Fora do Windows
(ou sem `pywin32`), cai para só reduzir a velocidade via `pyttsx3`,
sem controle de tom (SAPI5 é a única API aqui com esse recurso pronto
sem dependência nova).

Tom da voz robótica (`personalidade.tom_voz_robotica`, -9 por padrão
numa escala de -10 a 10 do próprio SAPI5): quando `robotic=True`,
também prefere uma voz MASCULINA entre as instaladas no mesmo idioma
(`_escolher_voz`) -- tom grave numa voz grave de base soa mais
consistente que o mesmo tom aplicado a uma voz aguda. Continua sendo
só seleção entre vozes JÁ instaladas no Windows (nenhuma delas é
clonada nem imita ninguém específico) -- se não houver nenhuma voz
masculina no idioma pedido, usa a que houver.

Desligada por padrão (`personalidade.voz_robotica`/`efeito_ultron`,
`false`): o Jarvis fala com a voz normal do sistema. O modo grave/
processado abaixo continua disponível como opção (liga com
"voz robótica"/"personalidade ultron" no chat), pra quem quiser um
tom mais "de máquina" -- mas isso é sempre efeito de áudio sobre a
MESMA voz do sistema, nunca clonagem da voz de nenhum terceiro
(real ou de ficção).

Escolha manual de voz (`voz.voz_tts_id`, vazio por padrão): "lista as
vozes"/"usa a voz ..." (plugins/escolher_voz.py) deixa a pessoa
escolher entre as vozes JÁ instaladas no sistema -- quando configurado,
tem prioridade sobre a heurística automática de idioma/gênero
(`_escolher_voz()`) nos três motores (pyttsx3, SAPI direto, DSP). Só
seleção entre vozes do próprio Windows, nunca clonagem de terceiros.

Barge-in (interromper o Jarvis falando): `speak(texto, verificar_interromper=callback)`
aceita um `callback` opcional, checado periodicamente ENQUANTO fala --
se retornar True, a fala para imediatamente (`interromper()` também
pode ser chamado de outra thread a qualquer momento). Implementado nos
três motores (pyttsx3, prosódia SAPI, DSP/winsound): nenhum deles tem
uma forma nativa de "pausar e checar" no meio de uma chamada síncrona
só, então cada um usa a tática que sua própria API permite -- pyttsx3
roda `runAndWait()` numa thread e um supervisor chama `.stop()`; SAPI
fala em modo assíncrono (`SVSFlagsAsync`) e um loop de espera curta
consulta o callback, purgando com `Speak("", SVSFPurgeBeforeSpeak)` se
precisar parar; o WAV renderizado (efeito DSP) toca via
`winsound.PlaySound(..., SND_ASYNC)` com o mesmo esquema, purgando com
`PlaySound(None, SND_PURGE)`. Quem decide QUANDO interromper (ex.:
detectar volume alto no microfone enquanto fala) fica fora daqui --
ver voz/loop.py e gui/app.py.
"""

import sys
import threading
import time
import xml.sax.saxutils as saxutils

from logs.logger import get_logger

log = get_logger("voz")

try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

try:
    import win32com.client
    HAS_SAPI_COM = sys.platform == "win32"
except ImportError:
    HAS_SAPI_COM = False

try:
    import numpy as _np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

_SVSFIsXML = 32  # flag do SAPI5 indicando que o texto passado é XML de prosódia, não texto puro
_SVSFlagsAsync = 1  # fala em segundo plano, Speak() retorna na hora -- necessário pra poder interromper
_SVSFPurgeBeforeSpeak = 2  # ao falar "" com essa flag, para/descarta qualquer fala assíncrona em andamento
_SSFMCreateForWrite = 3  # modo do SAPI.SpFileStream pra escrever um WAV
_RATE_PADRAO = 205
_PITCH_ROBOTICO_PADRAO = -9
_PASSO_POLL_SEGUNDOS = 0.05  # intervalo de checagem do callback de interrupção, nos 3 motores


def _rate_para_sapi(rate: int) -> int:
    """Converte "palavras por minuto" (convenção pyttsx3) pra escala
    do SAPI5 (-10 a 10, 0 = ~180ppm) -- aproximação linear (cada
    unidade de Rate muda a velocidade em ~12ppm), suficiente pra dar
    a mesma sensação de "mais rápido/devagar" nas duas engines sem
    precisar calibrar cada voz instalada individualmente."""
    return max(-10, min(10, round((rate - 180) / 12)))


def _escolher_voz(voices, language_hint: str, preferir_masculina: bool):
    """Entre as vozes SAPI5 instaladas, escolhe a que bate com o idioma
    pedido -- e, se `preferir_masculina`, a mais grave/masculina entre
    essas (via GetAttribute("Gender"), quando o driver da voz expõe
    esse atributo; nem todo instalador de voz preenche isso, daí o
    try/except). Retorna None se nenhuma voz bater com o idioma --
    nesse caso quem chama não deve mexer em `.Voice`, deixando o
    default do próprio SAPI."""
    candidatas = [v for v in voices if language_hint.lower() in v.GetDescription().lower()]
    if not candidatas:
        return None
    if preferir_masculina:
        for v in candidatas:
            try:
                if v.GetAttribute("Gender").lower() == "male":
                    return v
            except Exception:
                continue
    return candidatas[0]


class TextToSpeech:
    def __init__(self, rate: int = None, voice_language_hint: str = "pt", robotic: bool = False, pitch: int = None):
        self._engine = None
        self._sapi = None
        if rate is None:
            from config.settings import get_settings
            rate = int(get_settings().get("voz.velocidade_fala", _RATE_PADRAO))
        if pitch is None:
            from config.settings import get_settings
            pitch = int(get_settings().get("personalidade.tom_voz_robotica", _PITCH_ROBOTICO_PADRAO))
        self.rate = rate
        self.pitch = max(-10, min(10, pitch))
        self.voice_language_hint = voice_language_hint
        self.robotic = robotic

    def available(self) -> bool:
        return HAS_PYTTSX3 or HAS_SAPI_COM

    def listar_vozes(self) -> list:
        """Lista as vozes de TTS instaladas no sistema (`{"id", "nome"}`
        cada) -- usado por "lista as vozes"/"muda a voz pra ..."
        (plugins/escolher_voz.py) pra deixar a pessoa escolher entre as
        JÁ instaladas no Windows (nenhuma delas é clonada/imita
        ninguém). Prefere SAPI5 (Windows -- `GetDescription()` já traz
        nome+idioma legíveis); sem SAPI, cai pro pyttsx3 (menos
        detalhado, mas funciona em qualquer plataforma)."""
        vozes = []
        if HAS_SAPI_COM:
            try:
                sapi = win32com.client.Dispatch("SAPI.SpVoice")
                for v in sapi.GetVoices():
                    vozes.append({"id": v.Id, "nome": v.GetDescription()})
                return vozes
            except Exception as e:
                log.warning("não consegui listar vozes via SAPI5: %s", e)
        if HAS_PYTTSX3:
            try:
                engine = pyttsx3.init()
                for v in engine.getProperty("voices"):
                    vozes.append({"id": v.id, "nome": v.name})
            except Exception as e:
                log.warning("não consegui listar vozes via pyttsx3: %s", e)
        return vozes

    @staticmethod
    def _voz_escolhida_manualmente() -> str:
        from config.settings import get_settings
        return get_settings().get("voz.voz_tts_id", "") or ""

    def _ensure_engine(self):
        if self._engine is not None:
            return
        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", self.rate)
        voz_id = self._voz_escolhida_manualmente()
        if voz_id:
            self._engine.setProperty("voice", voz_id)
            return
        for voice in self._engine.getProperty("voices"):
            if self.voice_language_hint.lower() in (voice.id + voice.name).lower():
                self._engine.setProperty("voice", voice.id)
                break

    def _ensure_sapi(self):
        if self._sapi is not None:
            return
        self._sapi = win32com.client.Dispatch("SAPI.SpVoice")
        self._sapi.Rate = _rate_para_sapi(self.rate)
        voz = self._resolver_voz_configurada(self._sapi.GetVoices())
        if voz is None:
            voz = _escolher_voz(self._sapi.GetVoices(), self.voice_language_hint, preferir_masculina=self.robotic)
        if voz is not None:
            self._sapi.Voice = voz

    def _resolver_voz_configurada(self, voices):
        """Se a pessoa escolheu uma voz específica ("usa a voz ...",
        ver plugins/escolher_voz.py), essa escolha tem prioridade sobre
        a heurística de idioma/gênero de `_escolher_voz()`. Retorna
        None se não há escolha salva (ou se o id salvo não bate com
        nenhuma voz mais instalada), pra quem chama cair no
        comportamento de sempre."""
        voz_id = self._voz_escolhida_manualmente()
        if not voz_id:
            return None
        for v in voices:
            if v.Id == voz_id:
                return v
        return None

    def speak(self, text: str, verificar_interromper=None):
        """`verificar_interromper` (opcional): callback sem argumentos,
        checado periodicamente enquanto fala -- retornar True para a
        fala imediatamente (barge-in). Ver docstring do módulo."""
        if self.robotic and HAS_SAPI_COM:
            try:
                self._speak_robotic(text, verificar_interromper)
                return
            except Exception as e:
                log.warning("voz robótica (SAPI5 XML) falhou, caindo para voz normal: %s", e)
        if HAS_PYTTSX3:
            self._ensure_engine()
            self._engine.say(text)
            self._falar_pyttsx3_interrompivel(verificar_interromper)
            return
        if HAS_SAPI_COM:
            # Sem pyttsx3, mas com SAPI5 disponível (Windows) -- fala
            # texto puro, sem a prosódia XML da voz robótica. Sem isso,
            # `available()` prometia funcionar (checa HAS_SAPI_COM) mas
            # `speak()` sempre levantava RuntimeError nesse cenário.
            self._ensure_sapi()
            self._falar_sapi_interrompivel(text, is_xml=False, verificar_interromper=verificar_interromper)
            return
        raise RuntimeError("Instale 'pyttsx3' para o Jarvis falar (pip install pyttsx3).")

    def interromper(self):
        """Para a fala em andamento AGORA, se houver -- seguro de
        chamar de OUTRA thread (ex.: monitor de barge-in, ver
        voz/loop.py) a qualquer momento, inclusive se nada estiver
        tocando (vira no-op). Tenta os três motores possíveis; cada um
        ignora silenciosamente se não for o que está ativo no momento."""
        try:
            if self._engine is not None:
                self._engine.stop()
        except Exception:
            pass
        try:
            if self._sapi is not None:
                self._sapi.Speak("", _SVSFPurgeBeforeSpeak)
        except Exception:
            pass
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

    def _falar_pyttsx3_interrompivel(self, verificar_interromper):
        """`engine.runAndWait()` bloqueia sem chance de checar nada no
        meio -- roda numa thread separada, e ESTA thread (a que chamou
        speak()) faz o polling, chamando engine.stop() (thread-safe o
        bastante no driver SAPI5 usado aqui no Windows) se for preciso
        interromper. Sem `verificar_interromper`, comportamento
        idêntico a antes (só runAndWait direto)."""
        if verificar_interromper is None:
            self._engine.runAndWait()
            return
        t = threading.Thread(target=self._engine.runAndWait, daemon=True)
        t.start()
        while t.is_alive():
            if verificar_interromper():
                try:
                    self._engine.stop()
                except Exception:
                    pass
                break
            t.join(timeout=_PASSO_POLL_SEGUNDOS)

    def _falar_sapi_interrompivel(self, texto_ou_xml: str, is_xml: bool, verificar_interromper):
        """Fala via SAPI5 em modo ASSÍNCRONO (`SVSFlagsAsync`) -- sem
        isso, `Speak()` bloqueia até terminar e não haveria como checar
        `verificar_interromper` no meio. Sem o callback, ainda usa o
        modo síncrono de sempre (mais simples, sem thread nem polling
        à toa quando ninguém pediu pra poder interromper)."""
        flags = (_SVSFIsXML if is_xml else 0)
        if verificar_interromper is None:
            self._sapi.Speak(texto_ou_xml, flags)
            return
        self._sapi.Speak(texto_ou_xml, flags | _SVSFlagsAsync)
        while True:
            # WaitUntilDone(ms) devolve True se terminou dentro do prazo --
            # esperas curtas repetidas dão chance de checar o callback
            # sem atraso perceptível na hora de interromper.
            terminou = self._sapi.WaitUntilDone(int(_PASSO_POLL_SEGUNDOS * 1000))
            if terminou:
                return
            if verificar_interromper():
                self._sapi.Speak("", _SVSFPurgeBeforeSpeak)
                return

    def _speak_robotic(self, text: str, verificar_interromper=None):
        # Efeito de voz grave/processada (DSP, desligado por padrão):
        # renderiza a fala grave num WAV e pós-processa o áudio (camada
        # detunada = "coro de vozes", leve ring-mod = borda metálica,
        # reverb curto = espaço frio, soft-clip = peso) antes de tocar.
        # NÃO é clonagem da voz de ninguém -- é a MESMA voz do sistema
        # com efeitos de áudio por cima. Precisa de numpy + SAPI
        # (Windows); sem isso, cai pra prosódia XML simples abaixo.
        if self._efeito_neutron_disponivel():
            try:
                self._speak_neutron_dsp(text, verificar_interromper)
                return
            except Exception as e:
                log.warning("efeito de voz processada (DSP) falhou, usando prosódia simples: %s", e)

        # Fallback: prosódia SAPI5 direta (pitch absoluto de -10 a 10,
        # 0 = padrão da voz), sem os efeitos de áudio. Combinado com
        # _ensure_sapi() preferindo uma voz masculina, já dá um tom
        # grave/mecânico -- só sem a camada/reverb do modo DSP.
        self._ensure_sapi()
        texto_seguro = saxutils.escape(text)
        xml = f'<pitch absmiddle="{self.pitch}"/><rate absspeed="{_rate_para_sapi(self.rate)}"/>{texto_seguro}'
        self._falar_sapi_interrompivel(xml, is_xml=True, verificar_interromper=verificar_interromper)

    # ---------- Perfil Neutron (processamento de áudio) ----------

    def _efeito_neutron_ligado(self) -> bool:
        """Perfil próprio do Neutron, sem copiar a voz de ninguém.

        A chave antiga permanece como fallback apenas para configurações
        existentes; instalações novas usam ``efeito_neutron``.
        """
        from config.settings import get_settings
        settings = get_settings()
        return bool(settings.get("personalidade.efeito_neutron", settings.get("personalidade.efeito_ultron", False)))

    def _intensidade_neutron(self) -> float:
        from config.settings import get_settings
        try:
            settings = get_settings()
            v = float(settings.get("personalidade.intensidade_neutron", settings.get("personalidade.intensidade_ultron", 0.42)))
        except (TypeError, ValueError):
            v = 0.42
        return max(0.0, min(1.0, v))

    def _efeito_neutron_disponivel(self) -> bool:
        return sys.platform == "win32" and HAS_SAPI_COM and HAS_NUMPY and self._efeito_neutron_ligado()

    def _efeito_ultron_ligado(self) -> bool:
        from config.settings import get_settings
        return bool(get_settings().get("personalidade.efeito_ultron", False))

    def _intensidade_ultron(self) -> float:
        from config.settings import get_settings
        try:
            v = float(get_settings().get("personalidade.intensidade_ultron", 0.7))
        except (TypeError, ValueError):
            v = 0.7
        return max(0.0, min(1.0, v))

    def _efeito_ultron_disponivel(self) -> bool:
        return sys.platform == "win32" and HAS_SAPI_COM and HAS_NUMPY and self._efeito_ultron_ligado()

    def _speak_neutron_dsp(self, text: str, verificar_interromper=None):
        import os
        import tempfile
        import winsound

        # Reserva os caminhos de forma atômica. ``mktemp`` poderia criar
        # uma janela de corrida entre escolher o nome e o SAPI escrever o
        # WAV, causando falhas intermitentes (ou pior, sobrescrita) em
        # diretórios temporários compartilhados.
        fd_bruto, bruto = tempfile.mkstemp(suffix="_neutron_raw.wav")
        fd_processado, processado = tempfile.mkstemp(suffix="_neutron_processed.wav")
        os.close(fd_bruto)
        os.close(fd_processado)
        try:
            samplerate, dados = self._render_sapi_wav(text, bruto)
            y = self._efeitos_neutron(dados, samplerate)
            self._escrever_wav(processado, y, samplerate)
            if verificar_interromper is None:
                # SND_FILENAME síncrono de sempre -- continua bloqueando até
                # terminar, pra encaixar na fila de fala do
                # gui/app.py:_SpeakWorker, que espera uma fala terminar antes
                # de começar a próxima.
                winsound.PlaySound(processado, winsound.SND_FILENAME)
            else:
                # SND_ASYNC: toca em segundo plano e retorna na hora, o que
                # permite checar verificar_interromper enquanto toca -- o
                # loop abaixo ainda BLOQUEIA pelo tempo certo (ou até
                # interromper), então de fora o comportamento de speak()
                # continua sendo bloqueante como sempre foi.
                winsound.PlaySound(processado, winsound.SND_FILENAME | winsound.SND_ASYNC)
                duracao = len(y) / float(samplerate)
                decorrido = 0.0
                while decorrido < duracao:
                    if verificar_interromper():
                        winsound.PlaySound(None, winsound.SND_PURGE)
                        break
                    time.sleep(_PASSO_POLL_SEGUNDOS)
                    decorrido += _PASSO_POLL_SEGUNDOS
        finally:
            for caminho in (bruto, processado):
                try:
                    os.remove(caminho)
                except OSError:
                    pass

    def _render_sapi_wav(self, text: str, caminho: str):
        """Sintetiza a fala (com o pitch grave) num arquivo WAV via
        SAPI SpFileStream, em vez de tocar direto -- pra poder
        pós-processar. Retorna (samplerate, sinal float32 mono em -1..1).
        Usa uma SpVoice PRÓPRIA (não a self._sapi compartilhada) pra não
        deixar a saída redirecionada pro arquivo por engano depois."""
        import wave

        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(caminho, _SSFMCreateForWrite)
        try:
            voz = win32com.client.Dispatch("SAPI.SpVoice")
            escolhida = self._resolver_voz_configurada(voz.GetVoices())
            if escolhida is None:
                escolhida = _escolher_voz(voz.GetVoices(), self.voice_language_hint, preferir_masculina=True)
            if escolhida is not None:
                voz.Voice = escolhida
            # O Neutron usa uma voz firme e limpa, sem forçar um grave
            # extremo. A textura eletrônica vem do processamento próprio
            # abaixo, preservando inteligibilidade em português.
            voz.Rate = _rate_para_sapi(self.rate)
            pitch_neutron = max(-6, min(self.pitch, 0))
            voz.AudioOutputStream = stream
            texto_seguro = saxutils.escape(text)
            xml = f'<pitch absmiddle="{pitch_neutron}"/>{texto_seguro}'
            voz.Speak(xml, _SVSFIsXML)
        finally:
            stream.Close()

        with wave.open(caminho, "rb") as w:
            samplerate = w.getframerate()
            canais = w.getnchannels()
            largura = w.getsampwidth()
            cru = w.readframes(w.getnframes())
        if largura != 2:
            raise RuntimeError(f"WAV do SAPI não veio em 16-bit (sampwidth={largura}).")
        sinal = _np.frombuffer(cru, dtype=_np.int16).astype(_np.float32) / 32768.0
        if canais == 2:
            sinal = sinal.reshape(-1, 2).mean(axis=1)
        return samplerate, sinal

    @staticmethod
    def _suavizar(sig, largura: int):
        """Passa-baixa simples via média móvel ponderada (janela de
        Hann) -- usado tanto pra reforçar graves (janela larga) quanto
        pra tirar a aspereza dos agudos (janela estreita). Sem recursão/
        IIR, então não tem risco de instabilidade nem artefato de fase."""
        largura = max(2, int(largura))
        k = _np.hanning(largura)
        soma = k.sum()
        if soma <= 0:
            return sig
        return _np.convolve(sig, (k / soma).astype(_np.float32), mode="same").astype(_np.float32)

    def _efeitos_neutron(self, x, samplerate: int):
        """Cadeia original do Neutron: firme, clara, espacial e levemente
        eletrônica, sem tentar copiar qualquer voz ou personagem.
        Intensidade regulável por ``personalidade.intensidade_neutron``
        (0..1). Mantém a fala inteligível de propósito.

        Ordem pensada como uma cadeia de estúdio: doblagem/coro ->
        reforço de graves (corpo) -> suavização de agudos (tira o
        chiado) -> sheen metálico sutil -> saturação (peso) -> reverb
        cinematográfico -> normalização."""
        intens = self._intensidade_ultron()
        n = len(x)
        if n == 0 or intens <= 0:
            return x
        indices = _np.arange(n)
        t = indices / float(samplerate)

        # 1) DOBLAGEM/CORO -- o "mais-que-humano". Duas cópias levemente
        #    detunadas (±10 cents, sutil pra não soar desafinado) somadas
        #    por baixo, dão largura e a sensação de "várias vozes numa".
        def _detune(sig, cents):
            r = 2 ** (cents / 1200.0)
            origem = _np.clip(indices * r, 0, n - 1)
            return _np.interp(origem, indices, sig).astype(_np.float32)

        coro = 0.4 * intens * (_detune(x, 10.0) + _detune(x, -10.0))
        y = x + coro

        # 2) CORPO/GRAVES -- reforça a região grave (uma passa-baixa larga
        #    somada de volta) pra dar aquele peito ressonante de IA
        #    gigante, em vez de uma voz fininha de sintetizador.
        graves = self._suavizar(y, samplerate * 0.006)  # ~ até ~150-250 Hz
        y = y + graves * (0.7 * intens)

        # 3) TIRA A ASPEREZA -- uma passa-baixa MUITO estreita misturada
        #    de leve arredonda os agudos sibilantes/metálicos ("ss", "ch")
        #    que soam artificiais no TTS, deixando a voz mais "analógica".
        y = y * (1 - 0.25 * intens) + self._suavizar(y, samplerate * 0.0006) * (0.25 * intens)

        # 4) SHEEN METÁLICO sutil -- ring-mod bem baixo (portadora grave,
        #    ~48 Hz) dá um brilho de "máquina" sem virar Dalek buzzento.
        ring = y * _np.sin(2 * _np.pi * 48.0 * t).astype(_np.float32)
        mix_ring = 0.12 * intens
        y = y * (1 - mix_ring) + ring * mix_ring

        # 5) SATURAÇÃO -- soft-clip dá peso/ameaça e "cola" as camadas,
        #    sem estourar (tanh limita naturalmente).
        y = _np.tanh(y * (1.0 + 1.4 * intens))

        # 6) REVERB CINEMATOGRÁFICO -- mais taps que antes, decaindo mais
        #    longo, pra um espaço frio e grande (sala de servidores) em
        #    vez de um eco curtinho de quarto.
        cauda = _np.zeros_like(y)
        for atraso_ms, ganho in ((37, 0.30), (73, 0.24), (115, 0.18), (170, 0.12), (240, 0.07)):
            d = int(samplerate * atraso_ms / 1000.0)
            if 0 < d < n:
                eco = _np.zeros_like(y)
                eco[d:] = y[:-d]
                cauda = cauda + eco * ganho
        y = y + cauda * intens

        pico = float(_np.max(_np.abs(y))) or 1.0
        return (y / pico) * 0.95

    def _escrever_wav(self, caminho: str, y, samplerate: int):
        import wave

        pcm = (_np.clip(y, -1.0, 1.0) * 32767).astype(_np.int16).tobytes()
        with wave.open(caminho, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(samplerate)
            w.writeframes(pcm)
