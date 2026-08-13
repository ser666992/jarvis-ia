"""Central de controle do Neutron.

Reúne diagnóstico, atividades, memória, plugins, integrações, privacidade,
perfis, lembretes, comandos rápidos e exportação criptografada.
"""

import json
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
    QWidget,
)

from config.settings import get_settings
from core.memory import MEMORY_CATEGORIES
from core.personality import NOME


class ControlCenter(QDialog):
    commandRequested = Signal(str)

    def __init__(self, jarvis, parent=None):
        super().__init__(parent)
        self.jarvis = jarvis
        self.settings = get_settings()
        self.setWindowTitle(f"{NOME} — Central de controle")
        self.resize(940, 680)
        self.setStyleSheet(
            "QDialog,QWidget{background:#0d0f12;color:#ececf1;font-family:'Segoe UI'}"
            "QLineEdit,QTextEdit,QComboBox,QSpinBox,QTableWidget{background:#17181b;"
            "color:#ececf1;border:1px solid #2d2e33;border-radius:7px;padding:7px}"
            "QHeaderView::section{background:#202123;color:#a9a9b2;border:0;"
            "border-bottom:1px solid #303136;padding:7px}"
            "QPushButton{background:#202123;color:#d4d4dc;border:1px solid #34353a;"
            "border-radius:8px;padding:7px 12px}"
            "QPushButton:hover{background:#2a2b2f;color:white}"
            "QPushButton:checked{background:#2f6fed;color:white;border-color:#2f6fed}"
            "QTabWidget::pane{border:1px solid #25262a;border-radius:9px;top:-1px}"
            "QTabBar::tab{background:#121315;color:#8e8e9c;padding:9px 13px;"
            "border-bottom:2px solid transparent}"
            "QTabBar::tab:hover{color:#d4d4dc;background:#191a1d}"
            "QTabBar::tab:selected{background:#191a1d;color:white;border-bottom:2px solid #2f6fed}"
            "QScrollBar:vertical{background:transparent;width:8px}"
            "QScrollBar::handle:vertical{background:#3a3b40;border-radius:4px;min-height:25px}"
        )
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self._build_diagnostico()
        self._build_atividade()
        self._build_memoria()
        self._build_integracoes()
        self._build_plugins()
        self._build_preferencias()
        self._build_agenda()
        self._build_projects()
        self._build_security()
        self._build_performance()
        self._build_missions()
        self._build_updates()

    @staticmethod
    def _table(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def _build_diagnostico(self):
        page, layout = QWidget(), QVBoxLayout()
        page.setLayout(layout)
        row = QHBoxLayout()
        self.diag_summary = QLabel()
        btn = QPushButton("Atualizar diagnóstico")
        btn.clicked.connect(self.refresh_diagnostico)
        row.addWidget(self.diag_summary, 1)
        row.addWidget(btn)
        layout.addLayout(row)
        self.diag_table = self._table(["Estado", "Área", "Recurso", "Detalhe"])
        layout.addWidget(self.diag_table)
        self.tabs.addTab(page, "Diagnóstico")
        self.refresh_diagnostico()

    def refresh_diagnostico(self):
        from core.diagnostico import rodar_diagnostico
        items = rodar_diagnostico()
        self.diag_table.setRowCount(len(items))
        ok_count = 0
        for row, item in enumerate(items):
            ok_count += int(item["ok"])
            values = ["✓ Pronto" if item["ok"] else "⚠ Atenção",
                      item["area"], item["nome"], item["detalhe"]]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if col == 0:
                    cell.setForeground(Qt.green if item["ok"] else Qt.yellow)
                self.diag_table.setItem(row, col, cell)
        self.diag_summary.setText(f"{ok_count}/{len(items)} recursos prontos")
        self.diag_table.resizeColumnsToContents()

    def _build_atividade(self):
        page, layout = QWidget(), QVBoxLayout()
        page.setLayout(layout)
        row = QHBoxLayout()
        self.activity_filter = QLineEdit()
        self.activity_filter.setPlaceholderText("Filtrar atividades...")
        self.activity_filter.textChanged.connect(self.refresh_atividade)
        btn = QPushButton("Atualizar")
        btn.clicked.connect(self.refresh_atividade)
        row.addWidget(self.activity_filter, 1)
        row.addWidget(btn)
        layout.addLayout(row)
        self.activity_table = self._table(["Quando", "Tipo", "Descrição"])
        layout.addWidget(self.activity_table)
        self.tabs.addTab(page, "Atividade")
        self.refresh_atividade()

    def refresh_atividade(self):
        filtro = self.activity_filter.text().lower() if hasattr(self, "activity_filter") else ""
        events = self.jarvis.memory.recent_events(300)
        events = [e for e in events if not filtro or filtro in
                  f"{e['event_type']} {e.get('description', '')}".lower()]
        self.activity_table.setRowCount(len(events))
        for row, event in enumerate(events):
            for col, value in enumerate((event["timestamp"][:19], event["event_type"],
                                         event.get("description") or "")):
                self.activity_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.activity_table.resizeColumnsToContents()

    def _build_memoria(self):
        page, layout = QWidget(), QVBoxLayout()
        page.setLayout(layout)
        controls = QHBoxLayout()
        self.memory_search = QLineEdit()
        self.memory_search.setPlaceholderText("Pesquisar memória...")
        self.memory_search.textChanged.connect(self.refresh_memoria)
        for label, callback in (("Adicionar", self.add_memory), ("Editar", self.edit_memory),
                                ("Apagar", self.delete_memory),
                                ("Lembrar por 24h", self.add_temp_memory),
                                ("Atualizar", self.refresh_memoria)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        controls.insertWidget(0, self.memory_search, 1)
        layout.addLayout(controls)
        self.memory_table = self._table(["Categoria", "Título", "Conteúdo", "Prioridade"])
        layout.addWidget(self.memory_table)
        self.tabs.addTab(page, "Memória")
        self.refresh_memoria()

    def refresh_memoria(self):
        query = self.memory_search.text().strip() if hasattr(self, "memory_search") else ""
        items = (self.jarvis.memory.search_memory(self.jarvis.user_id, query, limit=300)
                 if query else self.jarvis.memory.list_memory(self.jarvis.user_id, limit=300))
        self.memory_table.setRowCount(len(items))
        for row, item in enumerate(items):
            for col, value in enumerate((item["category"], item["title"],
                                         item["content"], item["priority"])):
                self.memory_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.memory_table.resizeColumnsToContents()

    def _memory_dialog(self, existing=None):
        category, ok = QInputDialog.getItem(
            self, "Categoria", "Categoria:", list(MEMORY_CATEGORIES),
            list(MEMORY_CATEGORIES).index(existing["category"]) if existing else 0, False)
        if not ok:
            return None
        title, ok = QInputDialog.getText(self, "Título", "Título:",
                                         text=existing["title"] if existing else "")
        if not ok or not title.strip():
            return None
        content, ok = QInputDialog.getMultiLineText(
            self, "Conteúdo", "Conteúdo:", existing["content"] if existing else "")
        if not ok or not content.strip():
            return None
        priority, ok = QInputDialog.getInt(
            self, "Prioridade", "0 a 100:", existing["priority"] if existing else 50, 0, 100)
        return (category, title.strip(), content.strip(), priority) if ok else None

    def add_memory(self):
        data = self._memory_dialog()
        if data:
            self.jarvis.memory.save_memory(self.jarvis.user_id, *data)
            self.refresh_memoria()

    def _selected_memory(self):
        row = self.memory_table.currentRow()
        if row < 0:
            return None
        return self.jarvis.memory.get_memory(
            self.jarvis.user_id, self.memory_table.item(row, 0).text(),
            self.memory_table.item(row, 1).text())

    def edit_memory(self):
        old = self._selected_memory()
        if not old:
            return
        data = self._memory_dialog(old)
        if data:
            if data[:2] != (old["category"], old["title"]):
                self.jarvis.memory.remove_memory(
                    self.jarvis.user_id, old["category"], old["title"])
            self.jarvis.memory.save_memory(self.jarvis.user_id, *data)
            self.refresh_memoria()

    def delete_memory(self):
        item = self._selected_memory()
        if item and QMessageBox.question(
                self, NOME, f'Apagar a memória "{item["title"]}"?') == QMessageBox.Yes:
            self.jarvis.memory.remove_memory(
                self.jarvis.user_id, item["category"], item["title"])
            self.refresh_memoria()

    def add_temp_memory(self):
        content, ok = QInputDialog.getMultiLineText(
            self, "Memória temporária", "O que devo lembrar pelas próximas 24 horas?")
        if ok and content.strip():
            from core.advanced import remember_temporarily
            remember_temporarily(self.jarvis.user_id, content, 24)
            QMessageBox.information(self, NOME, "Memória temporária salva por 24 horas.")

    def _build_integracoes(self):
        page, form = QWidget(), QFormLayout()
        page.setLayout(form)
        cfg = self.settings.get_provider_config("nvidia")
        self.nvidia_key = QLineEdit(cfg.get("api_key", ""))
        self.nvidia_key.setEchoMode(QLineEdit.Password)
        self.nvidia_model = QLineEdit(cfg.get("modelo", "meta/llama-3.1-70b-instruct"))
        form.addRow("NVIDIA API key:", self.nvidia_key)
        form.addRow("Modelo NVIDIA:", self.nvidia_model)
        save = QPushButton("Salvar NVIDIA")
        save.clicked.connect(self.save_nvidia)
        test = QPushButton("Testar NVIDIA")
        test.clicked.connect(lambda: self.commandRequested.emit("diagnóstico completo"))
        row = QHBoxLayout()
        row.addWidget(save); row.addWidget(test)
        form.addRow(row)
        self.instagram_status = QLabel("Status ainda não verificado")
        form.addRow("Instagram:", self.instagram_status)
        self.instagram_mode = QComboBox()
        self.instagram_mode.addItem("Perfil separado do Neutron (recomendado)", "dedicado")
        self.instagram_mode.addItem("Reaproveitar meu navegador", "navegador")
        saved_mode = self.settings.get("instagram.modo_conexao", "dedicado")
        self.instagram_mode.setCurrentIndex(max(0, self.instagram_mode.findData(saved_mode)))
        form.addRow("Forma de conexão:", self.instagram_mode)
        self.instagram_reply_profile = QComboBox()
        for label, value in (
            ("Casual", "casual"), ("Profissional", "profissional"),
            ("Atendimento", "atendimento"), ("Vendas", "vendas"),
            ("Amigos", "amigos"),
        ):
            self.instagram_reply_profile.addItem(label, value)
        saved_profile = self.settings.get("instagram.perfil_resposta", "casual")
        self.instagram_reply_profile.setCurrentIndex(
            max(0, self.instagram_reply_profile.findData(saved_profile)))
        self.instagram_reply_profile.currentIndexChanged.connect(
            self.save_instagram_reply_profile)
        form.addRow("Estilo das respostas:", self.instagram_reply_profile)
        self.instagram_help = QLabel(
            "O login abre diretamente no Instagram. O Neutron não recebe nem salva sua senha.")
        self.instagram_help.setWordWrap(True)
        form.addRow(self.instagram_help)
        row2 = QHBoxLayout()
        connect = QPushButton("Conectar Instagram")
        connect.clicked.connect(self.connect_instagram)
        verify = QPushButton("Verificar sessão")
        verify.clicked.connect(self.verify_instagram)
        close = QPushButton("Fechar janela")
        close.clicked.connect(self.close_instagram_session)
        row2.addWidget(connect); row2.addWidget(verify); row2.addWidget(close)
        form.addRow(row2)
        self._instagram_timer = QTimer(self)
        self._instagram_timer.setInterval(3000)
        self._instagram_timer.timeout.connect(self.verify_instagram)
        self._instagram_checks = 0
        self.tabs.addTab(page, "Integrações")

    def save_nvidia(self):
        key = self.nvidia_key.text().strip()
        if key:
            try:
                from seguranca.vault import set_secret
                set_secret("ia.nvidia.api_key", key)
                self.settings.set("ia.provedores.nvidia.api_key", "")
            except Exception as e:
                QMessageBox.critical(self, NOME, f"Não consegui usar o cofre seguro: {e}")
                return
        self.settings.set("ia.provedores.nvidia.modelo", self.nvidia_model.text().strip())
        self.settings.save()
        if self.jarvis.ia_manager:
            self.jarvis.ia_manager.refresh()
        QMessageBox.information(self, NOME, "Configuração NVIDIA salva.")

    def connect_instagram(self):
        from automacao import instagram_auto
        if not instagram_auto.available():
            QMessageBox.warning(
                self, NOME, "O Playwright/Chromium não está instalado para abrir o Instagram.")
            return
        self.save_instagram_reply_profile()
        self.instagram_status.setText("Abrindo o Instagram…")
        try:
            mensagem = instagram_auto.conectar_instagram(self.instagram_mode.currentData())
        except Exception as e:
            self.instagram_status.setText("⚠ Falha ao abrir")
            QMessageBox.critical(self, NOME, f"Não consegui abrir o Instagram:\n{e}")
            return
        self._instagram_checks = 0
        self._instagram_timer.start()
        self.instagram_status.setText("Aguardando login/2FA no Instagram…")
        QMessageBox.information(
            self, "Conectar Instagram",
            mensagem + "\n\nPode voltar para esta janela: a confirmação será automática.")

    def save_instagram_reply_profile(self):
        self.settings.set(
            "instagram.perfil_resposta", self.instagram_reply_profile.currentData())
        self.settings.save()

    def verify_instagram(self):
        from automacao import instagram_auto
        labels = {
            "indisponivel": "⚠ Integração indisponível",
            "conectado": "✓ Conta conectada e confirmada",
            "verificacao": "● Conclua a verificação/2FA no Instagram",
            "desconectado": "● Aguardando login no Instagram",
            "carregando": "● Carregando Instagram…",
            "erro": "⚠ Não foi possível verificar",
        }
        estado = instagram_auto.estado_conexao()
        self.instagram_status.setText(labels.get(estado, labels["erro"]))
        self._instagram_checks += 1
        if estado == "conectado":
            self._instagram_timer.stop()
            try:
                from core.timeline import registrar
                registrar("instagram_conectado", "")
            except Exception:
                pass
        elif self._instagram_checks >= 40:
            self._instagram_timer.stop()

    def close_instagram_session(self):
        from automacao import instagram_auto
        instagram_auto.fechar_sessao()
        self._instagram_timer.stop()
        self.instagram_status.setText("Janela fechada — a sessão salva foi preservada")

    def _build_plugins(self):
        page, layout = QWidget(), QVBoxLayout()
        page.setLayout(layout)
        layout.addWidget(QLabel("Desmarque uma habilidade para impedir que ela receba comandos."))
        self.plugin_table = self._table(["Ativo", "Plugin", "Descrição"])
        layout.addWidget(self.plugin_table)
        btn = QPushButton("Salvar estado dos plugins")
        btn.clicked.connect(self.save_plugins)
        snapshot_btn = QPushButton("Criar snapshot do selecionado")
        snapshot_btn.clicked.connect(self.snapshot_plugin)
        rollback_btn = QPushButton("Restaurar versão anterior")
        rollback_btn.clicked.connect(self.rollback_plugin)
        row = QHBoxLayout()
        row.addWidget(btn); row.addWidget(snapshot_btn); row.addWidget(rollback_btn)
        layout.addLayout(row)
        self.tabs.addTab(page, "Habilidades")
        disabled = set(self.settings.get("plugins.desativados", []) or [])
        plugins = self.jarvis.plugins.list_plugins()
        self.plugin_table.setRowCount(len(plugins))
        for row, (name, desc) in enumerate(plugins):
            active = QTableWidgetItem()
            active.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            active.setCheckState(Qt.Unchecked if name in disabled else Qt.Checked)
            self.plugin_table.setItem(row, 0, active)
            self.plugin_table.setItem(row, 1, QTableWidgetItem(name))
            self.plugin_table.setItem(row, 2, QTableWidgetItem(desc))
        self.plugin_table.resizeColumnsToContents()

    def save_plugins(self):
        disabled = []
        for row in range(self.plugin_table.rowCount()):
            if self.plugin_table.item(row, 0).checkState() != Qt.Checked:
                disabled.append(self.plugin_table.item(row, 1).text())
        self.settings.set("plugins.desativados", disabled)
        self.settings.save()
        QMessageBox.information(self, NOME, "Estado das habilidades salvo.")

    def _selected_plugin(self):
        row = self.plugin_table.currentRow()
        if row < 0:
            return None
        name = self.plugin_table.item(row, 1).text()
        return next((p for p in self.jarvis.plugins.plugins if p.name == name), None)

    def snapshot_plugin(self):
        plugin = self._selected_plugin()
        path = getattr(plugin, "_jarvis_source_path", "") if plugin else ""
        if not path:
            return
        from core.plugin_sandbox import snapshot
        saved = snapshot(path)
        QMessageBox.information(self, NOME, f"Snapshot criado:\n{saved}")

    def rollback_plugin(self):
        plugin = self._selected_plugin()
        path = getattr(plugin, "_jarvis_source_path", "") if plugin else ""
        if not path:
            return
        from core.plugin_sandbox import restore, versions
        available = versions(path)
        if not available:
            QMessageBox.information(self, NOME, "Nenhuma versão anterior disponível.")
            return
        if QMessageBox.question(
                self, NOME, f"Restaurar a versão mais recente de {plugin.name}?") != QMessageBox.Yes:
            return
        restore(path, available[0])
        self.jarvis.reload_plugins()
        QMessageBox.information(self, NOME, "Versão restaurada e plugins recarregados.")

    def _build_preferencias(self):
        page, form = QWidget(), QFormLayout()
        page.setLayout(form)
        self.private = QCheckBox("Não salvar conversas, aprendizado nem eventos")
        self.private.setChecked(bool(self.settings.get("privacidade.modo_privado", False)))
        self.offline = QCheckBox("Ativar modelo local como fallback offline")
        self.offline.setChecked(bool(self.settings.get("ia.modelo_local.ativar", True)))
        self.sources = QCheckBox("Exibir confiança nas respostas")
        self.sources.setChecked(bool(self.settings.get("personalidade.mostrar_confianca", False)))
        self.profile = QComboBox()
        self.profile.addItems(["pessoal", "trabalho", "estudos", "jogos"])
        self.profile.setCurrentText(self.settings.get("geral.perfil_uso", "pessoal"))
        self.permission_internet = QCheckBox("Permitir pesquisa e navegação na internet")
        self.permission_pc = QCheckBox("Permitir controle de programas, mouse e teclado")
        self.permission_instagram = QCheckBox("Permitir acesso à integração do Instagram")
        self.permission_devices = QCheckBox("Permitir controle de dispositivos conectados")
        for checkbox, path in (
            (self.permission_internet, "permissoes.internet"),
            (self.permission_pc, "permissoes.controle_pc"),
            (self.permission_instagram, "permissoes.instagram"),
            (self.permission_devices, "permissoes.dispositivos"),
        ):
            checkbox.setChecked(bool(self.settings.get(path, True)))
        self.quick = QTextEdit()
        self.quick.setPlainText("\n".join(self.settings.get(
            "gui.comandos_rapidos", ["diagnóstico completo", "minhas mensagens do instagram",
                                     "o que aconteceu hoje", "meus lembretes"])))
        self.quick.setMaximumHeight(120)
        form.addRow(self.private)
        form.addRow(self.offline)
        form.addRow(self.sources)
        form.addRow("Perfil de uso:", self.profile)
        form.addRow(QLabel("Permissões:"))
        form.addRow(self.permission_internet)
        form.addRow(self.permission_pc)
        form.addRow(self.permission_instagram)
        form.addRow(self.permission_devices)
        form.addRow("Comandos rápidos (um por linha):", self.quick)
        save = QPushButton("Salvar preferências")
        save.clicked.connect(self.save_preferences)
        export = QPushButton("Exportar configuração criptografada")
        export.clicked.connect(self.export_settings)
        import_btn = QPushButton("Importar configuração criptografada")
        import_btn.clicked.connect(self.import_settings)
        row = QHBoxLayout()
        row.addWidget(save); row.addWidget(export); row.addWidget(import_btn)
        form.addRow(row)
        self.tabs.addTab(page, "Privacidade e perfis")

    def save_preferences(self):
        self.settings.set("privacidade.modo_privado", self.private.isChecked())
        self.settings.set("ia.modelo_local.ativar", self.offline.isChecked())
        self.settings.set("personalidade.mostrar_confianca", self.sources.isChecked())
        self.settings.set("geral.perfil_uso", self.profile.currentText())
        self.settings.set("permissoes.internet", self.permission_internet.isChecked())
        self.settings.set("permissoes.controle_pc", self.permission_pc.isChecked())
        self.settings.set("permissoes.instagram", self.permission_instagram.isChecked())
        self.settings.set("permissoes.dispositivos", self.permission_devices.isChecked())
        self.settings.set("gui.comandos_rapidos", [
            x.strip() for x in self.quick.toPlainText().splitlines() if x.strip()])
        self.settings.save()
        QMessageBox.information(self, NOME, "Preferências salvas.")

    def export_settings(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar configuração", f"neutron_config_{datetime.now():%Y%m%d}.neutron",
            "Configuração Neutron (*.neutron)")
        if not path:
            return
        from seguranca.crypto import encrypt, is_real_encryption
        if not is_real_encryption():
            QMessageBox.warning(self, NOME, "Instale 'cryptography' para exportação realmente criptografada.")
            return
        token = encrypt(json.dumps(self.settings.data, ensure_ascii=False))
        with open(path, "w", encoding="utf-8") as f:
            f.write(token)
        QMessageBox.information(self, NOME, "Configuração exportada com criptografia.")

    def import_settings(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar configuração", "", "Configuração Neutron (*.neutron)")
        if not path:
            return
        try:
            from seguranca.crypto import decrypt
            with open(path, "r", encoding="utf-8") as f:
                data = json.loads(decrypt(f.read().strip()))
            if not isinstance(data, dict) or "geral" not in data:
                raise ValueError("arquivo não contém uma configuração válida")
            if QMessageBox.question(
                    self, NOME, "Substituir a configuração atual pela importada?") != QMessageBox.Yes:
                return
            self.settings._data = data
            self.settings.save()
            if self.jarvis.ia_manager:
                self.jarvis.ia_manager.refresh()
            QMessageBox.information(self, NOME, "Configuração importada. Reinicie para aplicar tudo.")
        except Exception as e:
            QMessageBox.critical(self, NOME, f"Falha ao importar: {e}")

    def _build_agenda(self):
        page, layout = QWidget(), QVBoxLayout()
        page.setLayout(layout)
        row = QHBoxLayout()
        btn = QPushButton("Atualizar lembretes")
        btn.clicked.connect(self.refresh_reminders)
        command = QPushButton("Criar pelo chat")
        command.clicked.connect(lambda: self.commandRequested.emit(
            "me lembre de revisar o Neutron amanhã às 09:00"))
        row.addWidget(btn); row.addWidget(command)
        layout.addLayout(row)
        self.reminders_table = self._table(["Quando", "Mensagem", "Recorrência"])
        layout.addWidget(self.reminders_table)
        self.tabs.addTab(page, "Agenda")
        self.refresh_reminders()

    def refresh_reminders(self):
        from automacao.reminders import list_pending
        items = list_pending(self.jarvis.user_id)
        self.reminders_table.setRowCount(len(items))
        for row, item in enumerate(items):
            for col, value in enumerate((item["quando"], item["mensagem"],
                                         item.get("intervalo_segundos") or "não")):
                self.reminders_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.reminders_table.resizeColumnsToContents()

    def _build_projects(self):
        page, layout = QWidget(), QVBoxLayout()
        page.setLayout(layout)
        row = QHBoxLayout()
        for label, callback in (
            ("Novo projeto", self.add_project),
            ("Criar checkpoint", self.add_project_checkpoint),
            ("Atualizar", self.refresh_projects),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.projects_table = self._table(["ID", "Projeto", "Descrição", "Status", "Atualizado"])
        layout.addWidget(self.projects_table)
        self.tabs.addTab(page, "Projetos")
        self.refresh_projects()

    def refresh_projects(self):
        from core.advanced import list_projects
        items = list_projects(self.jarvis.user_id)
        self.projects_table.setRowCount(len(items))
        for row, item in enumerate(items):
            for col, value in enumerate((
                item["id"], item["name"], item["description"] or "",
                item["status"], item["updated_at"][:19],
            )):
                self.projects_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.projects_table.resizeColumnsToContents()

    def add_project(self):
        name, ok = QInputDialog.getText(self, "Novo projeto", "Nome:")
        if not ok or not name.strip():
            return
        desc, ok = QInputDialog.getMultiLineText(self, "Novo projeto", "Descrição:")
        if ok:
            from core.advanced import save_project
            save_project(self.jarvis.user_id, name, desc)
            self.refresh_projects()

    def add_project_checkpoint(self):
        row = self.projects_table.currentRow()
        if row < 0:
            return
        title, ok = QInputDialog.getText(self, "Checkpoint", "O que foi concluído/decidido?")
        if ok and title.strip():
            from core.advanced import add_checkpoint
            add_checkpoint(int(self.projects_table.item(row, 0).text()), title)
            QMessageBox.information(self, NOME, "Checkpoint salvo.")

    def _build_security(self):
        page, layout = QWidget(), QVBoxLayout()
        page.setLayout(layout)
        self.security_text = QTextEdit()
        self.security_text.setReadOnly(True)
        layout.addWidget(self.security_text)
        row = QHBoxLayout()
        audit = QPushButton("Auditar plugins")
        audit.clicked.connect(self.audit_plugins)
        simulate = QPushButton("Simular automação")
        simulate.clicked.connect(self.simulate_automation)
        reset = QPushButton("Reativar circuit breakers")
        reset.clicked.connect(self.reset_breakers)
        emergency = QPushButton("PARADA DE EMERGÊNCIA")
        emergency.setStyleSheet(
            "background:#7f1d1d;color:white;border:1px solid #ef4444;font-weight:bold")
        emergency.clicked.connect(self.emergency_stop)
        row.addWidget(audit); row.addWidget(simulate); row.addWidget(reset)
        row.addWidget(emergency)
        layout.addLayout(row)
        self.tabs.addTab(page, "Segurança")
        self.refresh_security()

    def refresh_security(self):
        from core.resilience import status
        state = status()
        text = ["Proteção contra prompt injection: ativa",
                "Cofre de chaves: Credential Manager/keyring",
                f"Circuit breakers com falhas: {len(state)}"]
        for name, item in state.items():
            text.append(f"- {name}: {item['failures']} falha(s)")
        self.security_text.setPlainText("\n".join(text))

    def audit_plugins(self):
        from core.plugin_sandbox import inspect_plugin
        lines, problems = [], 0
        for plugin in self.jarvis.plugins.plugins:
            path = getattr(plugin, "_jarvis_source_path", "")
            if not path:
                continue
            try:
                result = inspect_plugin(path)
                problems += len(result["findings"])
                lines.append(f"{plugin.name}: " + (
                    "OK" if result["ok"] else "; ".join(result["findings"])))
            except Exception as e:
                problems += 1
                lines.append(f"{plugin.name}: erro na auditoria: {e}")
        self.security_text.setPlainText(
            f"Auditoria concluída: {problems} alerta(s)\n\n" + "\n".join(lines))

    def simulate_automation(self):
        text, ok = QInputDialog.getMultiLineText(
            self, "Simular automação", "Um comando por linha:")
        if not ok:
            return
        from automacao.simulator import simulate
        result = simulate(text.splitlines())
        self.security_text.setPlainText("\n".join(
            f"{x['step']}. [{x['risk']}] {x['command']} — NÃO executado" for x in result))

    def reset_breakers(self):
        from core.resilience import reset
        reset()
        self.refresh_security()

    def emergency_stop(self):
        if QMessageBox.question(
                self, NOME,
                "Parar todas as rotinas, automações e a sessão controlada do Instagram?"
                ) != QMessageBox.Yes:
            return
        from core.emergency import stop_all
        result = stop_all()
        self.security_text.setPlainText(
            f"Parada concluída: {result['rotinas_interrompidas']} rotina(s) interrompida(s). "
            "Reinicie o Neutron para reativar as rotinas configuradas.")

    def _build_performance(self):
        page, layout = QWidget(), QVBoxLayout()
        page.setLayout(layout)
        btn = QPushButton("Atualizar métricas")
        btn.clicked.connect(self.refresh_performance)
        layout.addWidget(btn)
        self.performance_table = self._table(
            ["Provedor", "Chamadas", "Sucessos", "Taxa", "Média (ms)"])
        layout.addWidget(self.performance_table)
        self.tabs.addTab(page, "Desempenho")
        self.refresh_performance()

    def refresh_performance(self):
        from core.advanced import provider_summary
        items = provider_summary()
        self.performance_table.setRowCount(len(items))
        for row, item in enumerate(items):
            for col, value in enumerate((
                item["provider"], item["calls"], item["successes"],
                f'{item["success_rate"]}%', item["avg_ms"],
            )):
                self.performance_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.performance_table.resizeColumnsToContents()

    def _build_updates(self):
        page, layout = QWidget(), QVBoxLayout()
        page.setLayout(layout)
        message = QLabel(
            "A versão nova é baixada e testada fora da instalação. "
            "Aplicar exige sua aprovação e uma árvore de trabalho limpa.")
        message.setWordWrap(True)
        layout.addWidget(message)
        row = QHBoxLayout()
        buttons = (
            ("Verificar versão", lambda: self.commandRequested.emit(
                "verifica atualização do jarvis")),
            ("Baixar e testar isoladamente", lambda: self.commandRequested.emit(
                "testa atualização do jarvis")),
            ("Aplicar versão aprovada", self.confirm_update),
            ("Atualizar relatório", self.refresh_updates),
        )
        for title, callback in buttons:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.update_status = QLabel()
        self.update_status.setWordWrap(True)
        layout.addWidget(self.update_status)
        self.update_report = QTextEdit()
        self.update_report.setReadOnly(True)
        layout.addWidget(self.update_report)
        self.tabs.addTab(page, "Atualizações")
        self.refresh_updates()

    def _build_missions(self):
        page, layout = QWidget(), QVBoxLayout()
        page.setLayout(layout)
        layout.addWidget(QLabel(
            "Missões continuam após reiniciar. Passos de alto risco aguardam aprovação."))
        row = QHBoxLayout()
        for title, callback in (
            ("Nova missão", self.new_mission),
            ("Executar/continuar", self.run_mission),
            ("Aprovar passo", self.approve_mission_step),
            ("Atualizar", self.refresh_missions),
        ):
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.missions_table = self._table(
            ["ID", "Status", "Objetivo", "Progresso", "Próximo risco"])
        layout.addWidget(self.missions_table)
        self.tabs.addTab(page, "Missões")
        self.refresh_missions()

    def refresh_missions(self):
        from automacao.missoes import listar
        items = listar(self.jarvis.user_id)
        self.missions_table.setRowCount(len(items))
        for row, mission in enumerate(items):
            done = sum(step["status"] == "concluido" for step in mission["passos"])
            pending = next(
                (step for step in mission["passos"] if step["status"] != "concluido"), {})
            values = (
                mission["id"], mission["status"], mission["objetivo"],
                f"{done}/{len(mission['passos'])}", pending.get("risco", "—"))
            for col, value in enumerate(values):
                self.missions_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.missions_table.resizeColumnsToContents()

    def _selected_mission_id(self):
        row = self.missions_table.currentRow()
        return int(self.missions_table.item(row, 0).text()) if row >= 0 else None

    def new_mission(self):
        objective, ok = QInputDialog.getMultiLineText(
            self, "Nova missão", "Qual resultado o Neutron deve alcançar?")
        if ok and objective.strip():
            self.commandRequested.emit(f"nova missão: {objective.strip()}")

    def run_mission(self):
        mission_id = self._selected_mission_id()
        if mission_id is not None:
            self.commandRequested.emit(f"executa missão {mission_id}")

    def approve_mission_step(self):
        mission_id = self._selected_mission_id()
        if mission_id is None:
            return
        step, ok = QInputDialog.getInt(
            self, "Aprovar passo", "Número do passo:", 1, 1, 20)
        if ok and QMessageBox.question(
                self, NOME, f"Aprovar o passo {step} da missão {mission_id}?"
                ) == QMessageBox.Yes:
            self.commandRequested.emit(f"aprova passo {step} da missão {mission_id}")

    def confirm_update(self):
        if QMessageBox.question(
                self, NOME,
                "Aplicar a versão que passou nos testes isolados? "
                "Alterações locais bloqueiam a operação automaticamente.") == QMessageBox.Yes:
            self.commandRequested.emit("atualiza o jarvis, confirmo")

    def refresh_updates(self):
        from atualizacoes import last_report, working_tree_status
        dirty = working_tree_status()
        self.update_status.setText(
            "✓ Instalação pronta para atualizar"
            if not dirty else
            f"⚠ Atualização protegida: {len(dirty)} alteração(ões) local(is)")
        report = last_report()
        self.update_report.setPlainText(
            json.dumps(report, ensure_ascii=False, indent=2)
            if report else "Nenhuma versão candidata foi testada ainda.")
