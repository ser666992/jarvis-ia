"""
gui/orb.py
==========
Widget "molécula": um núcleo brilhante com partículas orbitando em
anéis elípticos, desenhado inteiramente com QPainter (sem imagens
externas). Gira devagar e sem brilho quando ocioso; acelera, pulsa e
muda de cor quando o Jarvis está processando uma resposta -- ver
set_thinking().

A cor não troca de golpe entre ocioso/pensando -- `_color_mix`
interpola gradualmente (junto com `_energy`), então a transição fica
suave em vez de um "flash" abrupto. Um vinheta radial sutil atrás do
orbe (`_draw_vignette`) dá profundidade ao fundo preto puro.
"""

import math

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

# Cada anel: (raio, nº de partículas, velocidade angular, achatamento vertical)
_RINGS = (
    (60, 3, 0.9, 0.35),
    (85, 4, -0.6, 0.55),
    (105, 5, 0.4, 0.8),
)

_COLOR_IDLE = QColor(79, 209, 255)
_COLOR_THINKING = QColor(168, 130, 255)
_COLOR_LISTENING = QColor(94, 234, 212)


def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )


class MoleculeOrb(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0.0
        self._energy = 0.15
        self._target_energy = 0.15
        self._color_mix = 0.0
        self._target_color_mix = 0.0
        self._thinking = False
        self._listening = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def set_thinking(self, thinking: bool):
        self._thinking = thinking
        if not self._listening:
            self._target_energy = 1.0 if thinking else 0.15
            self._target_color_mix = 1.0 if thinking else 0.0

    def set_listening(self, listening: bool):
        """Estado distinto de 'pensando' -- microfone ativo esperando
        você falar (ver gui/app.py, botão de microfone). Cor própria
        (_COLOR_LISTENING) e energia alta, mas sem competir com o
        estado de 'pensando' quando os dois se sobrepõem (a resposta
        de voz só chega DEPOIS de parar de ouvir, então na prática
        nunca ficam ativos ao mesmo tempo -- a checagem aqui é só
        defensiva)."""
        self._listening = listening
        self._target_energy = 1.0 if listening else (1.0 if self._thinking else 0.15)
        self._target_color_mix = -1.0 if listening else (1.0 if self._thinking else 0.0)

    def _tick(self):
        self._angle += 0.03 + self._energy * 0.05
        self._energy += (self._target_energy - self._energy) * 0.08
        self._color_mix += (self._target_color_mix - self._color_mix) * 0.06
        self.update()

    def _draw_vignette(self, painter: QPainter, cx: float, cy: float, base_color: QColor):
        vignette = QRadialGradient(QPointF(cx, cy), max(self.width(), self.height()) * 0.65)
        tinge = QColor(base_color)
        tinge.setAlpha(14)
        edge = QColor(0, 0, 0, 0)
        vignette.setColorAt(0.0, tinge)
        vignette.setColorAt(1.0, edge)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(vignette))
        painter.drawRect(self.rect())

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#000000"))

        cx, cy = self.width() / 2, self.height() / 2
        pulse = 1.0 + 0.08 * math.sin(self._angle * 3) * self._energy
        # _color_mix >= 0 -> interpola pra "pensando"; < 0 -> interpola pra
        # "ouvindo" (_COLOR_LISTENING) -- mesmo escalar, só o sinal decide
        # qual dos dois estados a cor está migrando em direção.
        if self._color_mix >= 0:
            base_color = _lerp_color(_COLOR_IDLE, _COLOR_THINKING, self._color_mix)
        else:
            base_color = _lerp_color(_COLOR_IDLE, _COLOR_LISTENING, -self._color_mix)

        self._draw_vignette(painter, cx, cy, base_color)

        glow_radius = 34 * pulse * (0.8 + 0.4 * self._energy)
        glow_color = QColor(base_color)
        glow_color.setAlpha(160)
        transparent = QColor(base_color)
        transparent.setAlpha(0)
        gradient = QRadialGradient(QPointF(cx, cy), glow_radius * 2.2)
        gradient.setColorAt(0.0, glow_color)
        gradient.setColorAt(1.0, transparent)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(cx, cy), glow_radius * 2.2, glow_radius * 2.2)

        core_highlight = QColor(255, 255, 255, 200)
        painter.setBrush(QBrush(base_color))
        painter.drawEllipse(QPointF(cx, cy), glow_radius * 0.4, glow_radius * 0.4)
        painter.setBrush(QBrush(core_highlight))
        painter.drawEllipse(QPointF(cx - glow_radius * 0.12, cy - glow_radius * 0.12), glow_radius * 0.12, glow_radius * 0.12)

        line_color = QColor(base_color)
        line_color.setAlpha(90)
        pen = QPen(line_color)
        pen.setWidthF(1.0)

        for ring_idx, (radius, count, speed_factor, tilt) in enumerate(_RINGS):
            r = radius * (0.9 + 0.15 * self._energy)
            points = []
            for i in range(count):
                a = self._angle * speed_factor + (2 * math.pi / count) * i + ring_idx
                x = cx + math.cos(a) * r
                y = cy + math.sin(a) * r * tilt
                points.append(QPointF(x, y))

            painter.setPen(pen)
            for p in points:
                painter.drawLine(QPointF(cx, cy), p)
            for i in range(len(points)):
                painter.drawLine(points[i], points[(i + 1) % len(points)])

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(base_color))
            for p in points:
                painter.drawEllipse(p, 4.5, 4.5)

        painter.end()
