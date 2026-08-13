"""Abertura rápida e minimalista do Neutron."""

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from config.settings import get_settings
from core.personality import NOME

_BOOT_SECONDS = 2.4
_WELCOME_SECONDS = 0.9


class IntroSequence(QWidget):
    """Boot curto; mantém a API usada por ``gui.app.run_gui``."""

    concluido = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        settings = get_settings()
        default = settings.get("geral.usuario_padrao", "default_user")
        self._operator = default if default and default != "default_user" else None
        self._typed_name = ""
        self._phase = "boot"
        self._started = time.monotonic()
        self._finished = False
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def showEvent(self, event):
        self.setFocus()
        self._started = time.monotonic()
        if not self._timer.isActive() and not self._finished:
            self._timer.start(16)
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _elapsed(self):
        return time.monotonic() - self._started

    def _change_phase(self, phase):
        self._phase = phase
        self._started = time.monotonic()

    def _tick(self):
        elapsed = self._elapsed()
        if self._phase == "boot" and elapsed >= _BOOT_SECONDS:
            self._change_phase("welcome" if self._operator else "operator")
        elif self._phase in ("welcome", "registered") and elapsed >= _WELCOME_SECONDS:
            self._finish(self._operator or self._typed_name)
        self.update()

    def _finish(self, name):
        if self._finished:
            return
        self._finished = True
        self._timer.stop()
        clean_name = (name or "default_user").strip()[:32] or "default_user"
        if clean_name != "default_user":
            try:
                settings = get_settings()
                settings.set("geral.usuario_padrao", clean_name)
                settings.save()
            except Exception:
                # Falha de persistência não pode prender o usuário na
                # abertura; a sessão ainda inicia com o nome informado.
                pass
        self.concluido.emit(clean_name)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._finish(self._operator or self._typed_name or "default_user")
            return
        if self._phase != "operator":
            event.ignore()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._typed_name.strip():
                self._change_phase("registered")
            return
        if event.key() == Qt.Key_Backspace:
            self._typed_name = self._typed_name[:-1]
            self.update()
            return
        text = event.text()
        if text and text.isprintable() and len(self._typed_name) < 32:
            self._typed_name += text
            self.update()

    def mousePressEvent(self, event):
        self.setFocus()
        # Clique pula apenas quando já existe identidade. Na primeira
        # configuração, não cria silenciosamente "default_user".
        if self._operator and self._phase in ("boot", "welcome"):
            self._finish(self._operator)
        event.accept()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d0f12"))
        cx, cy = self.width() / 2, self.height() / 2 - 24
        radius = max(24.0, min(self.width(), self.height()) * 0.075)
        self._draw_core(painter, cx, cy, radius)
        if self._phase == "boot":
            self._draw_boot(painter, cx, cy, radius)
        else:
            self._draw_identity(painter, cx, cy, radius)
        self._draw_footer(painter)
        painter.end()

    def _draw_core(self, painter, cx, cy, radius):
        t = time.monotonic()
        pulse = 1.0 + math.sin(t * 2.2) * 0.035
        glow = QRadialGradient(QPointF(cx, cy), radius * 3.0)
        glow.setColorAt(0.0, QColor(205, 238, 255, 235))
        glow.setColorAt(0.25, QColor(70, 138, 245, 170))
        glow.setColorAt(0.62, QColor(34, 70, 170, 60))
        glow.setColorAt(1.0, QColor(13, 15, 18, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), radius * 3, radius * 3)
        for index, squash in enumerate((0.34, 0.62)):
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(math.degrees(t * (0.18 + index * 0.1) * (-1 if index else 1)))
            painter.setPen(QPen(QColor(87, 145, 240, 115), 1.1))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 0), radius * (2.0 + index * 0.5), radius * squash)
            painter.restore()
        surface = QRadialGradient(
            QPointF(cx - radius * 0.25, cy - radius * 0.3), radius * 1.25)
        surface.setColorAt(0.0, QColor(238, 249, 255))
        surface.setColorAt(0.35, QColor(92, 172, 255))
        surface.setColorAt(1.0, QColor(25, 54, 158))
        painter.setBrush(surface)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), radius * pulse, radius * pulse)

    def _draw_boot(self, painter, cx, cy, radius):
        progress = min(1.0, self._elapsed() / _BOOT_SECONDS)
        self._text(painter, NOME, cy + radius * 2.8, 28, QColor("#f4f4f5"), True)
        self._text(
            painter, "Preparando memória, ferramentas e inteligência",
            cy + radius * 3.55, 11, QColor("#8e8e9c"))
        width = min(300.0, self.width() * 0.42)
        y = cy + radius * 4.2
        painter.setPen(QPen(QColor("#292a2e"), 3))
        painter.drawLine(QPointF(cx - width / 2, y), QPointF(cx + width / 2, y))
        painter.setPen(QPen(QColor("#6d94e8"), 3))
        painter.drawLine(
            QPointF(cx - width / 2, y),
            QPointF(cx - width / 2 + width * progress, y))

    def _draw_identity(self, painter, cx, cy, radius):
        if self._phase == "operator":
            self._text(painter, "Como devo chamar você?", cy + radius * 2.8,
                       22, QColor("#f4f4f5"), True)
            self._text(painter, "Digite seu nome e pressione Enter",
                       cy + radius * 3.5, 11, QColor("#8e8e9c"))
            cursor = "|" if int(time.monotonic() * 2) % 2 else " "
            self._text(painter, self._typed_name + cursor, cy + radius * 4.35,
                       18, QColor("#a9c3f7"), True)
            return
        name = self._operator or self._typed_name.strip()
        title = "Bem-vindo de volta" if self._phase == "welcome" else "Tudo pronto"
        self._text(painter, title, cy + radius * 2.8, 22, QColor("#f4f4f5"), True)
        self._text(painter, name, cy + radius * 3.55, 13, QColor("#8e8e9c"))

    def _text(self, painter, text, y, size, color, bold=False):
        painter.setPen(color)
        painter.setFont(QFont("Segoe UI", size, QFont.DemiBold if bold else QFont.Normal))
        painter.drawText(QRectF(0, y - size, self.width(), size * 2.2), Qt.AlignCenter, text)

    def _draw_footer(self, painter):
        painter.setPen(QColor("#5f6067"))
        painter.setFont(QFont("Segoe UI", 9))
        instruction = (
            "Esc ou clique para pular"
            if self._operator else
            "Esc para continuar sem cadastrar um nome")
        painter.drawText(
            QRectF(0, self.height() - 38, self.width(), 20), Qt.AlignCenter, instruction)
