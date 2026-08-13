"""
gui/app.py
==========
Interface gráfica do Neutron: fundo escuro, o núcleo de estrela de
nêutrons (`gui/neutron_core.py`) reagindo ao estado da IA, e um chat mostrando as
respostas -- da base de conhecimento, plugins (inclusive abrir
programas, via automacao/apps.py) ou IA externa. Tudo passa pelo mesmo
`Jarvis.process()` do modo texto (core/jarvis.py), então qualquer
coisa que funciona no terminal funciona aqui também.

Processar uma mensagem pode envolver uma chamada de rede (provedor de
IA externo) e não pode travar a interface -- por isso roda numa
QThread (_ProcessWorker) enquanto o orbe anima "pensando".

`Jarvis(user_id=...)` em si também não é instantâneo -- carrega
memória, plugins, base de conhecimento e detecção de GPU (que importa
`torch`, o maior custo sozinho), e isso pode levar de alguns segundos a
mais de 20s dependendo da máquina. Por isso a janela aparece
IMEDIATAMENTE, num estado "carregando", enquanto `Jarvis()` é criado
numa QThread separada (`_JarvisLoader`) -- sem isso, a janela inteira
ficava invisível até o carregamento terminar, o que parecia (e na
prática era) "o programa não abre".

Voz (TTS): a GUI é só texto por padrão em outros lugares do projeto
(o modo de voz "de verdade" é `python main.py --voz`, ver voz/loop.py),
mas aqui a GUI TAMBÉM fala as respostas em voz alta (botão "Voz" liga/
desliga) -- usa o mesmo `voz.tts.TextToSpeech` (com o efeito robótico
de `personalidade.voz_robotica`, se ligado). Falas rodam numa fila
processada por um único `_SpeakWorker` persistente: `pyttsx3` não é
seguro pra chamadas concorrentes na mesma engine, então enfileirar
evita sobrepor ou corromper falas quando duas respostas chegam perto
uma da outra (chat + notificação, por exemplo).
"""

import html
import queue
import re
import sys
import time

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStyle,
    QSystemTrayIcon, QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config.settings import get_settings
from core.jarvis import Jarvis
from core.personality import NOME
from gui.neutron_core import NeutronCore
from logs.logger import get_logger
from plugins.logins_web import SAVE_INTENT_RE
from voz.tts import TextToSpeech

log = get_logger("gui")

_SAVE_LOGIN_SITE_RE = re.compile(r"\blogin\s+(?:do|da|de|no|na)\s+(.+)", re.IGNORECASE)


class _NotifyBridge(QObject):
    """Ponte thread-safe entre uma notificação disparada em thread de
    fundo (lembrete, comentário automático -- ambos via
    threading.Timer, ver automacao/tasks.py) e a UI Qt, que só pode ser
    tocada pela thread principal. Sinais Qt emitidos de outra thread
    para um slot na thread principal usam conexão em fila
    automaticamente, então isto é seguro."""
    fired = Signal(str, str)


class _ProcessWorker(QThread):
    done = Signal(str)

    def __init__(self, jarvis: Jarvis, text: str, parent=None):
        super().__init__(parent)
        self._jarvis = jarvis
        self._text = text

    def run(self):
        try:
            resposta = self._jarvis.process(self._text)
        except Exception as e:
            resposta = f"Erro ao processar: {e}"
        self.done.emit(resposta)


class _ListenWorker(QThread):
    """Grava e transcreve UM comando por voz (voz/stt.py) numa thread
    separada -- gravar bloqueia por até alguns segundos, e a UI não
    pode travar durante isso. Usa a mesma detecção de silêncio de
    voz/stt.py:_gravar_ate_silencio (para sozinho ao detectar que você
    parou de falar, sem esperar sempre a duração máxima).

    Usa `listen_and_transcribe_detalhado()` (não a versão simples) pra
    também saber se a transcrição saiu CONFIÁVEL -- sem isso, uma
    transcrição ruim (curta demais, volume baixo, "ora o amargo" em vez
    do que foi dito de verdade) ia direto pro Jarvis processar como se
    fosse o pedido real, gerando uma resposta sem nexo em vez de pedir
    pra repetir (ver _on_ouviu() em MainWindow)."""
    ouviu = Signal(str, bool, str)  # texto, confiavel, motivo
    falhou = Signal(str)

    def run(self):
        try:
            from voz.stt import SpeechToText
            stt = SpeechToText(language="pt-BR")
            if not stt.available():
                self.falhou.emit(
                    "Nenhum motor de voz disponível (instale 'vosk'/'faster-whisper'/"
                    "'SpeechRecognition' + 'sounddevice', ver requirements-voz.txt)."
                )
                return
            resultado = stt.listen_and_transcribe_detalhado(duration_seconds=12.0)
            self.ouviu.emit(resultado["texto"].strip(), bool(resultado["confiavel"]), resultado.get("motivo") or "")
        except Exception as e:
            self.falhou.emit(str(e))


class _SpeakWorker(QThread):
    """Fala uma fila de textos, um de cada vez, numa thread persistente
    -- pyttsx3 não é seguro pra chamadas concorrentes na mesma engine,
    então uma fila com um único worker evita sobrepor falas.

    Barge-in: cada fala roda com um `BargeInMonitor` (voz/stt.py)
    escutando o microfone em paralelo -- se você começar a falar por
    cima, a fala do Jarvis para na hora (`interrompido` emitido, pra
    MainWindow reagir) em vez de precisar esperar a resposta inteira."""
    interrompido = Signal()

    def __init__(self, tts: TextToSpeech, parent=None):
        super().__init__(parent)
        self._tts = tts
        self._fila = queue.Queue()
        self._parar = False

    def enqueue(self, texto: str):
        self._fila.put(texto)

    def parar(self):
        self._parar = True
        self._fila.put(None)
        self._tts.interromper()

    def run(self):
        from voz.stt import BargeInMonitor

        while not self._parar:
            try:
                texto = self._fila.get(timeout=0.5)
            except queue.Empty:
                continue
            if texto is None:
                break
            if not get_settings().get("voz.barge_in_ativo", True):
                try:
                    self._tts.speak(texto)
                except Exception:
                    pass
                continue
            sensibilidade = float(get_settings().get("voz.sensibilidade_barge_in", 2.8))
            monitor = BargeInMonitor(sensibilidade=sensibilidade)
            monitor.iniciar()
            try:
                self._tts.speak(texto, verificar_interromper=monitor.interrompido)
            except Exception:
                pass
            finally:
                monitor.parar()
            if monitor.interrompido():
                self.interrompido.emit()


class _JarvisLoader(QThread):
    """Constrói o Jarvis(user_id=...) fora da thread principal -- essa
    chamada sozinha pode levar vários segundos (ver nota no topo do
    arquivo), e a janela não pode ficar invisível esse tempo todo."""
    pronto = Signal(object)
    falhou = Signal(str)

    def __init__(self, user_id: str, parent=None):
        super().__init__(parent)
        self.user_id = user_id

    def run(self):
        try:
            jarvis = Jarvis(user_id=self.user_id)
        except Exception as e:
            self.falhou.emit(str(e))
            return
        self.pronto.emit(jarvis)


class MainWindow(QMainWindow):
    def __init__(self, user_id: str):
        super().__init__()
        self.jarvis = None
        self.user_id = user_id
        self._worker = None
        self._speak_worker = None
        self._listen_worker = None
        self._loader = None
        self._closing_requested = False
        self._permitir_fechar = False
        self._message_queue = []
        self._last_response = ""
        self._voice_enabled = True
        self._resposta_inicio = time.monotonic()

        self._pensando_timer = QTimer(self)
        self._pensando_timer.setInterval(400)
        self._pensando_timer.timeout.connect(self._animar_pensando)
        self._pensando_dots = 0

        self.setWindowTitle(NOME)
        self.resize(980, 720)
        self.setMinimumSize(720, 560)
        self._build_ui()
        self._build_tray()
        self._build_shortcuts()
        self._start_loading()

    def _build_shortcuts(self):
        focus = QShortcut(QKeySequence("Ctrl+Space"), self)
        focus.activated.connect(self.input_line.setFocus)
        cancel = QShortcut(QKeySequence("Escape"), self)
        cancel.activated.connect(self._cancel_current)
        center = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        center.activated.connect(self._open_control_center)
        self._shortcuts = (focus, cancel, center)

    def closeEvent(self, event):
        if self._speak_worker is not None:
            self._speak_worker.parar()
            self._speak_worker.wait(2000)
            self._speak_worker = None

        threads_ativas = [
            thread for thread in (self._loader, self._worker, self._listen_worker)
            if thread is not None and thread.isRunning()
        ]
        if threads_ativas and not self._permitir_fechar:
            # Destruir uma QThread ativa derruba o processo inteiro. Pede o
            # fechamento e conclui automaticamente assim que as operações
            # bloqueantes retornarem.
            self._closing_requested = True
            self.status_label.setText("Encerrando assim que a operação atual terminar...")
            event.ignore()
            return
        super().closeEvent(event)

    def _fechar_quando_seguro(self):
        if not self._closing_requested:
            return
        if any(
            thread is not None and thread.isRunning()
            for thread in (self._loader, self._worker, self._listen_worker)
        ):
            return
        self._permitir_fechar = True
        QTimer.singleShot(0, self.close)

    def _start_loading(self):
        self.status_label.setText(f"Iniciando o {NOME} (memória, plugins, IA)...")
        self.send_btn.setEnabled(False)
        self.input_line.setEnabled(False)
        self.mic_btn.setEnabled(False)
        self.orb.set_thinking(True)
        self._append_jarvis("Um momento, estou iniciando...")

        self._loader = _JarvisLoader(self.user_id, parent=self)
        self._loader.pronto.connect(self._on_jarvis_pronto)
        self._loader.falhou.connect(self._on_jarvis_falhou)
        self._loader.finished.connect(self._on_loader_finished)
        self._loader.start()

    def _on_loader_finished(self):
        if self._loader is not None:
            self._loader.deleteLater()
            self._loader = None
        self._fechar_quando_seguro()

    def _on_jarvis_pronto(self, jarvis):
        self.jarvis = jarvis
        self.orb.set_thinking(False)
        self.send_btn.setEnabled(True)
        self.input_line.setEnabled(True)
        self.mic_btn.setEnabled(True)
        self.status_label.setText(f"Pronto — sessão de {self.user_id}")
        self._greet()

    def _on_jarvis_falhou(self, erro: str):
        self.orb.set_thinking(False)
        self.status_label.setText("Falha ao iniciar")
        self._append_jarvis(f"Erro ao iniciar o {NOME}: {erro}")

    def _on_mic_clicked(self):
        if self._listen_worker is not None or self.jarvis is None:
            return
        self.mic_btn.setEnabled(False)
        self.input_line.setEnabled(False)
        self.status_label.setText("Ouvindo...")
        self.orb.set_listening(True)

        self._listen_worker = _ListenWorker(parent=self)
        self._listen_worker.ouviu.connect(self._on_ouviu)
        self._listen_worker.falhou.connect(self._on_falhou_ouvir)
        self._listen_worker.finished.connect(self._on_listen_finished)
        self._listen_worker.start()

    def _on_listen_finished(self):
        if self._listen_worker is not None:
            self._listen_worker.deleteLater()
            self._listen_worker = None
        self._fechar_quando_seguro()

    def _on_ouviu(self, texto: str, confiavel: bool, motivo: str):
        self.orb.set_listening(False)
        self.mic_btn.setEnabled(True)
        self.input_line.setEnabled(True)
        self.status_label.setText(f"Pronto — sessão de {self.user_id}")
        if not texto:
            self._append_jarvis("(não consegui entender o que você disse, tente de novo)")
            return
        if not confiavel:
            # Transcrição saiu, mas pouco confiável (curta/baixa demais) --
            # NÃO manda pro Jarvis processar como se fosse o pedido real
            # (isso já gerou resposta sem nexo de verdade, ver
            # plugins/calibracao_voz.py). Pede pra repetir em vez de
            # arriscar um palpite.
            log.info("transcrição pouco confiável (%s): %r", motivo, texto)
            aviso = "Não peguei bem o que você disse, pode repetir?"
            self._append_jarvis(aviso)
            self._falar(aviso)
            return
        self.input_line.setText(texto)
        self._on_send()

    def _on_falhou_ouvir(self, erro: str):
        self.orb.set_listening(False)
        self.mic_btn.setEnabled(True)
        self.input_line.setEnabled(True)
        self.status_label.setText(f"Pronto — sessão de {self.user_id}")
        self._append_jarvis(f"[erro ao ouvir] {erro}")

    def _animar_pensando(self):
        self._pensando_dots = (self._pensando_dots + 1) % 4
        self.status_label.setText(f"{NOME} está pensando" + "." * self._pensando_dots)

    def _toggle_voice(self):
        self._voice_enabled = self.voice_btn.isChecked()
        self.voice_btn.setText("Voz")
        self.voice_btn.setToolTip(
            "Leitura das respostas ativada" if self._voice_enabled
            else "Leitura das respostas desativada")

    def _texto_autonomo_btn(self, ligado: bool) -> str:
        return "Autônomo"

    def _toggle_modo_autonomo(self):
        ligado = self.autonomo_btn.isChecked()
        self.autonomo_btn.setText(self._texto_autonomo_btn(ligado))
        settings = get_settings()
        settings.set("personalidade.modo_autonomo", ligado)
        settings.save()
        if ligado:
            minutos = settings.get("personalidade.modo_autonomo_ociosidade_minutos", 5)
            self._append_jarvis(
                f"Modo Autônomo ativado. Quando o PC ficar {minutos} minuto(s) sem uso, executo "
                'sozinho o próximo objetivo cadastrado -- diga "novo objetivo autônomo: <o quê>" '
                "pra cadastrar o que devo fazer."
            )
        else:
            self._append_jarvis("Modo Autônomo desativado -- não vou mais trabalhar sozinho no ócio.")

    def _open_control_center(self):
        if self.jarvis is None:
            self.status_label.setText("A Central estará disponível quando a inicialização terminar.")
            return
        from gui.control_center import ControlCenter
        dialog = ControlCenter(self.jarvis, self)
        dialog.commandRequested.connect(self._send_external_command)
        dialog.exec()

    def _send_external_command(self, text: str):
        self.input_line.setText(text)
        self._on_send()

    def _cancel_current(self):
        if self._worker is None or not self._worker.isRunning():
            return
        self._worker._cancelled = True
        self._worker.requestInterruption()
        self.status_label.setText("Cancelando — aguardando a operação liberar a conexão...")
        self.cancel_btn.setEnabled(False)

    def _feedback(self, positive: bool):
        if not self._last_response or self.jarvis is None:
            return
        if not get_settings().get("privacidade.modo_privado", False):
            tipo = "feedback_positivo" if positive else "feedback_negativo"
            self.jarvis.memory.log_event(tipo, self._last_response[:300])
        self.status_label.setText("Feedback registrado. Obrigado.")

    def _ensure_speak_worker(self):
        """Cria o worker de fala sob demanda, na primeira vez que
        alguma resposta precisar ser falada -- assim quem nunca liga
        o som (ou não tem `pyttsx3` instalado) nunca paga esse custo."""
        if self._speak_worker is not None:
            return self._speak_worker
        try:
            robotic = bool(get_settings().get("personalidade.voz_robotica", False))
            tts = TextToSpeech(robotic=robotic)
            if not tts.available():
                self._speak_worker = False
                return False
            worker = _SpeakWorker(tts, parent=self)
            worker.interrompido.connect(self._on_fala_interrompida)
            worker.start()
            self._speak_worker = worker
        except Exception:
            self._speak_worker = False
        return self._speak_worker

    def _falar(self, texto: str):
        if not self._voice_enabled:
            return
        worker = self._ensure_speak_worker()
        if worker:
            worker.enqueue(texto)

    def _on_fala_interrompida(self):
        """Callback do sinal `_SpeakWorker.interrompido` -- disparado
        quando o barge-in detecta que você começou a falar por cima e
        para a fala do Jarvis no meio. Só um sinal visual discreto (não
        atrapalha se você já for clicar no microfone em seguida)."""
        self.status_label.setText(f"Pronto — sessão de {self.user_id} (interrompido)")

    def _abrir_dialogo_login(self, site_prefill: str = ""):
        """Diálogo pra salvar um login de site (automacao/logins_web.py)
        com o campo de senha mascarado (QLineEdit.Password) -- chama
        `logins_web.salvar_login()` DIRETO, sem passar pelo chat/
        `Jarvis.process()`, porque este último grava toda mensagem no
        histórico de conversa antes de qualquer plugin rodar. Se a
        senha viesse digitada no chat, ela ficaria em texto puro no
        banco de dados (e nos backups automáticos) -- ver aviso em
        plugins/logins_web.py.

        Antes um botão ("Salvar login"), agora é aberto pelo comando
        "salvar login" (ver _on_send() -- intercepta ANTES de mandar
        pro chat, então a senha continua nunca passando por lá).
        `site_prefill` pré-preenche o campo de site quando o comando já
        mencionava um (ex.: "salva o login do github")."""
        dialogo = QDialog(self)
        dialogo.setWindowTitle("Salvar login de site")
        form = QFormLayout(dialogo)

        site_edit = QLineEdit()
        site_edit.setText(site_prefill)
        url_edit = QLineEdit()
        url_edit.setPlaceholderText("https://exemplo.com/login")
        usuario_edit = QLineEdit()
        senha_edit = QLineEdit()
        senha_edit.setEchoMode(QLineEdit.Password)

        form.addRow("Site (nome curto):", site_edit)
        form.addRow("URL de login:", url_edit)
        form.addRow("Usuário/e-mail:", usuario_edit)
        form.addRow("Senha:", senha_edit)

        botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botoes.accepted.connect(dialogo.accept)
        botoes.rejected.connect(dialogo.reject)
        form.addRow(botoes)

        if dialogo.exec() != QDialog.Accepted:
            return

        site = site_edit.text().strip()
        url = url_edit.text().strip()
        usuario = usuario_edit.text().strip()
        senha = senha_edit.text()
        if not (site and url and usuario and senha):
            QMessageBox.warning(self, NOME, "Preencha todos os campos.")
            return

        try:
            from automacao import logins_web
            if not logins_web.available():
                QMessageBox.warning(
                    self, NOME,
                    "Instale 'keyring' e 'playwright' (requirements-automacao.txt) "
                    "para eu guardar e usar logins de sites.",
                )
                return
            logins_web.salvar_login(site, url, usuario, senha)
        except Exception as e:
            QMessageBox.critical(self, NOME, f"Falha ao salvar login: {e}")
            return

        QMessageBox.information(
            self, NOME,
            f'Login de "{site}" salvo com segurança. Diga "loga no {site}" no chat quando quiser usar.',
        )

    def _build_tray(self):
        """Registra esta janela como notifier (automacao/notify.py):
        quando um lembrete dispara, ou um comentário automático sobre
        a atividade do usuário é gerado (plugins/observation.py),
        mostra um balão na bandeja do sistema e também posta a
        mensagem no chat."""
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
        self.tray.setToolTip(NOME)
        self.tray.show()

        self._notify_bridge = _NotifyBridge()
        self._notify_bridge.fired.connect(self._on_notification)
        try:
            from automacao.notify import add_notifier
            add_notifier(self._notify_bridge.fired.emit)
        except Exception:
            pass

    def _on_notification(self, titulo: str, mensagem: str):
        self.tray.showMessage(titulo, mensagem, QSystemTrayIcon.Information, 8000)
        self._append_jarvis(f"[{titulo}] {mensagem}")
        self._falar(mensagem)

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("appRoot")
        central.setStyleSheet("""
            QWidget#appRoot { background: #0d0f12; color: #ececf1; }
            QLabel { background: transparent; }
            QPushButton {
                background: transparent; color: #b4b4bd; border: 1px solid #2b2d31;
                border-radius: 9px; padding: 7px 11px; font: 12px "Segoe UI";
            }
            QPushButton:hover { background: #202123; color: #ffffff; border-color: #3b3d42; }
            QPushButton:pressed { background: #292a2d; }
            QPushButton:disabled { color: #5d5f66; border-color: #202226; }
            QPushButton:checked { background: #2f6fed; color: white; border-color: #2f6fed; }
            QToolTip { background: #202123; color: #ececf1; border: 1px solid #34363b; }
        """)
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(22, 14, 22, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(12)
        self.orb = NeutronCore()
        self.orb.setFixedSize(74, 58)
        header.addWidget(self.orb)

        identity = QVBoxLayout()
        identity.setSpacing(1)
        title = QLabel(NOME)
        title.setFont(QFont("Segoe UI", 15, QFont.DemiBold))
        title.setStyleSheet("color:#f4f4f5")
        identity.addWidget(title)
        self.status_label = QLabel(f"Pronto — sessão de {self.user_id}")
        self.status_label.setStyleSheet("color:#8e8ea0;font:11px 'Segoe UI'")
        identity.addWidget(self.status_label)
        header.addLayout(identity)
        header.addStretch(1)

        self.voice_btn = QPushButton("Voz")
        self.voice_btn.setCheckable(True)
        self.voice_btn.setChecked(True)
        self.voice_btn.setCursor(Qt.PointingHandCursor)
        self.voice_btn.setToolTip("Ativar ou desativar leitura das respostas")
        self.voice_btn.clicked.connect(self._toggle_voice)
        header.addWidget(self.voice_btn)

        autonomo_ligado = bool(get_settings().get("personalidade.modo_autonomo", False))
        self.autonomo_btn = QPushButton("Autônomo")
        self.autonomo_btn.setCheckable(True)
        self.autonomo_btn.setChecked(autonomo_ligado)
        self.autonomo_btn.setCursor(Qt.PointingHandCursor)
        self.autonomo_btn.setToolTip(
            f"Quando ligado, o {NOME} executa sozinho os objetivos cadastrados assim que o PC "
            "ficar alguns minutos sem uso (diga \"novo objetivo autônomo: <o quê>\" pra cadastrar)."
        )
        self.autonomo_btn.clicked.connect(self._toggle_modo_autonomo)
        header.addWidget(self.autonomo_btn)

        self.center_btn = QPushButton("Central")
        self.center_btn.setCursor(Qt.PointingHandCursor)
        self.center_btn.clicked.connect(self._open_control_center)
        header.addWidget(self.center_btn)
        layout.addLayout(header)

        self.chat_log = QTextBrowser()
        self.chat_log.setReadOnly(True)
        self.chat_log.setOpenExternalLinks(True)
        self.chat_log.document().setDefaultStyleSheet(
            "a { color:#7aa2f7; text-decoration:none }")
        self._chat_log_style_normal = """
            QTextBrowser {
                background:#121315; color:#ececf1; border:1px solid #25262a;
                border-radius:14px; padding:18px 22px;
                selection-background-color:#315fbb;
            }
            QScrollBar:vertical { background:transparent; width:8px; margin:5px 2px; }
            QScrollBar::handle:vertical { background:#3a3b40; border-radius:4px; min-height:30px; }
            QScrollBar::handle:vertical:hover { background:#52545b; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
        """
        self._chat_log_style_flash = self._chat_log_style_normal.replace(
            "border:1px solid #25262a", "border:1px solid #3f68b5")
        self.chat_log.setStyleSheet(self._chat_log_style_normal)
        self.chat_log.setFont(QFont("Segoe UI", 11))
        layout.addWidget(self.chat_log, stretch=1)

        utility_row = QHBoxLayout()
        utility_row.setSpacing(6)
        quick_label = QLabel("Sugestões")
        quick_label.setStyleSheet("color:#71717a;font:11px 'Segoe UI';margin-right:3px")
        utility_row.addWidget(quick_label)
        for command in get_settings().get(
                "gui.comandos_rapidos",
                ["diagnóstico completo", "minhas mensagens do instagram", "o que aconteceu hoje"]):
            button = QPushButton(command[:25])
            button.setToolTip(command)
            button.setStyleSheet(
                "QPushButton{background:#17181b;color:#a9a9b2;border:1px solid #292a2e;"
                "border-radius:12px;padding:5px 10px;font:11px 'Segoe UI'}"
                "QPushButton:hover{background:#222326;color:white}")
            button.clicked.connect(
                lambda _checked=False, value=command: self._send_external_command(value))
            utility_row.addWidget(button)
        utility_row.addStretch(1)

        self.good_btn = QPushButton("Útil")
        self.bad_btn = QPushButton("Melhorar")
        for button, positive in ((self.good_btn, True), (self.bad_btn, False)):
            button.setEnabled(False)
            button.clicked.connect(lambda _checked=False, p=positive: self._feedback(p))
            utility_row.addWidget(button)
        layout.addLayout(utility_row)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.mic_btn = QPushButton("Voz")
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.setFixedWidth(54)
        self.mic_btn.setStyleSheet(
            "QPushButton{background:#202123;color:#c5c5d0;border:1px solid #303136;"
            "border-radius:13px;padding:12px 8px} QPushButton:hover{background:#2a2b2f;color:white}"
        )
        self.mic_btn.clicked.connect(self._on_mic_clicked)
        input_row.addWidget(self.mic_btn)

        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("Pergunte qualquer coisa...")
        self.input_line.setMinimumHeight(48)
        self.input_line.setStyleSheet(
            "QLineEdit{background:#202123;color:#f4f4f5;border:1px solid #34353a;"
            "border-radius:13px;padding:0 16px;font:13px 'Segoe UI'}"
            "QLineEdit:focus{border-color:#565861;background:#242528}"
            "QLineEdit:disabled{color:#6f7077}"
        )
        self.input_line.returnPressed.connect(self._on_send)
        input_row.addWidget(self.input_line, stretch=1)

        self.send_btn = QPushButton("Enviar  →")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setMinimumHeight(48)
        self.send_btn.setStyleSheet(
            "QPushButton{background:#f4f4f5;color:#111113;border:0;border-radius:13px;"
            "padding:0 20px;font:bold 12px 'Segoe UI'}"
            "QPushButton:hover{background:white} QPushButton:disabled{background:#292a2e;color:#66676e}"
        )
        self.send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self.send_btn)

        self.cancel_btn = QPushButton("Parar")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_current)
        self.cancel_btn.setMinimumHeight(48)
        self.cancel_btn.setStyleSheet(
            "QPushButton{background:#2a1d20;color:#ffb4bd;border:1px solid #683039;"
            "border-radius:13px;padding:0 14px} QPushButton:disabled{background:#191a1d;"
            "color:#55565c;border-color:#242529}"
        )
        input_row.addWidget(self.cancel_btn)

        layout.addLayout(input_row)
        hint = QLabel("Enter para enviar  ·  Esc para parar  ·  Ctrl+Espaço para focar")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color:#5f6067;font:10px 'Segoe UI'")
        layout.addWidget(hint)
        self.input_line.setFocus()

    def _greet(self):
        self._append_jarvis(
            f"{NOME} pronto. Digite /ajuda para ver o que eu sei fazer, ou peça "
            "para eu abrir um programa (ex.: \"abra o navegador\")."
        )
        if self.jarvis.ia_manager is None:
            self._append_jarvis(
                "Nenhum provedor de IA externo configurado ainda (isso é "
                "opcional). Para configurar, rode 'python main.py --texto' e "
                "use o comando /configurarapi."
            )

    def _flash_chat(self):
        """Pisca a borda do chat brevemente quando uma mensagem nova
        chega -- QTextEdit já usa `setGraphicsEffect` pro glow (só
        aceita UM efeito por vez), então em vez de uma animação de
        opacidade via QGraphicsOpacityEffect (que substituiria o glow),
        o "flash" aqui troca a cor da borda via stylesheet por um
        instante e volta, sem mexer no efeito gráfico existente."""
        self.chat_log.setStyleSheet(self._chat_log_style_flash)
        QTimer.singleShot(280, lambda: self.chat_log.setStyleSheet(self._chat_log_style_normal))

    def _append_user(self, text: str):
        self.chat_log.append(
            f'<div style="margin-top:12px; margin-bottom:18px; margin-left:90px; '
            f'padding:11px 15px; background-color:#25262a; color:#f4f4f5;">'
            f'<span style="color:#a9a9b2;font-size:11px;">VOCÊ</span><br>'
            f'{html.escape(text)}</div>'
        )
        self._flash_chat()

    def _append_jarvis(self, text: str):
        body = html.escape(text)
        body = re.sub(
            r"(https?://[^\s&lt;&gt;]+)",
            r'<a style="color:#62b8ff" href="\1">\1</a>',
            body,
        ).replace("\n", "<br>")
        self.chat_log.append(
            f'<div style="margin-top:12px; margin-bottom:20px; margin-right:70px; '
            f'padding:8px 5px; color:#e7e7ec;">'
            f'<span style="color:#7aa2f7;font-size:11px;">{NOME.upper()}</span><br>'
            f'{body}</div>'
        )
        self.chat_log.moveCursor(QTextCursor.End)
        self._flash_chat()

    def _on_send(self):
        text = self.input_line.text().strip()
        if not text or self.jarvis is None:
            return
        if self._worker is not None:
            self.input_line.clear()
            self._message_queue.append(text)
            self.status_label.setText(
                f"{len(self._message_queue)} mensagem(ns) aguardando na fila")
            return
        self.input_line.clear()
        self._append_user(text)

        if text.lower() in ("/sair", "/exit", "/quit"):
            self.close()
            return

        if SAVE_INTENT_RE.search(text):
            # Intercepta AQUI, antes de `_ProcessWorker`/`Jarvis.process()`
            # -- essencial pra segurança: process() grava toda mensagem no
            # histórico de conversa, e "salvar login" nunca deve levar uma
            # senha por esse caminho (ver plugins/logins_web.py). Abre o
            # mesmo diálogo seguro que antes era só um botão.
            m = _SAVE_LOGIN_SITE_RE.search(text)
            site_prefill = m.group(1).strip(" ,.!?") if m else ""
            self._append_jarvis(
                "Abrindo o diálogo seguro pra salvar o login (usuário/senha não passam pelo chat)."
            )
            self._abrir_dialogo_login(site_prefill)
            return

        self.send_btn.setEnabled(True)
        self.input_line.setEnabled(True)
        self.mic_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._pensando_dots = 0
        self.status_label.setText(f"{NOME} está pensando")
        self._pensando_timer.start()
        self._acender_nucleo(text)
        self._resposta_inicio = time.monotonic()

        self._worker = _ProcessWorker(self.jarvis, text, parent=self)
        self._worker._cancelled = False
        self._worker.done.connect(self._on_response)
        self._worker.finished.connect(self._on_process_finished)
        self._worker.start()

    def _on_process_finished(self):
        # O sinal com a resposta pode chegar um pouco antes de finished.
        # Só aqui é seguro permitir que o objeto QThread seja descartado.
        if self._worker is not None:
            self._worker.deleteLater()
            if getattr(self._worker, "_cancelled", False):
                self._pensando_timer.stop()
                self.orb.reset()
                self._append_jarvis("Operação cancelada. A resposta foi descartada.")
                self._worker = None
                self.send_btn.setEnabled(True)
                self.input_line.setEnabled(True)
                self.mic_btn.setEnabled(True)
                self.cancel_btn.setEnabled(False)
                self._start_next_queued()
        self._fechar_quando_seguro()

    def _acender_nucleo(self, text: str):
        """Escolhe o modo do núcleo (`gui/neutron_core.py`) pela mensagem --
        pesquisar EJETA faíscas pra fora, aprender puxa partículas de
        dado PRA DENTRO, o resto é o trabalho normal (pulso/energia). É
        só um sinal visual pelo tipo do pedido; qualquer um deles ainda é
        o Jarvis processando."""
        low = text.lower()
        if any(k in low for k in ("pesquisa", "procura na internet", "navega na internet",
                                   "investiga", "descubra", "descobre", "busca na")):
            self.orb.set_searching(True)
        elif any(k in low for k in ("aprend", "habilidade", "inventa uma", "sonha uma", "consolida")):
            self.orb.set_learning(True)
        else:
            self.orb.set_thinking(True)

    # Duração mínima que o núcleo fica "aceso" (pensando/aprendendo/
    # pesquisando) antes de voltar ao ocioso -- MUITAS respostas
    # (comandos locais, sem IA) voltam em bem menos que isso, e sem um
    # piso a animação praticamente não dava tempo de ficar visível
    # (só um "pisca" de poucos quadros) antes de já reverter -- por
    # isso parecia "não funcionar", mesmo a lógica de cor/energia
    # estando correta por baixo.
    _DURACAO_MINIMA_NUCLEO = 0.9

    def _on_response(self, resposta: str):
        if self._worker is not None and getattr(self._worker, "_cancelled", False):
            return
        decorrido = time.monotonic() - self._resposta_inicio
        faltam = self._DURACAO_MINIMA_NUCLEO - decorrido
        if faltam > 0:
            QTimer.singleShot(int(faltam * 1000), lambda: self._finalizar_resposta(resposta))
        else:
            self._finalizar_resposta(resposta)

    def _finalizar_resposta(self, resposta: str):
        self._pensando_timer.stop()
        self._append_jarvis(resposta)
        self.status_label.setText(f"Pronto — sessão de {self.user_id}")
        self.orb.set_thinking(False)
        self.send_btn.setEnabled(True)
        self.input_line.setEnabled(True)
        self.mic_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.input_line.setFocus()
        self._worker = None
        self._last_response = resposta
        self.good_btn.setEnabled(True)
        self.bad_btn.setEnabled(True)
        if self.jarvis is not None and not get_settings().get("privacidade.modo_privado", False):
            elapsed = max(0.0, time.monotonic() - self._resposta_inicio)
            self.jarvis.memory.log_event(
                "performance_resposta", f"segundos={elapsed:.3f} caracteres={len(resposta)}")
        self._falar(resposta)
        self._start_next_queued()

    def _start_next_queued(self):
        if self._worker is not None or not self._message_queue:
            return
        text = self._message_queue.pop(0)
        self.input_line.setText(text)
        QTimer.singleShot(0, self._on_send)


def _ask_username() -> str:
    """Sugere o último usuário usado (config.json -> geral.usuario_padrao)
    em vez de sempre cair pro literal "default_user" -- sem isso, digitar
    o nome numa sessão e só apertar ENTER na próxima criava um perfil/
    memória SEPARADO a cada vez, e o Jarvis parecia "esquecer" tudo
    porque, na prática, estava conversando com um usuário diferente."""
    settings = get_settings()
    padrao = settings.get("geral.usuario_padrao", "default_user")
    text, ok = QInputDialog.getText(
        None, NOME, f"Nome de usuário (ENTER para continuar como '{padrao}'):",
        QLineEdit.Normal, "",
    )
    if not ok or not text.strip():
        return padrao
    digitado = text.strip()
    if digitado != padrao:
        settings.set("geral.usuario_padrao", digitado)
        settings.save()
    return digitado


def _forcar_foco_win32(window):
    """AttachThreadInput: o jeito "de verdade" de um processo trazer a
    própria janela pro primeiro plano no Windows, mesmo com o bloqueio
    de foco ativo. `SetForegroundWindow` sozinho só funciona se quem
    chama JÁ é o processo em primeiro plano -- testado e confirmado
    neste projeto: rodando de um terminal que estava em foco, a chamada
    funcionava; mas o PRÓPRIO processo do Jarvis chamando
    `activateWindow()`/`SetForegroundWindow` de dentro de si mesmo,
    logo depois de iniciar (como acontece com qualquer app lançado por
    um atalho/script), era recusada -- a janela existia, maximizada,
    visível, mas o foco continuava com quem lançou o processo. O
    workaround documentado da própria Microsoft pra esse bloqueio:
    "grudar" temporariamente a thread de entrada da janela que está em
    foco na nossa, chamar SetForegroundWindow (agora permitido, pois as
    threads contam como uma só pro Windows), e desgrudar em seguida."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(window.winId())
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        foreground_hwnd = user32.GetForegroundWindow()
        foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None)
        current_thread = kernel32.GetCurrentThreadId()

        anexado = False
        if foreground_thread and foreground_thread != current_thread:
            anexado = bool(user32.AttachThreadInput(foreground_thread, current_thread, True))
        try:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE (garante que não está minimizada)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
        finally:
            if anexado:
                user32.AttachThreadInput(foreground_thread, current_thread, False)
    except Exception:
        pass


def _forcar_foco(window):
    """Traz a janela pra frente DE VERDADE. O Windows bloqueia um
    processo em segundo plano de "roubar" o foco de quem está em uso
    (SetForegroundWindow restrito) -- reproduzido e confirmado: a
    janela abria (existia, maximizada, IsWindowVisible=True) mas ficava
    atrás de qualquer outra janela em foco, parecendo "não abriu" pro
    usuário mesmo o processo estando de pé e respondendo. Combina duas
    táticas: o truque Qt de "sempre no topo" por um instante (funciona
    na maioria dos casos) e, no Windows, o AttachThreadInput via WinAPI
    direto (mais confiável, não depende do gerenciador de janelas
    aceitar o WindowStaysOnTopHint)."""
    window.setWindowState(window.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
    window.show()
    window.raise_()
    window.activateWindow()
    window.setWindowFlags(window.windowFlags() | Qt.WindowStaysOnTopHint)
    window.show()
    _forcar_foco_win32(window)
    QTimer.singleShot(200, lambda: (
        window.setWindowFlags(window.windowFlags() & ~Qt.WindowStaysOnTopHint),
        window.show(),
        window.raise_(),
        window.activateWindow(),
        _forcar_foco_win32(window),
    ))


def _abrir_janela_principal(app, user_id: str):
    if not user_id or not user_id.strip():
        user_id = _ask_username()
    window = MainWindow(user_id)
    # guarda a referência no app pra não ser coletada pelo GC quando a
    # função de callback da intro retornar.
    app._jarvis_window = window
    # Abre maximizada (ocupa a tela toda, mas mantém barra de título/
    # botões e a barra de tarefas do Windows continua visível -- pedido
    # explícito do usuário, "tela cheia" no sentido maximizado, não
    # kiosk/borderless). resize() em __init__ continua servindo de
    # tamanho de volta caso o usuário desmaximize manualmente depois.
    window.showMaximized()
    _forcar_foco(window)


def run_gui():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    usar_intro = bool(get_settings().get("geral.intro_animada", True))
    if not usar_intro:
        _abrir_janela_principal(app, _ask_username())
        sys.exit(app.exec())

    # Abertura curta (gui/intro.py): prepara visualmente o carregamento
    # e identifica o operador. Esc pula; qualquer falha cai pro fluxo
    # simples, para a abertura nunca impedir o Neutron de iniciar.
    try:
        from gui.intro import IntroSequence

        intro = IntroSequence()
        intro.setWindowTitle(NOME)
        intro.resize(880, 680)
        app._jarvis_intro = intro

        def _ao_concluir(nome: str):
            intro.close()
            _abrir_janela_principal(app, nome)

        intro.concluido.connect(_ao_concluir)
        # Maximizada também -- senão a intro aparece pequena e a janela
        # principal "salta" pra tela cheia logo em seguida, inconsistente.
        intro.showMaximized()
        _forcar_foco(intro)
    except Exception:
        _abrir_janela_principal(app, _ask_username())

    sys.exit(app.exec())
