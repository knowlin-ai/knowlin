"""Werkzeuge fürs Gespräch (seit 0.40, „Gespräch in Echtzeit“): das Wetter. Teil von `ToolRunner` (Mixin).

`self.wetter` (ein `wetter.Wetter`) und `self.wetter_ort` (liefert die Stadt aus den Einstellungen) setzt die Laufzeit.
Die Uhrzeit steht schon in jedem Kontext („jetzt“) und im Alltagsbuddy – dafür braucht es kein eigenes Werkzeug.
"""

from __future__ import annotations

import asyncio
from typing import Any

WETTER_TOOL = {
    "name": "wetter",
    "description": "Wetter heute oder morgen (Open-Meteo): Temperatur, Wetterlage, Regenrisiko. Ohne ort gilt die Stadt "
    "aus den Einstellungen; ort nur, wenn der Mensch eine Stadt nennt („Wetter in Wien“). Nie raten, nie einen Standort "
    "erfragen oder ermitteln. Gib den Satz aus `text` kurz in eigenen Worten wieder.",
    "input_schema": {"type": "object", "properties": {
        "tag": {"type": "string", "enum": ["heute", "morgen"]},
        "ort": {"type": "string", "description": "Stadtname, nur wenn genannt"}}},
}


class GespraechWerkzeuge:
    async def _wetter(self, a: dict[str, Any]) -> dict[str, Any]:
        dienst = getattr(self, "wetter", None)
        if dienst is None:
            return {"ok": False, "fehler": "Wetter nicht verfügbar"}
        ort = str(a.get("ort") or "").strip() or (self.wetter_ort() if callable(getattr(self, "wetter_ort", None)) else "")
        en = bool(getattr(self, "englisch", lambda: False)())
        tag = "morgen" if a.get("tag") == "morgen" else "heute"
        return await asyncio.to_thread(dienst.abfrage, ort, tag, en)
