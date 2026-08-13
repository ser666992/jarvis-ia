"""
visao/gestures.py
====================
Detecção de mãos/gestos via MediaPipe (opcional).
"""

from logs.logger import get_logger

log = get_logger("visao")

try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False

_hands = None


def available() -> bool:
    return HAS_MEDIAPIPE


def _get_hands():
    global _hands
    if _hands is None:
        _hands = mp.solutions.hands.Hands(
            static_image_mode=False, max_num_hands=2, min_detection_confidence=0.6,
        )
    return _hands


def detect_hands(frame) -> list:
    """Retorna lista de landmarks (21 pontos (x,y,z) por mão detectada)."""
    if not HAS_MEDIAPIPE:
        raise RuntimeError("Instale 'mediapipe' para detecção de mãos/gestos.")
    import cv2
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = _get_hands().process(rgb)
    if not result.multi_hand_landmarks:
        return []
    return [
        [(lm.x, lm.y, lm.z) for lm in hand.landmark]
        for hand in result.multi_hand_landmarks
    ]
