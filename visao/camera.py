"""
visao/camera.py
==================
Captura de webcam via OpenCV (`cv2.VideoCapture`).
"""

from logs.logger import get_logger

log = get_logger("visao")

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False


class Camera:
    def __init__(self, index: int = 0):
        self.index = index
        self._cap = None

    def available(self) -> bool:
        return HAS_OPENCV

    def open(self):
        if not HAS_OPENCV:
            raise RuntimeError("Instale 'opencv-python' para usar a câmera (pip install opencv-python).")
        if self._cap is None or not self._cap.isOpened():
            self._cap = cv2.VideoCapture(self.index)
        return self._cap

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def snapshot(self):
        """Captura um único frame (numpy array BGR) ou None se falhar."""
        cap = self.open()
        ok, frame = cap.read()
        return frame if ok else None

    def save_snapshot(self, path: str) -> bool:
        frame = self.snapshot()
        if frame is None:
            return False
        return bool(cv2.imwrite(path, frame))
