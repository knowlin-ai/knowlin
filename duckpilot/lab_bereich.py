"""Knowlin Lab als eigener Bereich (seit 0.50): alle Lernwege an einem Ort und der Raum aus der Quest.

Maintainer (Plan 0.50): „Die Trainingshalle als eigener Bereich – dazu der Raum aus der Quest im Simulator.“

* **Lernwege:** Was jeder Körper lernen kann – Akrobatik, Parcours und Training (Körper mit Trainingshalle), Laufen
  lernen (Vierbeiner), Vormachen und selbst üben (Arme mit Greifer), Mentor (jeder mit Kopf). Welcher Körper was kann,
  steht im Profil (`Koerper.lab`, Fähigkeiten, Familie) – nie über den Namen.
* **Raum aus der Quest:** Die Brille vermisst das Zimmer (WebXR „plane-detection“): Boden und Flächen wie Tische, Sofa,
  Regal. Gespeichert werden nur Maße (Meter) – keine Bilder, keine Raumkarte der Brille. Der einfache Simulator kann
  das Zimmer dann statt des Wohnzimmers benutzen. Diese Datei prüft und rechnet nur; angewendet wird in
  `server/routes/lab.py`.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

DATEI = "quest_raum.json"
MAX_PUNKTE = 64
MAX_FLAECHEN = 24
GRENZE_M = 12.0
MIN_RAUM_M, MAX_RAUM_M = 1.5, 8.0
NAMEN = {"table": "Tisch", "desk": "Tisch", "couch": "Sofa", "sofa": "Sofa", "shelf": "Regal", "bed": "Bett",
         "storage": "Schrank", "cabinet": "Schrank", "screen": "Bildschirm"}

# (id, Name, ein Satz, Ansicht, Teil); wer ihn gehen kann, sagt `kann()` aus dem Körperprofil
LERNWEGE: tuple[tuple[str, str, str, str, str], ...] = (
    ("akrobatik", "Akrobatik", "Haltungen und Sprünge mit der Gliederpuppe ausprobieren – in echter Physik.", "akrobatik", ""),
    ("parcours", "Parcours", "Rampen, Stufen und Engstellen bauen und sie hindurchschicken.", "parcours", ""),
    ("training", "Training", "Gangarten trainieren, Policies von Pollen oder aus Isaac Lab laden.", "training", ""),
    ("laufen", "Laufen lernen", "Eine eigene Gangart in der Physik lernen und unter den Gangarten wählen.", "tricks", "tricks"),
    ("vormachen", "Vormachen und üben", "Mit der Hand vor der Webcam zeigen, als Auftrag merken, selbst üben.", "cockpit", ""),
    ("mentor", "Mentor", "Lernziele, Fortschritt, Kopf führen mit Handy oder Quest.", "mentor", ""),
)


def kann(lernweg: str, profil: Any) -> bool:
    """Kann dieser Körper (Profil aus `koerper.py`) diesen Lernweg gehen?"""
    f = set(getattr(profil, "faehigkeiten", ()) or ())
    if lernweg in ("akrobatik", "parcours", "training"):
        return bool(getattr(profil, "lab", False))
    if lernweg == "laufen":
        return getattr(profil, "familie", "") == "vierbeiner" and "beine" in f
    if lernweg == "vormachen":
        return "greifer" in f
    if lernweg == "mentor":
        return "kopf" in f or "arm" in f
    return False


def lernwege(profile: list[Any], aktiv: str) -> list[dict[str, Any]]:
    """Alle Lernwege mit den Körpern, die sie gehen können; `jetzt`: der aktive Körper kann ihn."""
    out = []
    for wid, name, satz, ansicht, teil in LERNWEGE:
        wer = [p for p in profile if kann(wid, p)]
        out.append({"id": wid, "name": name, "satz": satz, "ansicht": ansicht, "teil": teil,
                    "koerper": [p.name for p in wer], "jetzt": any(p.koerper_zustand == aktiv for p in wer)})
    return out


# ── Raum aus der Quest ─────────────────────────────────────────────────────
def _punkt(p: Any) -> tuple[float, float] | None:
    try:
        x, y = float(p[0]), float(p[1])
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)) or abs(x) > GRENZE_M or abs(y) > GRENZE_M:
        return None
    return round(x, 3), round(y, 3)


def pruefen(daten: Any) -> tuple[dict[str, Any] | None, str]:
    """Messung aus der Brille → Zimmer: rechteckiger Boden (Mitte im Ursprung) und Möbel als Kästen. Nur Zahlen."""
    if not isinstance(daten, dict):
        return None, "Keine Messung."
    boden = [q for q in (_punkt(p) for p in (daten.get("boden") or [])[:MAX_PUNKTE]) if q]
    if len(boden) < 3:
        return None, "Den Boden hat die Brille nicht erkannt – einmal langsam umschauen, dann noch einmal."
    xs, ys = [p[0] for p in boden], [p[1] for p in boden]
    breite, tiefe = max(xs) - min(xs), max(ys) - min(ys)
    if not (MIN_RAUM_M <= breite <= MAX_RAUM_M and MIN_RAUM_M <= tiefe <= MAX_RAUM_M):
        return None, f"Der Boden misst {breite:.1f} × {tiefe:.1f} m – gehen ab 1,5 bis 8 m je Seite."
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    moebel = []
    for f in (daten.get("flaechen") or [])[:MAX_FLAECHEN]:
        if not isinstance(f, dict):
            continue
        m = _punkt((f.get("x"), f.get("y")))
        try:
            sx, sy, h = float(f.get("breite")), float(f.get("tiefe")), float(f.get("hoehe"))
        except (TypeError, ValueError):
            continue
        if m is None or not all(math.isfinite(v) for v in (sx, sy, h)):
            continue
        if not (0.1 <= sx <= 4 and 0.1 <= sy <= 4 and 0.15 <= h <= 2.5):
            continue
        x, y = m[0] - cx, m[1] - cy
        if abs(x) > breite / 2 or abs(y) > tiefe / 2:
            continue
        art = str(f.get("art") or "").lower()
        moebel.append({"name": NAMEN.get(art, "Möbel"), "x": round(x, 3), "y": round(y, 3), "sx": round(sx, 3),
                       "sy": round(sy, 3), "h": round(h, 3)})
    return {"breite": round(breite, 2), "tiefe": round(tiefe, 2), "versatz": [round(cx, 3), round(cy, 3)],
            "moebel": moebel, "zeit": time.strftime("%Y-%m-%d %H:%M")}, ""


class QuestRaum:
    """Gemessenes Zimmer und ob der Simulator es benutzt (`<daten>/quest_raum.json`)."""

    def __init__(self, ordner: Path) -> None:
        self.pfad = Path(ordner) / DATEI

    def laden(self) -> dict[str, Any] | None:
        try:
            d = json.loads(self.pfad.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) and d.get("breite") else None
        except (OSError, ValueError):
            return None

    def speichern(self, raum: dict[str, Any], aktiv: bool | None = None) -> None:
        alt = self.laden() or {}
        raum = {**raum, "aktiv": bool(alt.get("aktiv")) if aktiv is None else aktiv}
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self.pfad.write_text(json.dumps(raum, ensure_ascii=False), encoding="utf-8")

    def loeschen(self) -> None:
        try:
            self.pfad.unlink()
        except OSError:
            pass
