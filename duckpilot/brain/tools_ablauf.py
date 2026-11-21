"""Werkzeug „ablauf“ (seit 0.49, Ablauf-Baukasten und Duck Cards): gespeicherte Abläufe nennen, starten, anhalten.

Teil von `ToolRunner` (Mixin). Abgespielt wird über den Server (`routes/ablauf.py`), damit Fenster und Stimme dasselbe
zeigen; `self.ablauf_dienst` setzt die Laufzeit. Ohne Sprachmodell: „Spiel den Ablauf Kreis“, „Welche Abläufe gibt es?“.
"""

from __future__ import annotations

import re
from typing import Any

ABLAUF_TOOL = {
    "name": "ablauf",
    "description": "Gespeicherte Abläufe aus dem Baukasten (auch aus Duck Cards gelesen): aktion liste = Namen nennen, "
    "start = einen Ablauf abspielen (name), stopp = anhalten. Schritte, die dieser Körper nicht kann, überspringt er "
    "und nennt sie.",
    "input_schema": {"type": "object", "properties": {
        "aktion": {"type": "string", "enum": ["liste", "start", "stopp"]}, "name": {"type": "string"}},
        "required": ["aktion"]},
}

START = re.compile(r"\b(?:spiel|starte|mach|führ)\w*\s+(?:den\s+|die\s+)?ablauf\s+[„\"']?(?P<name>[^„\"'?.!]+)", re.I)
LISTE = re.compile(r"\bwelche\s+abl(ä|ae)ufe\b|\bzeig\w*\s+(mir\s+)?(die\s+)?abl(ä|ae)ufe\b", re.I)


class AblaufWerkzeuge:
    async def _ablauf(self, a: dict[str, Any]) -> dict[str, Any]:
        dienst = getattr(self, "ablauf_dienst", None)
        if dienst is None:
            return {"ok": False, "fehler": "Abläufe gibt es nur mit dem Knowlin-Server."}
        aktion = str(a.get("aktion") or "")
        if aktion == "liste":
            namen = sorted(dienst.ablage.alle())
            return {"ok": True, "ablaeufe": namen,
                    "text": ("Gespeicherte Abläufe: " + ", ".join(namen) + ".") if namen else "Noch keine Abläufe gespeichert."}
        if aktion == "stopp":
            return await dienst.stopp()
        if aktion == "start":
            name = str(a.get("name") or "").strip()
            alle = dienst.ablage.alle()
            treffer = next((k for k in alle if k.lower() == name.lower()), None)
            if treffer is None:
                return {"ok": False, "fehler": f"Einen Ablauf „{name}“ gibt es nicht."}
            return await dienst.start({"name": treffer})
        return {"ok": False, "fehler": "aktion: liste, start oder stopp"}

    async def _ablauf_befehl(self, text: str) -> dict[str, Any] | None:
        if LISTE.search(text or ""):
            return await self.run("ablauf", {"aktion": "liste"})
        m = START.search(text or "")
        if m:
            return await self.run("ablauf", {"aktion": "start", "name": m.group("name").strip()})
        return None
