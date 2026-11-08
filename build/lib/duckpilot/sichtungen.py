"""„Wo hast du die Socke zuletzt gesehen?“ – Sichtungen von Dingen und Orten (seit 0.37, Kern).

Was die Ente sieht (`Perception.objects`), merkt sie sich mit Stelle und Zeit – **nur Dinge und Möbel**. Menschen,
Gesichter und der Laserpunkt kommen nie hinein (Projektregel: nur Dinge und Orte). Die Antwort beschreibt die Stelle
so, wie ein Mensch sie beschreibt: beim nächsten Möbelstück oder einem gemerkten Ort, dazu wie lange es her ist.

Gespeichert wird je Körper (`sichtungen/<koerper>.json` im Datenordner) – Simulator und echte Wohnung haben verschiedene
Koordinaten. Die Datei bleibt am PC; sie gehört wie die Karte nie in ein Knowlet oder einen Fehlerbericht.
"""

from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Any

NIE = {"person", "laser", "gesicht", "face"}     # wird nie gemerkt
TAKT_S = 0.5                                       # je Ding höchstens so oft eintragen
MAX = 200
NAH_MOEBEL_M = 0.9
NAH_ORT_M = 1.2

ALIAS = {"sock": "socke", "brick": "klemmbaustein", "lego": "klemmbaustein", "baustein": "klemmbaustein",
         "chess": "schachfigur", "pawn": "schachfigur", "figur": "schachfigur", "bauer": "schachfigur",
         "block": "klötzchen", "kloetzchen": "klötzchen", "sofa": "sofa", "couch": "sofa", "shelf": "regal",
         "box": "kiste", "plant": "pflanze", "stool": "hocker", "table": "couchtisch", "tisch": "couchtisch"}

AKKUSATIV = {"socke": "die", "klötzchen": "das", "klemmbaustein": "den", "schachfigur": "die", "ball": "den"}


def _en(name: str) -> str:
    """Name eines Dings/Möbels auf Englisch (Oberflächenkatalog), klein für den Satz."""
    from .i18n import ui_text

    return ui_text(name, "en").lower()


def _norm(text: str) -> str:
    return re.sub(r"[^a-zäöüß]", "", text.lower())


def _welt(st: Any, obj: dict[str, Any]) -> tuple[float, float]:
    """Wie `motion.behaviors._welt`: Entfernung vom Kopf (3 cm vor der Mitte), Richtung vom Rumpf aus."""
    r = float(obj["entfernung_m"]) + 0.03
    b = math.radians(float(obj["richtung_grad"]))
    return st.x + r * math.cos(st.yaw + b), st.y + r * math.sin(st.yaw + b)


def wie_lange(sekunden: float, en: bool = False) -> str:
    s = max(0.0, sekunden)
    if s < 30:
        return "just now" if en else "gerade eben"
    if s < 90:
        return "a minute ago" if en else "vor einer Minute"
    if s < 3600:
        n = round(s / 60)
        return f"{n} minutes ago" if en else f"vor {n} Minuten"
    if s < 2 * 3600:
        return "an hour ago" if en else "vor einer Stunde"
    if s < 86400:
        n = round(s / 3600)
        return f"{n} hours ago" if en else f"vor {n} Stunden"
    n = round(s / 86400)
    return ("yesterday" if n == 1 else f"{n} days ago") if en else ("gestern" if n == 1 else f"vor {n} Tagen")


class Sichtungen:
    """Letzte Sichtung je Ding: {name: {art, x, y, t, mal}} – `t` ist Unix-Zeit."""

    def __init__(self, pfad: Path | None = None) -> None:
        self.pfad = pfad
        self.daten: dict[str, dict[str, Any]] = {}
        self.geaendert = False
        self._zuletzt: dict[str, float] = {}
        if pfad and pfad.exists():
            try:
                roh = json.loads(pfad.read_text(encoding="utf-8"))
                self.daten = {k: v for k, v in roh.get("dinge", {}).items() if v.get("art") not in NIE}
            except (ValueError, OSError, AttributeError):
                self.daten = {}

    # ── eintragen ────────────────────────────────────────────────────────
    def beobachte(self, st: Any, jetzt: float | None = None) -> int:
        """Alle gerade gesehenen Dinge eintragen (ohne Menschen). → Anzahl eingetragener."""
        jetzt = time.time() if jetzt is None else jetzt
        n = 0
        for obj in getattr(getattr(st, "perception", None), "objects", None) or []:
            art = str(obj.get("art", ""))
            name = str(obj.get("name", "")).strip()
            if not name or art in NIE or "entfernung_m" not in obj:
                continue
            if jetzt - self._zuletzt.get(name, 0.0) < TAKT_S:
                continue
            self._zuletzt[name] = jetzt
            x, y = _welt(st, obj)
            alt = self.daten.get(name)
            self.daten[name] = {"art": art, "x": round(x, 3), "y": round(y, 3), "t": round(jetzt, 1),
                                "mal": (alt or {}).get("mal", 0) + 1}
            self.geaendert = True
            n += 1
        if len(self.daten) > MAX:                         # älteste zuerst vergessen
            for k in sorted(self.daten, key=lambda k: self.daten[k]["t"])[:len(self.daten) - MAX]:
                del self.daten[k]
        return n

    def speichern(self) -> None:
        if not self.pfad or not self.geaendert:
            return
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.pfad.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "dinge": self.daten}, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.pfad)
        self.geaendert = False

    def vergessen(self) -> None:
        self.daten.clear()
        self.geaendert = True

    # ── fragen ───────────────────────────────────────────────────────────
    def finde(self, frage: str) -> str | None:
        """Welches gemerkte Ding ist gemeint? (Name, Teil davon oder englisches Wort)"""
        if not frage:
            return None
        woerter = [_norm(w) for w in re.split(r"\W+", frage.lower()) if len(_norm(w)) >= 3]
        woerter = [ALIAS.get(w, w) for w in woerter]
        for name in sorted(self.daten, key=lambda k: -self.daten[k]["t"]):
            n = _norm(name)
            if any(w == n or (len(w) >= 4 and (w in n or n in w)) for w in woerter):
                return name
        return None

    def stelle(self, name: str, orte: dict[str, tuple[float, float]] | None = None, en: bool = False) -> str:
        """Die Stelle in Worten: beim nächsten Möbelstück, sonst beim nächsten gemerkten Ort, sonst Koordinaten."""
        d = self.daten[name]
        moebel = [(math.hypot(v["x"] - d["x"], v["y"] - d["y"]), k) for k, v in self.daten.items()
                  if v.get("art") == "möbel" and k != name]
        moebel.sort()
        if moebel and moebel[0][0] <= NAH_MOEBEL_M:
            return f"near the {_en(moebel[0][1])}" if en else f"beim {moebel[0][1]}" if not moebel[0][1].endswith("e") \
                else f"bei der {moebel[0][1]}"
        nahe = sorted((math.hypot(x - d["x"], y - d["y"]), k) for k, (x, y) in (orte or {}).items())
        if nahe and nahe[0][0] <= NAH_ORT_M:
            return f"near {nahe[0][1]}" if en else f"bei {nahe[0][1]}"
        return f"at ({d['x']:.1f}, {d['y']:.1f})" if en else f"bei ({d['x']:.1f} | {d['y']:.1f})"

    def antwort(self, frage: str, orte: dict[str, tuple[float, float]] | None = None, en: bool = False,
                jetzt: float | None = None) -> dict[str, Any]:
        jetzt = time.time() if jetzt is None else jetzt
        name = self.finde(frage)
        if name is None:
            bekannt = self.liste()
            text = (("I haven't seen that yet." if en else "Das habe ich noch nicht gesehen.")
                    + (f" {'I know' if en else 'Ich kenne'}: {', '.join(bekannt[:8])}." if bekannt else ""))
            return {"ok": True, "gefunden": False, "text": text, "bekannt": bekannt}
        d = self.daten[name]
        wann = wie_lange(jetzt - d["t"], en)
        wo = self.stelle(name, orte, en)
        text = (f"I last saw the {_en(name)} {wann}, {wo}." if en
                else f"{(AKKUSATIV.get(name.lower(), '') + ' ').lstrip().capitalize()}{name} habe ich zuletzt {wann} "
                     f"gesehen, {wo}.")
        return {"ok": True, "gefunden": True, "ding": name, "x": d["x"], "y": d["y"], "vor_s": round(jetzt - d["t"]),
                "wo": wo, "text": text}

    def liste(self) -> list[str]:
        """Gemerkte Dinge ohne Möbel, zuletzt gesehene zuerst."""
        return [k for k in sorted(self.daten, key=lambda k: -self.daten[k]["t"]) if self.daten[k].get("art") != "möbel"]

    def fuer_anzeige(self, jetzt: float | None = None) -> list[dict[str, Any]]:
        jetzt = time.time() if jetzt is None else jetzt
        return [{"name": k, "art": v["art"], "x": v["x"], "y": v["y"], "vor_s": round(jetzt - v["t"])}
                for k, v in sorted(self.daten.items(), key=lambda kv: -kv[1]["t"])]
