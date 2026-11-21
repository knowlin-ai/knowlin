"""Mentor als eigenes Modul (seit 0.48): Lernziele, Fortschritt und Übungen an einem Ort.

Maintainer: „Du zeigst, Knowlin lernt – mit Handy, Webcam oder Brille.“ Was Knowlin durch Zuschauen lernt, lag bisher
verstreut: Aris Beispiele und gelerntes Netz, gemerkte Aufträge an der Werkbank, Bellos gelernte Gangart, seit 0.48
die Kopfbewegungen der Marionette. Hier kommt es zusammen:

- **Lernziele:** eigene (ein Satz, für welchen Körper, erledigt ja/nein – in `<daten>/mentor.json`) und die, die sich
  aus dem Gelernten ergeben (mit Fortschritt aus den echten Zahlen, nie geschätzt).
- **Übungen:** was man vormachen oder üben kann, mit dem Körper, den es braucht, und wohin der Knopf führt.

Rein rechnend bis auf die kleine Ablage der eigenen Ziele; die Zahlen liefert die Laufzeit (`routes/mentor.py`).
Nichts über Personen: Ziele sind Sätze über den Roboter, Beispiele nur Bewegungen.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

DATEI = "mentor.json"
MAX_ZIELE = 40
TEXT_MAX = 120

# Übungen: (id, Titel, was man tut, braucht Eigenschaft, Ansicht, Teil)
UEBUNGEN: tuple[tuple[str, str, str, str, str, str], ...] = (
    ("marionette_handy", "Kopf führen mit dem Handy",
     "Handy neigen und drehen – der Kopf macht mit. Aufnehmen, benennen, später allein nachmachen lassen.",
     "kopf", "mentor", ""),
    ("marionette_vr", "Mit dem eigenen Kopf in der Quest",
     "In VR ansehen, dann „Kopf vormachen“: Sie folgt deinem Kopf; mit der Hand führst du einen Arm.",
     "kopf", "cockpit", ""),
    ("vormachen_hand", "Vormachen mit der Hand",
     "Webcam oder Handykamera: Ari folgt deiner Hand, Daumen und Zeigefinger zusammen greifen.",
     "arm", "cockpit", ""),
    ("ari_lernen", "Ari lernt eine Aufgabe",
     "Ein paar Beispiele vormachen, „Lernen“, dann „Ausprobieren“ und „Selbst üben“.",
     "arm", "cockpit", ""),
    ("auftrag_merken", "Ablauf als Auftrag merken",
     "Würfel nacheinander umlegen – das Vorgemachte wird ein Auftrag, den Ari allein ausführt.",
     "arm", "cockpit", ""),
    ("bello_laufen", "Bello lernt laufen",
     "Im Physikmodell eine schnellere Gangart suchen – nur übernommen, wenn sie besser ist.",
     "beine", "tricks", "tricks"),
)


def text_sauber(text: str) -> str:
    return re.sub(r"[\x00-\x1f<>]", "", str(text or "")).strip()[:TEXT_MAX]


class Lernziele:
    """Eigene Lernziele – ein Satz, ein Körper, erledigt oder nicht."""

    def __init__(self, ordner: Path) -> None:
        self.pfad = Path(ordner) / DATEI

    def alle(self) -> list[dict[str, Any]]:
        try:
            d = json.loads(self.pfad.read_text(encoding="utf-8"))
            return [z for z in d.get("ziele", []) if isinstance(z, dict) and z.get("id")] if isinstance(d, dict) else []
        except (OSError, ValueError):
            return []

    def neu(self, text: str, koerper: str) -> tuple[dict[str, Any] | None, str]:
        text = text_sauber(text)
        if len(text) < 3:
            return None, "Schreib in ein paar Worten, was sie lernen soll."
        ziele = self.alle()
        if len(ziele) >= MAX_ZIELE:
            return None, f"Schon {MAX_ZIELE} Lernziele – erledigte erst löschen."
        z = {"id": uuid.uuid4().hex[:10], "text": text, "koerper": str(koerper or "")[:40], "erledigt": False,
             "angelegt": int(time.time())}
        self._schreiben([*ziele, z])
        return z, ""

    def setzen(self, zid: str, erledigt: bool) -> bool:
        ziele = self.alle()
        for z in ziele:
            if z["id"] == zid:
                z["erledigt"] = bool(erledigt)
                self._schreiben(ziele)
                return True
        return False

    def loeschen(self, zid: str) -> bool:
        ziele = self.alle()
        neu = [z for z in ziele if z["id"] != zid]
        if len(neu) == len(ziele):
            return False
        self._schreiben(neu)
        return True

    def _schreiben(self, ziele: list[dict[str, Any]]) -> None:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.pfad.with_suffix(".teil")
        tmp.write_text(json.dumps({"ziele": ziele}, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.pfad)


def gelernte_ziele(ari: dict[str, Any] | None, auftraege: dict[str, dict[str, Any]], bello: dict[str, Any] | None,
                   bewegungen: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Ziele aus dem, was schon gelernt wurde – Fortschritt nur aus echten Zahlen."""
    out: list[dict[str, Any]] = []
    if ari:
        a = ari.get("aufgabe") or {}
        g = ari.get("gelernt") or {}
        n = int(ari.get("beispiele") or 0)
        if n or g:
            titel = f"{a.get('wuerfel', 'Würfel')} → {a.get('kiste', 'Kiste')}"
            if g:
                anteil = g.get("geschafft", 0) / max(1, g.get("versuche", 1))
                stand = f"gelernt – im Test {g.get('geschafft', 0)} von {g.get('versuche', 0)} geschafft"
            else:
                anteil, stand = None, f"{n} Beispiel{'e' if n != 1 else ''} vorgemacht, noch nicht gelernt"
            out.append({"id": "ari_aufgabe", "titel": titel, "koerper": "so101", "art": "vormachen",
                        "fortschritt": anteil, "stand": stand, "eigen": False})
    for k, v in sorted(auftraege.items()):
        out.append({"id": f"auftrag_{k}", "titel": str(v.get("titel") or k), "koerper": "so101", "art": "auftrag",
                    "fortschritt": 1.0, "stand": f"gemerkt · {len(v.get('schritte') or [])} Schritte", "eigen": False})
    if bello and bello.get("gelernt"):
        tempo = bello.get("tempo")
        out.append({"id": "bello_gang", "titel": "Schneller laufen", "koerper": "bittle", "art": "ueben",
                    "fortschritt": 1.0, "stand": f"gelernte Gangart · {tempo * 100:.0f} cm/s" if tempo else "gelernte Gangart",
                    "eigen": False})
    for koerper, liste in sorted(bewegungen.items()):
        for b in liste:
            out.append({"id": f"bewegung_{koerper}_{b['name']}", "titel": b["name"], "koerper": koerper, "art": "marionette",
                        "fortschritt": 1.0, "stand": f"Kopfbewegung · {b['dauer']:.1f} s".replace(".", ","),
                        "eigen": False, "bewegung": b["name"]})
    return out


def ueberblick(eigene: list[dict[str, Any]], gelernt: list[dict[str, Any]], eigenschaften: set[str],
               koerper: str) -> dict[str, Any]:
    ziele = [{"id": z["id"], "titel": z["text"], "koerper": z.get("koerper", ""), "art": "eigen",
              "fortschritt": 1.0 if z.get("erledigt") else 0.0, "stand": "erledigt" if z.get("erledigt") else "offen",
              "eigen": True, "erledigt": bool(z.get("erledigt"))} for z in eigene]
    ziele += gelernt
    uebungen = [{"id": i, "titel": t, "text": x, "braucht": b, "ansicht": v, "teil": p, "geht": b in eigenschaften}
                for i, t, x, b, v, p in UEBUNGEN]
    offen = sum(1 for z in ziele if z["eigen"] and not z.get("erledigt"))
    return {"ziele": ziele, "uebungen": uebungen, "koerper": koerper,
            "zahlen": {"ziele": len(ziele), "offen": offen, "gelernt": sum(1 for z in ziele if not z["eigen"]),
                       "bewegungen": sum(1 for z in ziele if z["art"] == "marionette")}}
