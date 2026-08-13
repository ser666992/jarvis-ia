"""
gui/redcore.py
===============
RedCore: o navegador do próprio Ultron -- pedido explícito do usuário
(2026-07-06): "um navegador... pra o Ultron ter acesso a toda internet,
o próprio navegador dele que eu posso usar, e ele vê tudo que eu uso, e
pode apagar a memória dele".

É um navegador REAL (QtWebEngine -- Chromium embutido no Qt, já
disponível no ambiente, mesmo framework de todo o resto da GUI): abas,
barra de endereço, voltar/avançar/recarregar -- não um brinquedo, acessa
qualquer site que um navegador normal acessa.

Roda como processo PRÓPRIO e SEPARADO da janela principal do Jarvis (não
tenta criar uma janela Qt dentro da QThread de outra QApplication --
isso quebraria; ver gui/app.py sobre por que widgets Qt só podem ser
manipulados na thread principal). "abre o redcore" (plugins/redcore.py)
só dá `subprocess.Popen([sys.executable, "-m", "gui.redcore", user_id])`,
igual abrir qualquer outro programa.

"Ele vê tudo que eu uso, incluindo e-mails" (pedido explícito, ainda
mais direto, 2026-07-06): cada navegação registra URL + título + TEXTO
VISÍVEL da página inteira (automacao/redcore_historico.py) -- não é só
metadado. Como webmail (Gmail/Outlook) costuma ser uma SPA que troca de
e-mail sem mudar a URL, cada aba também tira uma "foto" periódica do
texto (`_INTERVALO_CAPTURA_MS`), pra pegar o que você está lendo mesmo
sem navegação nova. Isso NÃO é o histórico interno do Chromium/Qt
(cookies, senhas, cache continuam onde sempre estiveram) -- é um
registro PRÓPRIO do Jarvis, em texto puro no banco local. "Pode apagar
a memória dele": botão "🗑 Limpar histórico" na barra de ferramentas, e
o comando de chat "apaga o histórico do redcore" (plugins/redcore.py).
"""

import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import (
    QApplication, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QTabWidget, QToolBar,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

_PAGINA_INICIAL = "https://www.google.com/"
_INTERVALO_CAPTURA_MS = 20_000  # 20s -- frequente o bastante pra pegar troca de e-mail
_MIN_CONTEUDO_CHARS = 20  # ignora capturas triviais (tela em branco/carregando)

_ESTILO = """
QMainWindow, QWidget { background-color: #0c0505; }
QToolBar { background-color: #1b0f0f; border: none; padding: 4px; spacing: 6px; }
QLineEdit {
    background-color: #1b1010; color: #fbf9f9; border: 1px solid #382323;
    border-radius: 8px; padding: 6px 10px; font-size: 13px;
}
QLineEdit:focus { border: 1px solid #c22a1f; }
QPushButton {
    background-color: #241515; color: #e7e5e5; border: 1px solid #382323;
    border-radius: 8px; padding: 6px 10px;
}
QPushButton:hover { background-color: #351f1f; }
QTabWidget::pane { border: 1px solid #331c1c; }
QTabBar::tab {
    background-color: #1b0f0f; color: #c9baba; padding: 7px 14px;
    border: 1px solid #331c1c; border-bottom: none;
}
QTabBar::tab:selected { background-color: #261010; color: #ff5f52; }
"""


class RedCoreBrowser(QMainWindow):
    def __init__(self, user_id: str = "default_user"):
        super().__init__()
        self.user_id = user_id
        self.setWindowTitle("RedCore")
        self.resize(1200, 800)
        self.setStyleSheet(_ESTILO)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self._fechar_aba)
        self.tabs.currentChanged.connect(self._aba_mudou)
        self.setCentralWidget(self.tabs)

        self._build_toolbar()
        self.nova_aba(_PAGINA_INICIAL)

    # ---------- barra de ferramentas ----------

    def _build_toolbar(self):
        barra = QToolBar()
        barra.setMovable(False)
        self.addToolBar(barra)

        btn_voltar = QPushButton("←")
        btn_voltar.clicked.connect(lambda: self._aba_atual() and self._aba_atual().back())
        barra.addWidget(btn_voltar)

        btn_avancar = QPushButton("→")
        btn_avancar.clicked.connect(lambda: self._aba_atual() and self._aba_atual().forward())
        barra.addWidget(btn_avancar)

        btn_recarregar = QPushButton("⟳")
        btn_recarregar.clicked.connect(lambda: self._aba_atual() and self._aba_atual().reload())
        barra.addWidget(btn_recarregar)

        self.barra_endereco = QLineEdit()
        self.barra_endereco.setPlaceholderText("Digite um endereço ou pesquise...")
        self.barra_endereco.returnPressed.connect(self._navegar_da_barra)
        barra.addWidget(self.barra_endereco)

        btn_nova_aba = QPushButton("+ Aba")
        btn_nova_aba.clicked.connect(lambda: self.nova_aba(_PAGINA_INICIAL))
        barra.addWidget(btn_nova_aba)

        btn_limpar = QPushButton("🗑 Limpar histórico")
        btn_limpar.clicked.connect(self._limpar_historico)
        barra.addWidget(btn_limpar)

    # ---------- abas ----------

    def _aba_atual(self) -> QWebEngineView:
        return self.tabs.currentWidget()

    def nova_aba(self, url: str):
        view = QWebEngineView()
        view._visita_id = -1        # id da linha do histórico da visita atual (redcore_historico)
        view._ultimo_conteudo = None  # último texto capturado -- evita logar a mesma coisa de novo
        view.load(QUrl(url))
        indice = self.tabs.addTab(view, "Nova aba")
        self.tabs.setCurrentIndex(indice)

        view.titleChanged.connect(lambda titulo, v=view: self._titulo_mudou(v, titulo))
        view.urlChanged.connect(lambda qurl, v=view: self._url_mudou(v, qurl))
        view.loadFinished.connect(lambda ok, v=view: self._pagina_carregou(v, ok))

        # Captura periódica -- pega conteúdo que muda SEM navegação nova
        # (trocar de e-mail numa SPA como Gmail/Outlook não muda a URL).
        timer = QTimer(self)
        timer.setInterval(_INTERVALO_CAPTURA_MS)
        timer.timeout.connect(lambda v=view: self._capturar_conteudo_periodico(v))
        timer.start()
        view._timer_captura = timer  # guarda referência (senão o GC do Python pode coletar o timer)
        return view

    def _fechar_aba(self, indice: int):
        widget = self.tabs.widget(indice)
        if widget is not None and hasattr(widget, "_timer_captura"):
            widget._timer_captura.stop()
        self.tabs.removeTab(indice)
        if widget:
            widget.deleteLater()
        if self.tabs.count() == 0:
            self.close()

    def _aba_mudou(self, _indice: int):
        aba = self._aba_atual()
        if aba is not None:
            self.barra_endereco.setText(aba.url().toString())

    def _titulo_mudou(self, view: QWebEngineView, titulo: str):
        indice = self.tabs.indexOf(view)
        if indice != -1:
            texto = (titulo[:24] + "…") if len(titulo) > 24 else (titulo or "Nova aba")
            self.tabs.setTabText(indice, texto)

    def _url_mudou(self, view: QWebEngineView, qurl: QUrl):
        url = qurl.toString()
        if view is self._aba_atual():
            self.barra_endereco.setText(url)
        # Navegação nova de verdade -- abre uma linha NOVA no histórico
        # (o conteúdo/título ainda vão chegar via loadFinished/titleChanged,
        # ver atualizar_conteudo) e reseta o "último conteúdo visto" pra
        # não confundir com o da página anterior nesta mesma aba.
        from automacao import redcore_historico
        try:
            view._visita_id = redcore_historico.registrar_visita(self.user_id, url, view.title())
        except Exception:
            view._visita_id = -1
        view._ultimo_conteudo = None

    def _pagina_carregou(self, view: QWebEngineView, ok: bool):
        if not ok or view is None:
            return

        def _recebeu_texto(texto, v=view):
            if not texto:
                return
            v._ultimo_conteudo = texto
            from automacao import redcore_historico
            try:
                redcore_historico.atualizar_conteudo(
                    getattr(v, "_visita_id", -1), titulo=v.title(), conteudo=texto,
                )
            except Exception:
                pass

        try:
            view.page().toPlainText(_recebeu_texto)
        except Exception:
            pass

    def _capturar_conteudo_periodico(self, view: QWebEngineView):
        """Roda a cada _INTERVALO_CAPTURA_MS por aba -- pega o texto
        atual e, se for DIFERENTE do último capturado (ex.: você trocou
        de e-mail numa SPA sem a URL mudar), registra como uma visita
        NOVA (é conteúdo novo que você olhou, merece linha própria no
        histórico, não só sobrescrever a mesma)."""
        try:
            if view is None or not view.isVisible():
                return
        except RuntimeError:
            return  # widget C++ já destruído (aba fechada); o timer some no próximo _fechar_aba

        def _recebeu_texto(texto, v=view):
            anterior = getattr(v, "_ultimo_conteudo", None)
            if not texto or len(texto.strip()) < _MIN_CONTEUDO_CHARS or texto == anterior:
                return
            v._ultimo_conteudo = texto
            from automacao import redcore_historico
            try:
                v._visita_id = redcore_historico.registrar_visita(
                    self.user_id, v.url().toString(), v.title(), texto,
                )
            except Exception:
                pass

        try:
            view.page().toPlainText(_recebeu_texto)
        except Exception:
            pass

    # ---------- barra de endereço ----------

    def _navegar_da_barra(self):
        texto = self.barra_endereco.text().strip()
        if not texto:
            return
        aba = self._aba_atual()
        if aba is None:
            aba = self.nova_aba(_PAGINA_INICIAL)
        aba.load(QUrl(_resolver_endereco(texto)))

    # ---------- histórico ----------

    def _limpar_historico(self):
        resp = QMessageBox.question(
            self, "Limpar histórico do RedCore",
            "Isso apaga TUDO que o Jarvis registrou (URLs, títulos e o texto das páginas vistas, "
            "incluindo e-mails abertos). Não afeta cookies, senhas salvas ou downloads do "
            "navegador em si. Confirma?",
        )
        if resp != QMessageBox.Yes:
            return
        from automacao import redcore_historico
        total = redcore_historico.limpar_historico(self.user_id)
        QMessageBox.information(self, "Histórico limpo", f"{total} visita(s) removida(s) da memória do Jarvis.")


def _resolver_endereco(texto: str) -> str:
    """Trata a barra de endereço como um navegador de verdade trata:
    URL direta se parecer com uma, senão pesquisa."""
    if texto.startswith("http://") or texto.startswith("https://"):
        return texto
    if "." in texto and " " not in texto:
        return f"https://{texto}"
    import urllib.parse
    return f"https://www.google.com/search?q={urllib.parse.quote(texto)}"


def run_redcore(user_id: str = "default_user"):
    """Sempre roda como processo PRÓPRIO (ver docstring do módulo) --
    por isso sempre cria a QApplication e o loop de eventos aqui, sem
    tentar reaproveitar uma instância existente de outro processo (isso
    não seria possível entre processos separados de qualquer forma)."""
    app = QApplication(sys.argv)
    janela = RedCoreBrowser(user_id)
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    _user_id = sys.argv[1] if len(sys.argv) > 1 else "default_user"
    run_redcore(_user_id)
