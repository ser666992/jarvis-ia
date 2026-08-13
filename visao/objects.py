"""
visao/objects.py
===================
Detecção de objetos via YOLO (`ultralytics`), opcional. A biblioteca
baixa automaticamente um checkpoint (ex.: `yolov8n.pt`) na primeira
chamada real -- por isso, assim como em `ia/local_model.py`,
`available()` só checa se a biblioteca está instalada, sem baixar
nada; o download só acontece dentro de `detect()`.
"""

from logs.logger import get_logger

log = get_logger("visao")

try:
    import ultralytics  # noqa: F401
    HAS_ULTRALYTICS = True
except ImportError:
    HAS_ULTRALYTICS = False

_model = None
_model_name = None


def available() -> bool:
    return HAS_ULTRALYTICS


def detect(frame, model_name: str = "yolov8n.pt", confidence: float = 0.5) -> list:
    """Retorna lista de {"classe": str, "confianca": float, "caixa": (x1,y1,x2,y2)}."""
    global _model, _model_name
    if not HAS_ULTRALYTICS:
        raise RuntimeError("Instale 'ultralytics' para detecção de objetos (pip install ultralytics).")
    from ultralytics import YOLO
    if _model is None or _model_name != model_name:
        _model = YOLO(model_name)
        _model_name = model_name

    results = _model.predict(source=frame, conf=confidence, verbose=False)
    detections = []
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            detections.append({
                "classe": r.names.get(cls_id, str(cls_id)),
                "confianca": float(box.conf[0]),
                "caixa": tuple(float(v) for v in box.xyxy[0]),
            })
    return detections
