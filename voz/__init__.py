from voz.loop import VoiceLoop
from voz.stt import SpeechToText
from voz.tts import TextToSpeech
from voz.wakeword import WakeWordDetector

__all__ = ["SpeechToText", "TextToSpeech", "WakeWordDetector", "VoiceLoop", "status"]


def status() -> dict:
    stt = SpeechToText()
    tts = TextToSpeech()
    stt_ok = stt.available()
    tts_ok = tts.available()
    if stt_ok and tts_ok:
        motivo = f"STT via {stt.backend_disponivel()}; TTS via pyttsx3"
    else:
        faltando = []
        if not stt_ok:
            faltando.append("reconhecimento de voz (vosk / faster-whisper / SpeechRecognition)")
        if not tts_ok:
            faltando.append("síntese de voz (pyttsx3)")
        motivo = "dependências ausentes: " + "; ".join(faltando)
    return {
        "disponivel": stt_ok and tts_ok,
        "motivo": motivo,
        "detalhes": {"stt": stt_ok, "tts": tts_ok},
    }
