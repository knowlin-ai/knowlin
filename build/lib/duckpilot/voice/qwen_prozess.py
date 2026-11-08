"""Qwen3-TTS in einem eigenen Prozess (seit 0.37.8).

Hinweis aus dem Test „nach dem Aktivieren der Stimme hängt das Programm – es reagiert nicht mehr“: Qwen lief bisher im
selben Prozess wie die Oberfläche. Das Laden von PyTorch und dem Modell (unter Windows mit ROCm, beim ersten Mal mit
Übersetzen der Grafikkarten-Programme) hält den Python-Interpreter lange fest, und hängt oder stürzt der Grafiktreiber,
hängt oder stirbt duckpilot mit. Jetzt rechnet ein eigener Arbeitsprozess:

- Die Oberfläche bleibt immer bedienbar; Not-Aus, Chat und Mikrofon laufen weiter.
- Hängt ein Satz länger als `SATZ_S`, wird der Arbeiter beendet und beim nächsten Satz neu gestartet.
- Stirbt der Arbeiter, steht der Grund in `qwen-arbeiter.log` im App-Datenordner (für den Fehlerbericht).

Protokoll: Pickle-Rahmen (4 Byte Länge + Daten) über stdin/stdout des Kindprozesses – nur zwischen duckpilot und
seinem eigenen Kind. Alles, was Bibliotheken auf stdout schreiben, landet im Log statt im Protokoll.
"""

from __future__ import annotations

import builtins
import itertools
import logging
import os
import pickle
import queue
import struct
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, BinaryIO, Callable

from . import tts

log = logging.getLogger(__name__)

SATZ_S = 300.0          # so lange darf ein Satz höchstens dauern (erster Satz auf der Grafikkarte übersetzt Programme)
LOG_NAME = "qwen-arbeiter.log"


def _senden(f: BinaryIO, obj: Any) -> None:
    data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    f.write(struct.pack(">I", len(data)) + data)
    f.flush()


def _lesen(f: BinaryIO) -> Any:
    kopf = f.read(4)
    if len(kopf) < 4:
        raise EOFError
    (n,) = struct.unpack(">I", kopf)
    data = f.read(n)
    if len(data) < n:
        raise EOFError
    return pickle.loads(data)


class QwenProzess(tts.QwenEngine):
    """Wie QwenEngine – Dateien (Stimmen, Modellordner) hier, Rechnen im Arbeitsprozess."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self._proc: subprocess.Popen | None = None
        self._antworten: queue.Queue = queue.Queue()
        self._ids = itertools.count(1)
        self._schreiben = threading.Lock()
        self._geladen: str | None = None        # Repo des geladenen Sprechmodells im Arbeiter

    # ── Arbeiter starten und stoppen ─────────────────────────────────────
    def _starten(self) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        self._geladen = None
        self.root.mkdir(parents=True, exist_ok=True)
        logf = open(self.root / LOG_NAME, "ab")  # noqa: SIM115 – bleibt offen, solange der Arbeiter läuft
        kw: dict[str, Any] = {}
        if sys.platform == "win32":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HF_HUB_DISABLE_XET": "1"}
        self._proc = subprocess.Popen([sys.executable, "-m", "duckpilot.voice.qwen_prozess", str(self.root)],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=logf, env=env,
                                      cwd=str(Path(__file__).resolve().parents[2]), **kw)   # dieselbe duckpilot-Fassung
        self._antworten = queue.Queue()
        threading.Thread(target=self._mitlesen, args=(self._proc, self._antworten), daemon=True,
                         name="qwen-arbeiter").start()
        log.info("Qwen-Arbeiter gestartet (PID %s)", self._proc.pid)
        return self._proc

    @staticmethod
    def _mitlesen(proc: subprocess.Popen, antworten: queue.Queue) -> None:
        try:
            while True:
                antworten.put(_lesen(proc.stdout))
        except Exception:
            antworten.put(None)                  # Arbeiter weg

    def beenden(self) -> None:
        proc, self._proc, self._geladen = self._proc, None, None
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()                      # nur unser eigenes Kind, über seine PID
                proc.wait(timeout=5)
            except Exception:
                log.debug("Qwen-Arbeiter beenden", exc_info=True)

    def _letzte_logzeile(self) -> str:
        try:
            zeilen = (self.root / LOG_NAME).read_text("utf-8", errors="replace").strip().splitlines()
            return next((z for z in reversed(zeilen) if z.strip()), "")[-200:]
        except OSError:
            return ""

    # ── Aufträge ─────────────────────────────────────────────────────────
    def _auftrag(self, art: str, args: dict[str, Any], frist: float | None,
                 fortschritt: Callable[..., None] | None = None) -> Any:
        proc = self._starten()
        jid = next(self._ids)
        with self._schreiben:
            try:
                _senden(proc.stdin, (jid, art, args))
            except (BrokenPipeError, OSError):
                self.beenden()
                raise tts.EngineError("Qwen3-TTS-Arbeiter ist weg – beim nächsten Satz startet er neu") from None
        import time

        ende = None if frist is None else time.monotonic() + frist
        while True:
            rest = None if ende is None else ende - time.monotonic()
            if rest is not None and rest <= 0:
                self.beenden()
                raise tts.EngineError(f"Qwen3-TTS hat {int(frist)} s nicht geantwortet und wurde neu gestartet "
                                      f"(Protokoll: {LOG_NAME})")
            try:
                msg = self._antworten.get(timeout=min(1.0, rest) if rest is not None else 1.0)
            except queue.Empty:
                if proc.poll() is not None:
                    msg = None
                else:
                    continue
            if msg is None:
                code = proc.poll()
                self.beenden()
                grund = self._letzte_logzeile()
                raise tts.EngineError(f"Qwen3-TTS ist abgestürzt (Code {code}){f': {grund}' if grund else ''} – "
                                      "beim nächsten Satz startet es neu")
            mid, status, inhalt = msg
            if mid != jid:
                continue                          # Rest eines abgebrochenen Auftrags
            if status == "fortschritt":
                if fortschritt:
                    fortschritt(*inhalt)
                continue
            if status == "fehler":
                name, text = inhalt
                typ = getattr(builtins, name, None)
                if isinstance(typ, type) and issubclass(typ, Exception) and typ is not Exception:
                    try:
                        raise typ(text)
                    except TypeError:
                        pass
                if name == "EngineError":
                    raise tts.EngineError(text)
                raise RuntimeError(f"{name}: {text}")
            return inhalt

    # ── Schnittstelle wie QwenEngine ─────────────────────────────────────
    def loaded(self, quality: str = "schnell") -> bool:
        lebt = self._proc is None or self._proc.poll() is None
        return lebt and self._geladen == tts.QWEN_BASE.get(quality, tts.QWEN_BASE["schnell"])

    def base(self, quality: str = "schnell", progress: Callable[[int, int | None], None] | None = None):
        repo = tts.QWEN_BASE.get(quality, tts.QWEN_BASE["schnell"])
        if not self.loaded(quality):
            self.device = self._auftrag("base", {"quality": quality}, None, progress)   # Download: ohne Frist
            self._geladen = repo
        return self._geladen

    def synthesize(self, text: str, vid: str, style: tts.Style, quality: str = "schnell"):
        if not (self.voices_dir / f"{vid}.wav").exists():
            raise tts.EngineError("Diese Entenstimme gibt es nicht mehr – bitte neu entwerfen oder auswählen")
        if not self.loaded(quality):
            self.base(quality)
        return self._auftrag("satz", {"text": text, "vid": vid, "style": style, "quality": quality}, SATZ_S)

    def design(self, instruct: str, text: str, takes: int = 3, progress: Callable[[str], None] | None = None):
        self._geladen = None                     # der Arbeiter entlädt das Sprechmodell fürs Entwerfen
        return self._auftrag("entwurf", {"instruct": instruct, "text": text, "takes": takes}, None, progress)


# ── Kindprozess ──────────────────────────────────────────────────────────
def arbeiten(root: Path, ein: BinaryIO, aus: BinaryIO) -> None:
    eng = tts.QwenEngine(root)
    while True:
        try:
            jid, art, args = _lesen(ein)
        except EOFError:
            return                                # duckpilot ist weg

        def melden(*werte: Any, _jid: int = jid) -> None:
            _senden(aus, (_jid, "fortschritt", werte))

        try:
            if art == "base":
                eng.base(args["quality"], melden)
                ergebnis: Any = eng.device
            elif art == "satz":
                import time

                t0 = time.monotonic()
                ergebnis = eng.synthesize(args["text"], args["vid"], args["style"], args["quality"])
                x, sr = ergebnis[0], ergebnis[1]
                dauer = len(x) / sr if sr else 0.0
                logging.getLogger("qwen-arbeiter").info(       # Tempo fürs Protokoll – ohne den Text
                    "Satz: %.1f s Ton in %.1f s (%s, %s)", dauer, time.monotonic() - t0, eng.device, args["quality"])
            elif art == "entwurf":
                ergebnis = eng.design(args["instruct"], args["text"], args["takes"], melden)
            else:
                raise ValueError(f"unbekannter Auftrag {art}")
            _senden(aus, (jid, "ok", ergebnis))
        except Exception as exc:
            logging.getLogger("qwen-arbeiter").exception("Auftrag %s", art)
            _senden(aus, (jid, "fehler", (type(exc).__name__, str(exc))))


def main() -> None:
    # Protokoll auf einer eigenen Kopie von stdout; was Bibliotheken drucken, geht ins Log (stderr)
    proto = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(name)s: %(message)s")
    arbeiten(Path(sys.argv[1]), sys.stdin.buffer, proto)


if __name__ == "__main__":
    main()
