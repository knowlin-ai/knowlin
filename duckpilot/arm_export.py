"""Aris Beispiele als Paket für LeRobot (seit 0.38.64, Stufe A4; Maintainer: „A, dann B“).

Knowlin schreibt kein Parquet selbst (dafür bräuchte es pyarrow). Stattdessen enthält die ZIP-Datei die Takte als
JSON-Zeilen, eine Beschreibung im Stil von LeRobot (`meta/info.json`) und ein kleines Skript, das daraus mit LeRobot
einen echten Datensatz baut (`LeRobotDataset.create` → `add_frame` → `save_episode`):

    pip install lerobot
    python nach_lerobot.py --repo-id <dein-name>/ari-wuerfel

- `observation.state` und `action`: die sechs Gelenke des SO-101 in Grad, Namen wie beim `so101_follower`.
- `observation.environment_state`: die elf Werte, die Ari beim Lernen sieht (`arm_lernen.beobachtung`).
- Keine Kamerabilder: Die Beispiele kommen aus dem Simulator. Am echten Arm braucht eine Policy Bilder – dafür ist
  der Export ein Anfang (Aufbau, Namen, Takt), kein fertiger Datensatz für den echten Arm.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from .arm_lernen import BEOBACHTUNG, GELENKE, SCHRITT_S

FPS = round(1 / SCHRITT_S)          # LeRobot will ganze Bilder je Sekunde; der Takt ist 0,15 s ≈ 7 je Sekunde

SKRIPT = '''"""Baut aus Knowlins Export einen LeRobot-Datensatz (ohne Bilder). Aufruf:

    pip install lerobot
    python nach_lerobot.py --repo-id <name>/<datensatz> [--ziel ordner] [--hochladen]

Nicht mit jeder LeRobot-Version geprüft: Ältere Versionen haben `lerobot.common.datasets`, neuere `lerobot.datasets`.
"""
import argparse
import json
from pathlib import Path

import numpy as np

try:
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
except ImportError:  # ältere LeRobot-Versionen
    from lerobot.common.datasets.lerobot_dataset import LeRobotDataset

hier = Path(__file__).parent
info = json.loads((hier / "meta" / "info.json").read_text(encoding="utf-8"))
p = argparse.ArgumentParser()
p.add_argument("--repo-id", required=True)
p.add_argument("--ziel", default=None)
p.add_argument("--hochladen", action="store_true")
args = p.parse_args()

merkmale = {k: {"dtype": v["dtype"], "shape": tuple(v["shape"]), "names": v["names"]}
            for k, v in info["features"].items() if k in ("observation.state", "observation.environment_state", "action")}
ds = LeRobotDataset.create(repo_id=args.repo_id, fps=info["fps"], features=merkmale, robot_type=info["robot_type"],
                           root=args.ziel, use_videos=False)
for zeile in (hier / "episoden.jsonl").read_text(encoding="utf-8").splitlines():
    ep = json.loads(zeile)
    for t in ep["takte"]:
        bild = {"observation.state": np.array(t["state"], np.float32),
                "observation.environment_state": np.array(t["env"], np.float32),
                "action": np.array(t["action"], np.float32)}
        try:
            ds.add_frame({**bild, "task": ep["task"]})
        except (TypeError, ValueError, KeyError):
            ds.add_frame(bild, task=ep["task"])      # ältere Schnittstelle
    ds.save_episode()
if hasattr(ds, "finalize"):
    ds.finalize()
if args.hochladen:
    ds.push_to_hub()
print("fertig:", ds.root)
'''


def _aufgabe_text(a: dict[str, str]) -> str:
    return f"Leg den {a['wuerfel']} in die {a['kiste']}."


def paket(beispiele: list[dict[str, Any]], aufgabe: dict[str, str], version: str) -> bytes:
    """ZIP mit `episoden.jsonl`, `meta/info.json`, `meta/tasks.jsonl`, `nach_lerobot.py` und `LIESMICH.md`."""
    task = _aufgabe_text(aufgabe)
    zeilen, frames = [], 0
    for i, b in enumerate(beispiele):
        takte = [{"state": s[2], "action": s[3], "env": s[0], "timestamp": round(j / FPS, 4)}
                 for j, s in enumerate(b["schritte"]) if len(s) >= 4]
        if not takte:
            continue
        frames += len(takte)
        zeilen.append(json.dumps({"episode_index": i, "task": task, "von": b.get("von", "?"), "takte": takte},
                                 ensure_ascii=False))
    namen = [f"{g}.pos" for g in GELENKE]
    info = {
        "codebase_version": "v2.1", "robot_type": "so101_follower", "fps": FPS,
        "total_episodes": len(zeilen), "total_frames": frames, "total_tasks": 1,
        "features": {
            "observation.state": {"dtype": "float32", "shape": [len(GELENKE)], "names": namen},
            "observation.environment_state": {"dtype": "float32", "shape": [len(BEOBACHTUNG)], "names": list(BEOBACHTUNG)},
            "action": {"dtype": "float32", "shape": [len(GELENKE)], "names": namen},
        },
        "quelle": f"Knowlin {version}, Simulator (So101Sim), ohne Kamerabilder",
    }
    liesmich = (
        "# Ari – Beispiele aus Knowlin\n\n"
        f"Aufgabe: {task}\n\n{len(zeilen)} Beispiele, {frames} Takte, {FPS} Takte je Sekunde, ohne Bilder.\n\n"
        "Daraus einen LeRobot-Datensatz bauen:\n\n    pip install lerobot\n"
        "    python nach_lerobot.py --repo-id <name>/ari-wuerfel\n\n"
        "Gelenke in Grad wie beim so101_follower. Die Beispiele kommen aus dem Simulator; am echten Arm braucht eine "
        "Policy zusätzlich Kamerabilder.\n"
    )
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("episoden.jsonl", "\n".join(zeilen) + ("\n" if zeilen else ""))
        z.writestr("meta/info.json", json.dumps(info, ensure_ascii=False, indent=2))
        z.writestr("meta/tasks.jsonl", json.dumps({"task_index": 0, "task": task}, ensure_ascii=False) + "\n")
        z.writestr("nach_lerobot.py", SKRIPT)
        z.writestr("LIESMICH.md", liesmich)
    return puffer.getvalue()
