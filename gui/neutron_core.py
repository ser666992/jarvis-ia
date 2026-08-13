"""Núcleo visual original do Neutron.

Não representa um olho nem um cérebro: é uma estrela de nêutrons
estabilizada por anéis magnéticos e fluxos de partículas. A API pública
mantém os estados usados pela GUI para a troca ser segura.
"""

import math
import random

from PySide6.QtCore import QElapsedTimer, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


_ENERGIA = {"idle": 0.16, "thinking": 0.92, "learning": 0.74, "searching": 1.0, "listening": 0.58}


class NeutronCore(QWidget):
    """Estrela de nêutrons animada, compatível com o antigo widget visual."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._modo = "idle"
        self._energia = _ENERGIA["idle"]
        self._alvo = self._energia
        self._t = 0.0
        self._particulas = []
        self._relogio = QElapsedTimer()
        self._relogio.start()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _set_modo(self, modo: str):
        self._modo = modo
        self._alvo = _ENERGIA.get(modo, _ENERGIA["idle"])

    def set_thinking(self, on: bool):
        self._set_modo("thinking" if on else "idle")

    def set_listening(self, on: bool):
        self._set_modo("listening" if on else "idle")

    def set_learning(self, on: bool):
        self._set_modo("learning" if on else "idle")

    def set_searching(self, on: bool):
        self._set_modo("searching" if on else "idle")

    def reset(self):
        self._set_modo("idle")

    def _tick(self):
        # Usa o tempo realmente decorrido. Com o antigo incremento fixo,
        # qualquer engasgo da interface deixava a animação permanentemente
        # mais lenta e a taxa de partículas dependia do FPS da máquina.
        dt = min(max(self._relogio.restart() / 1000.0, 0.001), 0.05)
        self._t += dt
        suavizacao = 1.0 - math.exp(-6.5 * dt)
        self._energia += (self._alvo - self._energia) * suavizacao
        taxa_por_segundo = 9.0 + self._energia * 25.0
        taxa = 1.0 - math.exp(-taxa_por_segundo * dt)
        if random.random() < taxa:
            self._particulas.append({
                "ang": random.uniform(0, math.tau),
                "fase": random.uniform(0.0, 1.0),
                "vel": random.uniform(0.75, 1.85),
                "orbita": random.randrange(3),
            })
        vivas = []
        for p in self._particulas:
            p["fase"] += p["vel"] * dt * (1.0 + self._energia)
            if p["fase"] < 1.0:
                vivas.append(p)
        self._particulas = vivas[-90:]
        self.update()

    def showEvent(self, event):
        self._relogio.restart()
        if not self._timer.isActive():
            self._timer.start(16)
        super().showEvent(event)

    def hideEvent(self, event):
        # Janela minimizada/oculta não precisa redesenhar a 60 FPS.
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(13, 15, 18))
        cx, cy = self.width() / 2, self.height() / 2
        raio = max(8.0, min(self.width(), self.height()) * 0.145)
        self._desenhar_fundo(painter, cx, cy)
        self._desenhar_orbitas(painter, cx, cy, raio)
        self._desenhar_fluxos(painter, cx, cy, raio)
        self._desenhar_nucleo(painter, cx, cy, raio)
        painter.end()

    def _desenhar_fundo(self, painter, cx, cy):
        grad = QRadialGradient(QPointF(cx, cy), max(self.width(), self.height()) * 0.62)
        grad.setColorAt(0.0, QColor(15, 40, 92, int(45 + self._energia * 50)))
        grad.setColorAt(0.45, QColor(6, 15, 42, 42))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawRect(self.rect())

    def _desenhar_orbitas(self, painter, cx, cy, raio):
        for indice, inclinacao in enumerate((0.36, 0.63, 0.88)):
            rot = self._t * (0.33 + indice * 0.14) * (1 if indice != 1 else -1)
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(math.degrees(rot))
            cor = QColor(80, 180, 255, int(70 + self._energia * 125))
            pen = QPen(cor)
            pen.setWidthF(1.1 + self._energia * 0.8)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 0), raio * (1.75 + indice * 0.36), raio * inclinacao)
            painter.restore()

    def _desenhar_fluxos(self, painter, cx, cy, raio):
        painter.setPen(Qt.NoPen)
        for p in self._particulas:
            # No modo de aprendizado a matéria cai no núcleo; nos demais,
            # ela é expelida como um jato de plasma.
            progresso = p["fase"] if self._modo != "learning" else 1.0 - p["fase"]
            r = raio * (0.55 + progresso * 2.9)
            ang = p["ang"] + self._t * (0.65 + p["orbita"] * 0.22)
            x = cx + math.cos(ang) * r
            y = cy + math.sin(ang) * r * (0.42 + p["orbita"] * 0.12)
            alpha = max(0, int(230 * (1.0 - p["fase"]) ** 1.5))
            cor = QColor(135, 220, 255, alpha) if self._modo != "learning" else QColor(160, 130, 255, alpha)
            painter.setBrush(cor)
            tamanho = 1.3 + self._energia * 1.8
            painter.drawEllipse(QPointF(x, y), tamanho, tamanho)

    def _desenhar_nucleo(self, painter, cx, cy, raio):
        pulso = 1.0 + math.sin(self._t * (1.2 + self._energia * 3.2)) * (0.035 + self._energia * 0.055)
        r = raio * pulso
        halo = QRadialGradient(QPointF(cx, cy), r * 2.5)
        halo.setColorAt(0.0, QColor(160, 230, 255, int(180 + self._energia * 60)))
        halo.setColorAt(0.24, QColor(65, 145, 255, int(145 + self._energia * 65)))
        halo.setColorAt(0.55, QColor(25, 58, 190, int(80 + self._energia * 80)))
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(QPointF(cx, cy), r * 2.5, r * 2.5)

        superficie = QRadialGradient(QPointF(cx - r * 0.25, cy - r * 0.3), r * 1.2)
        superficie.setColorAt(0.0, QColor(235, 250, 255))
        superficie.setColorAt(0.25, QColor(110, 205, 255))
        superficie.setColorAt(0.7, QColor(32, 82, 232))
        superficie.setColorAt(1.0, QColor(7, 17, 72))
        painter.setBrush(superficie)
        painter.drawEllipse(QPointF(cx, cy), r, r)
