"""Werkzeug „nachschlagen“ (seit 0.51): kurz in der Wikipedia nachschauen – nur wenn eingeschaltet (`websuche`).

Teil von `ToolRunner` (Mixin). Den Dienst (`nachschlagen.Nachschlagen`) und die Einstellung setzt die Laufzeit
(`self.nachschlagen_dienst`, `self.websuche_an`). Ohne Sprachmodell: „Schlag Ada Lovelace nach“, „Was steht in der
Wikipedia über den Mond?“. An die Wikipedia geht nur der Suchbegriff.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

NACHSCHLAGEN_TOOL = {
    "name": "nachschlagen",
    "description": "Einen Begriff kurz in der Wikipedia nachschlagen (die ersten zwei Sätze, mit Quelle). Nur wenn der "
    "Mensch etwas wissen will, das du nicht sicher weißt – nie Personen aus dem Gespräch oder dem Gedächtnis "
    "nachschlagen. Geht nur, wenn „Im Netz nachschlagen“ eingeschaltet ist; sonst sag das ehrlich.",
    "input_schema": {"type": "object", "properties": {"begriff": {"type": "string"}}, "required": ["begriff"]},
}

BEFEHL = re.compile(r"\b(?:schlag|schlage|guck|schau)\w*\s+(?:mal\s+)?(?P<b>.{2,80}?)\s+nach\b"
                    r"|\bwas\s+steht\s+(?:in\s+der\s+)?wikipedia\s+(?:über|zu)\s+(?P<w>.{2,80})", re.I)


class WissenWerkzeuge:
    async def _nachschlagen(self, a: dict[str, Any]) -> dict[str, Any]:
        dienst = getattr(self, "nachschlagen_dienst", None)
        if dienst is None:
            return {"ok": False, "fehler": "Nachschlagen gibt es nur mit dem Knowlin-Server."}
        an = bool(self.websuche_an()) if callable(getattr(self, "websuche_an", None)) else False
        r = await asyncio.to_thread(dienst.frage, a.get("begriff"), an)
        if r.get("ok"):
            r = {**r, "antwort": f"{r['text']} (Wikipedia)"}
        return r

    async def _nachschlagen_befehl(self, text: str) -> dict[str, Any] | None:
        m = BEFEHL.search(text or "")
        if not m:
            return None
        begriff = re.sub(r"^(?:den|die|das|der|dem)\s+", "", (m.group("b") or m.group("w") or "").strip(" ?!."), flags=re.I)
        return await self.run("nachschlagen", {"begriff": begriff})
