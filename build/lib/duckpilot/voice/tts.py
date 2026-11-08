"""Die Stimme der Ente: Sprachsynthese lokal auf dem PC.

Zwei Motoren, beide Open Source und offline:

* **Piper** – schnell und leicht, läuft auf jedem Prozessor (ONNX). Deutsche Stimmen
  von Thorsten-Voice u. a.; „Thorsten emotional“ kann fröhlich, überrascht, flüsternd,
  verschlafen … – das nutzt die Ente für ihre Stimmung. Lizenz: GPL-3.0 (Programm),
  Stimmen je nach Datensatz (Thorsten: CC0).
* **Qwen3-TTS** – deutlich natürlicher, mit „Stimme entwerfen“: Man beschreibt die
  Entenstimme in Worten, das Modell erfindet sie, danach spricht die Ente immer mit
  genau dieser Stimme. Braucht eine Grafikkarte (AMD per ROCm, NVIDIA per CUDA) –
  auf dem Prozessor geht es, ist aber langsam. Lizenz: Apache-2.0.

Dazu der „Entenfilter“: etwas höher, etwas nasaler – damit auch eine normale
Menschenstimme nach Ente klingt. Und eine Schnabelspur (0…1 alle 0,1 s), damit sich
der Schnabel beim Sprechen bewegt.

Alles Schwere (numpy, piper, torch) wird erst geladen, wenn es gebraucht wird.
Modelle und Stimmen liegen im lokalen App-Datenordner, nicht in OneDrive.
"""

from __future__ import annotations

import io
import json
import logging
import math
import threading
import time
import urllib.request
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

HF = "https://huggingface.co"
PIPER_REPO = "rhasspy/piper-voices"

# Deutsche Piper-Stimmen (Auswahl). mb = ungefähre Größe des Downloads.
PIPER_VOICES: dict[str, dict[str, Any]] = {
    "thorsten_emotional": {
        "name": "Thorsten, mit Gefühl", "pfad": "de/de_DE/thorsten_emotional/medium/de_DE-thorsten_emotional-medium",
        "mb": 77, "art": "männlich · fröhlich, überrascht, flüsternd, verschlafen", "gefuehle": True},
    "thorsten": {
        "name": "Thorsten, klar", "pfad": "de/de_DE/thorsten/high/de_DE-thorsten-high",
        "mb": 114, "art": "männlich · beste Piper-Qualität"},
    "kerstin": {
        "name": "Kerstin", "pfad": "de/de_DE/kerstin/low/de_DE-kerstin-low",
        "mb": 63, "art": "weiblich · freundlich"},
    "ramona": {
        "name": "Ramona", "pfad": "de/de_DE/ramona/low/de_DE-ramona-low",
        "mb": 63, "art": "weiblich · ruhig"},
    "eva_k": {
        "name": "Eva", "pfad": "de/de_DE/eva_k/x_low/de_DE-eva_k-x_low",
        "mb": 21, "art": "weiblich · sehr klein, einfache Qualität"},
}

# Stimmung der Ente → Sprecher von „Thorsten, mit Gefühl“
EMOTIONAL_SPEAKER = {
    "begeistert": "amused", "fröhlich": "amused", "stolz": "amused", "erleichtert": "amused",
    "erschrocken": "surprised", "staunen": "surprised", "mitfühlend": "whisper", "müde": "sleepy",
}

QWEN_BASE = {"schnell": "Qwen/Qwen3-TTS-12Hz-0.6B-Base", "hoch": "Qwen/Qwen3-TTS-12Hz-1.7B-Base"}
QWEN_DESIGN = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
QWEN_MB = {"schnell": 2400, "hoch": 4500, "entwurf": 4500}

# Vorlagen für „Stimme entwerfen“ – der Mensch kann sie ändern oder eigene schreiben.
DESIGN_PRESETS: dict[str, str] = {
    "Quirlige Ente": "A small, bubbly cartoon duck character: high, bright and slightly nasal voice with a playful "
                     "quack-like edge, quick cheerful tempo, warm and affectionate, young and curious.",
    "Gemütliche Ente": "A cozy, friendly duck: soft, warm, slightly nasal mid-high voice, calm relaxed tempo, "
                       "smiling while talking, gentle and kind.",
    "Freche Ente": "A cheeky young duck: high, lively voice with a little rasp and a laugh in it, bouncy rhythm, "
                   "mischievous but lovable, slightly nasal.",
}
DESIGN_TEXT = "Hallo! Ich bin {name}, deine kleine Ente. Schön, dass du da bist – wollen wir zusammen etwas ausprobieren?"

# Je Körper eigene Vorlagen (Hinweis aus dem Test 5.11.: „Stimme entwerfen ist noch nicht auf die Robotertypen angepasst“).
# Schlüssel wie `config.modul`, dazu „kopf“ für Knowlin ohne Körper. Die Microduck behält die Enten-Vorlagen oben.
DESIGN_PRESETS_MODUL: dict[str, dict[str, str]] = {
    "duckpilot": DESIGN_PRESETS,
    "open_duck_mini": {
        "Bastler-Ente": "A home-built robot duck: somewhat deeper, warm, slightly nasal voice, easygoing tempo, proud and "
                        "a little clumsy, with tinkerer's charm and a smile in the voice.",
        "Große Ente": "A bigger, good-natured duck: deep, round, sonorous voice with a slightly quacky undertone, slow "
                      "friendly tempo, gruff but warm-hearted.",
        "Tollpatschige Ente": "A clumsy young duck: mid to lower voice, a bit bumpy and lively, likes to laugh at itself, "
                              "slightly nasal, warm and playful.",
    },
    "reachy_mini": {
        "Freundlicher Tischroboter": "A friendly, curious little desktop robot: warm, clear mid-range voice with a slight "
                                     "technical, softly synthetic sheen, calm attentive tempo, kind and helpful, not squeaky.",
        "Neugieriger Beobachter": "An attentive, curious robot: calm, soft mid-pitched voice, easily amazed, speaks "
                                  "deliberately and clearly, with quiet dry humor and a hint of electronics in the sound.",
        "Fröhlicher Helfer": "A cheerful little helper robot: bright, warm voice, a bit quicker and lively, friendly and "
                             "engaging, slightly metallic undertone but natural and easy to understand.",
    },
    "kopf": {
        "Ruhig und tief": "A calm, deep, warm voice of an adult being – serious, clear and a little mysterious, slow tempo, "
                          "distinct pronunciation.",
        "Freundlich und klar": "A friendly, clear, mid-range voice – calm and attentive, relaxed tempo, warm, with a quiet "
                               "smile.",
    },
}
# Was die entworfenen Fassungen sagen – Reachy und Knowlin ohne Ente
DESIGN_TEXT_MODUL: dict[str, str] = {
    "duckpilot": DESIGN_TEXT,
    "open_duck_mini": "Hallo! Ich bin {name}, eine selbstgebaute Ente. Schön, dass du da bist – wollen wir zusammen etwas "
                      "ausprobieren?",
    "reachy_mini": "Hallo! Ich bin {name}, ein kleiner Roboter auf deinem Schreibtisch. Schön, dass du da bist – wollen wir "
                   "zusammen etwas ausprobieren?",
    "kopf": "Hallo. Ich bin {name}. Schön, dass du da bist – wollen wir gemeinsam etwas herausfinden?",
}
STANDARD_NAME = {"duckpilot": "Quacki", "open_duck_mini": "Odi", "reachy_mini": "Reachy", "kopf": "Knowlin"}


def design_text(art: str, name: str | None) -> str:
    """Der Satz, den die entworfenen Fassungen sprechen – passend zum Körper (`config.modul`) oder „kopf“."""
    art = art if art in DESIGN_TEXT_MODUL else "duckpilot"
    return DESIGN_TEXT_MODUL[art].format(name=(name or "").strip() or STANDARD_NAME[art])

SAMPLE_RATE_OUT = 24000


def _has(module: str) -> bool:
    """Installiert? Ohne es zu laden (torch zu importieren kostet Sekunden und viel Speicher)."""
    import importlib
    import importlib.util

    importlib.invalidate_caches()
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


# ── Klangbearbeitung (numpy) ────────────────────────────────────────────────
def _ordner_bytes(ordner: Path) -> int:
    """Summe aller Dateigrößen in einem Ordner (auch halbe Downloads); fehlt er, 0."""
    if not ordner.exists():
        return 0
    n = 0
    for f in ordner.iterdir():
        try:
            if f.is_file():
                n += f.stat().st_size
        except OSError:
            continue
    return n


def _repo_bytes(repo: str) -> int | None:
    """Gesamtgröße eines Modells auf Hugging Face – None, wenn das nicht abzufragen ist."""
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(repo, files_metadata=True)
        return sum(int(s.size or 0) for s in (info.siblings or [])) or None
    except Exception:
        return None


def download_text(n: int, gesamt: int | None) -> str:
    """„1,2 von 2,4 GB (50 %)“ – deutsch formatiert."""
    def gb(x: int) -> str:
        return f"{x / 1e9:.1f}".replace(".", ",")
    if not gesamt:
        return f"{gb(n)} GB"
    return f"{gb(n)} von {gb(gesamt)} GB ({min(99, int(n * 100 / gesamt))} %)"


def _np():
    import numpy as np

    return np


def resample(x, factor: float):
    """Länge × factor durch lineare Interpolation (reicht für Sprache; Tonhöhe ändert sich mit)."""
    np = _np()
    n = max(1, int(round(len(x) * factor)))
    if n == len(x):
        return x.astype(np.float32)
    pos = np.linspace(0, len(x) - 1, n)
    return np.interp(pos, np.arange(len(x)), x).astype(np.float32)


def time_stretch(x, factor: float, sr: int):
    """Länge × factor bei gleicher Tonhöhe (WSOLA – sucht passende Stücke und blendet sie über)."""
    np = _np()
    if abs(factor - 1.0) < 1e-3 or len(x) < 2048:
        return x.astype(np.float32)
    win = max(256, int(sr * 0.04) // 2 * 2)
    hop_out = win // 2
    hop_in = hop_out / factor
    tol = win // 4
    window = np.hanning(win).astype(np.float32)
    n_out = int(len(x) * factor)
    out = np.zeros(n_out + win, dtype=np.float32)
    norm = np.zeros(n_out + win, dtype=np.float32)
    pad = np.concatenate([np.zeros(tol, np.float32), x.astype(np.float32), np.zeros(win + tol, np.float32)])
    prev = 0
    k = 0
    while k * hop_out < n_out:
        ideal = int(k * hop_in)
        if k == 0:
            best = ideal
        else:
            natural = pad[tol + prev + hop_out: tol + prev + hop_out + win]
            lo, hi = ideal, ideal + 2 * tol
            region = pad[lo: hi + win]
            if len(region) < win or len(natural) < win:
                best = ideal
            else:
                corr = np.correlate(region, natural, mode="valid")
                best = lo + int(np.argmax(corr)) - tol
        best = max(0, min(best, len(x) - 1))
        seg = pad[tol + best: tol + best + win]
        if len(seg) < win:
            seg = np.pad(seg, (0, win - len(seg)))
        o = k * hop_out
        out[o: o + win] += seg * window
        norm[o: o + win] += window
        prev = best
        k += 1
    norm[norm < 1e-3] = 1.0
    return (out / norm)[:n_out]


def eq(x, sr: int, amount: float):
    """Entenfarbe: tiefe Töne weg, nasale Mitten (≈1,3 kHz) und etwas Glanz dazu."""
    np = _np()
    if amount <= 0 or len(x) < 64:
        return x
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    db = (
        -9.0 * amount / (1 + (f / 220.0) ** 4)                       # weniger Brust
        + 7.0 * amount * np.exp(-0.5 * (np.log2(np.maximum(f, 1) / 1300.0) / 0.45) ** 2)   # Nase
        + 2.5 * amount * np.exp(-0.5 * (np.log2(np.maximum(f, 1) / 3200.0) / 0.5) ** 2)    # Glanz
    )
    y = np.fft.irfft(spec * 10 ** (db / 20), n=len(x)).astype(np.float32)
    peak = float(np.max(np.abs(y))) or 1.0
    return y * min(1.0, 0.95 / peak) if peak > 0.95 else y


def semitones(amount: float) -> float:
    """Wie viel höher die Ente spricht: bis zu sieben Halbtöne (mit Formanten – das macht den Comic-Klang)."""
    return 7.0 * max(0.0, min(1.0, amount))


def duck_filter(x, sr: int, amount: float, already_slow: float = 1.0):
    """Höher und nasaler. `already_slow` > 1: die Stimme wurde schon langsamer erzeugt (Piper) –
    dann reicht Umtasten, und die Länge stimmt wieder."""
    if amount <= 0:
        return x
    p = 2 ** (semitones(amount) / 12)
    y = resample(x, 1 / p)
    rest = p / already_slow
    if abs(rest - 1.0) > 0.01:
        y = time_stretch(y, rest, sr)
    return eq(y, sr, amount)


def mouth_track(x, sr: int, step: float = 0.1) -> list[float]:
    """Schnabelöffnung 0…1 alle `step` Sekunden aus der Lautstärke."""
    np = _np()
    n = max(1, int(sr * step))
    frames = len(x) // n
    if frames == 0:
        return []
    rms = np.sqrt(np.mean(np.square(x[: frames * n].reshape(frames, n)), axis=1))
    ref = float(np.percentile(rms, 92)) or 1.0
    level = np.clip(rms / ref, 0, 1) ** 0.7
    level[level < 0.12] = 0.0
    return [round(float(v), 2) for v in level]


def to_wav(x, sr: int) -> bytes:
    np = _np()
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()


def read_wav(data: bytes):
    np = _np()
    with wave.open(io.BytesIO(data), "rb") as w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError("nur 16-Bit-WAV")
    x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


# ── Ergebnis ────────────────────────────────────────────────────────────────
@dataclass
class Audio:
    wav: bytes
    mund: list[float]
    sekunden: float
    rechenzeit: float = 0.0


@dataclass
class Style:
    stimmung: str = "ausgeglichen"
    goofy: bool = False
    energie: float = 0.5
    entenhaft: float = 0.4
    tempo: float = 1.0               # > 1 schneller


# ── Motoren ─────────────────────────────────────────────────────────────────
class EngineError(RuntimeError):
    pass


def _download(url: str, dest: Path, progress: Callable[[float], None] | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".teil")
    req = urllib.request.Request(url, headers={"User-Agent": "duckpilot"})
    with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    tmp.replace(dest)


def _qwen_sprache() -> str:
    """Qwen3-TTS spricht in der eingestellten Sprache der Ente (seit 0.34)."""
    from .. import i18n
    return "English" if i18n.sprache() == "en" else "German"


class PiperEngine:
    id = "piper"
    name = "Piper"

    def __init__(self, root: Path) -> None:
        self.root = root / "stimmen" / "piper"
        self._voices: dict[str, Any] = {}
        self._lock = threading.Lock()

    @staticmethod
    def installed() -> bool:
        return _has("piper")

    def files(self, vid: str) -> tuple[Path, Path]:
        stem = PIPER_VOICES[vid]["pfad"].rsplit("/", 1)[-1]
        return self.root / f"{stem}.onnx", self.root / f"{stem}.onnx.json"

    def has_voice(self, vid: str) -> bool:
        if vid not in PIPER_VOICES:
            return False
        model, conf = self.files(vid)
        return model.exists() and conf.exists()

    def download(self, vid: str, progress: Callable[[float], None] | None = None) -> None:
        if vid not in PIPER_VOICES:
            raise EngineError(f"Keine Piper-Stimme '{vid}'")
        model, conf = self.files(vid)
        base = f"{HF}/{PIPER_REPO}/resolve/main/{PIPER_VOICES[vid]['pfad']}"
        _download(f"{base}.onnx.json", conf)
        _download(f"{base}.onnx", model, progress)

    def _voice(self, vid: str):
        with self._lock:
            if vid not in self._voices:
                if not self.has_voice(vid):
                    raise EngineError(f"Stimme „{PIPER_VOICES.get(vid, {}).get('name', vid)}“ ist noch nicht geladen")
                from piper import PiperVoice

                model, conf = self.files(vid)
                self._voices[vid] = PiperVoice.load(str(model), config_path=str(conf))
            return self._voices[vid]

    def speakers(self, vid: str) -> dict[str, int]:
        try:
            conf = json.loads(self.files(vid)[1].read_text(encoding="utf-8"))
            return dict(conf.get("speaker_id_map") or {})
        except Exception:
            return {}

    def synthesize(self, text: str, vid: str, style: Style):
        """→ (samples float32, sample_rate). Langsamer erzeugt, damit der Entenfilter die Länge zurückholt."""
        from piper import SynthesisConfig

        np = _np()
        voice = self._voice(vid)
        p = 2 ** (semitones(style.entenhaft) / 12)
        speaker = None
        if PIPER_VOICES[vid].get("gefuehle"):
            spk = self.speakers(vid)
            want = "amused" if style.goofy else EMOTIONAL_SPEAKER.get(style.stimmung, "neutral")
            speaker = spk.get(want, spk.get("neutral"))
        cfg = SynthesisConfig(speaker_id=speaker, length_scale=p / max(0.6, style.tempo),
                              noise_scale=0.7 if style.goofy else 0.6, noise_w_scale=0.85)
        chunks = list(voice.synthesize(text, cfg))
        if not chunks:
            return np.zeros(1, np.float32), voice.config.sample_rate, p
        x = np.concatenate([c.audio_float_array for c in chunks]).astype(np.float32)
        return x, chunks[0].sample_rate, p


class QwenEngine:
    """Qwen3-TTS: entworfene Stimme (VoiceDesign) → geklont gesprochen (Base)."""

    id = "qwen"
    name = "Qwen3-TTS"

    def __init__(self, root: Path) -> None:
        self.root = root
        self.models_dir = root / "modelle"
        self.voices_dir = root / "stimmen" / "qwen"
        self._base = None
        self._base_id = None
        self._prompts: dict[str, Any] = {}
        self._lock = threading.Lock()
        self.device = None

    @staticmethod
    def installed() -> bool:
        return not QwenEngine.missing()

    @staticmethod
    def missing() -> list[str]:
        from .install import missing

        return missing("qwen")

    @staticmethod
    def accelerator() -> dict[str, Any]:
        """Welche Grafikkarte torch sieht (ROCm erscheint unter torch.cuda)."""
        try:
            import torch

            if torch.cuda.is_available():
                name = torch.cuda.get_device_name(0)
                rocm = bool(getattr(torch.version, "hip", None))
                return {"gpu": True, "name": name, "art": "ROCm" if rocm else "CUDA"}
        except Exception as exc:
            return {"gpu": False, "name": None, "art": None, "fehler": str(exc)}
        return {"gpu": False, "name": None, "art": None}

    def _ordner(self, repo: str) -> Path:
        return self.models_dir / ("models--" + repo.replace("/", "--"))

    def angefangen(self, repo: str) -> int:
        """Schon heruntergeladene Bytes (fertige und halbe Dateien) – > 0 und nicht fertig = Download fortsetzen."""
        return _ordner_bytes(self._ordner(repo) / "blobs")

    def download(self, repo: str, progress: Callable[[int, int | None], None] | None = None) -> str:
        """Modell holen, mit Fortschritt (Bytes, Gesamtgröße) und Fortsetzen (seit 0.37.7, Wunsch des Maintainers).

        huggingface_hub setzt halbe Dateien (`*.incomplete`) beim nächsten Mal per Range-Anfrage fort – auch nach einem
        Neustart von duckpilot. Der Xet-Weg schreibt anderswo hin und lässt sich so nicht messen, deshalb der klassische
        Download. Der Fortschritt wird jede Sekunde an der Größe des Modellordners gemessen.
        """
        import os

        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        import huggingface_hub.constants as hf_konst
        from huggingface_hub import snapshot_download

        hf_konst.HF_HUB_DISABLE_XET = True
        gesamt = _repo_bytes(repo)
        blobs = self._ordner(repo) / "blobs"
        stop = threading.Event()

        def beobachten() -> None:
            while not stop.wait(1.0):
                try:
                    progress(_ordner_bytes(blobs), gesamt)
                except Exception:
                    log.debug("Download-Fortschritt", exc_info=True)

        if progress:
            progress(_ordner_bytes(blobs), gesamt)
            threading.Thread(target=beobachten, daemon=True, name="download-fortschritt").start()
        try:
            return snapshot_download(repo, cache_dir=str(self.models_dir))
        finally:
            stop.set()

    def _load(self, repo: str, progress: Callable[[int, int | None], None] | None = None):
        import torch
        from qwen_tts import Qwen3TTSModel

        path = self.download(repo, progress)
        if torch.cuda.is_available():
            kw = {"device_map": "cuda:0", "dtype": torch.bfloat16}
            self.device = "gpu"
        else:
            kw = {"device_map": "cpu", "dtype": torch.float32}
            self.device = "cpu"
        return Qwen3TTSModel.from_pretrained(path, attn_implementation="sdpa", **kw)

    def loaded(self, quality: str = "schnell") -> bool:
        """Ist das Sprechmodell (Base) schon geladen? Erst dann spricht die Ente mit der entworfenen Stimme."""
        return self._base is not None and self._base_id == QWEN_BASE.get(quality, QWEN_BASE["schnell"])

    def has_model(self, repo: str) -> bool:
        folder = self._ordner(repo)
        snaps = folder / "snapshots"
        halb = (folder / "blobs").exists() and any((folder / "blobs").glob("*.incomplete"))
        return snaps.exists() and any(snaps.iterdir()) and not halb

    def voices(self) -> list[dict[str, Any]]:
        out = []
        if self.voices_dir.exists():
            for meta in sorted(self.voices_dir.glob("*.json")):
                try:
                    info = json.loads(meta.read_text(encoding="utf-8"))
                    if (self.voices_dir / f"{meta.stem}.wav").exists():
                        out.append({"id": meta.stem, **{k: info.get(k) for k in ("name", "beschreibung", "erstellt")}})
                except Exception:
                    continue
        return out

    def base(self, quality: str = "schnell", progress: Callable[[int, int | None], None] | None = None):
        repo = QWEN_BASE.get(quality, QWEN_BASE["schnell"])
        with self._lock:
            if self._base is None or self._base_id != repo:
                self._base = None
                self._prompts.clear()
                self._free()
                self._base = self._load(repo, progress)
                self._base_id = repo
            return self._base

    def _free(self) -> None:
        try:
            import gc

            import torch

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _prompt(self, vid: str, model):
        wav = self.voices_dir / f"{vid}.wav"
        key = f"{vid}@{wav.stat().st_mtime_ns}"      # neu gespeicherte Stimme gleichen Namens → neu einlesen
        if key not in self._prompts:
            meta = json.loads((self.voices_dir / f"{vid}.json").read_text(encoding="utf-8"))
            x, sr = read_wav(wav.read_bytes())
            self._prompts[key] = model.create_voice_clone_prompt(ref_audio=(x, sr), ref_text=meta["text"])
        return self._prompts[key]

    def synthesize(self, text: str, vid: str, style: Style, quality: str = "schnell"):
        np = _np()
        if not (self.voices_dir / f"{vid}.wav").exists():
            raise EngineError("Diese Entenstimme gibt es nicht mehr – bitte neu entwerfen oder auswählen")
        model = self.base(quality)
        prompt = self._prompt(vid, model)
        wavs, sr = model.generate_voice_clone(text=text, language=_qwen_sprache(), voice_clone_prompt=prompt)
        x = np.asarray(wavs[0], dtype=np.float32)
        return x, sr, 1.0

    def design(self, instruct: str, text: str, takes: int = 3, progress: Callable[[str], None] | None = None):
        """Neue Stimme erfinden: mehrere Fassungen derselben Probe. Danach wird das große Modell wieder entladen."""
        np = _np()
        with self._lock:
            self._base = None
            self._prompts.clear()
            self._free()
            if progress:
                progress("lade das Entwurfsmodell (beim ersten Mal ≈ 4,5 GB) …")

            def geladen(n: int, gesamt: int | None) -> None:
                if progress and gesamt and n < gesamt:
                    progress(f"lädt das Entwurfsmodell herunter: {download_text(n, gesamt)}")

            model = self._load(QWEN_DESIGN, geladen)
            out = []
            try:
                for i in range(takes):
                    if progress:
                        progress(f"erfinde Fassung {i + 1} von {takes} …")
                    wavs, sr = model.generate_voice_design(text=text, language=_qwen_sprache(), instruct=instruct,
                                                           do_sample=True)
                    out.append((np.asarray(wavs[0], dtype=np.float32), sr))
            finally:
                del model
                self._free()
            return out

    def save_voice(self, vid: str, name: str, x, sr: int, text: str, instruct: str,
                   beschreibung: str | None = None) -> None:
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        (self.voices_dir / f"{vid}.wav").write_bytes(to_wav(x, sr))
        (self.voices_dir / f"{vid}.json").write_text(json.dumps({
            "name": name, "text": text, "beschreibung": beschreibung or instruct, "modell_beschreibung": instruct,
            "erstellt": time.strftime("%Y-%m-%d %H:%M"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        self._prompts.pop(vid, None)

    def delete_voice(self, vid: str) -> None:
        for ext in (".wav", ".json"):
            p = self.voices_dir / f"{vid}{ext}"
            if p.exists():
                p.unlink()
        self._prompts.pop(vid, None)


@dataclass
class Synth:
    """Gemeinsamer Eingang: wählt den Motor, wendet den Entenfilter an, misst den Schnabel."""

    root: Path
    piper: PiperEngine = field(init=False)
    qwen: QwenEngine = field(init=False)          # QwenProzess

    def __post_init__(self) -> None:
        self.piper = PiperEngine(self.root)
        import atexit

        from .qwen_prozess import QwenProzess  # Qwen rechnet in einem eigenen Prozess (seit 0.37.8)

        self.qwen = QwenProzess(self.root)
        atexit.register(self.qwen.beenden)

    def render(self, text: str, engine: str, voice: str, style: Style, quality: str = "schnell") -> Audio:
        t0 = time.monotonic()
        if engine == "piper":
            x, sr, slow = self.piper.synthesize(text, voice, style)
        elif engine == "qwen":
            x, sr, slow = self.qwen.synthesize(text, voice, style, quality)
            if abs(style.tempo - 1.0) > 0.03:
                x = time_stretch(x, 1 / style.tempo, sr)
        else:
            raise EngineError(f"Unbekannter Sprachmotor '{engine}'")
        x = duck_filter(x, sr, style.entenhaft, already_slow=slow)
        x = _trim(x, sr)
        return Audio(to_wav(x, sr), mouth_track(x, sr), round(len(x) / sr, 2), round(time.monotonic() - t0, 2))


def _trim(x, sr: int):
    """Stille am Anfang und Ende kürzen – sonst stockt das Gespräch zwischen Sätzen."""
    np = _np()
    if len(x) == 0:
        return x
    loud = np.where(np.abs(x) > 0.02)[0]
    if len(loud) == 0:
        return x[:1]
    a = max(0, loud[0] - int(0.03 * sr))
    b = min(len(x), loud[-1] + int(0.08 * sr))
    return x[a:b]


def fmt_seconds(s: float) -> str:
    return f"{s:.1f} s".replace(".", ",") if s < 60 else f"{math.floor(s / 60)} min"
