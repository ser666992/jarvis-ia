"""
voz/stt.py
============
Reconhecimento de voz (fala -> texto). Tenta, em ordem de preferência
(offline primeiro):
  1. `vosk` (totalmente offline, modelos pequenos)
  2. `faster-whisper` (offline, mais pesado, mais preciso)
  3. `speech_recognition` (usa o reconhecedor gratuito do Google por
     padrão, que é uma API ONLINE -- só é usado se as opções offline
     acima não estiverem instaladas, e isso fica explícito no status)

Todos exigem capturar áudio do microfone via `sounddevice`. Sem essa
lib (ou sem microfone), `available()` retorna False.

Detecção de silêncio (melhoria): `vosk`/`faster-whisper` gravavam por
uma duração FIXA sempre (ex.: sempre esperava os 5 segundos inteiros,
mesmo se você falasse uma frase curta e parasse em 1s) -- agora
`_gravar_ate_silencio()` grava em streaming e para sozinho assim que
detecta silêncio depois de você falar (config
`voz.silencio_para_parar_segundos`, 0.6s por padrão -- resposta rápida,
tipo ChatGPT, sem esperar de mais pra reagir, mas sem ser tão agressivo
a ponto de cortar uma pausa natural no meio de uma frase mais longa --
ver `calibrar_microfone()` pra um valor calibrado na SUA fala, em vez
de um palpite genérico), com um teto de segurança
(`duracao_maxima_comando_segundos`, 20s por padrão) pra nunca ficar
preso gravando pra sempre. Esse limiar de silêncio (o que conta como
"parou de falar") é CALIBRADO no ruído de fundo real do ambiente a cada
gravação (não é mais um valor fixo) -- um valor fixo funcionava mal em
ambientes diferentes do que foi originalmente medido: microfone com
ganho alto ou cômodo com ruído de fundo real nunca "caía" abaixo do
limiar fixo, e a gravação sempre esperava o teto máximo inteiro (era a
causa raiz de "demora muito pra terminar"). Além disso, se você ainda
estiver falando ativamente bem na hora em que bateria o teto máximo, a
gravação ganha uma folga extra em vez de cortar sua frase no meio. `speech_recognition` já fazia isso nativamente
(`Recognizer.listen()`), por isso não precisou de mudança.

Endpointing mais esperto com `vosk` (melhoria): além do RMS calibrado
acima, `_listen_vosk()` alimenta um `KaldiRecognizer` "ao vivo" bloco a
bloco DURANTE a gravação (não só no final) -- `AcceptWaveform()` do
próprio vosk sinaliza sozinho quando o decodificador (informado pelo
MODELO acústico, não só amplitude crua) entende que a frase terminou,
o que costuma distinguir melhor uma respiração/ruído de boca de um
silêncio de verdade. Esse sinal vira um critério de parada ADICIONAL
(quem disparar primeiro, RMS ou reconhecimento, termina a gravação) --
nunca pior que antes, só mais uma chance de parar cedo com mais
confiança. O reconhecedor "ao vivo" é só pra decidir O MOMENTO de
parar; a transcrição final de verdade continua sendo feita depois,
numa passada limpa sobre o áudio já com redução de ruído aplicada (ver
`_listen_vosk`) -- não dá pra aproveitar o texto já reconhecido ao
vivo porque ele rodou sobre áudio ainda cru. `faster-whisper` não tem
um endpointer de streaming equivalente, então continua só no RMS.

Melhorias adicionais:
- **Redução de ruído** (opcional, `noisereduce`): aplicada no áudio
  gravado antes de transcrever, se a lib estiver instalada -- sem ela,
  transcreve o áudio bruto normalmente (degrada graciosamente).
- **Aviso de qualidade baixa**: `listen_and_transcribe_detalhado()`
  calcula se o trecho gravado tem volume/duração suficiente pra uma
  transcrição confiável, e avisa em vez de devolver um texto vazio/
  errado silenciosamente. `listen_and_transcribe()` continua existindo
  (compatibilidade com quem já chama), só devolve o texto puro.
- **Idioma automático**: com `faster-whisper` (único motor aqui que
  tem detecção de idioma de verdade embutida), `language="auto"`
  detecta sozinho em vez de assumir um idioma fixo. `vosk` e o
  fallback online continuam precisando de um idioma configurado --
  cada modelo do vosk já É de um idioma específico, não tem como
  "auto-detectar" sem carregar vários modelos ao mesmo tempo (custo
  alto demais pra valer a pena aqui).
- **Modelo de português configurável** (`voz.modelo_stt_tamanho`,
  "pequeno" por padrão): o vosk tem dois modelos de PT -- o "small"
  (~30MB, rápido, o padrão) e o "vosk-model-pt-fb" (~1.6GB, mais
  preciso em teoria). Testado aqui: o modelo grande (versão
  `vosk-model-pt-fb-v0.1.1-20220516_2113`) **falha ao carregar com a
  vosk 0.3.45 instalada** -- erro nativo reproduzido em dois downloads
  frescos independentes (`ConstArpaLm <LmStates> section reading
  failed`, no arquivo `rescore/G.carpa`), ou seja não é corrupção de
  rede, é incompatibilidade de formato entre esse modelo e essa versão
  da lib. `_carregar_modelo_vosk()` já trata isso com um fallback
  automático pro pequeno (o modo de voz nunca fica indisponível por
  causa disso), mas por causa da falha reprodutível o padrão voltou a
  ser `"pequeno"` -- manter `"grande"` como padrão só faria todo início
  de programa perder tempo baixando/tentando carregar 1.6GB pra falhar
  de novo. Quem quiser tentar o grande mesmo assim (ex. depois de uma
  atualização da lib `vosk` que resolva isso) pode configurar
  `"grande"` manualmente; a mitigação real pra transcrição ruim tipo
  "ora o amargo" segue sendo a calibração de microfone + o aviso de
  confiança baixa, não o tamanho do modelo.
"""

import importlib.util
import threading

from config.settings import get_settings
from logs.logger import get_logger

log = get_logger("voz")

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False

try:
    import vosk
    HAS_VOSK = True
except ImportError:
    HAS_VOSK = False

try:
    import speech_recognition as sr
    HAS_SPEECH_RECOGNITION = True
except ImportError:
    HAS_SPEECH_RECOGNITION = False

# faster-whisper e noisereduce são MUITO lentos de IMPORTAR de verdade
# (~15-20 SEGUNDOS cada, medido -- puxam ctranslate2/scipy por baixo),
# mesmo quando nem chegam a ser o motor usado (vosk, já instalado, é
# preferido e é rápido). Antes isso rodava aqui em cima, no import do
# módulo -- ou seja, TODA abertura do Ultron pagava ~35s de import
# parado antes até da tela aparecer (era a causa real de "o Ultron não
# abre": ele abria, só demorava demais sem dar nenhum sinal). Por isso
# só checamos se estão INSTALADOS (find_spec -- olha se o pacote existe
# sem executar o módulo, é rápido) aqui; o import de verdade só
# acontece dentro de _listen_whisper()/_reduzir_ruido(), na hora que
# forem genuinamente usados.
HAS_FASTER_WHISPER = importlib.util.find_spec("faster_whisper") is not None
HAS_NOISEREDUCE = importlib.util.find_spec("noisereduce") is not None

_RMS_MINIMO_CONFIAVEL = 300.0  # abaixo disso (escala int16), a fala captada foi baixa demais pra confiar
_SAMPLERATE_PADRAO = 16000
# Nome EXATO como aparece no índice online do vosk (confirmado contra
# vosk.MODEL_LIST_URL antes de usar aqui -- um nome que não bate faz
# Model.get_model_by_name() chamar sys.exit(1), então não é seguro
# arriscar um nome "quase certo"). ~1.6GB, bem mais preciso que o
# "small" (~30MB) que era usado antes -- ver docstring do módulo.
_VOSK_MODELO_PT_GRANDE = "vosk-model-pt-fb-v0.1.1-20220516_2113"


def _has_input_device() -> bool:
    """Verifica se o Windows/SO enxerga algum microfone de verdade --
    sem isso, `backend_disponivel()` reportaria as libs como
    disponíveis (elas só checam se o pacote foi importado), e o erro
    real (PortAudioError opaco) só apareceria depois, no meio da
    conversa, ao tentar gravar. Falhar cedo aqui dá uma mensagem clara
    ("verifique o microfone") em vez de um traceback confuso."""
    if not HAS_SOUNDDEVICE:
        return True  # sem sounddevice não há como checar por aqui -- deixa o erro real aparecer na hora de gravar
    try:
        sd.query_devices(kind="input")
        return True
    except Exception:
        return False


class SpeechToText:
    def __init__(self, language: str = "pt-BR", engine: str = "auto"):
        self.language = language
        self.engine = engine
        self._vosk_model = None
        self._whisper_model = None

    def backend_disponivel(self) -> str:
        if not _has_input_device():
            return ""
        if self.engine in ("auto", "vosk") and HAS_VOSK and HAS_SOUNDDEVICE:
            return "vosk"
        if self.engine in ("auto", "whisper") and HAS_FASTER_WHISPER and HAS_SOUNDDEVICE:
            return "faster-whisper"
        if self.engine in ("auto", "google") and HAS_SPEECH_RECOGNITION:
            return "speech_recognition (online, Google)"
        return ""

    def available(self) -> bool:
        return bool(self.backend_disponivel())

    def calibrar_microfone(self, duracao_segundos: float = 7.0, samplerate: int = _SAMPLERATE_PADRAO) -> dict:
        """Grava por uma duração FIXA (sem parar cedo -- é um teste, não
        um comando de verdade) enquanto o usuário fala naturalmente, e
        analisa o áudio pra sugerir um `silencio_para_parar_segundos`
        calibrado na fala REAL dele -- em vez do palpite genérico (0.6s)
        que serve bem pra pouca gente e mal pra quem fala mais devagar ou
        com mais pausas no meio da frase.

        A ideia central: mede a MAIOR PAUSA INTERNA (silêncio ENTRE dois
        trechos falados, não a pausa final de "terminei de falar") ao
        longo da gravação -- uma frase como "quais animais... [pausa pra
        pensar] ...moram na amazônia" tem uma pausa no meio que NUNCA
        pode ser confundida com "a pessoa parou de falar", senão toda
        frase mais longa/pensada é cortada no meio (sintoma real
        reportado: "ele tá cortando minhas frases no meio"). A pausa
        FINAL (depois do último trecho falado) é descartada de propósito
        na medição -- incluí-la sempre dominaria e inflaria a
        recomendação sem necessidade.

        Também usa o mesmo `rms_max`/`ruido_ambiente_rms` medidos aqui
        pra sugerir uma `sensibilidade_barge_in_recomendada` (ver
        `BargeInMonitor`) -- a MARGEM entre o pico da sua voz e o chão
        de ruído do ambiente indica quão folgado o limiar de barge-in
        pode ser: margem pequena (voz mais baixa/quarto mais barulhento)
        pede um multiplicador menor (mais sensível, senão o barge-in
        nunca dispara pra essa pessoa); margem grande (voz forte/quarto
        silencioso) aguenta um multiplicador maior (menos sensível,
        menos chance de falso positivo com um ruído pequeno qualquer).

        Retorna {"ruido_ambiente_rms", "rms_max",
        "maior_pausa_interna_segundos", "silencio_recomendado_segundos",
        "sensibilidade_barge_in_recomendada", "qualidade", "aviso"} --
        "qualidade" é "boa"/"volume_baixo"/"ruido_alto", "aviso" tem uma
        dica em texto quando não for "boa" (None quando estiver tudo
        bem)."""
        if not HAS_SOUNDDEVICE:
            raise RuntimeError("Instale 'sounddevice' (requirements-voz.txt) pra eu conseguir testar o microfone.")
        import numpy as np

        bloco_seg = 0.03
        tamanho_bloco = max(1, int(samplerate * bloco_seg))
        n_calibracao = 8
        piso_limiar, teto_limiar = 150.0, 3000.0

        rms_por_bloco = []
        with sd.InputStream(samplerate=samplerate, channels=1, dtype="int16", blocksize=tamanho_bloco) as stream:
            for _ in range(int(duracao_segundos / bloco_seg)):
                bloco, _overflow = stream.read(tamanho_bloco)
                rms = float(np.sqrt(np.mean(bloco.astype("float64") ** 2))) if bloco.size else 0.0
                rms_por_bloco.append(rms)

        if len(rms_por_bloco) < n_calibracao:
            raise RuntimeError("Gravação curta demais pra calibrar -- tente de novo.")

        ruido_base = min(rms_por_bloco[:n_calibracao])
        limiar = max(piso_limiar, min(teto_limiar, ruido_base * 3.5))
        rms_max = max(rms_por_bloco)

        # marca cada bloco como "falando"/"silêncio" pelo limiar calibrado
        # acima, e soma a duração de cada trecho de silêncio que fica
        # ENTRE dois trechos falados (o de antes do primeiro "falando"
        # nunca conta -- é só a pessoa ainda não ter começado -- e o de
        # depois do último "falando" também não -- ver docstring).
        falando = [r >= limiar for r in rms_por_bloco]
        pausas_internas = []
        silencio_atual = 0
        ja_falou_antes = False
        for f in falando:
            if f:
                if ja_falou_antes and silencio_atual > 0:
                    pausas_internas.append(silencio_atual * bloco_seg)
                silencio_atual = 0
                ja_falou_antes = True
            elif ja_falou_antes:
                silencio_atual += 1

        maior_pausa = max(pausas_internas) if pausas_internas else 0.0
        # margem de 30% acima da maior pausa real medida -- dentro de um
        # piso (nunca tão baixo que volte a cortar por engano) e um teto
        # (nunca tão alto que fique lento pra reagir de verdade).
        recomendado = max(0.4, min(1.5, maior_pausa * 1.3)) if pausas_internas else 0.5

        qualidade, aviso = "boa", None
        if rms_max < _RMS_MINIMO_CONFIAVEL:
            qualidade = "volume_baixo"
            aviso = "Captei um volume bem baixo -- tente falar mais perto do microfone, ou aumentar o ganho dele."
        elif ruido_base > 800:
            qualidade = "ruido_alto"
            aviso = "Percebi bastante ruído de fundo no ambiente -- um fone de ouvido com microfone ajudaria."

        # margem entre o pico da voz e o chão de ruído -- ver docstring
        # acima pro porquê disso virar o multiplicador de sensibilidade
        # do barge-in. 0.35 calibrado pra bater com o default anterior
        # (2.8) numa margem "típica" (~8x).
        margem = rms_max / max(ruido_base, 1.0)
        sensibilidade_barge_in = max(1.8, min(4.5, margem * 0.35))

        return {
            "ruido_ambiente_rms": round(ruido_base, 1),
            "rms_max": round(rms_max, 1),
            "maior_pausa_interna_segundos": round(maior_pausa, 2),
            "silencio_recomendado_segundos": round(recomendado, 2),
            "sensibilidade_barge_in_recomendada": round(sensibilidade_barge_in, 2),
            "qualidade": qualidade,
            "aviso": aviso,
        }

    def listen_and_transcribe(self, duration_seconds: float = 5.0) -> str:
        """Compatibilidade com quem já chama isto esperando só o texto
        -- ver listen_and_transcribe_detalhado() pra qualidade/idioma
        detectado."""
        return self.listen_and_transcribe_detalhado(duration_seconds)["texto"]

    def listen_and_transcribe_detalhado(self, duration_seconds: float = 5.0) -> dict:
        """Retorna {"texto", "confiavel", "motivo", "idioma_detectado"}.
        `confiavel=False` significa que o trecho gravado foi curto/
        baixo demais pra confiar na transcrição (`motivo` explica) --
        `texto` ainda vem preenchido com o melhor palpite do motor,
        nunca None, então quem chama pode decidir ignorar ou não."""
        backend = self.backend_disponivel()
        if not backend:
            raise RuntimeError(
                "Nenhum motor de reconhecimento de voz disponível. Instale "
                "'vosk', 'faster-whisper' ou 'SpeechRecognition' + 'sounddevice' "
                "(ver requirements-voz.txt)."
            )
        if backend == "vosk":
            return self._listen_vosk(duration_seconds)
        if backend == "faster-whisper":
            return self._listen_whisper(duration_seconds)
        return self._listen_speech_recognition()

    def _gravar_ate_silencio(self, duracao_maxima: float, samplerate: int = _SAMPLERATE_PADRAO,
                              recognizer_ao_vivo=None):
        """Grava em streaming (blocos de 30ms) e para sozinho assim que
        detecta `voz.silencio_para_parar_segundos` de silêncio DEPOIS
        de ter detectado fala -- em vez de sempre gravar a duração
        máxima inteira, mesmo quando a pessoa já parou de falar.

        `recognizer_ao_vivo` (opcional, um `vosk.KaldiRecognizer` já
        criado por quem chama): quando passado, cada bloco também é
        alimentado a ele em tempo real, e `AcceptWaveform()` retornando
        verdadeiro (o próprio vosk decidindo que a frase terminou, via
        o MODELO acústico -- não só amplitude) vira um critério de
        parada adicional, testado ANTES do critério por RMS. Só usado
        por `_listen_vosk()`; `_listen_whisper()` não passa nada, e o
        comportamento fica idêntico a antes.

        Três melhorias em cima da versão original (que sentia "lenta pra
        terminar" e "cortava" quem falasse mais que a duração máxima):

        1. **Limiar de silêncio calibrado no ambiente**, não mais um
           valor fixo (500.0). Um valor fixo funciona mal em qualquer
           ambiente diferente do que foi medido: microfone com ganho
           alto ou quarto com ruído de fundo real nunca CAI abaixo de
           500 -> `falou`/`silencio_acumulado` nunca fecham, e a
           gravação sempre bate no teto máximo (a causa raiz de
           "demora muito pra terminar"). Por isso os primeiros ~240ms
           são usados só pra medir o ruído de fundo real (sem exigir
           silêncio absoluto do usuário -- ele já pode começar a falar
           nesse instante, o áudio não é descartado) e o limiar vira
           `ruído_base * 3.5`, dentro de um piso/teto sensato.
        2. **Extensão suave no teto máximo**: se a pessoa ainda está
           falando ativamente (sem ter completado o silêncio exigido)
           bem no instante em que bateria o teto, a gravação ganha mais
           um pouco de fôlego em vez de cortar a frase no meio -- até um
           teto absoluto (`duracao_maxima` + folga), pra nunca virar
           gravação infinita.
        3. **Endpointing via reconhecimento** (opcional, `recognizer_ao_vivo`):
           além do RMS, o próprio decodificador do vosk pode sinalizar
           que a frase terminou -- geralmente mais rápido/confiável que
           esperar `silencio_para_parar_segundos` inteiro de RMS baixo,
           porque é informado pelo conteúdo fonético, não só volume.

        Retorna (audio, samplerate, metadados) -- metadados tem "falou",
        "rms_max", "endpoint_por_reconhecimento" (usados por
        _avaliar_qualidade(), as duas primeiras, pra decidir se dá pra
        confiar na transcrição) e "ruido_ambiente_rms" (o chão de ruído
        medido nos primeiros ~240ms DESTA gravação -- usado por quem
        chama pra notar se o ambiente mudou desde a última calibração,
        ver VoiceLoop._checar_mudanca_de_ambiente)."""
        import numpy as np

        settings = get_settings()
        silencio_seg = float(settings.get("voz.silencio_para_parar_segundos", 0.6))
        duracao_minima = min(0.6, duracao_maxima)  # nunca corta na respiração inicial

        bloco_seg = 0.03
        tamanho_bloco = max(1, int(samplerate * bloco_seg))
        n_calibracao = 8  # ~240ms de ruído ambiente antes de fixar o limiar de silêncio
        piso_limiar, teto_limiar = 150.0, 3000.0

        folga_maxima = min(10.0, duracao_maxima)  # quanto essa gravação pode "estourar" o teto se a pessoa ainda estiver falando
        limite_absoluto = duracao_maxima + folga_maxima

        blocos = []
        rms_blocos = []
        falou = False
        rms_max = 0.0
        silencio_acumulado = 0.0
        tempo_total = 0.0
        limiar_rms = None  # só é fixado depois da janela de calibração
        ruido_ambiente_rms = None
        endpoint_por_reconhecimento = False

        with sd.InputStream(samplerate=samplerate, channels=1, dtype="int16", blocksize=tamanho_bloco) as stream:
            while tempo_total < limite_absoluto:
                bloco, _overflow = stream.read(tamanho_bloco)
                blocos.append(bloco.copy())
                tempo_total += bloco_seg
                rms = float(np.sqrt(np.mean(bloco.astype("float64") ** 2))) if bloco.size else 0.0
                rms_max = max(rms_max, rms)

                if limiar_rms is None:
                    rms_blocos.append(rms)
                    if len(rms_blocos) < n_calibracao:
                        continue
                    # usa o MÍNIMO (não a média) dos blocos de calibração --
                    # se a pessoa já começou a falar durante essa janela,
                    # a média ficaria alta demais e o limiar perderia a fala
                    # baixinha; o mínimo tende a ser silêncio de verdade.
                    ruido_base = min(rms_blocos)
                    ruido_ambiente_rms = ruido_base
                    limiar_rms = max(piso_limiar, min(teto_limiar, ruido_base * 3.5))
                    # reavalia retroativamente os blocos de calibração com o
                    # limiar recém-calculado, pro caso de a pessoa já ter
                    # começado a falar dentro dessa janela.
                    for r in rms_blocos:
                        if r >= limiar_rms:
                            falou = True
                            silencio_acumulado = 0.0
                        else:
                            silencio_acumulado += bloco_seg
                    # mantém o reconhecedor "ao vivo" em dia com os blocos já
                    # coletados durante a calibração (senão ele ficaria ~240ms
                    # atrasado em relação ao que já foi gravado).
                    if recognizer_ao_vivo is not None:
                        for b in blocos:
                            recognizer_ao_vivo.AcceptWaveform(b.tobytes())
                    continue

                if rms >= limiar_rms:
                    falou = True
                    silencio_acumulado = 0.0
                else:
                    silencio_acumulado += bloco_seg

                # Endpointing via reconhecimento -- checado ANTES do critério
                # por RMS abaixo: se o próprio vosk já decidiu que a frase
                # terminou (via o modelo acústico), não faz sentido esperar
                # mais silêncio por amplitude.
                if recognizer_ao_vivo is not None and recognizer_ao_vivo.AcceptWaveform(bloco.tobytes()):
                    if falou and tempo_total >= duracao_minima:
                        endpoint_por_reconhecimento = True
                        break

                silencio_completo = falou and silencio_acumulado >= silencio_seg
                if tempo_total >= duracao_minima and silencio_completo:
                    break
                # bateu o teto normal sem nunca ter detectado fala -- não
                # adianta esperar a folga extra (ela é só pra quem está
                # ativamente falando).
                if tempo_total >= duracao_maxima and not falou:
                    break
                # bateu o teto normal e a pessoa ainda está falando (sem
                # silêncio completo ainda) -- deixa continuar até a folga
                # máxima em vez de cortar a frase no meio (loop acima cuida
                # do limite absoluto).

        metadados = {
            "falou": falou, "rms_max": rms_max, "duracao_segundos": tempo_total,
            "endpoint_por_reconhecimento": endpoint_por_reconhecimento,
            "ruido_ambiente_rms": ruido_ambiente_rms,
        }
        if not blocos:
            return np.zeros((0, 1), dtype="int16"), samplerate, metadados
        return np.concatenate(blocos), samplerate, metadados

    def _avaliar_qualidade(self, metadados: dict) -> tuple:
        """(confiavel: bool, motivo: str|None) -- heurística simples:
        precisa ter detectado fala de verdade E com volume razoável.
        Não é análise espectral nem detecção de clipping/distorção de
        verdade, só um filtro honesto pro caso óbvio de "praticamente
        não captou nada"."""
        if not metadados["falou"]:
            return False, "não detectei fala (silêncio ou volume baixo demais)"
        if metadados["rms_max"] < _RMS_MINIMO_CONFIAVEL:
            return False, "volume captado foi baixo demais pra uma transcrição confiável"
        return True, None

    def _reduzir_ruido(self, audio, samplerate: int):
        """Aplica redução de ruído (noisereduce) se a lib estiver
        disponível -- sem ela, retorna o áudio bruto sem modificar
        (degrada graciosamente, nunca impede a transcrição)."""
        if not HAS_NOISEREDUCE or audio.size == 0:
            return audio
        try:
            import noisereduce as nr
            audio_float = audio.astype("float32").flatten() / 32768.0
            reduzido = nr.reduce_noise(y=audio_float, sr=samplerate)
            return (reduzido * 32768.0).astype("int16").reshape(-1, 1)
        except Exception as e:
            log.warning("redução de ruído falhou, usando áudio original: %s", e)
            return audio

    def _carregar_modelo_vosk(self):
        """Carrega (ou baixa, na primeira vez) o modelo do vosk pro
        idioma configurado -- ver docstring do módulo pro porquê do
        modelo GRANDE ser o padrão pra português."""
        if not self.language.startswith("pt"):
            return vosk.Model(lang="en-us")

        tamanho = get_settings().get("voz.modelo_stt_tamanho", "pequeno")
        if tamanho == "grande":
            try:
                return vosk.Model(model_name=_VOSK_MODELO_PT_GRANDE)
            except Exception as e:
                # Falha de download (sem internet na primeira vez, etc.)
                # -- cai pro modelo pequeno em vez de deixar o modo de
                # voz inteiro indisponível por causa de 1.6GB faltando.
                log.warning(
                    "falha ao carregar o modelo grande do vosk (%s) -- caindo pro modelo pequeno.", e,
                )
        return vosk.Model(lang="pt")

    def _listen_vosk(self, duration_seconds: float) -> dict:
        import json as _json

        if self._vosk_model is None:
            try:
                self._vosk_model = self._carregar_modelo_vosk()
            except Exception as e:
                raise RuntimeError(
                    f"Não consegui carregar o modelo do vosk ({e}). Confira sua conexão na "
                    "primeira vez (o modelo é baixado automaticamente), ou baixe manualmente "
                    "em alphacephei.com/vosk/models."
                ) from e

        # Modelo carregado ANTES de gravar (diferente de antes) -- precisamos
        # de um KaldiRecognizer pronto pra alimentar em tempo real durante a
        # própria gravação (endpointing via reconhecimento, ver
        # _gravar_ate_silencio). Esse recognizer é só pra decidir O MOMENTO
        # de parar; roda sobre áudio ainda CRU (sem redução de ruído), então
        # seu texto é descartado -- a transcrição de verdade usa um
        # recognizer novo, depois, sobre o áudio já processado.
        recognizer_ao_vivo = vosk.KaldiRecognizer(self._vosk_model, _SAMPLERATE_PADRAO)
        audio, samplerate, metadados = self._gravar_ate_silencio(
            duration_seconds, samplerate=_SAMPLERATE_PADRAO, recognizer_ao_vivo=recognizer_ao_vivo,
        )
        confiavel, motivo = self._avaliar_qualidade(metadados)
        audio = self._reduzir_ruido(audio, samplerate)

        rec = vosk.KaldiRecognizer(self._vosk_model, samplerate)
        rec.AcceptWaveform(audio.tobytes())
        result = _json.loads(rec.FinalResult())
        return {
            "texto": result.get("text", ""),
            "confiavel": confiavel,
            "motivo": motivo,
            "idioma_detectado": None,  # vosk não detecta idioma -- o modelo carregado já é fixo
            "ruido_ambiente_rms": metadados["ruido_ambiente_rms"],
        }

    def _listen_whisper(self, duration_seconds: float) -> dict:
        from faster_whisper import WhisperModel

        audio, samplerate, metadados = self._gravar_ate_silencio(duration_seconds)
        confiavel, motivo = self._avaliar_qualidade(metadados)
        audio = self._reduzir_ruido(audio, samplerate)
        if self._whisper_model is None:
            self._whisper_model = WhisperModel("small", device="cpu")
        audio_float = (audio.astype("float32") / 32768.0).flatten()
        idioma = None if self.language in ("auto", None) else self.language[:2]
        segments, info = self._whisper_model.transcribe(audio_float, language=idioma)
        texto = " ".join(seg.text for seg in segments).strip()
        return {
            "texto": texto,
            "confiavel": confiavel,
            "motivo": motivo,
            "idioma_detectado": getattr(info, "language", idioma),
            "ruido_ambiente_rms": metadados["ruido_ambiente_rms"],
        }

    def _listen_speech_recognition(self) -> dict:
        # motor online -- não passa por _gravar_ate_silencio (usa o VAD
        # próprio do speech_recognition), então não há chão de ruído
        # medido igual aos outros motores pra reportar aqui.
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source)
        try:
            texto = recognizer.recognize_google(audio, language=self.language)
            return {"texto": texto, "confiavel": True, "motivo": None, "idioma_detectado": None, "ruido_ambiente_rms": None}
        except sr.UnknownValueError:
            return {
                "texto": "",
                "confiavel": False,
                "motivo": "não entendi o áudio (fala baixa, ruído ou idioma diferente do configurado)",
                "idioma_detectado": None,
                "ruido_ambiente_rms": None,
            }


class BargeInMonitor:
    """Barge-in: detecta se você começou a falar por cima ENQUANTO o
    Jarvis está falando, pra interromper a fala dele (ver
    voz/tts.py:interromper()) em vez de esperar ele terminar -- mais
    parecido com uma conversa de verdade (e com o modo de voz do
    ChatGPT) do que ficar preso ouvindo uma resposta inteira sem poder
    cortar.

    Versão SIMPLES, de propósito: só volume (RMS calibrado no ruído
    ambiente, mesma técnica de _gravar_ate_silencio), sem transcrever
    nada -- rápido e barato, não depende de qual motor de STT está
    configurado. Exige alguns blocos CONSECUTIVOS acima do limiar
    (~90ms sustentados) antes de disparar, pra não confundir um "pop"
    isolado (uma tossida, um clique) com o usuário realmente falando.

    Risco conhecido, documentado e NÃO resolvido aqui (ver
    voz/README.md): sem cancelamento de eco, o próprio alto-falante
    tocando a fala do Jarvis pode ser captado de volta pelo microfone e
    disparar um falso positivo -- pior sem fone de ouvido e com o
    volume alto. Não trava nada se acontecer (o Jarvis só para de
    falar um pouco antes do fim, na pior das hipóteses), mas é uma
    limitação honesta, não um bug escondido."""

    _BLOCOS_CONSECUTIVOS_NECESSARIOS = 3  # ~90ms sustentados (blocos de 30ms)
    _N_CALIBRACAO = 6

    def __init__(self, samplerate: int = _SAMPLERATE_PADRAO, sensibilidade: float = 2.8):
        self.samplerate = samplerate
        self.sensibilidade = sensibilidade
        self._evento_interrompido = threading.Event()
        self._evento_parar = threading.Event()
        self._thread = None

    def iniciar(self):
        """Começa a monitorar o microfone em segundo plano -- sem
        `sounddevice` instalado, vira no-op silencioso (barge-in é só
        um extra; nunca deveria impedir o Jarvis de falar normalmente)."""
        if not HAS_SOUNDDEVICE:
            return
        self._evento_parar.clear()
        self._evento_interrompido.clear()
        self._thread = threading.Thread(target=self._monitorar, daemon=True)
        self._thread.start()

    def parar(self):
        self._evento_parar.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def interrompido(self) -> bool:
        return self._evento_interrompido.is_set()

    def _monitorar(self):
        try:
            import numpy as np
        except ImportError:
            return
        bloco_seg = 0.03
        tamanho_bloco = max(1, int(self.samplerate * bloco_seg))
        rms_blocos = []
        limiar = None
        blocos_altos_seguidos = 0
        try:
            with sd.InputStream(samplerate=self.samplerate, channels=1, dtype="int16", blocksize=tamanho_bloco) as stream:
                while not self._evento_parar.is_set():
                    bloco, _overflow = stream.read(tamanho_bloco)
                    rms = float(np.sqrt(np.mean(bloco.astype("float64") ** 2))) if bloco.size else 0.0

                    if limiar is None:
                        rms_blocos.append(rms)
                        if len(rms_blocos) < self._N_CALIBRACAO:
                            continue
                        limiar = max(200.0, min(4000.0, min(rms_blocos) * self.sensibilidade))
                        continue

                    if rms >= limiar:
                        blocos_altos_seguidos += 1
                        if blocos_altos_seguidos >= self._BLOCOS_CONSECUTIVOS_NECESSARIOS:
                            self._evento_interrompido.set()
                            return
                    else:
                        blocos_altos_seguidos = 0
        except Exception as e:
            # barge-in é um EXTRA -- qualquer falha aqui (ex.: microfone
            # ocupado por outra gravação ao mesmo tempo) nunca deve
            # atrapalhar a fala normal, só desiste de detectar interrupção
            # nesta rodada.
            log.warning("barge-in: monitor do microfone parou (%s)", e)
