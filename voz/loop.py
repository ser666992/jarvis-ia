"""
voz/loop.py
=============
VoiceLoop: laço de conversa contínua por voz -- ouvir, transcrever,
processar no Jarvis, falar a resposta. Usado por `main.py --voz`.

Configuração lida automaticamente de `config.json` quando não
passada explicitamente no construtor:
  - `voz.ativar_wakeword` / `voz.palavra_chave` / `voz.palavras_chave`:
    liga a palavra de ativação ("jarvis, que horas são" em vez de
    precisar reiniciar o modo voz pra cada frase) -- `palavras_chave`
    (lista) permite mais de uma, ex. `["jarvis", "ark"]`, além de
    `palavra_chave` (singular, continua funcionando) -- ver
    voz/wakeword.py.
  - `personalidade.voz_robotica`: tom de voz mais grave/mecânico via
    SAPI5 (ver voz/tts.py) -- não é clonagem de nenhuma voz de
    terceiros, só prosódia (pitch/rate) da própria API do Windows.

Barge-in: enquanto o Jarvis fala a resposta, um `BargeInMonitor` (ver
voz/stt.py) escuta o microfone em paralelo -- se detectar que você
começou a falar por cima, a fala para na hora (voz/tts.py:interromper())
em vez de precisar esperar a resposta inteira terminar antes de poder
falar de novo. Versão simples (só volume, sem transcrever nada
enquanto fala) -- ver limitação honesta na docstring de BargeInMonitor.
Sensibilidade calibrável junto com o microfone (`voz.sensibilidade_barge_in`,
ver `calibrar_microfone()`); "modo silencioso" (`voz.barge_in_ativo=False`)
desliga isso temporariamente sem precisar reiniciar o modo de voz.

Calibração automática na primeira vez: antes do primeiro turno de
verdade, `_calibrar_se_necessario()` guia uma calibração rápida do
microfone (mesma medição de "calibra o microfone",
plugins/calibracao_voz.py) e marca `voz.microfone_calibrado` -- só
acontece uma vez; depois disso é por comando quando a pessoa quiser.

Mudança de ambiente: cada gravação já mede o chão de ruído real (ver
voz/stt.py:_gravar_ate_silencio) -- `_checar_mudanca_de_ambiente()`
compara isso com o que foi medido na última calibração
(`voz.ruido_ambiente_calibrado`) e sugere recalibrar (uma vez por
sessão) se estiver bem diferente, em vez de deixar a pessoa descobrir
sozinha que mudou de cômodo/ligou o ventilador e o Jarvis passou a
cortar frases de novo.
"""

from config.settings import get_settings
from core.personality import NOME
from logs.logger import get_logger
from voz.stt import BargeInMonitor, SpeechToText
from voz.tts import TextToSpeech
from voz.wakeword import WakeWordDetector

log = get_logger("voz")


class VoiceLoop:
    def __init__(self, jarvis, keyword: str = None, keywords: list = None, language: str = "pt-BR",
                 use_wakeword: bool = None, robotic: bool = None):
        settings = get_settings()
        if keyword is None and keywords is None:
            keyword = settings.get("voz.palavra_chave", "jarvis")
            keywords = settings.get("voz.palavras_chave", [])
        if use_wakeword is None:
            use_wakeword = settings.get("voz.ativar_wakeword", False)
        if robotic is None:
            robotic = settings.get("personalidade.voz_robotica", False)
        self._duracao_maxima_comando = float(settings.get("voz.duracao_maxima_comando_segundos", 20.0))

        self.jarvis = jarvis
        self.stt = SpeechToText(language=language)
        self.tts = TextToSpeech(robotic=bool(robotic))
        self.wakeword = WakeWordDetector(keyword=keyword, keywords=keywords, stt=self.stt) if use_wakeword else None
        self._avisou_mudanca_ambiente = False

    def available(self) -> bool:
        return self.stt.available() and self.tts.available()

    def _calibrar_se_necessario(self):
        """Na primeira vez que o modo de voz roda (`voz.microfone_calibrado`
        ainda False), guia uma calibração rápida do microfone ANTES de
        começar a ouvir de verdade -- em vez de depender de alguém
        lembrar de rodar "calibra o microfone" por conta própria e
        conviver com os palpites genéricos até lá. Roda só uma vez;
        depois disso, recalibrar é por comando de voz
        (plugins/calibracao_voz.py) quando a pessoa quiser."""
        settings = get_settings()
        if settings.get("voz.microfone_calibrado", False):
            return
        if not self.stt.available():
            return

        print("Antes de começar, vou calibrar o microfone pro seu jeito de falar...")
        try:
            self.tts.speak(
                "Antes de começar, vou calibrar o microfone pro seu jeito de falar. "
                "Fale uma frase natural e um pouco longa, com alguma pausa no meio."
            )
        except Exception:
            pass

        try:
            resultado = self.stt.calibrar_microfone()
        except Exception as e:
            log.warning("calibração inicial do microfone falhou: %s", e)
            print(f"[voz] não consegui calibrar automaticamente ({e}) -- seguindo com os valores padrão.")
            return

        settings.set("voz.silencio_para_parar_segundos", resultado["silencio_recomendado_segundos"])
        settings.set("voz.sensibilidade_barge_in", resultado["sensibilidade_barge_in_recomendada"])
        settings.set("voz.ruido_ambiente_calibrado", resultado["ruido_ambiente_rms"])
        settings.set("voz.microfone_calibrado", True)
        settings.save()

        print(
            f'Calibrado! Silêncio pra parar de ouvir: {resultado["silencio_recomendado_segundos"]}s '
            f'-- maior pausa detectada na sua fala: {resultado["maior_pausa_interna_segundos"]}s.'
        )
        if resultado["aviso"]:
            print(f"[voz] {resultado['aviso']}")
        try:
            self.tts.speak("Prontinho, já calibrei. Pode falar normalmente.")
        except Exception:
            pass

    def _ouvir_comando(self) -> dict:
        """Um turno de escuta -- retorna {"texto", "confiavel", "motivo"}.
        Com palavra de ativação, aceita tanto "jarvis, comando" numa
        respiração só quanto "jarvis" seguido de uma pausa e o comando
        depois; sem palavra de ativação, ouve direto. A gravação em si
        para sozinha quando detecta silêncio (ver
        voz/stt.py:_gravar_ate_silencio) -- `_duracao_maxima_comando`
        é só o teto de segurança, não uma espera fixa.

        `confiavel=False` (ver voz/stt.py:listen_and_transcribe_detalhado)
        significa que a transcrição saiu curta/baixa demais pra confiar
        -- quem chama (run()) usa isso pra pedir pra repetir em vez de
        mandar direto pro Jarvis processar um texto capenga. O caminho
        "comando dito na mesma respiração que a palavra-chave" também
        expõe essa mesma confiança agora (voz/wakeword.py:listen_for_command
        já devolve {"texto", "confiavel", "motivo"})."""
        if not (self.wakeword and self.wakeword.available()):
            print("Ouvindo...")
            return self.stt.listen_and_transcribe_detalhado(duration_seconds=self._duracao_maxima_comando)

        print("Aguardando palavra-chave...")
        resultado = self.wakeword.listen_for_command()
        if resultado is None:
            return {"texto": "", "confiavel": True, "motivo": None}
        if resultado["texto"]:
            return resultado
        print("Ouvindo o comando...")
        return self.stt.listen_and_transcribe_detalhado(duration_seconds=self._duracao_maxima_comando)

    def _checar_mudanca_de_ambiente(self, ruido_atual):
        """Se o ruído de fundo medido NESTA gravação estiver bem
        diferente do que foi medido na última calibração
        (`voz.ruido_ambiente_calibrado`, ver calibrar_microfone()),
        sugere recalibrar -- uma vez por sessão (não a cada turno,
        senão vira spam pra quem realmente mora/trabalha num ambiente
        mais barulhento o tempo todo). `ruido_atual` vem de
        `listen_and_transcribe_detalhado()["ruido_ambiente_rms"]`
        (None pro motor online, que não faz essa medição -- nesse caso
        não há o que comparar)."""
        if ruido_atual is None or self._avisou_mudanca_ambiente:
            return
        baseline = get_settings().get("voz.ruido_ambiente_calibrado")
        if not baseline or baseline <= 0:
            return
        razao = ruido_atual / baseline
        if razao <= 2.5 and razao >= 0.4:
            return
        self._avisou_mudanca_ambiente = True
        log.info("ambiente mudou desde a calibração (ruído atual %.0f vs. calibrado %.0f)", ruido_atual, baseline)
        self._falar_interrompivel(
            "Percebi que o ambiente mudou desde a última calibração do microfone -- "
            'se eu começar a cortar suas frases ou demorar pra reagir, diga "calibra o microfone" de novo.'
        )

    def _falar_interrompivel(self, texto: str):
        """Fala `texto`, mas para na hora se detectar que você começou
        a falar por cima (barge-in, ver BargeInMonitor em voz/stt.py).
        `voz.barge_in_ativo` (padrão True) permite desligar isso na
        hora ("modo silencioso") sem precisar reiniciar o modo de voz
        -- com ele desligado, fala do jeito de sempre (sem monitorar o
        microfone em paralelo)."""
        settings = get_settings()
        if not settings.get("voz.barge_in_ativo", True):
            self.tts.speak(texto)
            return
        sensibilidade = float(settings.get("voz.sensibilidade_barge_in", 2.8))
        monitor = BargeInMonitor(sensibilidade=sensibilidade)
        monitor.iniciar()
        try:
            self.tts.speak(texto, verificar_interromper=monitor.interrompido)
        finally:
            monitor.parar()
        if monitor.interrompido():
            print("(interrompido)")

    def run(self, max_turns: int = None):
        if not self.available():
            raise RuntimeError(
                "Voz indisponível: instale as dependências de voz "
                "(ver requirements-voz.txt) e verifique o microfone."
            )

        self._calibrar_se_necessario()

        modo = f'com palavra de ativação "{self.wakeword.keyword}"' if self.wakeword else "sem palavra de ativação"
        print(f"{NOME} (modo voz, {modo}) pronto. Fale normalmente. Ctrl+C para sair.")
        turns = 0
        while max_turns is None or turns < max_turns:
            try:
                resultado = self._ouvir_comando()
                self._checar_mudanca_de_ambiente(resultado.get("ruido_ambiente_rms"))
                text = resultado["texto"].strip()
                if not text:
                    continue

                if not resultado["confiavel"]:
                    # Transcrição saiu, mas pouco confiável (curta/baixa
                    # demais) -- NÃO manda pro Jarvis processar como se
                    # fosse o pedido real (isso já gerou resposta sem
                    # nexo de verdade, tipo "ora o amargo" virando
                    # pergunta sobre café). Pede pra repetir em vez de
                    # arriscar um palpite.
                    log.info("transcrição pouco confiável (%s): %r", resultado["motivo"], text)
                    self._falar_interrompivel("Não peguei bem o que você disse, pode repetir?")
                    continue

                print(f"Você disse: {text}")

                resposta = self.jarvis.process(text)
                print(f"{NOME}: {resposta}")
                self._falar_interrompivel(resposta)
                turns += 1
            except KeyboardInterrupt:
                print("Encerrando modo voz.")
                break
            except Exception as e:
                log.warning("erro no loop de voz: %s", e)
                print(f"[voz] erro: {e}")
                # Pequena pausa antes de tentar de novo -- sem isso, um
                # erro que se repete a cada turno (ex.: configuração
                # quebrada) giraria o loop o mais rápido possível,
                # consumindo CPU à toa e spammando o mesmo erro.
                import time
                time.sleep(1.5)
