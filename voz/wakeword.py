"""
voz/wakeword.py
==================
Detecção de palavra-chave de ativação ("Jarvis"). Duas estratégias:

  1. `pvporcupine` (Picovoice), se instalado E com uma chave de acesso
     configurada (`voz.picovoice_access_key`, grátis em
     console.picovoice.ai) -- wake word de baixíssima latência, processa
     o áudio em tempo real (sem transcrever nada), roda sobre um stream
     contínuo via `sounddevice`. "jarvis" já é uma palavra-chave nativa
     do Porcupine, não precisa de arquivo `.ppn` customizado.
  2. Fallback simples (sem chave configurada, ou sem `pvporcupine`):
     transcreve um trecho curto de áudio (via `voz.stt.SpeechToText`) e
     verifica se a palavra-chave aparece no texto. Menos preciso e mais
     lento que o Porcupine, mas funciona com qualquer backend de STT já
     instalado, sem dependência/chave extra.

IMPORTANTE (bug corrigido): antes, `backend()` reportava "porcupine"
como disponível só por `pvporcupine` estar instalado, mesmo sem chave
de acesso configurada -- e como o backend Porcupine nunca foi
implementado de verdade, `wait_for_wakeword()`/`listen_for_command()`
sempre levantavam `NotImplementedError` nesse caso, quebrando o modo de
voz inteiro pra quem tivesse a lib instalada. Agora `backend()` só
escolhe "porcupine" quando há uma chave configurada, e o backend em si
foi implementado de verdade (stream de áudio + `porcupine.process()`).

Múltiplas palavras de ativação: `keywords=["jarvis", "ark"]` aceita
qualquer uma delas (`keyword` singular continua aceito, por
compatibilidade, e é somado à lista). No Porcupine, isso é suporte
nativo (`pvporcupine.create(keywords=[...])` já aceita várias, e
`process()` retorna o índice de qual delas foi ouvida). No fallback
via STT, verifica se QUALQUER uma aparece no texto transcrito.
Limitação honesta: o Porcupine só reconhece palavras da sua lista
pré-treinada (ex. "jarvis", "computer", "alexa", "friday"...) -- uma
palavra customizada fora dessa lista (ex. "ARK") faz `pvporcupine.create()`
falhar para o conjunto INTEIRO, e o detector cai pro fallback via STT
para todas as palavras daquela sessão (não há suporte a treinar/usar
um arquivo `.ppn` customizado aqui).
"""

from config.settings import get_settings
from logs.logger import get_logger

log = get_logger("voz")

try:
    import pvporcupine
    HAS_PORCUPINE = True
except ImportError:
    HAS_PORCUPINE = False

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False


class WakeWordDetector:
    def __init__(self, keyword: str = None, keywords: list = None, stt=None, access_key: str = None):
        """`keywords` aceita uma ou mais palavras de ativação -- qualquer
        uma delas ativa. `keyword` (singular) continua aceito por
        compatibilidade e é somado à lista (sem duplicar)."""
        todas = list(keywords) if keywords else []
        if keyword:
            todas.append(keyword)
        self.keywords = []
        for k in todas:
            k = (k or "").strip().lower()
            if k and k not in self.keywords:
                self.keywords.append(k)
        if not self.keywords:
            self.keywords = ["jarvis"]
        self.keyword = self.keywords[0]  # compat: quem já lia .keyword (singular) continua funcionando
        self.stt = stt
        self.access_key = access_key if access_key is not None else get_settings().get("voz.picovoice_access_key", "")
        self._porcupine_indisponivel = False  # true se já tentamos criar e falhou (ex.: palavra não suportada)

    def backend(self) -> str:
        if HAS_PORCUPINE and HAS_SOUNDDEVICE and self.access_key and not self._porcupine_indisponivel:
            return "porcupine"
        if self.stt and self.stt.available():
            return "stt_fallback"
        return ""

    def available(self) -> bool:
        return bool(self.backend())

    def _aguardar_porcupine(self, timeout_seconds: float = None) -> bool:
        """Bloqueia processando o microfone em tempo real até detectar
        a palavra-chave, ou até `timeout_seconds` se passar (None =
        espera indefinidamente). Retorna True se detectou."""
        import queue
        import struct
        import time

        try:
            porcupine = pvporcupine.create(access_key=self.access_key, keywords=self.keywords)
        except Exception as e:
            # Chave inválida, ou alguma das palavras escolhidas não está
            # na lista nativa do Porcupine -- não adianta tentar de novo
            # até a configuração mudar, então desiste do backend Porcupine
            # pro resto da sessão e deixa o fallback via STT assumir.
            self._porcupine_indisponivel = True
            log.warning("Porcupine indisponível (%s) -- usando fallback via STT.", e)
            return False

        fila = queue.Queue()

        def _callback(indata, frames, time_info, status):
            fila.put(bytes(indata))

        detectado = False
        inicio = time.monotonic()
        try:
            with sd.RawInputStream(
                samplerate=porcupine.sample_rate, blocksize=porcupine.frame_length,
                dtype="int16", channels=1, callback=_callback,
            ):
                while True:
                    if timeout_seconds is not None and (time.monotonic() - inicio) > timeout_seconds:
                        break
                    try:
                        dados = fila.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    if len(dados) != porcupine.frame_length * 2:  # 2 bytes por amostra (int16)
                        continue
                    # struct.unpack (não memoryview/numpy) porque é o formato que o
                    # binding em ctypes do pvporcupine espera receber (mesmo padrão
                    # usado nos exemplos oficiais da Picovoice).
                    pcm = struct.unpack_from("%dh" % porcupine.frame_length, dados)
                    if porcupine.process(pcm) >= 0:
                        detectado = True
                        break
        finally:
            porcupine.delete()
        return detectado

    def wait_for_wakeword(self, timeout_check_seconds: float = 3.0) -> bool:
        """Bloqueia até detectar a palavra-chave (ou até o fim de uma
        janela de escuta, no fallback). Retorna True se detectou."""
        backend = self.backend()
        if backend == "stt_fallback":
            text = self.stt.listen_and_transcribe(duration_seconds=timeout_check_seconds).lower()
            return any(k in text for k in self.keywords)
        if backend == "porcupine":
            return self._aguardar_porcupine(timeout_seconds=timeout_check_seconds)
        raise RuntimeError("Nenhum backend de wake word disponível.")

    def listen_for_command(self, timeout_check_seconds: float = 4.0):
        """Escuta até ouvir a palavra-chave e retorna o comando.

        Retorna:
          - None: a palavra-chave não apareceu nessa janela de escuta
            (quem chama deve tentar de novo).
          - dict {"texto", "confiavel", "motivo"}: a palavra-chave
            apareceu. "texto" vem vazio (`confiavel=True`) se só a
            palavra-chave foi dita (quem chama deve ouvir de novo, sem
            a palavra-chave dessa vez); caso contrário é o comando
            dito, com a MESMA checagem de confiança de qualquer outra
            transcrição (`voz/stt.py:_avaliar_qualidade`, via
            `listen_and_transcribe_detalhado`) -- antes, o comando
            dito na mesma respiração que a palavra-chave ("jarvis, que
            horas são") ou logo depois dela era sempre tratado como
            confiável incondicionalmente, sem checar volume/duração,
            diferente de qualquer outro caminho de escuta (gap
            conhecido, fechado aqui: uma transcrição ruim nesse
            caminho específico ia direto pro Jarvis processar, em vez
            de pedir pra repetir como os outros caminhos já faziam).

        No fallback via STT, aceita tanto "jarvis, comando" numa
        respiração só (extrai o que vem depois da palavra-chave na
        mesma transcrição) quanto "jarvis" sozinho seguido de pausa.
        No Porcupine, a detecção é em áudio bruto (não transcrito),
        então ao detectar a palavra-chave já iniciamos uma escuta
        separada pelo comando em seguida -- mesmo padrão de "beep,
        depois fale" de assistentes de voz comuns.
        """
        backend = self.backend()
        if backend == "stt_fallback":
            resultado = self.stt.listen_and_transcribe_detalhado(duration_seconds=timeout_check_seconds)
            texto = resultado["texto"].strip()
            texto_low = texto.lower()
            idx, tamanho_achada = -1, 0
            for k in self.keywords:
                pos = texto_low.find(k)
                if pos != -1 and (idx == -1 or pos < idx):
                    idx, tamanho_achada = pos, len(k)
            if idx == -1:
                return None
            comando = texto[idx + tamanho_achada:].strip(" ,.!?-")
            return {"texto": comando, "confiavel": bool(resultado["confiavel"]), "motivo": resultado.get("motivo")}
        if backend == "porcupine":
            detectado = self._aguardar_porcupine(timeout_seconds=timeout_check_seconds)
            if not detectado:
                return None
            if not (self.stt and self.stt.available()):
                return {"texto": "", "confiavel": True, "motivo": None}
            resultado = self.stt.listen_and_transcribe_detalhado(duration_seconds=timeout_check_seconds)
            return {"texto": resultado["texto"].strip(), "confiavel": bool(resultado["confiavel"]), "motivo": resultado.get("motivo")}
        raise RuntimeError("Nenhum backend de wake word disponível.")
