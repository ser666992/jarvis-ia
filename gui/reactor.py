"""
gui/reactor.py
==============
O "Núcleo": uma esfera feita de centenas de partículas (pontos numa
esfera distribuídos por espiral de Fibonacci, projetados em 2D com
perspectiva), desenhada inteiramente com QPainter -- sem imagem/vídeo
externo, mesma filosofia do gui/orb.py.

Comportamento (o que o usuário pediu):
- gira e "respira"/pulsa devagar quando ocioso;
- **quanto mais a IA trabalha, MAIOR e mais rápida ela fica** (energia);
- **quando está aprendendo, muda de cor** (set_learning);
- **quando está pesquisando, ejeta partículas** pra fora, tipo plasma
  de um reator de fusão (set_searching);
- estado próprio pra "ouvindo" (microfone), como o orbe antigo.

Interface compatível com o MoleculeOrb antigo (set_thinking/set_listening),
mais set_learning/set_searching -- ver gui/app.py.
"""

import math
import random

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

_N_PARTICULAS = 520
_PERSPECTIVA = 2.4
_TILT = 0.5  # inclinação fixa (radianos) -- dá uma vista 3/4 em vez de topo reto

# Cor por estado -- interpoladas suavemente (nada troca de golpe), mas
# de propósito com HUES bem distintos entre si (não só variações de
# brilho do mesmo azul) -- a versão anterior tinha "idle" e "thinking"
# quase na mesma cor (79,209,255 vs 120,200,255), então a "troca de
# cor" praticamente não dava pra perceber a olho nu mesmo funcionando
# tecnicamente por baixo.
_COR = {
    "idle": QColor(45, 110, 150),       # azul-petróleo apagado (repouso)
    "thinking": QColor(80, 200, 255),   # ciano vívido (processando)
    "learning": QColor(90, 235, 130),   # verde vívido (aprendendo)
    "searching": QColor(255, 165, 45),  # âmbar vívido (pesquisando)
    "listening": QColor(94, 234, 212),  # teal (ouvindo)
}
_ENERGIA = {"idle": 0.15, "thinking": 1.0, "learning": 0.85, "searching": 0.95, "listening": 0.7}


def _fibonacci_sphere(n: int):
    """n pontos ~uniformes na superfície de uma esfera unitária."""
    pts = []
    phi = math.pi * (3.0 - math.sqrt(5.0))  # ângulo áureo
    for i in range(n):
        y = 1 - (i / max(1, n - 1)) * 2  # 1 .. -1
        raio = math.sqrt(max(0.0, 1 - y * y))
        th = phi * i
        pts.append((math.cos(th) * raio, y, math.sin(th) * raio))
    return pts


def _lerp(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )


class ReactorCore(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pontos = _fibonacci_sphere(_N_PARTICULAS)
        self._angle = 0.0

        self._modo = "idle"
        self._energy = _ENERGIA["idle"]
        self._target_energy = _ENERGIA["idle"]
        self._cor = QColor(_COR["idle"])
        self._cor_alvo = QColor(_COR["idle"])

        self._ejetadas = []  # partículas de "pesquisa" saindo do núcleo

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    # ---------- API (compatível com o orbe antigo + estados novos) ----------

    def _set_modo(self, modo: str):
        self._modo = modo
        self._target_energy = _ENERGIA.get(modo, 0.15)
        self._cor_alvo = QColor(_COR.get(modo, _COR["idle"]))

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

    # ---------- animação ----------

    def _tick(self):
        self._angle += 0.006 + self._energy * 0.02
        # Fatores de interpolação mais rápidos que antes (0.07/0.06 ->
        # 0.14/0.12) -- a transição precisa ficar VISIVELMENTE completa
        # dentro da janela curta (a maioria das respostas volta rápido,
        # ver gui/app.py:_DURACAO_MINIMA_NUCLEO), não só "começar" a mudar.
        self._energy += (self._target_energy - self._energy) * 0.14
        self._cor = _lerp(self._cor, self._cor_alvo, 0.12)

        # ejeção de partículas quando pesquisando (plasma do reator)
        if self._modo == "searching" and random.random() < 0.6:
            self._emitir_particula()
        vivas = []
        for p in self._ejetadas:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vida"] -= 0.02
            if p["vida"] > 0:
                vivas.append(p)
        self._ejetadas = vivas

        self.update()

    def _emitir_particula(self):
        cx, cy = self.width() / 2, self.height() / 2
        r = self._raio_atual()
        ang = random.uniform(0, 2 * math.pi)
        vel = random.uniform(1.6, 3.4)
        self._ejetadas.append({
            "x": cx + math.cos(ang) * r * 0.6,
            "y": cy + math.sin(ang) * r * 0.6,
            "vx": math.cos(ang) * vel,
            "vy": math.sin(ang) * vel * 0.7,
            "vida": 1.0,
        })

    def _raio_atual(self) -> float:
        # cresce com a energia ("quanto mais trabalha, maior fica") + respira.
        # Faixa de crescimento alargada (0.5 -> 0.68) pra o "fica maior
        # trabalhando" ficar óbvio a olho nu, não só um leve inchaço.
        base = min(self.width(), self.height()) * 0.28
        respira = 1.0 + 0.05 * math.sin(self._angle * 2.2)
        return base * respira * (0.78 + 0.68 * self._energy)

    # ---------- desenho ----------

    def paintEvent(self, _e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        cx, cy = self.width() / 2, self.height() / 2
        r = self._raio_atual()
        cor = self._cor

        self._desenhar_vinheta(painter, cx, cy, cor)
        self._desenhar_particulas_ejetadas(painter, cor)
        self._desenhar_nucleo_quente(painter, cx, cy, r, cor)
        self._desenhar_esfera(painter, cx, cy, r, cor)

        painter.end()

    def _desenhar_vinheta(self, painter, cx, cy, cor):
        v = QRadialGradient(QPointF(cx, cy), max(self.width(), self.height()) * 0.6)
        c = QColor(cor)
        c.setAlpha(int(16 + 22 * self._energy))
        v.setColorAt(0.0, c)
        v.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(v))
        painter.drawRect(self.rect())

    def _desenhar_nucleo_quente(self, painter, cx, cy, r, cor):
        # centro incandescente estilo reator de fusão
        glow_r = r * (0.55 + 0.25 * self._energy)
        grad = QRadialGradient(QPointF(cx, cy), glow_r)
        centro = QColor(255, 255, 255, int(120 + 100 * self._energy))
        meio = QColor(cor)
        meio.setAlpha(int(120 + 90 * self._energy))
        grad.setColorAt(0.0, centro)
        grad.setColorAt(0.35, meio)
        grad.setColorAt(1.0, QColor(cor.red(), cor.green(), cor.blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

    def _desenhar_esfera(self, painter, cx, cy, r, cor):
        cosb, sinb = math.cos(self._angle), math.sin(self._angle)
        cost, sint = math.cos(_TILT), math.sin(_TILT)
        painter.setPen(Qt.NoPen)

        for px, py, pz in self._pontos:
            # rotação em Y
            x1 = px * cosb + pz * sinb
            z1 = -px * sinb + pz * cosb
            # inclinação em X
            y2 = py * cost - z1 * sint
            z2 = py * sint + z1 * cost
            # projeção em perspectiva (z2 em -1..1)
            f = _PERSPECTIVA / (_PERSPECTIVA - z2)
            sx = cx + x1 * r * f
            sy = cy + y2 * r * f
            profundidade = (z2 + 1) / 2  # 0 (fundo) .. 1 (frente)
            tam = (1.1 + 2.4 * profundidade) * f * (0.85 + 0.4 * self._energy)
            c = QColor(cor)
            c.setAlpha(int(35 + 205 * profundidade))
            painter.setBrush(QBrush(c))
            painter.drawEllipse(QPointF(sx, sy), tam, tam)

    def _desenhar_particulas_ejetadas(self, painter, cor):
        painter.setPen(Qt.NoPen)
        for p in self._ejetadas:
            c = QColor(cor)
            c.setAlpha(int(200 * max(0.0, p["vida"])))
            painter.setBrush(QBrush(c))
            painter.drawEllipse(QPointF(p["x"], p["y"]), 2.4, 2.4)
