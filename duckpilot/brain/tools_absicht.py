"""Werkzeuge „absicht“ und „selbstbild“ (seit 0.38.43, Etappe G2): Das Sprachmodell sagt, was es meint; der Körper
handelt aus, ob er kann, was er stattdessen tut oder warum nicht (`duckpilot/aktionen.py`).

Teil von `ToolRunner` (Mixin) – `self.engine` setzt der ToolRunner, `self.run` führt die gewählte Umsetzung aus.
"""

from __future__ import annotations

from typing import Any

from .. import aktionen as A
from .. import koerper

ABSICHT_TOOL = {
    "name": "absicht",
    "description": "Eine Geste nach ihrer Absicht zeigen – der Körper entscheidet, wie: kann (wie gemeint), ersatz "
                   "(anders, z. B. nur mit dem Kopf) oder nein (mit Grund). Sag ehrlich, was passiert ist, besonders bei "
                   "ersatz und nein. Aktionen: " + "; ".join(f"{k} ({v['absicht']})" for k, v in A.AKTIONEN.items()) + ".",
    "input_schema": {"type": "object", "properties": {"aktion": {"type": "string", "enum": list(A.AKTIONEN)}},
                     "required": ["aktion"]},
}
SELBSTBILD_TOOL = {
    "name": "selbstbild",
    "description": "Wie es dir gerade geht und was du kannst – aus den Daten deines Körpers (Haltung, Fähigkeiten, "
                   "Sperre nach dem Not-Aus, Akku, was du hältst). Nimm es, wenn jemand fragt, wie es dir geht oder was "
                   "du kannst, und antworte nur mit dem, was hier steht; was unter „unsicher“ steht, sag als unsicher.",
    "input_schema": {"type": "object", "properties": {}},
}


class AbsichtWerkzeuge:
    def _lage(self) -> tuple[Any, set[str], dict[str, bool]]:
        be = self.engine.backend
        st = be.state()
        gesperrt = bool(getattr(self.engine, "notaus_gesperrt", lambda: False)())
        lage = {"gesperrt": gesperrt, "gefallen": bool(st.fallen), "hochgehoben": bool(st.picked_up),
                "stromlos": bool(st.connected and not st.powered and not st.fallen)}
        return st, set(be.eigenschaften()), lage

    async def _absicht(self, a: dict[str, Any]) -> dict[str, Any]:
        _st, faehig, lage = self._lage()
        plan = A.aushandeln(str(a.get("aktion") or ""), faehig, lage)
        if plan["antwort"] == "nein":
            return {"ok": False, **plan}
        out = await self.run(plan["werkzeug"], plan["argumente"])
        if not out.get("ok", True):
            return {"ok": False, "antwort": "nein", "grund": out.get("fehler") or "Der Körper hat abgelehnt."}
        return {"ok": True, "antwort": plan["antwort"], "wie": plan["wie"], "absicht": plan["absicht"]}

    def _selbstbild(self) -> dict[str, Any]:
        st, faehig, lage = self._lage()
        return {"ok": True, **A.selbstbild(st, faehig, koerper.KURZ, lage["gesperrt"])}
