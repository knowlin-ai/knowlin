#!/usr/bin/env python3
"""Übernimmt Pollens 14 Emotionen (pollen-robotics/microduck_emotions, Apache-2.0).

    python tools/import_emotions.py <pfad>/microduck_emotions

Die Keyframes (alle 0,1 s, Radiant, Abweichungen von der Grundhaltung) werden in das
Choreografie-Format von duckpilot übersetzt (Grad, deutsche Schlüssel) und landen in
duckpilot/motion/pollen_emotions.json. Die Töne werden zu Opus und liegen unter
duckpilot/server/static/sounds/emotions/. Braucht ffmpeg – nur beim Import.

"sit" (am Boden, tot stellen) wird wie bei Pollen zum Hinsetzen beim ersten Sitz-Keyframe (`"skill": "hinsetzen"`)
– aber nur, wenn das Gefühl ausdrücklich gewünscht ist; als Einlage im Leerlauf bleibt es bei der tiefen Haltung.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

# Pollen-Name → (deutscher Name, kurze Beschreibung für Claude und die Oberfläche)
NAMES = {
    "sad": ("betruebt", "Kopf sinkt, leises Gurren, zwei langsame Kopfschüttler"),
    "devastated": ("am_boden", "geht in die Knie, Kopf hängt, schüttelt ihn dreimal"),
    "curious": ("was_was", "„Was? Was?“ – Kopf vor, zur einen, dann zur anderen Seite geneigt"),
    "mmh": ("hmm", "„Wie meinst du das?“ – kleiner Kopfneiger mit gedämpftem „mmh?“"),
    "yes": ("jawohl", "ein klares Nicken mit einem Quak"),
    "yes_fast": ("jep", "dasselbe Nicken, kurz angebunden"),
    "no": ("noe", "ein Kopfschütteln mit „no-ah“"),
    "defiant": ("wer_sagt_das", "„Wer sagt das?“ – Schnabel hoch nach links, dann nach rechts"),
    "angry": ("grummelig", "Blick von oben, vier Kopfrucke mit kurzem Bellen"),
    "mock": ("naeaeae", "„Gnagnagna“ – Schnabel hoch, Kopf wiegt hin und her"),
    "excited": ("aufgeregt", "sechs immer schnellere Kopfschwünge, Quaks steigen an"),
    "impatient": ("ungeduldig", "„Na los!“ – vier schnelle Kopfschüttler, dann ein Schnauben"),
    "laugh": ("lachen", "Schnabel hoch, langes „haaa“ und sieben kurze „ha“"),
    "play_dead": ("tot_stellen", "Alarmruf, Kopf zur Seite, sackt zusammen – und wacht wieder auf"),
}
DEG = 180.0 / math.pi


def frame(kf: dict, sitting: bool) -> dict:
    out: dict = {"t": round(kf["t"], 2)}
    out["kopf"] = {
        # Pollen: neck < 0 = Hals nach vorn/unten; duckpilot-Spec: nacken + = nach vorn/unten
        "nacken": round(-(kf.get("neck") or 0.0) * DEG, 1),
        "nicken": round((kf.get("head_pitch") or 0.0) * DEG, 1),
        "drehen": round((kf.get("head_yaw") or 0.0) * DEG, 1),
        "neigen": round((kf.get("head_roll") or 0.0) * DEG, 1),
    }
    z_mm = (kf.get("body_z") or 0.0) * 1000 - (22.0 if sitting else 0.0)
    out["koerper"] = {"kippen": round((kf.get("body_pitch") or 0.0) * DEG, 1), "hoehe_mm": round(z_mm, 1)}
    out["schnabel"] = round(kf.get("mouth") or 0.0, 2)
    tw = kf.get("twist") or [0, 0, 0]
    if any(abs(v) > 1e-6 for v in tw):
        out["fahren"] = {"vx": tw[0], "vy": tw[1], "drehrate_grad": round(tw[2] * DEG, 1)}
    return out


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = Path(sys.argv[1]).expanduser()
    root = Path(__file__).resolve().parent.parent
    snd_out = root / "duckpilot" / "server" / "static" / "sounds" / "emotions"
    snd_out.mkdir(parents=True, exist_ok=True)
    for old in snd_out.glob("*.ogg"):
        old.unlink()
    meta = json.loads((src / "emotions.json").read_text())
    commit = subprocess.run(["git", "-C", str(src), "log", "-1", "--format=%h"], capture_output=True, text=True).stdout.strip()
    pack = {"quelle": f"pollen-robotics/microduck_emotions@{commit}", "lizenz": "Apache-2.0, © Pollen Robotics",
            "emotionen": {}}
    for e in meta["emotions"]:
        de, text = NAMES[e["name"]]
        kfs = json.loads((src / e["keyframes"]).read_text())["keyframes"]
        sitting = False
        spec = []
        for kf in kfs:
            first_sit = kf.get("skill") == "sit" and not sitting
            if kf.get("skill") == "sit":
                sitting = True
            spec.append(frame(kf, sitting))
            if first_sit:
                spec[-1]["skill"] = "hinsetzen"
        spec[-1]["kopf"] = {}
        spec[-1]["koerper"] = {}
        spec[-1]["schnabel"] = 0.0
        clips = []
        for i, wav in enumerate(e.get("sounds") or []):
            name = f"{de}{'_' + 'abc'[i] if len(e['sounds']) > 1 else ''}.ogg"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src / wav), "-c:a", "libopus", "-b:a", "56k",
                            str(snd_out / name)], check=True)
            clips.append(name[:-4])
        spec[0]["klang"] = clips
        spec[0]["klang_bei"] = e.get("sound_at_s", 0.0)
        pack["emotionen"][de] = {"pollen": e["name"], "text": text, "dauer": e["duration_s"], "spec": spec}
    (snd_out / "index.json").write_text(json.dumps({"dateien": sorted(f.name for f in snd_out.glob("*.ogg"))}, indent=1))
    dest = root / "duckpilot" / "motion" / "pollen_emotions.json"
    dest.write_text(json.dumps(pack, ensure_ascii=False, separators=(",", ":")))
    total = sum(f.stat().st_size for f in snd_out.glob("*.ogg"))
    print(f"{dest.name}: {len(pack['emotionen'])} Emotionen, {dest.stat().st_size // 1024} KB; Töne {total // 1024} KB")


if __name__ == "__main__":
    main()
