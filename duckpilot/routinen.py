"""Routinen für den Alltagsbuddy (seit 0.42, Fahrplan „Alltag“).

Eine Routine hat einen Namen, optional eine Uhrzeit mit Wochentagen und ein paar Schritte aus einer festen Liste.
Sie läuft zur Uhrzeit von selbst oder auf Zuruf („Starte die Morgenroutine“).

Bewusst klein gehalten: Die Schritte sagen etwas an (Begrüßung, Tagesüberblick, Wetter, To-dos), zeigen eine Geste
oder wechseln zwischen Ruhe und Aktiv. Keine freien Befehle, nichts am Haus (Licht, Schlösser, Heizung) – damit eine
Routine um 7 Uhr nie etwas tut, was niemand mitbekommt. Bewegung entscheidet der Alltagsbuddy: nach einem Not-Aus, gestürzt
oder hochgehoben gibt es keine Geste und kein Aufstehen.

Hier steckt nur Prüfen und „Was ist fällig?“ – ohne asyncio, ohne Roboter. Ausgeführt wird in `skills/alltag.py`.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from typing import Any

SCHRITTE: dict[str, str] = {
    "ueberblick": "Tagesüberblick",
    "wetter": "Wetter",
    "todos": "To-dos vorlesen",
    "freuen": "sich freuen",
    "aktiv": "aufwachen",
    "ruhe": "zur Ruhe",
}
TAGE: dict[str, tuple[int, ...]] = {
    "taeglich": (0, 1, 2, 3, 4, 5, 6),
    "werktags": (0, 1, 2, 3, 4),
    "wochenende": (5, 6),
}
TAGE_TEXT = {"taeglich": "täglich", "werktags": "werktags", "wochenende": "am Wochenende"}
NACHHOLEN_MIN = 30          # PC war aus: höchstens so spät noch nachholen, sonst bis morgen warten
MAX_ROUTINEN = 20
MAX_TEXT = 200

_ZEIT = re.compile(r"^\s*(?:um\s+)?(\d{1,2})(?:[:.](\d{2}))?\s*(?:uhr)?\s*$", re.IGNORECASE)


def zeit_pruefen(roh: Any) -> str:
    """„7“, „7:30“, „um 7.30 Uhr“ → „07:30“; leer → „“ (nur auf Zuruf)."""
    text = str(roh or "").strip()
    if not text:
        return ""
    m = _ZEIT.match(text)
    if not m:
        raise ValueError("Uhrzeit wie 7:30 angeben – oder leer lassen, dann läuft die Routine nur auf Zuruf.")
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h > 23 or mi > 59:
        raise ValueError("Diese Uhrzeit gibt es nicht.")
    return f"{h:02d}:{mi:02d}"


def pruefen(name: Any, zeit: Any = "", tage: Any = "taeglich", schritte: Any = (), ansage: Any = "") -> dict[str, Any]:
    """Eine neue Routine aus Eingaben – wirft ValueError mit einem Satz, den man versteht."""
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:40]
    if not name:
        raise ValueError("Wie heißt die Routine? Zum Beispiel „Morgen“.")
    tage = str(tage or "taeglich")
    if tage not in TAGE:
        raise ValueError("Tage: täglich, werktags oder am Wochenende.")
    if isinstance(schritte, str):
        schritte = [s for s in re.split(r"[,\s]+", schritte) if s]
    liste = []
    for s in schritte or ():
        s = str(s)
        if s not in SCHRITTE:
            raise ValueError(f"Unbekannter Schritt „{s}“.")
        if s not in liste:
            liste.append(s)
    if "aktiv" in liste and "ruhe" in liste:
        raise ValueError("Aufwachen und zur Ruhe in einer Routine – bitte nur eins davon.")
    ansage = re.sub(r"\s+", " ", str(ansage or "")).strip()[:MAX_TEXT]
    if not liste and not ansage:
        raise ValueError("Die Routine braucht mindestens einen Schritt oder eine Ansage.")
    return {"id": uuid.uuid4().hex[:8], "name": name, "zeit": zeit_pruefen(zeit), "tage": tage,
            "schritte": liste, "ansage": ansage, "an": True, "zuletzt": ""}


def faellig(routinen: list[dict[str, Any]], jetzt: datetime) -> list[dict[str, Any]]:
    """Routinen, deren Uhrzeit heute gerade erreicht ist – je Tag höchstens einmal. Setzt `zuletzt`."""
    heute = jetzt.date().isoformat()
    neu = []
    for r in routinen:
        if not r.get("an") or not r.get("zeit") or r.get("zuletzt") == heute:
            continue
        if jetzt.weekday() not in TAGE.get(r.get("tage", "taeglich"), ()):
            continue
        h, m = (int(x) for x in r["zeit"].split(":"))
        start = jetzt.replace(hour=h, minute=m, second=0, microsecond=0)
        if start <= jetzt:
            r["zuletzt"] = heute                       # auch wenn zu spät: heute nicht mehr
            if jetzt - start <= timedelta(minutes=NACHHOLEN_MIN):
                neu.append(r)
    return neu


def finden(routinen: list[dict[str, Any]], ref: str) -> dict[str, Any] | None:
    """Per id oder Name: „morgen“ findet „Morgen“ und „Morgenroutine“."""
    ref = str(ref or "").strip()
    for r in routinen:
        if r["id"] == ref:
            return r
    key = re.sub(r"[-\s]*routine$", "", ref.lower()).strip()
    if not key:
        return None
    genau = [r for r in routinen if re.sub(r"[-\s]*routine$", "", r["name"].lower()).strip() == key]
    if genau:
        return genau[0]
    teil = [r for r in routinen if key in r["name"].lower()]
    return teil[0] if len(teil) == 1 else None


def beschreiben(r: dict[str, Any]) -> str:
    """„Morgen – werktags um 07:30: Tagesüberblick, Wetter“."""
    wann = f"{TAGE_TEXT.get(r.get('tage', ''), '')} um {r['zeit']}" if r.get("zeit") else "nur auf Zuruf"
    teile = (["Ansage"] if r.get("ansage") else []) + [SCHRITTE[s] for s in r.get("schritte", []) if s in SCHRITTE]
    aus = "" if r.get("an", True) else " (pausiert)"
    return f"{r['name']} – {wann}{aus}: {', '.join(teile)}"
