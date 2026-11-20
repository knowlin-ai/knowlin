"""Werkzeug „zubehoer“ (seit 0.47, Zubehör der Microduck): Rollen anklemmen, geduckt fahren, Arena-Rennen und das
NFC-Polaroid („wovon träumt sie?“). Teil von `ToolRunner` (Mixin).

Nur für Körper, deren Profil das Zubehör nennt (`Koerper.zubehoer`) und die es im Simulator können – im Physikmodell
gibt es noch keine Rollen (`fehlt_dem_koerper`). `self.zubehoer_dienst` setzt die Laufzeit (Rennen und Polaroid
laufen über den Server, damit Fenster und Stimme dasselbe zeigen).
"""

from __future__ import annotations

import re
from typing import Any

ZUBEHOER_TOOL = {
    "name": "zubehoer",
    "description": "Zubehör der Microduck (einfacher Simulator): rollen_an / rollen_ab = Rollen an die Füße klemmen "
    "oder abnehmen (nur im Stand; mit Rollen schneller, rollt nach, kein Seitwärts, keine Tricks am Boden); ducken / "
    "aufrichten = geduckt noch schneller fahren; rennen = eine Runde Arena-Rennen durch die Tore mit Zeitmessung "
    "(selbst fahren); polaroid = das NFC-Polaroid zeigt, wovon sie träumt (aus dem Tag). Sag ehrlich, was geklappt hat.",
    "input_schema": {"type": "object", "properties": {
        "aktion": {"type": "string", "enum": ["rollen_an", "rollen_ab", "ducken", "aufrichten", "rennen", "polaroid"]}},
        "required": ["aktion"]},
}

# Ohne Sprachmodell: kurze, eindeutige Sätze (kein „Rolle“ – das ist der Trick „roulade“)
_BEFEHLE: tuple[tuple[str, str], ...] = (
    (r"\b(rollen|rollschuhe?)\s+(ab|weg|abnehmen|runter)\b|\bnimm\b.*\brollen\b.*\bab\b", "rollen_ab"),
    (r"\b(rollen|rollschuhe?)\s+(an|dran|anklemmen|anlegen)\b|\bfahr\w*\s+rollschuh|\bklemm\w*\b.*\brollen\b", "rollen_an"),
    (r"\b(duck dich|ducken|geduckt)\b", "ducken"),
    (r"\b(richte? dich auf|aufrichten|aufrecht)\b", "aufrichten"),
    (r"\b(arena-?rennen|fahr\w* (ein|das) rennen|rennen fahren|zeitfahren)\b", "rennen"),
    (r"\bpolaroid\b|\bwovon\b.*\bträum", "polaroid"),
)


def befehl(text: str) -> str | None:
    t = " ".join((text or "").lower().split())
    for muster, aktion in _BEFEHLE:
        if re.search(muster, t):
            return aktion
    return None


class ZubehoerWerkzeuge:
    async def _zubehoer(self, a: dict[str, Any]) -> dict[str, Any]:
        aktion = str(a.get("aktion") or "")
        be = self.engine.backend
        if aktion in ("rollen_an", "rollen_ab", "ducken", "aufrichten"):
            an = aktion != "rollen_ab"
            geduckt = {"ducken": True, "aufrichten": False}.get(aktion)
            if geduckt is not None:
                an = bool(getattr(be, "rollen", False))
                if not an:
                    return {"ok": False, "fehler": "Erst die Rollen anklemmen"}
            r = be.rollen_anlegen(an, geduckt)
            return {"ok": r.accepted, "text": r.reason or "", **({} if r.accepted else {"fehler": r.reason})}
        dienst = getattr(self, "zubehoer_dienst", None)
        if dienst is None:
            return {"ok": False, "fehler": "Rennen und Polaroid gibt es nur mit dem Knowlin-Server"}
        if aktion == "rennen":
            return await dienst.rennen_start(selbst=True)
        if aktion == "polaroid":
            return await dienst.polaroid(remote=False)
        return {"ok": False, "fehler": "aktion: rollen_an, rollen_ab, ducken, aufrichten, rennen oder polaroid"}

    async def _zubehoer_befehl(self, text: str) -> dict[str, Any] | None:
        """„Rollen an“, „fahr Rollschuh“, „Arena-Rennen“, „wovon träumst du?“ → Werkzeug; sonst None."""
        aktion = befehl(text)
        if aktion is None:
            return None
        from .. import koerper

        be = self.engine.backend
        profil = koerper.zu_zustand(getattr(be, "koerper_art", "") or koerper.holen("duckpilot").koerper_zustand)
        if not (profil and profil.zubehoer):            # andere Körper: kein Zubehör – der Satz geht weiter ans Übliche
            return None
        return await self.run("zubehoer", {"aktion": aktion})       # im Physikmodell sagt `run`, warum nicht
