"""LEDs und Tanz mit Licht (seit 0.39, Stack-chan „wie ab Werk“). Teil von `ToolRunner` (Mixin).

Nur für Körper mit der Eigenschaft `led` (heute Stack-chan): `licht` färbt die LEDs eine Weile, `tanz` lässt sie im Takt
durch die Regenbogenfarben wechseln, während der Kopf über `dance` (Stil „nicken“) mitwippt. Der Not-Aus macht beides
aus – der Körper wird stromlos, und `relax` löscht das Licht.
"""

from __future__ import annotations

from typing import Any

FARBEN = ("gruen", "blau", "rot", "gelb", "lila", "tuerkis", "orange", "weiss", "aus")

LICHT_TOOL = {
    "name": "licht",
    "description": "LEDs am Kopf: `farbe` lässt sie eine Weile in einer Farbe leuchten (aus = wieder nach Zustand). "
    "`tanz`: true = Tanz mit Licht – der Kopf wippt im Takt, die LEDs wechseln durch die Regenbogenfarben. Für "
    "„tanz mit Licht“, „mach dein Licht rot“, „Lichtshow“.",
    "input_schema": {"type": "object", "properties": {
        "farbe": {"type": "string", "enum": list(FARBEN)},
        "tanz": {"type": "boolean"},
        "sekunden": {"type": "number", "description": "1 bis 60, Standard 12 beim Tanz, sonst 5"},
        "bpm": {"type": "number", "description": "Takt beim Tanz, 60 bis 160"}}},
}


def _zahl(a: dict[str, Any], key: str, standard: float, lo: float, hi: float) -> float:
    try:
        v = float(a.get(key, standard))
    except (TypeError, ValueError):
        v = standard
    return max(lo, min(hi, v)) if v == v else standard


class LichtWerkzeuge:
    async def _licht(self, a: dict[str, Any]) -> dict[str, Any]:
        be = self.engine.backend
        if a.get("tanz"):
            sek = _zahl(a, "sekunden", 12.0, 1.0, 60.0)
            bpm = _zahl(a, "bpm", 110.0, 60.0, 160.0)
            if self.engine.notaus_gesperrt():
                return {"ok": False, "fehler": "Nach dem Not-Aus ruht der Körper noch – danach geht der Tanz wieder."}
            res = be.lichttanz(sek, bpm)
            if not res.accepted:
                return {"ok": False, "grund": res.reason}
            kopf = await self.run("dance", {"style": "nicken", "seconds": sek, "bpm": bpm})
            return {"ok": True, "licht": "tanzt", "kopf": kopf.get("ok", True) is not False, "sekunden": sek}
        farbe = str(a.get("farbe") or "")
        if farbe not in FARBEN:
            return {"ok": False, "fehler": f"farbe: {', '.join(FARBEN)} – oder tanz: true"}
        res = be.licht(None if farbe == "aus" else farbe, _zahl(a, "sekunden", 5.0, 0.5, 60.0))
        return {"ok": res.accepted, "grund": res.reason}
