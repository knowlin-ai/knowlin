"""Eigene Bewegungen trainieren – Pollens Training auf Hugging Face Jobs, ohne eigene NVIDIA-Karte.

Pollens Training (`microduck_rl`, mjlab + MuJoCo Warp) braucht eine NVIDIA-Grafikkarte. Pollen hat
dafür selbst einen Weg eingebaut: `uv run train <Aufgabe> --hf-jobs` schickt den Lauf an Hugging
Face Jobs (eine gemietete GPU, abgerechnet pro Minute). duckpilot macht genau dasselbe, nur ohne
Kommandozeile: Es lädt den aktuellen Stand von `pollen-robotics/microduck_rl` von GitHub, packt ihn
wie Pollens Skript, legt ihn in ein privates Dataset-Repo, startet den Job mit Pollens
Bootstrap-Skript und holt am Ende die exportierte Policy (`exported/policy.onnx`) zurück –
direkt in den Physik-Simulator zum Ausprobieren.

Claude darf einen Trainingslauf **vorschlagen** (Aufgabe, Dauer, Belohnungsgewichte); starten
kann nur der Mensch, mit zwei Klicks – ein Lauf kostet Geld.

Der Hugging-Face-Token liegt wie der Claude-Schlüssel im Windows-Tresor, nie in einer Datei.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import logging
import math
import re
import shlex
import tarfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

RL_REPO = "pollen-robotics/microduck_rl"
RL_TARBALL = f"https://codeload.github.com/{RL_REPO}/tar.gz/refs/heads/main"
DEFAULT_IMAGE = "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime"
# Grafikkarten bei Hugging Face Jobs: Preis laut HF (US-Dollar pro Stunde, sekundengenau abgerechnet) und eine
# grobe Schätzung der Sekunden pro Iteration bei 4096 Umgebungen. Gemessene Werte aus eigenen Läufen ersetzen sie.
GPUS: dict[str, dict[str, Any]] = {
    "l4x1": {"name": "NVIDIA L4 (24 GB) – Pollens Standard", "usd_h": 0.80, "s_it": 3.5},
    "a10g-large": {"name": "NVIDIA A10G (24 GB)", "usd_h": 1.50, "s_it": 3.0},
    "l40sx1": {"name": "NVIDIA L40S (48 GB) – schneller", "usd_h": 1.80, "s_it": 2.0},
    "a100-large": {"name": "NVIDIA A100 (80 GB) – sehr schnell", "usd_h": 2.50, "s_it": 1.6},
    "rtx-pro-6000": {"name": "NVIDIA RTX PRO 6000 (96 GB) – wie in NVIDIAs Vorführung", "usd_h": 2.75, "s_it": 1.5},
}
FLAVORS = {k: v["name"] for k, v in GPUS.items()}
EXPORT_FLAVOR = "t4-small"          # nur den letzten Zwischenstand nach ONNX umwandeln: kleine GPU reicht
SETUP_MIN = 10                      # Container, apt, uv sync, Export – grob
KEYRING_USER = "huggingface_token"

_WALK_REWARDS = ["track_linear_velocity", "track_angular_velocity", "upright", "pose", "foot_clearance", "foot_slip",
                 "air_time", "action_rate_l2", "head_pose_tracking", "body_pose_tracking"]
TASKS: dict[str, dict[str, Any]] = {
    "Mjlab-Velocity-Flat-MicroDuck": {"name": "Gehen auf ebenem Boden", "iter": 4000, "art": "gangart",
                                      "belohnungen": _WALK_REWARDS},
    "Mjlab-Velocity-Rough-MicroDuck": {"name": "Gehen auf unebenem Boden (Stufen, Schrägen)", "iter": 5000,
                                       "art": "gangart", "belohnungen": _WALK_REWARDS},
    "Mjlab-Velocity-Rough-Backlash-MicroDuck": {"name": "Gehen uneben, mit Getriebespiel (robuster am Roboter)",
                                                "iter": 5000, "art": "gangart", "belohnungen": _WALK_REWARDS},
    "Mjlab-VelStand-Flat-MicroDuck": {"name": "Gehen, Stehen und Aufstehen (VelStand)", "iter": 3000, "art": "gangart",
                                      "belohnungen": ["track_linear_velocity", "track_angular_velocity", "upright", "pose",
                                                      "foot_slip", "action_rate_l2"]},
    "Mjlab-VelStand-Rough-MicroDuck": {"name": "VelStand auf unebenem Boden", "iter": 3000, "art": "gangart",
                                       "belohnungen": ["track_linear_velocity", "track_angular_velocity", "upright",
                                                       "pose", "foot_slip", "action_rate_l2"]},
    "Mjlab-VelStand-Rough-Backlash-MicroDuck": {"name": "VelStand uneben, mit Getriebespiel (wie Pollens VelStand)",
                                                "iter": 3000, "art": "gangart",
                                                "belohnungen": ["track_linear_velocity", "track_angular_velocity",
                                                                "upright", "pose", "foot_slip", "action_rate_l2"]},
    "Mjlab-Spin-Flat-MicroDuck": {"name": "Pirouette", "iter": 2000, "art": "trick"},
    "Mjlab-Roulade-Flat-MicroDuck": {"name": "Purzelbaum", "iter": 3000, "art": "trick"},
    "Mjlab-BallKick-Flat-MicroDuck": {"name": "Ball schießen", "iter": 3000, "art": "trick"},
    "Mjlab-StandUp-Flat-MicroDuck": {"name": "Aufstehen nach dem Sturz", "iter": 4000, "art": "trick"},
    "Mjlab-StandUp-Rough-MicroDuck": {"name": "Aufstehen auf unebenem Boden", "iter": 4000, "art": "trick"},
    "Mjlab-SitStand-Flat-MicroDuck": {"name": "Hinsetzen und Aufstehen", "iter": 1500, "art": "platz"},
    "Mjlab-GroundPick-Flat-MicroDuck": {"name": "Etwas aufheben", "iter": 3000, "art": "platz"},
}
# Pollens geteilte Trainingsstände (pollen-robotics/microduck-training, docs/training_checkpoints.md):
# Aufgabe → Bündel. Gleiche Aufgabe = weitertrainieren (Lehrpläne laufen weiter), gleiche Familie =
# Warmstart (Gewichte bleiben, Lehrpläne beginnen neu). Spart einen großen Teil der Rechenzeit.
POLLEN_TRAINING = "pollen-robotics/microduck-training"
POLLEN_BUNDLES: dict[str, str] = {
    "Mjlab-VelStand-Rough-Backlash-MicroDuck": "velstand/0045i2si_2749",
    "Mjlab-BallKick-Flat-MicroDuck": "ball_kick_left/6bamlid8_2500",
    "Mjlab-GroundPick-Flat-MicroDuck": "ground_pick/4ly1pcxj_2750",
    "Mjlab-Roulade-Flat-MicroDuck": "microduck_roulade/blrqbcit_750",
    "Mjlab-SitStand-Flat-MicroDuck": "microduck_sitstand/vfhxgrum_2250",
    "Mjlab-StandUp-Flat-MicroDuck": "microduck_stand/69u48n8l_9750",
}


def family(task: str) -> str:
    """Aufgaben derselben Familie haben dieselben Beobachtungen und Aktionen (eben/uneben/Getriebespiel)."""
    return re.sub(r"-(Flat|Rough|Backlash)(?=-)", "", task)


def pollen_start(task: str) -> tuple[str, bool] | None:
    """(Bündel-Pfad, Warmstart?) aus Pollens Ständen – gleiche Aufgabe oder gleiche Familie."""
    if task in POLLEN_BUNDLES:
        return POLLEN_BUNDLES[task], False
    for other, bundle in POLLEN_BUNDLES.items():
        if family(other) == family(task):
            return bundle, True
    return None


# Was an `uv run train` durchgereicht werden darf: Pollens tyro-Optionen, nur Zahlen und Wahrheitswerte.
OVERRIDE_KEY = re.compile(r"(env|agent)\.[a-z0-9_]+(\.[a-z0-9_]+){0,5}")
OVERRIDE_VALUE = re.compile(r"-?\d+(\.\d+)?([eE]-?\d+)?|true|false|True|False")
BLOCKED_KEYS = ("agent.resume", "agent.load_run", "agent.load_checkpoint", "agent.run_name", "agent.logger",
                "agent.max_iterations", "env.scene.num_envs")

# Pollens Bootstrap (microduck_rl/src/mjlab_microduck/hf_jobs.py), unverändert in der Sache. Einziger Zusatz:
# Kann huggingface_hub kein Dataset einhängen (Versionen unter 1.0, die Qwen3-TTS braucht), lädt der Job den
# Code selbst mit dem Token herunter.
BOOTSTRAP = r"""
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -qq -y --no-install-recommends git curl ca-certificates xz-utils >/dev/null
curl -LsSf https://astral.sh/uv/0.11.30/install.sh | sh >/dev/null
export PATH="/root/.local/bin:$PATH"
export UV_LINK_MODE=copy
mkdir -p /work && cd /work
SRC_FILE="/src/$SRC_TARBALL"
if [ ! -f "$SRC_FILE" ]; then
    # ohne eingehängtes Dataset (ältere huggingface_hub-Versionen): Code selbst holen
    SRC_FILE=/tmp/src.tar.gz
    curl -fsSL -H "Authorization: Bearer $HF_TOKEN" -o "$SRC_FILE" \
        "https://huggingface.co/datasets/$SRC_REPO/resolve/main/$SRC_TARBALL"
fi
tar -xzf "$SRC_FILE"
uv sync --no-progress || { uv cache clean || true; uv sync --no-progress; }
mkdir -p logs/rsl_rl
nohup uv run python scripts/hf/uploader.py > /tmp/uploader.log 2>&1 &
UPLOADER_PID=$!
set +e
uv run train $TRAIN_ARGS
TRAIN_RC=$?
set -e
kill $UPLOADER_PID 2>/dev/null || true
CKPT_ONE_SHOT=1 uv run python scripts/hf/uploader.py || true
if [ "$TRAIN_RC" -eq 0 ]; then
    set +e
    TASK_ID=${TRAIN_ARGS%% *}
    CKPT=$(ls -t logs/rsl_rl/*/*/model_*.pt 2>/dev/null | head -1)
    if [ -n "$CKPT" ]; then
        uv run python scripts/export.py "$TASK_ID" --checkpoint-file "$CKPT" --num-envs 1 --onnx-file /work/policy.onnx \
        && uv run python - <<'PY'
import os
from huggingface_hub import HfApi
HfApi().upload_file(path_or_fileobj="/work/policy.onnx", path_in_repo="exported/policy.onnx",
                    repo_id=os.environ["CKPT_REPO"], repo_type="model")
PY
    fi
    set -e
fi
exit $TRAIN_RC
"""


# Nur exportieren: der letzte Zwischenstand eines abgebrochenen oder stehengebliebenen Laufs wird zur
# daemon-fertigen policy.onnx (Pollens scripts/export.py nimmt einen hf://-Pfad).
BOOTSTRAP_EXPORT = r"""
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -qq -y --no-install-recommends git curl ca-certificates xz-utils >/dev/null
curl -LsSf https://astral.sh/uv/0.11.30/install.sh | sh >/dev/null
export PATH="/root/.local/bin:$PATH"
export UV_LINK_MODE=copy
mkdir -p /work && cd /work
SRC_FILE="/src/$SRC_TARBALL"
if [ ! -f "$SRC_FILE" ]; then
    SRC_FILE=/tmp/src.tar.gz
    curl -fsSL -H "Authorization: Bearer $HF_TOKEN" -o "$SRC_FILE" \
        "https://huggingface.co/datasets/$SRC_REPO/resolve/main/$SRC_TARBALL"
fi
tar -xzf "$SRC_FILE"
uv sync --no-progress || { uv cache clean || true; uv sync --no-progress; }
echo "[export] $TASK_ID from $CKPT_PATH"
uv run python scripts/export.py "$TASK_ID" --checkpoint-file "hf://$CKPT_REPO/$CKPT_PATH" --num-envs 1 \
    --onnx-file /work/policy.onnx
uv run python - <<'PY'
import os
from huggingface_hub import HfApi
HfApi().upload_file(path_or_fileobj="/work/policy.onnx", path_in_repo="exported/policy.onnx",
                    repo_id=os.environ["CKPT_REPO"], repo_type="model")
print("[export] uploaded exported/policy.onnx")
PY
"""

STAGE = {"SCHEDULING": "wartet auf eine GPU", "RUNNING": "trainiert", "COMPLETED": "fertig",
         "ERROR": "fehlgeschlagen", "CANCELED": "abgebrochen", "CANCELLED": "abgebrochen", "DELETED": "abgebrochen"}
ACTIVE = ("bereitet vor", "gestartet", "wartet auf eine GPU", "trainiert", "exportiert")
EXPORT_MAX_MIN = 90          # länger darf ein Export nicht dauern


def latest_checkpoint(files: list[str]) -> str | None:
    """Neuester model_<N>.pt im Modell-Repo eines Laufs (Pfad wie logs/rsl_rl/<exp>/<run>/)."""
    best = None
    for f in files:
        m = re.fullmatch(r"((?:[\w-][\w.-]*/){0,4})model_(\d+)\.pt", f)
        if m and (best is None or int(m.group(2)) > best[0]):
            best = (int(m.group(2)), f)
    return best[1] if best else None


class TrainingError(RuntimeError):
    pass


def check_overrides(overrides: dict[str, Any] | None) -> dict[str, str]:
    clean: dict[str, str] = {}
    for key, value in (overrides or {}).items():
        key = str(key).strip().lstrip("-")
        val = str(value).strip()
        if not OVERRIDE_KEY.fullmatch(key) or key.startswith(BLOCKED_KEYS):
            raise ValueError(f"Option nicht erlaubt: {key[:60]}")
        if not OVERRIDE_VALUE.fullmatch(val):
            raise ValueError(f"{key}: nur Zahlen oder true/false")
        clean[key] = val
    if len(clean) > 20:
        raise ValueError("höchstens 20 Anpassungen")
    return clean


def check_plan(task: str, iterations: int | None = None, overrides: dict[str, Any] | None = None,
               flavor: str = "l4x1", start_von: str | None = None, max_stunden: Any = None,
               bei_stillstand: str = "weiter", measured: dict[str, float] | None = None) -> dict[str, Any]:
    """Einen Plan prüfen und in eine feste Form bringen. Wirft ValueError bei allem Unbekannten.
    `measured`: gemessene Sekunden pro Iteration (für Obergrenze und Prüfung, ob der Lauf hineinpasst)."""
    if task not in TASKS:
        raise ValueError(f"Unbekannte Aufgabe – erlaubt: {', '.join(TASKS)}")
    if flavor not in FLAVORS:
        raise ValueError(f"Unbekannte Grafikkarte – erlaubt: {', '.join(FLAVORS)}")
    it = int(iterations or TASKS[task]["iter"])
    if not 100 <= it <= 20000:
        raise ValueError("Iterationen: 100 bis 20 000")
    start = (start_von or "").strip() or None
    if start == "pollen":
        if pollen_start(task) is None:
            raise ValueError("Für diese Aufgabe gibt es keinen geteilten Stand von Pollen – „von vorn“ oder einen eigenen Lauf.")
    elif start is not None and not re.fullmatch(r"lauf:[\w-]{1,40}", start):
        raise ValueError("Start: „pollen“, „lauf:<id>“ oder leer (von vorn)")
    if bei_stillstand not in ("weiter", "abbrechen"):
        raise ValueError("Bei Stillstand: „weiter“ oder „abbrechen“")
    plan = {"aufgabe": task, "iterationen": it, "anpassungen": check_overrides(overrides), "grafikkarte": flavor,
            "start_von": start, "bei_stillstand": bei_stillstand}
    est = estimate(plan, measured)
    if est["stunden"] > 12:
        raise ValueError(f"Geschätzt ≈ {est['stunden']:.1f} h – mehr als die 12 h, die ein Lauf höchstens darf. "
                         "Weniger Iterationen, eine schnellere Grafikkarte oder auf einem Stand aufsetzen.")
    if max_stunden in (None, ""):
        hours = min(12, max(1, math.ceil(est["stunden"] * 1.5)))
    else:
        try:
            hours = int(max_stunden)
        except (TypeError, ValueError):
            raise ValueError("Höchstdauer: ganze Stunden von 1 bis 12") from None
        if not 1 <= hours <= 12:
            raise ValueError("Höchstdauer: ganze Stunden von 1 bis 12")
        if hours < est["stunden"]:
            raise ValueError(f"Die Obergrenze von {hours} h ist kürzer als die geschätzte Dauer (≈ {est['stunden']:.1f} h) – "
                             "der Lauf würde abgebrochen, bevor er die Policy exportiert. Mehr Stunden oder weniger Iterationen.")
    plan["max_stunden"] = hours
    return plan


def estimate(plan: dict[str, Any], measured: dict[str, float] | None = None) -> dict[str, Any]:
    """Grobe Dauer und Kosten. `measured`: gemessene Sekunden pro Iteration je Grafikkarte aus eigenen Läufen."""
    gpu = GPUS[plan["grafikkarte"]]
    s_it = (measured or {}).get(plan["grafikkarte"]) or gpu["s_it"]
    hours = (SETUP_MIN * 60 + plan["iterationen"] * s_it) / 3600
    out = {"stunden": round(hours, 2), "usd": round(hours * gpu["usd_h"], 2), "s_it": round(s_it, 2),
           "gemessen": bool((measured or {}).get(plan["grafikkarte"])), "usd_h": gpu["usd_h"]}
    if plan.get("max_stunden"):
        out["usd_max"] = round(plan["max_stunden"] * gpu["usd_h"], 2)
    return out


def train_args(plan: dict[str, Any], wandb: bool, init: str | None = None) -> list[str]:
    args = [plan["aufgabe"], "--env.scene.num-envs", "4096", "--agent.max_iterations", str(plan["iterationen"])]
    for key, value in plan["anpassungen"].items():
        args += [f"--{key}", value]
    if not wandb:
        args += ["--agent.logger", "tensorboard"]
    if init:
        args += ["--init-checkpoint", init]
    return args


# ── Lernkurven aus dem Protokoll (rsl_rl schreibt jede Iteration einen Block) ──────
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_ITER = re.compile(r"Learning iteration (\d+)/(\d+)")
_KV = re.compile(r"^\s*([A-Za-z_][\w /.-]*?):\s+(-?[\d.]+(?:[eE][-+]?\d+)?)s?\s*$")
_TIME = re.compile(r"^\s*(ETA|Time elapsed):\s+(\d+):(\d\d):(\d\d)\s*$")


def parse_log(lines: list[str]) -> list[dict[str, Any]]:
    """Protokollzeilen → eine Messreihe pro Iteration: Belohnung, Episodenlänge, einzelne Belohnungs- und
    Abbruchterme, Sekunden pro Iteration, Restzeit."""
    out: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for chunk in lines:
        for line in _ANSI.sub("", str(chunk)).splitlines():
            m = _ITER.search(line)
            if m:
                cur = {"it": int(m.group(1)), "von": int(m.group(2)), "terme": {}, "abbruch": {}}
                out.append(cur)
                continue
            if cur is None:
                continue
            t = _TIME.match(line)
            if t:
                secs = int(t.group(2)) * 3600 + int(t.group(3)) * 60 + int(t.group(4))
                cur["eta_s" if t.group(1) == "ETA" else "dauer_s"] = secs
                continue
            kv = _KV.match(line)
            if not kv:
                continue
            key, val = kv.group(1).strip(), float(kv.group(2))
            if key == "Mean reward":
                cur["belohnung"] = val
            elif key == "Mean episode length":
                cur["laenge"] = val
            elif key == "Mean action std":
                cur["streuung"] = val
            elif key == "Iteration time":
                cur["s_it"] = val
            elif key.startswith("Episode_Reward/"):
                cur["terme"][key.split("/", 1)[1]] = val
            elif key.startswith("Episode_Termination/"):
                cur["abbruch"][key.split("/", 1)[1]] = val
    return [r for r in out if "belohnung" in r or r["terme"]]


def summarize(series: list[dict[str, Any]]) -> dict[str, Any]:
    """Wo steht der Lauf? Fortschritt, Trend, Stillstand, was sich verbessert und was hakt."""
    if not series:
        return {"punkte": 0}
    series = sorted(series, key=lambda r: r["it"])
    last = series[-1]
    first_it = series[0]["it"]
    span = max(1, last["von"] - first_it) if last.get("von") else max(1, last["it"] - first_it)
    done = (last["it"] - first_it) / span
    rew = [(r["it"], r["belohnung"]) for r in series if "belohnung" in r]

    def window(frac: float) -> list[float]:
        cut = last["it"] - (last["it"] - first_it) * frac
        return [v for i, v in rew if i >= cut]

    out: dict[str, Any] = {"punkte": len(series), "iteration": last["it"], "von": last.get("von"),
                           "fortschritt": round(min(1.0, max(0.0, done)), 3)}
    if rew:
        vals = [v for _, v in rew]
        recent, earlier = window(0.15), window(0.45)[: max(1, len(window(0.45)) - len(window(0.15)))]
        r_now = sum(recent) / len(recent)
        r_before = sum(earlier) / len(earlier) if earlier else vals[0]
        scale = max(1e-6, abs(max(vals) - min(vals)), abs(r_before) * 0.05)
        trend = (r_now - r_before) / scale
        out.update(belohnung=round(r_now, 3), belohnung_start=round(vals[0], 3), belohnung_max=round(max(vals), 3),
                   trend=round(trend, 3))
        out["stillstand"] = bool(done >= 0.3 and (last["it"] - first_it) >= 300 and abs(trend) < 0.03)
    if "laenge" in last:
        out["episodenlaenge"] = round(last["laenge"], 1)
    s_its = [r["s_it"] for r in series[-20:] if r.get("s_it")]
    if s_its:
        out["s_it"] = round(sorted(s_its)[len(s_its) // 2], 2)
    if last.get("eta_s") is not None:
        out["rest_min"] = round(last["eta_s"] / 60)
    # Terme: Veränderung von der Mitte des Laufs bis jetzt
    mid = series[len(series) // 2]
    terms = []
    for k, v in last["terme"].items():
        before = mid["terme"].get(k)
        terms.append({"term": k, "jetzt": round(v, 4), "vorher": None if before is None else round(before, 4),
                      "aenderung": None if before is None else round(v - before, 4)})
    out["terme"] = sorted(terms, key=lambda t: t["term"])
    out["abbrueche"] = {k: round(v, 3) for k, v in sorted(last["abbruch"].items(), key=lambda kv: -kv[1])}
    # Fähigkeit: Anteil der Übungsdurchgänge, die bis zum Ende laufen (time_out) statt mit Sturz/Abbruch zu enden
    skill = [(r["it"], v) for r in series if (v := skill_of(r)) is not None]
    if skill:
        recent = [v for i, v in skill if i >= last["it"] - (last["it"] - first_it) * 0.1] or [skill[-1][1]]
        out["faehigkeit"] = round(sum(recent) / len(recent), 3)
        out["faehigkeit_start"] = round(skill[0][1], 3)
        out["faehigkeit_max"] = round(max(v for _, v in skill), 3)
    return out


def skill_of(point: dict[str, Any]) -> float | None:
    """Anteil time_out an allen Episodenenden dieser Iteration (0…1) – None, wenn das Protokoll es nicht nennt."""
    ab = point.get("abbruch") or {}
    if "time_out" not in ab:
        return None
    total = sum(v for v in ab.values() if isinstance(v, (int, float)) and v > 0)
    return max(0.0, min(1.0, ab["time_out"] / total)) if total > 0 else None


def repack_tarball(data: bytes) -> bytes:
    """GitHub-Archiv (alles unter „microduck_rl-main/“) → Pollens Form (Dateien an der Wurzel)."""
    src = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as dst:
        for m in src.getmembers():
            if not m.isfile():
                continue
            parts = m.name.split("/", 1)
            if len(parts) < 2 or not parts[1] or ".." in parts[1].split("/") or parts[1].startswith("/"):
                continue
            f = src.extractfile(m)
            if f is None:
                continue
            info = tarfile.TarInfo(parts[1])
            info.size = m.size
            info.mode = m.mode
            info.mtime = m.mtime
            dst.addfile(info, f)
    return out.getvalue()


# ── Token im Tresor ─────────────────────────────────────────────────────────
def get_token() -> str | None:
    from . import settings as S

    kr = S._keyring()
    if kr is None:
        return None
    try:
        return kr.get_password(S.KEYRING_SERVICE, KEYRING_USER)
    except Exception:
        return None


def set_token(token: str) -> None:
    from . import settings as S

    token = token.strip()
    if not re.fullmatch(r"hf_[A-Za-z0-9]{20,80}", token):
        raise ValueError("Das sieht nicht wie ein Hugging-Face-Token aus (hf_…).")
    kr = S._keyring()
    if kr is None:
        raise RuntimeError("Kein Tresor verfügbar.")
    kr.set_password(S.KEYRING_SERVICE, KEYRING_USER, token)


def delete_token() -> None:
    from . import settings as S

    kr = S._keyring()
    if kr is not None:
        try:
            kr.delete_password(S.KEYRING_SERVICE, KEYRING_USER)
        except Exception:
            pass


def token_hint(token: str | None) -> str | None:
    return f"hf_…{token[-4:]}" if token else None


# ── Läufe ───────────────────────────────────────────────────────────────────
class Trainer:
    def __init__(self, root: Path, api_factory=None, fetch=None) -> None:
        self.root = root / "training"
        self.file = self.root / "laeufe.json"
        self.api_factory = api_factory
        self.fetch = fetch or (lambda url: urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "duckpilot"}), timeout=120).read())
        self.vorschlag: dict[str, Any] | None = None
        self._lock = threading.RLock()     # laeufe.json wird aus mehreren Threads geändert

    # Speicher
    def runs(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, runs: list[dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(runs[-50:], ensure_ascii=False, indent=2), encoding="utf-8")

    def _update(self, rid: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            runs = self.runs()
            for r in runs:
                if r["id"] == rid:
                    r.update(fields)
                    self._save(runs)
                    return r
        raise KeyError(rid)

    def _claim(self, rid: str, expect: tuple[str, ...], **fields: Any) -> dict[str, Any] | None:
        """Felder nur setzen, wenn der Lauf (frisch gelesen) noch einen der erwarteten Zustände hat – damit zwei
        gleichzeitige Aktualisierungen nicht beide abbrechen oder beide einen Export starten."""
        with self._lock:
            runs = self.runs()
            r = next((x for x in runs if x["id"] == rid), None)
            if r is None or r.get("status") not in expect:
                return None
            r.update(fields)
            self._save(runs)
            return dict(r)

    def _api(self, token: str):
        if self.api_factory:
            return self.api_factory(token)
        try:
            from huggingface_hub import HfApi
        except ImportError as exc:
            raise TrainingError("huggingface_hub fehlt – unter Lernen → Training installieren.") from exc
        return HfApi(token=token)

    def account(self, token: str) -> dict[str, Any]:
        info = self._api(token).whoami()
        orgs = [o["name"] for o in info.get("orgs", []) if o.get("name")]
        return {"name": info.get("name"), "orgs": orgs}

    def measured(self) -> dict[str, float]:
        """Gemessene Sekunden pro Iteration je Grafikkarte (Median der eigenen Läufe)."""
        by: dict[str, list[float]] = {}
        for r in self.runs():
            v = (r.get("kurve") or {}).get("s_it")
            if v:
                by.setdefault(r["plan"]["grafikkarte"], []).append(float(v))
        return {k: sorted(v)[len(v) // 2] for k, v in by.items()}

    def _init_spec(self, api, plan: dict[str, Any]) -> tuple[str | None, bool, str]:
        """Woher der Lauf startet: (hf://-Pfad, Warmstart?, Beschreibung)."""
        start = plan.get("start_von")
        if not start:
            return None, False, "von vorn"
        if start == "pollen":
            got = pollen_start(plan["aufgabe"])
            if got is None:
                raise TrainingError("Kein Stand von Pollen für diese Aufgabe.")
            bundle, warm = got
            return f"hf://{POLLEN_TRAINING}/bundles/{bundle}", warm, f"Pollens Stand {bundle}"
        rid = start.split(":", 1)[1]
        src = next((r for r in self.runs() if r["id"] == rid), None)
        if src is None or not src.get("ckpt_repo"):
            raise TrainingError("Diesen Lauf gibt es nicht.")
        if family(src["plan"]["aufgabe"]) != family(plan["aufgabe"]):
            raise TrainingError("Weitertrainieren geht nur innerhalb derselben Aufgabe (eben/uneben/Getriebespiel).")
        ckpt = latest_checkpoint(list(api.list_repo_files(src["ckpt_repo"], repo_type="model")))
        if not ckpt:
            raise TrainingError("Im Lauf liegt noch kein Zwischenstand (model_*.pt).")
        warm = src["plan"]["aufgabe"] != plan["aufgabe"]
        return f"hf://{src['ckpt_repo']}/{ckpt}", warm, f"eigener Lauf {rid} ({ckpt.rsplit('/', 1)[-1]})"

    def submit(self, plan: dict[str, Any], token: str, namespace: str | None = None,
               wandb_key: str | None = None, progress=None, gruppe: str | None = None,
               variante: str | None = None) -> dict[str, Any]:
        """Läuft im Hintergrund-Thread: Quelle laden, packen, hochladen, Job starten."""
        try:
            from huggingface_hub import Volume
        except ImportError:          # huggingface_hub < 1.0 – der Job lädt den Code dann selbst
            Volume = None

        plan = check_plan(plan["aufgabe"], plan["iterationen"], plan.get("anpassungen"), plan.get("grafikkarte", "l4x1"),
                          plan.get("start_von"), plan.get("max_stunden"), plan.get("bei_stillstand", "weiter"),
                          self.measured())
        api = self._api(token)
        me = self.account(token)
        ns = namespace or me["name"]
        if ns not in (me["name"], *me["orgs"]):
            raise TrainingError(f"Namensraum {ns} gehört nicht zu diesem Token.")
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        rid = stamp
        measured = self.measured()
        with self._lock:
            runs = self.runs()
            n = 2
            while any(r["id"] == rid for r in runs):
                rid, n = f"{stamp}-{n}", n + 1
            run_name = f"{plan['aufgabe']}-{rid}".lower()
            src_repo = f"{ns}/mjlab-microduck-src"
            ckpt_repo = f"{ns}/{run_name}"
            runs.append({"id": rid, "plan": plan, "status": "bereitet vor", "namensraum": ns, "ckpt_repo": ckpt_repo,
                         "start": time.strftime("%Y-%m-%d %H:%M"), "job": None, "fehler": None,
                         "schaetzung": estimate(plan, measured), "gruppe": gruppe, "variante": variante})
            self._save(runs)
        try:
            init, warm, start_text = self._init_spec(api, plan)
            if progress:
                progress("lade Pollens Trainingscode von GitHub …")
            packed = repack_tarball(self.fetch(RL_TARBALL))
            name = f"src-{rid}.tar.gz"
            if progress:
                progress(f"lade den Code hoch ({len(packed) / 1e6:.1f} MB) …")
            api.create_repo(src_repo, repo_type="dataset", private=True, exist_ok=True)
            api.upload_file(path_or_fileobj=packed, path_in_repo=name, repo_id=src_repo, repo_type="dataset")
            api.create_repo(ckpt_repo, repo_type="model", private=True, exist_ok=True)
            env = {"MICRODUCK_IN_HF_JOB": "1", "CKPT_REPO": ckpt_repo, "SRC_TARBALL": name, "SRC_REPO": src_repo,
                   "GIT_SHA": "main",
                   "TRAIN_ARGS": " ".join(shlex.quote(a) for a in train_args(plan, bool(wandb_key), init))}
            if warm:
                env["MICRODUCK_WARM_START"] = "1"
            secrets = {"HF_TOKEN": token, **({"WANDB_API_KEY": wandb_key} if wandb_key else {})}
            if progress:
                progress("starte den Job …")
            extra = {}
            if Volume is not None:
                extra["volumes"] = [Volume(type="dataset", source=src_repo, mount_path="/src", read_only=True)]
            job = api.run_job(image=DEFAULT_IMAGE, command=["bash", "-c", BOOTSTRAP], env=env, secrets=secrets,
                              flavor=plan["grafikkarte"], timeout=f"{plan['max_stunden']}h", namespace=ns, **extra)
            return self._update(rid, job=job.id, url=getattr(job, "url", None), status="gestartet",
                                src_repo=src_repo, src_tarball=name, start_von=start_text, warmstart=warm)
        except Exception as exc:
            msg = str(exc)
            if "402" in msg or "credit" in msg.lower():
                msg = "Zu wenig Guthaben für Jobs – huggingface.co/settings/billing"
            elif "403" in msg:
                msg = "Der Token darf keine Jobs starten – einen fein eingestellten Token mit Jobs-Recht anlegen."
            self._update(rid, status="fehlgeschlagen", fehler=msg[:400])
            raise TrainingError(msg) from exc

    def _claim_if(self, rid: str, expect: tuple[str, ...], unset: str, **fields: Any) -> dict[str, Any] | None:
        with self._lock:
            r = next((x for x in self.runs() if x["id"] == rid), None)
            if r is None or r.get(unset):
                return None
            return self._claim(rid, expect, **fields)

    @staticmethod
    def _has_policy(api, r: dict[str, Any]) -> bool:
        try:
            return "exported/policy.onnx" in list(api.list_repo_files(r["ckpt_repo"], repo_type="model"))
        except Exception:
            return True               # im Zweifel nicht als fehlgeschlagen werten

    @staticmethod
    def _export_overdue(r: dict[str, Any]) -> bool:
        started = r.get("export_start")
        return bool(started) and time.time() - float(started) > EXPORT_MAX_MIN * 60

    def refresh(self, token: str, curves: bool = True) -> list[dict[str, Any]]:
        """Status aller laufenden Jobs nachfragen, Lernkurven nachziehen, Stillstand erkennen, Exporte verfolgen.
        Netzwerk außerhalb der Sperre; geschrieben wird je Lauf frisch gelesen (_claim), damit parallele Starts,
        Exporte und Aktualisierungen sich nicht gegenseitig überschreiben."""
        api = None
        training = ("gestartet", "wartet auf eine GPU", "trainiert")
        for snap in self.runs():
            rid, status = snap["id"], snap.get("status")
            if status not in ACTIVE:
                continue
            exporting = status == "exportiert"
            job = snap.get("export_job") if exporting else snap.get("job")
            if not job:
                if exporting and self._export_overdue(snap):
                    self._claim(rid, ("exportiert",), status="abgebrochen", fehler="Der Export ist nicht angelaufen.")
                continue
            api = api or self._api(token)
            try:
                st = api.inspect_job(job_id=job, namespace=snap["namensraum"]).status
                stage = str(getattr(st, "stage", "") or "").upper()
            except Exception as exc:
                if exporting and self._export_overdue(snap):
                    self._claim(rid, ("exportiert",), status="abgebrochen",
                                fehler="Der Export-Job ist nicht mehr auffindbar – „Zwischenstand exportieren“ versucht es neu.")
                else:
                    self._claim(rid, (status,), fehler=str(exc)[:200])
                continue
            if exporting:
                if stage == "COMPLETED":
                    if self._has_policy(api, snap):
                        self._claim(rid, ("exportiert",), status="fertig", fehler=None)
                    else:
                        self._claim(rid, ("exportiert",), status="abgebrochen",
                                    fehler="Der Export lief durch, hat aber keine policy.onnx abgelegt.")
                elif stage in ("ERROR", "CANCELED", "CANCELLED", "DELETED") or self._export_overdue(snap):
                    self._claim(rid, ("exportiert",), status="abgebrochen", fehler="Export des Zwischenstands fehlgeschlagen")
                continue
            fields: dict[str, Any] = {}
            label = STAGE.get(stage, stage.lower() or "unbekannt")
            if stage == "COMPLETED" and not self._has_policy(api, snap):
                label = "fehlgeschlagen"
                fields["fehler"] = ("Das Training lief durch, aber die Policy wurde nicht exportiert – "
                                    "„Zwischenstand exportieren“ holt das nach.")
            elif stage == "ERROR":
                fields["fehler"] = str(getattr(st, "message", "") or "")[:400]
            if label != status:
                fields["status"] = label
            if curves and stage in ("RUNNING", "COMPLETED"):
                try:
                    fields["kurve"] = self._update_curve(api, token, snap)
                except Exception as exc:
                    log.info("Lernkurve %s: %s", rid, exc)
            if fields:
                self._claim(rid, training, **fields)
            k = fields.get("kurve") or snap.get("kurve") or {}
            if stage == "RUNNING" and k.get("stillstand") and snap["plan"].get("bei_stillstand") == "abbrechen":
                claimed = self._claim_if(rid, training, "stillstand_seit", stillstand_seit=time.strftime("%Y-%m-%d %H:%M"))
                if not claimed:
                    continue                  # schon von einer anderen Aktualisierung erledigt
                try:
                    api.cancel_job(job_id=claimed["job"], namespace=claimed["namensraum"])
                    self._claim(rid, training + ("abgebrochen",), status="exportiert", export_job=None,
                                export_start=time.time(),
                                hinweis="Abgebrochen, weil sich die Belohnung nicht mehr verbessert hat – der letzte "
                                        "Zwischenstand wird exportiert.")
                    self._claim(rid, ("exportiert",), **self._start_export(api, token, claimed))
                except Exception as exc:
                    self._claim(rid, training + ("exportiert",), status="abgebrochen",
                                fehler=f"Abbruch bei Stillstand: {exc}"[:300])
        return self.runs()

    # ── Lernkurven ──────────────────────────────────────────────────────────
    def _curve_file(self, rid: str) -> Path:
        return self.root / "kurven" / f"{rid}.json"

    def series(self, rid: str) -> list[dict[str, Any]]:
        try:
            return json.loads(self._curve_file(rid).read_text(encoding="utf-8"))
        except Exception:
            return []

    def _update_curve(self, api, token: str, r: dict[str, Any], lines: int = 4000) -> dict[str, Any]:
        new = parse_log(self._fetch_lines(api, token, r, lines))
        with self._lock:
            return self._merge_curve(r["id"], new)

    def _merge_curve(self, rid: str, new: list[dict[str, Any]]) -> dict[str, Any]:
        known = {p["it"]: p for p in self.series(rid)}
        for p in new:
            known[p["it"]] = p
        pts = [known[k] for k in sorted(known)]
        if len(pts) > 400:                       # dünn halten, die letzten 60 voll
            head, tail = pts[:-60], pts[-60:]
            step = math.ceil(len(head) / 340)
            pts = head[::step] + tail
        f = self._curve_file(rid)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(pts, separators=(",", ":")), encoding="utf-8")
        return summarize(pts)

    def curve(self, token: str | None, rid: str) -> dict[str, Any]:
        """Lernkurve eines Laufs (bei laufendem Job frisch aus dem Protokoll)."""
        r = next((x for x in self.runs() if x["id"] == rid), None)
        if r is None:
            raise KeyError(rid)
        if token and r.get("job") and r.get("status") in ("trainiert", "fertig", "abgebrochen", "fehlgeschlagen"):
            try:
                summary = self._update_curve(self._api(token), token, r)
                self._update(rid, kurve=summary)
            except Exception as exc:
                log.info("Lernkurve %s: %s", rid, exc)
        pts = self.series(rid)
        return {"lauf": rid, "aufgabe": r["plan"]["aufgabe"], "status": r["status"], "zusammenfassung": summarize(pts),
                "punkte": [{"it": p["it"], "belohnung": p.get("belohnung"), "laenge": p.get("laenge"),
                            "faehigkeit": skill_of(p)} for p in pts]}

    # ── Zwischenstand exportieren ───────────────────────────────────────────
    def _start_export(self, api, token: str, r: dict[str, Any]) -> str:
        try:
            from huggingface_hub import Volume
        except ImportError:
            Volume = None
        ckpt = latest_checkpoint(list(api.list_repo_files(r["ckpt_repo"], repo_type="model")))
        if not ckpt:
            raise TrainingError("Im Lauf liegt noch kein Zwischenstand (model_*.pt).")
        if not r.get("src_tarball"):
            raise TrainingError("Für diesen Lauf fehlt der gespeicherte Code-Stand.")
        env = {"MICRODUCK_IN_HF_JOB": "1", "CKPT_REPO": r["ckpt_repo"], "CKPT_PATH": ckpt, "TASK_ID": r["plan"]["aufgabe"],
               "SRC_TARBALL": r["src_tarball"], "SRC_REPO": r.get("src_repo") or f"{r['namensraum']}/mjlab-microduck-src"}
        extra = {}
        if Volume is not None:
            extra["volumes"] = [Volume(type="dataset", source=env["SRC_REPO"], mount_path="/src", read_only=True)]
        job = api.run_job(image=DEFAULT_IMAGE, command=["bash", "-c", BOOTSTRAP_EXPORT], env=env,
                          secrets={"HF_TOKEN": token}, flavor=EXPORT_FLAVOR, timeout="1h", namespace=r["namensraum"],
                          **extra)
        return {"export_job": job.id, "export_von": ckpt, "export_start": time.time()}

    def export(self, token: str, rid: str) -> dict[str, Any]:
        r = next((x for x in self.runs() if x["id"] == rid), None)
        if r is None:
            raise KeyError(rid)
        before = r.get("status")
        if before not in ("abgebrochen", "fehlgeschlagen"):
            raise TrainingError("Exportieren geht für abgebrochene oder fehlgeschlagene Läufe – fertige haben ihr Ergebnis schon.")
        claimed = self._claim(rid, ("abgebrochen", "fehlgeschlagen"), status="exportiert", fehler=None, export_job=None,
                              export_start=time.time())
        if claimed is None:
            raise TrainingError("Dieser Lauf wird schon exportiert.")
        try:
            fields = self._start_export(self._api(token), token, claimed)
        except Exception:
            self._update(rid, status=before)
            raise
        return self._update(rid, **fields)

    def logs(self, token: str, rid: str, lines: int = 80) -> list[str]:
        r = next((x for x in self.runs() if x["id"] == rid), None)
        if not r or not r.get("job"):
            raise KeyError(rid)
        out = [line[:300] for line in self._fetch_lines(self._api(token), token, r, lines)]
        return out[-lines:]

    def _fetch_lines(self, api, token: str, r: dict[str, Any], lines: int) -> list[str]:
        try:
            raw = [str(x) for x in api.fetch_job_logs(job_id=r["job"], namespace=r["namensraum"], follow=False,
                                                      tail=lines)]
        except TypeError:
            # huggingface_hub < 1.0 kennt follow/tail nicht und folgt einem laufenden Job bis zum Ende –
            # deshalb selbst abrufen und nach ein paar Sekunden aufhören
            raw = self._logs_http(token, r["namensraum"], r["job"], lines)
        out = [ln for chunk in raw for ln in chunk.splitlines() if ln.strip()]   # ein Eintrag kann mehrere Zeilen haben
        return out[-lines:]

    @staticmethod
    def _logs_http(token: str, namespace: str, job: str, lines: int, seconds: float = 6.0) -> list[str]:
        import collections

        if not re.fullmatch(r"[\w.-]+", namespace) or not re.fullmatch(r"[\w-]+", job):
            raise ValueError("ungültige Job-Angabe")
        req = urllib.request.Request(f"https://huggingface.co/api/jobs/{namespace}/{job}/logs",
                                     headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"})
        out: collections.deque[str] = collections.deque(maxlen=lines)
        end = time.monotonic() + seconds
        try:
            with urllib.request.urlopen(req, timeout=seconds) as resp:
                while time.monotonic() < end:
                    raw = resp.readline()
                    if not raw:
                        break
                    line = raw.decode("utf-8", "replace").strip()
                    if line.startswith("data: {"):
                        try:
                            text = json.loads(line[6:]).get("data", "")
                        except ValueError:
                            continue
                        if text and not text.startswith("===== Job started"):
                            out.append(text[:2000])
        except TimeoutError:
            pass
        return list(out)

    def cancel(self, token: str, rid: str) -> dict[str, Any]:
        r = next((x for x in self.runs() if x["id"] == rid), None)
        if not r or not r.get("job"):
            raise KeyError(rid)
        job = r.get("export_job") if r.get("status") == "exportiert" and r.get("export_job") else r["job"]
        self._api(token).cancel_job(job_id=job, namespace=r["namensraum"])
        return self._update(rid, status="abgebrochen")

    def result(self, token: str, rid: str) -> Path:
        """Die exportierte Policy des Laufs herunterladen → Pfad."""
        r = next((x for x in self.runs() if x["id"] == rid), None)
        if not r:
            raise KeyError(rid)
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(r["ckpt_repo"], "exported/policy.onnx", token=token,
                               cache_dir=str(self.root / "ergebnisse"))
        self._update(rid, onnx=str(path))
        return Path(path)
