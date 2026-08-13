from visao import faces, gestures, objects, observe, ocr, screen
from visao.camera import HAS_OPENCV, Camera

__all__ = ["Camera", "faces", "objects", "gestures", "observe", "ocr", "screen", "status"]


def status() -> dict:
    partes = {
        "camera_opencv": HAS_OPENCV,
        "ocr": ocr.available(),
        "reconhecimento_facial": faces.recognize_available(),
        "deteccao_objetos": objects.available(),
        "gestos": gestures.available(),
        "captura_tela": screen.available(),
    }
    disponivel = any(partes.values())
    ativos = [k for k, v in partes.items() if v]
    motivo = (
        f"recursos ativos: {', '.join(ativos)}" if ativos else
        "nenhuma dependência de visão instalada (opencv-python, pytesseract, ultralytics, mediapipe, mss)"
    )
    return {"disponivel": disponivel, "motivo": motivo, "detalhes": partes}
