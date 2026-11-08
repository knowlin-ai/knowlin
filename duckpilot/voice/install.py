"""Zusatzpakete aus der Oberfläche installieren – nur feste Paketlisten, nie freie Eingaben.

Läuft mit dem Python von duckpilot (der Umgebung in %LOCALAPPDATA%\\duckpilot\\venv),
Zeile für Zeile mitgeschrieben, damit man in der Oberfläche sieht, was passiert.

Qwen3-TTS braucht PyTorch. Für die Grafikkarte gibt es drei Wege:
* AMD (Radeon RX 9000/7000): PyTorch mit ROCm direkt unter Windows, aus AMDs Paketquelle.
* NVIDIA: PyTorch mit CUDA aus der PyTorch-Paketquelle.
* Nur Prozessor: geht immer, ist für Qwen aber langsam.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

AMD_INDEX = "https://stable.repo.amd.com/rocm/whl-next/"
CUDA_INDEX = "https://download.pytorch.org/whl/cu128"
CPU_INDEX = "https://download.pytorch.org/whl/cpu"

# Radeon-Modell → ROCm-Architektur (AMDs Paket-Extras torch[device-gfx…])
AMD_ARCH = [("9070", "gfx1201"), ("9060", "gfx1200"), ("7900", "gfx1100"), ("7800", "gfx1101"),
            ("7700", "gfx1101"), ("7600", "gfx1102")]
GPUS = ("amd", "nvidia", "cpu")

# Qwen3-TTS hängt an transformers 4.57.3, und das verlangt huggingface_hub unter 1.0 (prüft es beim Laden).
# Deshalb steht dieselbe Grenze auch beim Trainingspaket – sonst macht das eine das andere kaputt.
HUB_PIN = "huggingface_hub>=0.34,<1.0"
QWEN_CORE = ["transformers==4.57.3", "accelerate==1.12.0", HUB_PIN, "einops", "soundfile"]
QWEN_AUDIO = ["librosa", "onnxruntime", "sox"]
QWEN_DEPS = QWEN_CORE + QWEN_AUDIO

PAKETE: dict[str, dict[str, Any]] = {
    "piper": {"name": "Piper (schnelle Stimme)", "mb": 40, "modul": "piper"},
    "qwen": {"name": "Qwen3-TTS (natürliche Stimme)", "mb": 3500, "modul": "qwen_tts"},
    "whisper": {"name": "Whisper (Spracherkennung auf dem PC)", "mb": 250, "modul": "faster_whisper"},
    "physik": {"name": "MuJoCo + ONNX (echte Physik)", "mb": 120, "modul": "mujoco"},
    "bam": {"name": "Rhobans Motormodell BAM (wie im Training)", "mb": 1, "modul": "bam"},
    "training": {"name": "Hugging Face (Training in der Cloud)", "mb": 5, "modul": "huggingface_hub"},
    "gesichter": {"name": "Personen erkennen (ONNX, Pillow – nur auf diesem PC)", "mb": 60, "modul": "PIL"},
    "lernen": {"name": "Selbst lernen am PC (PyTorch für die Grafikkarte, ONNX)", "mb": 2500, "modul": "torch"},
}
# Was zum Laufen alles da sein muss (Python-Modulnamen) – fehlt eins, gilt das Paket als unvollständig.
MODULE: dict[str, list[str]] = {
    "qwen": ["qwen_tts", "torch", "torchaudio", "transformers", "accelerate", "huggingface_hub", "einops", "soundfile",
             "librosa", "onnxruntime"],
    "physik": ["mujoco", "onnxruntime", "numpy"],
    "gesichter": ["onnxruntime", "numpy", "PIL"],
    "lernen": ["torch", "onnx", "onnxruntime", "mujoco", "numpy"],
}
BAM_ZIP = "https://github.com/Rhoban/bam/archive/refs/heads/mjlab_frictionloss.zip"


def detect_gpus() -> list[str]:
    """Namen der Grafikkarten (Windows: über PowerShell; sonst leer)."""
    if sys.platform != "win32":
        return []
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"],
            capture_output=True, text=True, timeout=15, creationflags=0x08000000,
        ).stdout
        return [line.strip() for line in out.splitlines() if line.strip()]
    except Exception:
        return []


def amd_arch(names: list[str]) -> str | None:
    for n in names:
        if "radeon" in n.lower():
            for key, arch in AMD_ARCH:
                if key in n:
                    return arch
    return None


def suggest_gpu(names: list[str]) -> str:
    if amd_arch(names):
        return "amd"
    if any("nvidia" in n.lower() or "geforce" in n.lower() or "rtx" in n.lower() for n in names):
        return "nvidia"
    return "cpu"


# Im eingebetteten Python des Installers (python*._pth neben python.exe) übergeht Python PYTHONPATH – pip baut
# Quellpakete aber in einer abgeschotteten Umgebung, die genau darüber eingebunden wird. Folge: „No module named
# 'setuptools'“ beim Paket `rocm` aus AMDs Quelle (gemeldet nach 0.38.32). Dort deshalb erst die Bauwerkzeuge in die
# eigene Umgebung legen und ohne Abschottung bauen.
BAUWERKZEUGE = ["setuptools>=77", "wheel", "packaging"]


def eingebettet(exe: str | Path | None = None) -> bool:
    """Läuft Knowlin im eingebetteten Python (Windows-Installer)?"""
    ordner = Path(exe or python_exe()).parent
    return any(ordner.glob("python*._pth"))


def commands(paket: str, gpu: str = "cpu", arch: str | None = None, eingebettet: bool = False) -> list[list[str]]:
    """Die pip-Aufrufe (ohne `python -m pip install`) – fest vorgegeben."""
    schritte = _commands(paket, gpu, arch)
    if not eingebettet:
        return schritte
    return [BAUWERKZEUGE] + [["--no-build-isolation", *s] for s in schritte]


def _commands(paket: str, gpu: str = "cpu", arch: str | None = None) -> list[list[str]]:
    if paket == "piper":
        return [["piper-tts>=1.3"]]
    if paket == "whisper":
        return [["faster-whisper>=1.0"]]
    if paket == "physik":
        return [["mujoco>=3.2", "onnxruntime>=1.18", "numpy"]]
    if paket == "training":
        return [[HUB_PIN]]
    if paket == "gesichter":
        return [["onnxruntime>=1.18", "numpy", "pillow>=10"]]
    if paket == "bam":
        # BAM verlangt Python < 3.13, läuft aber für das, was duckpilot braucht (bam.model, bam.mujoco)
        return [["--no-deps", "--ignore-requires-python", BAM_ZIP], ["colorama"]]
    if paket in ("qwen", "lernen"):
        if gpu == "amd":
            arch = arch if arch and re.fullmatch(r"gfx\d{3,4}", arch) else "gfx1201"
            torch = ["--index-url", AMD_INDEX, f"torch[device-{arch}]", "torchaudio"]
        elif gpu == "nvidia":
            torch = ["--index-url", CUDA_INDEX, "torch", "torchaudio"]
        else:
            torch = ["--index-url", CPU_INDEX, "torch", "torchaudio"]
        if paket == "lernen":            # torchaudio braucht das Lernen nicht
            return [torch[:-1], ["onnx>=1.16", "onnxruntime>=1.18", "mujoco>=3.2", "numpy"]]
        # einzeln, damit ein hakeliges Audio-Paket nicht auch den Rest (z. B. huggingface_hub) verhindert
        return [torch, ["--no-deps", "qwen-tts==0.1.1"], QWEN_CORE, QWEN_AUDIO]
    raise ValueError(f"Unbekanntes Paket '{paket}'")


def python_exe() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and exe.with_name("python.exe").exists():
        return str(exe.with_name("python.exe"))
    return str(exe)


def missing(paket: str) -> list[str]:
    """Welche Module fehlen – ohne sie zu laden (torch & Co. kosten Sekunden und viel Speicher)."""
    from .tts import _has

    if paket not in PAKETE:
        return []
    mods = MODULE.get(paket) or [PAKETE[paket]["modul"]]
    return [m for m in mods if not _has(m)]


def installed(paket: str) -> bool:
    return paket in PAKETE and not missing(paket)


class Installer:
    def __init__(self, on_change: Callable[[], None] | None = None) -> None:
        self.on_change = on_change
        self.jobs: dict[str, dict[str, Any]] = {}

    def _changed(self) -> None:
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                log.exception("Installer")

    def running(self) -> bool:
        return any(j.get("laeuft") for j in self.jobs.values())

    async def install(self, paket: str, gpu: str = "cpu", runner: Callable | None = None) -> dict[str, Any]:
        if paket not in PAKETE:
            raise ValueError(f"Unbekanntes Paket '{paket}'")
        if gpu not in GPUS:
            raise ValueError("Grafikkarte: amd, nvidia oder cpu")
        if self.running():
            raise ValueError("Es läuft schon eine Installation.")
        arch = None
        if paket in ("qwen", "lernen") and gpu == "amd":
            arch = amd_arch(await asyncio.to_thread(detect_gpus))
        steps = commands(paket, gpu, arch, eingebettet())
        job = self.jobs[paket] = {"laeuft": True, "zeilen": [], "fehler": None, "start": time.time(), "gpu": gpu,
                                  "schritt": 0, "schritte": len(steps)}
        self._changed()
        run = runner or self._pip
        try:
            for i, args in enumerate(steps):
                job["schritt"] = i + 1
                code = await run(args, job)
                if code != 0:
                    raise RuntimeError(f"pip endete mit Code {code}")
            fehlt = missing(paket) if runner is None else []
            job["fertig"] = not fehlt
            if fehlt:
                raise RuntimeError(f"pip ist durchgelaufen, aber es fehlt noch {', '.join(fehlt)} – "
                                   "duckpilot einmal neu starten und dann „Reparieren“")
        except Exception as exc:
            job["fehler"] = str(exc)
        finally:
            job["laeuft"] = False
            job["dauer"] = round(time.time() - job["start"])
            self._changed()
        return job

    async def _pip(self, args: list[str], job: dict[str, Any]) -> int:
        cmd = [python_exe(), "-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "off", *args]
        self._line(job, "$ pip install " + " ".join(args))
        kw: dict[str, Any] = {}
        if sys.platform == "win32":
            kw["creationflags"] = 0x08000000      # kein Konsolenfenster
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT, **kw)
        assert proc.stdout is not None
        last = time.monotonic()
        async for raw in proc.stdout:
            self._line(job, raw.decode("utf-8", "replace").rstrip())
            if time.monotonic() - last > 0.5:
                last = time.monotonic()
                self._changed()
        return await proc.wait()

    @staticmethod
    def _line(job: dict[str, Any], line: str) -> None:
        if not line.strip():
            return
        job["zeilen"].append(line[:300])
        del job["zeilen"][:-120]
