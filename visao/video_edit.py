"""
visao/video_edit.py
======================
Edição básica de vídeo (cortar um trecho, acelerar) usando só
`opencv-python` (já opcional em requirements-visao.txt) -- sem
depender de moviepy/ffmpeg externos. Serve o pedido de "criar vídeos"
combinado com visao/screen.py:record_screen() (gravação da tela) --
ver plugins/video_creation.py pros comandos de chat.
"""

from logs.logger import get_logger

log = get_logger("visao")

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


def available() -> bool:
    return HAS_CV2


def cortar(caminho_entrada: str, inicio_seg: float, fim_seg: float, caminho_saida: str) -> str:
    """Extrai o trecho entre inicio_seg e fim_seg num arquivo novo."""
    if not HAS_CV2:
        raise RuntimeError("Instale 'opencv-python' (requirements-visao.txt) pra editar vídeo.")
    cap = cv2.VideoCapture(caminho_entrada)
    if not cap.isOpened():
        raise RuntimeError(f"Não consegui abrir '{caminho_entrada}'.")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 10
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(caminho_saida, fourcc, fps, (width, height))
        try:
            frame_inicio = int(inicio_seg * fps)
            frame_fim = int(fim_seg * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_inicio)
            indice = frame_inicio
            while indice < frame_fim:
                ok, frame = cap.read()
                if not ok:
                    break
                writer.write(frame)
                indice += 1
        finally:
            writer.release()
    finally:
        cap.release()
    return caminho_saida


def acelerar(caminho_entrada: str, fator: float, caminho_saida: str) -> str:
    """Acelera o vídeo mantendo todos os frames, só aumentando o FPS de
    reprodução no arquivo de saída (fator=2 -> 2x mais rápido) -- mais
    simples e confiável do que descartar frames pra economizar tempo."""
    if not HAS_CV2:
        raise RuntimeError("Instale 'opencv-python' (requirements-visao.txt) pra editar vídeo.")
    if fator <= 0:
        raise ValueError("O fator de aceleração precisa ser maior que zero.")
    cap = cv2.VideoCapture(caminho_entrada)
    if not cap.isOpened():
        raise RuntimeError(f"Não consegui abrir '{caminho_entrada}'.")
    try:
        fps = (cap.get(cv2.CAP_PROP_FPS) or 10) * fator
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(caminho_saida, fourcc, fps, (width, height))
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                writer.write(frame)
        finally:
            writer.release()
    finally:
        cap.release()
    return caminho_saida
