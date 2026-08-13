"""
visao/faces.py
================
Detecção facial via Haar Cascade do próprio OpenCV (não exige download
extra -- os arquivos `.xml` vêm empacotados com `opencv-python`).
Reconhecimento (identificar QUEM é o rosto, não só que há um rosto) é
opcional via `face_recognition` (mais pesado, depende de `dlib`).
"""

from logs.logger import get_logger

log = get_logger("visao")

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    import face_recognition
    HAS_FACE_RECOGNITION = True
except ImportError:
    HAS_FACE_RECOGNITION = False

_cascade = None


def _get_cascade():
    global _cascade
    if _cascade is None:
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _cascade = cv2.CascadeClassifier(path)
    return _cascade


def available() -> bool:
    return HAS_OPENCV


def detect_faces(frame) -> list:
    """Retorna lista de (x, y, largura, altura) para cada rosto detectado."""
    if not HAS_OPENCV:
        raise RuntimeError("Instale 'opencv-python' para detecção facial.")
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    detected = _get_cascade().detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    return [tuple(int(v) for v in f) for f in detected]


def recognize_available() -> bool:
    return HAS_FACE_RECOGNITION


def encode_known_face(image_path: str):
    if not HAS_FACE_RECOGNITION:
        raise RuntimeError("Instale 'face_recognition' para reconhecimento (identificação) facial.")
    image = face_recognition.load_image_file(image_path)
    encodings = face_recognition.face_encodings(image)
    return encodings[0] if encodings else None


def identify_faces(frame, known_encodings: dict, tolerance: float = 0.6) -> list:
    """known_encodings: {nome: encoding}. Retorna lista de nomes
    identificados (ou "desconhecido") para cada rosto no frame."""
    if not HAS_FACE_RECOGNITION:
        raise RuntimeError("Instale 'face_recognition' para reconhecimento (identificação) facial.")
    import cv2 as _cv2
    rgb = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(rgb)
    encodings = face_recognition.face_encodings(rgb, locations)

    names = []
    for encoding in encodings:
        matches = face_recognition.compare_faces(list(known_encodings.values()), encoding, tolerance=tolerance)
        name = "desconhecido"
        if True in matches:
            name = list(known_encodings.keys())[matches.index(True)]
        names.append(name)
    return names
