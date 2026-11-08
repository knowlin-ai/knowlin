"""Lokale Spracherkennung mit faster-whisper – das Audio verlässt den PC nicht.

Optional: `pip install faster-whisper`. Beim ersten Start lädt es das Modell
(„small“ ≈ 460 MB) einmalig von Hugging Face herunter; danach läuft es offline.
Der Browser nimmt per Push-to-Talk auf und schickt die Aufnahme (WebM/Opus) an
/api/stt; dekodiert wird mit PyAV, das faster-whisper mitbringt.
"""

from __future__ import annotations

import asyncio
import io
import logging
import threading

log = logging.getLogger(__name__)


class WhisperSTT:
    def __init__(self, model: str = "small", device: str = "auto", language: str = "de") -> None:
        self.model_name = model
        self.device = device
        self.language = language
        self._model = None
        self._lock = threading.Lock()
        self.error: str | None = None

    @staticmethod
    def available() -> bool:
        try:
            import faster_whisper  # noqa: F401

            return True
        except ImportError:
            return False

    def _load(self):
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                compute = "int8"
                log.info("Lade Whisper-Modell %s …", self.model_name)
                self._model = WhisperModel(self.model_name, device=self.device, compute_type=compute)
            return self._model

    def warm_up(self) -> None:
        threading.Thread(target=self._safe_load, daemon=True).start()

    def _safe_load(self) -> None:
        try:
            self._load()
        except Exception as exc:  # z. B. kein Netz beim ersten Laden
            self.error = f"{type(exc).__name__}: {exc}"
            log.error("Whisper konnte nicht geladen werden: %s", self.error)

    def _transcribe(self, audio: bytes, hint: str | None) -> str:
        model = self._load()
        segments, _info = model.transcribe(
            io.BytesIO(audio),
            language=self.language,
            vad_filter=True,
            beam_size=3,
            initial_prompt=hint or "Befehle an eine Roboterente: lauf, dreh dich, tanz, setz dich, stopp.",
        )
        return " ".join(s.text.strip() for s in segments).strip()

    async def transcribe(self, audio: bytes, hint: str | None = None) -> str:
        return await asyncio.to_thread(self._transcribe, audio, hint)
