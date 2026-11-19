"""Werkzeug „haus“ (seit 0.45, Haushalt und Smart Home): Licht, Saugroboter, Szenen, Meldung aufs Handy und
„vor dem Saugroboter aufräumen“. Teil von `ToolRunner` (Mixin).

`self.haus` (ein `haus.Haus`) setzt die Laufzeit, dazu `self.haus_sperre` (gilt die Sperre nach dem Not-Aus?) und
`self.haus_aufraeumen` (startet das Aufräumen über den Haushaltsdienst). Was geschaltet werden darf, entscheidet nur
`haus.py` – das Sprachmodell bekommt nie eine Liste mit Schlössern, Alarm oder Heizung zu sehen.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .. import haus as H

HAUS_TOOL = {
    "name": "haus",
    "description": "Smart Home im eigenen Netz (Home Assistant oder Hue Bridge): liste = Geräte zeigen; schalten = Licht "
    "an/aus, Saugroboter start/pause/stopp/heim, Szene an (geraet = Kennung aus der Liste oder Raum-/Gerätename, z. B. "
    "„Wohnzimmer“); melden = kurze Nachricht aufs Handy (nur Text); aufraeumen = Kleines vom Boden zu einem Platz tragen "
    "und danach den Saugroboter starten (ziel = gemerkter Ort oder Möbel, sauger = true/false); rundgang = eine Runde "
    "durch die Wohnung (Simulator) mit Bericht, was auffällt. " + H.NIE_TEXT +
    " Sag ehrlich, was geschaltet wurde und was nicht.",
    "input_schema": {"type": "object", "properties": {
        "aktion": {"type": "string", "enum": ["liste", "schalten", "melden", "aufraeumen", "rundgang"]},
        "geraet": {"type": "string"},
        "art": {"type": "string", "enum": ["licht", "sauger", "szene"]},
        "befehl": {"type": "string", "enum": ["an", "aus", "start", "pause", "stopp", "heim"]},
        "text": {"type": "string"},
        "ziel": {"type": "string"},
        "sauger": {"type": "boolean"}},
        "required": ["aktion"]},
}


def _kurz(g: H.Geraet) -> str:
    return g.name + (f" ({g.raum})" if g.raum and g.raum.lower() not in g.name.lower() else "")


class HausWerkzeuge:
    async def _haus(self, a: dict[str, Any]) -> dict[str, Any]:
        haus: H.Haus | None = getattr(self, "haus", None)
        if haus is None:
            return {"ok": False, "fehler": "Smart Home ist hier nicht eingerichtet"}
        aktion = str(a.get("aktion") or "liste")
        if aktion == "aufraeumen":
            fn = getattr(self, "haus_aufraeumen", None)
            if fn is None:
                return {"ok": False, "fehler": "Aufräumen geht nur im einfachen Simulator mit einem Körper, der aufheben kann"}
            return await fn(str(a.get("ziel") or ""), a.get("sauger", True) is not False)
        if aktion == "rundgang":
            fn = getattr(self, "haus_rundgang", None)
            if fn is None:
                return {"ok": False, "fehler": "Den Rundgang gibt es im einfachen Simulator"}
            return await fn()
        stand = haus.stand()
        if not stand["ha"]["verbunden"] and not stand["hue"]["verbunden"]:
            return {"ok": False, "fehler": "Noch kein Smart Home verbunden – unter Alltag → Smart Home einrichten (am PC)"}
        if aktion == "liste":
            geraete, fehler = await asyncio.to_thread(haus.geraete, True)
            return {"ok": True, "geraete": [{"id": g.id, "name": _kurz(g), "art": g.art, "an": g.an} for g in geraete],
                    "fehler": fehler, "nie": H.NIE_TEXT}
        if aktion == "melden":
            text = " ".join(str(a.get("text") or "").split())[:H.MELDUNG_MAX]
            if not text:
                return {"ok": False, "fehler": "Was soll ich melden? (text)"}
            try:
                ok = await asyncio.to_thread(haus.melden, text)
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "fehler": f"Meldung ging nicht raus: {exc}"}
            return {"ok": ok, **({} if ok else {"fehler": "Kein Meldedienst eingetragen (Home Assistant → Meldungen)"})}
        if aktion != "schalten":
            return {"ok": False, "fehler": "aktion: liste, schalten, melden, aufraeumen oder rundgang"}
        befehl = str(a.get("befehl") or "")
        art = str(a.get("art") or "") or None
        wort = str(a.get("geraet") or "").strip()
        geraete, _ = await asyncio.to_thread(haus.geraete)
        ziele = [g for g in geraete if g.id == wort] or (await asyncio.to_thread(haus.finden, wort, art))
        if art is None and ziele:
            art = ziele[0].art
            ziele = [g for g in ziele if g.art == art]
        if not ziele:
            return {"ok": False, "fehler": f"Kein passendes Gerät für „{wort or art}“. " + H.NIE_TEXT}
        genannt = any(g.id == wort or g.name.lower() in wort.lower() or (g.raum and g.raum.lower() in wort.lower())
                      for g in ziele)
        if not genannt and len(ziele) > 1:          # „Licht an“ ohne Raum: nachfragen statt alles zu schalten
            raeume = sorted({g.raum for g in ziele if g.raum}) or sorted({g.name for g in ziele})
            return {"ok": False, "nachfrage": True, "fehler": "Welches? " + ", ".join(raeume[:8])}
        if art == "sauger" and befehl == "start" and callable(getattr(self, "haus_sperre", None)) and self.haus_sperre():
            return {"ok": False, "fehler": "Nach dem Not-Aus starte ich in der Sperre keinen Saugroboter – kurz warten."}
        if art in ("sauger", "szene"):
            ziele = ziele[:1]                     # ein Sauger, eine Szene – nie alle auf einmal
        geschaltet, fehler = [], []
        for g in ziele[:12]:
            try:
                await asyncio.to_thread(haus.schalten, g.id, befehl)
                geschaltet.append(_kurz(g))
            except Exception as exc:  # noqa: BLE001
                fehler.append(f"{_kurz(g)}: {exc}")
        wort_b = {"an": "an", "aus": "aus", "start": "gestartet", "pause": "pausiert", "stopp": "angehalten",
                  "heim": "zur Station geschickt"}.get(befehl, befehl)
        text = (f"{', '.join(geschaltet)} {wort_b}." if geschaltet else "") + (" Nicht geklappt: " + "; ".join(fehler)
                                                                               if fehler else "")
        return {"ok": bool(geschaltet), "geschaltet": geschaltet, "text": text.strip(), **({"fehler": text.strip()}
                                                                                          if not geschaltet else {})}

    async def _haus_befehl(self, text: str) -> dict[str, Any] | None:
        """Ohne Sprachmodell: „Licht im Wohnzimmer an“ → Werkzeug; None, wenn es kein Haushaltsbefehl ist."""
        b = H.befehl(text)
        if b is None:
            return None
        if b.get("nie"):
            return {"ok": False, "text": H.NIE_TEXT, "fehler": H.NIE_TEXT}
        if getattr(self, "haus", None) is None:
            return None
        if b.get("rundgang"):
            return await self.run("haus", {"aktion": "rundgang"})
        return await self.run("haus", {"aktion": "schalten", "art": b["art"], "befehl": b["aktion"], "geraet": text})
