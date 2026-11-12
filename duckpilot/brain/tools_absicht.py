"""Werkzeuge „absicht“ und „selbstbild“ (seit 0.38.43, Etappe G2): Das Sprachmodell sagt, was es meint; der Körper
handelt aus, ob er kann, was er stattdessen tut oder warum nicht (`duckpilot/aktionen.py`).

Teil von `ToolRunner` (Mixin) – `self.engine` setzt der ToolRunner, `self.run` führt die gewählte Umsetzung aus.
"""

from __future__ import annotations

from typing import Any

from .. import aktionen as A
from .. import arm as ARM
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

ARM_TOOL = {
    "name": "arm",
    "description": "Den Arm bewegen (SO-101 und andere Arme): eine Geste (" + ", ".join(ARM.GESTEN) + "), eine Haltung ("
                   + ", ".join(ARM.POSEN) + ") oder einzelne Gelenke in Grad (" + ", ".join(ARM.GELENKE)
                   + "; greifer 0 = zu … 100 = offen). Für Gefühle lieber „absicht“ nehmen.",
    "input_schema": {"type": "object", "properties": {
        "geste": {"type": "string", "enum": list(ARM.GESTEN)},
        "haltung": {"type": "string", "enum": list(ARM.POSEN)},
        "gelenke": {"type": "object", "additionalProperties": {"type": "number"}},
        "sekunden": {"type": "number"}}},
}

GREIFEN_TOOL = {
    "name": "greifen",
    "description": "An der Werkbank ein Ding mit dem Greifer nehmen (fährt hin, greift von oben, hebt es an). "
                   "Dinge: {dinge}. Was außer Reichweite liegt, lehnt der Arm mit Grund ab.",
    "input_schema": {"type": "object", "properties": {"ding": {"type": "string"}}, "required": ["ding"]},
}
ABLEGEN_TOOL = {
    "name": "ablegen",
    "description": "Was der Greifer hält, ablegen: in eine Kiste ({kisten}) oder „Platz“ = zurück an seinen Platz.",
    "input_schema": {"type": "object", "properties": {"ziel": {"type": "string"}}, "required": ["ziel"]},
}


def werkbank_werkzeuge(be: Any) -> list[dict[str, Any]]:
    """Greifen und Ablegen nur für Körper mit Werkbank (SO-101 im Simulator, seit 0.38.48) – mit ihren Namen."""
    wb = getattr(be, "werkbank", None)
    if wb is None or not hasattr(be, "greifen"):
        return []
    n = wb.namen()
    return [{**GREIFEN_TOOL, "description": GREIFEN_TOOL["description"].replace("{dinge}", ", ".join(n["dinge"]))},
            {**ABLEGEN_TOOL, "description": ABLEGEN_TOOL["description"].replace("{kisten}", ", ".join(n["kisten"]))}]


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
        aktion = str(a.get("aktion") or "")
        plan = A.aushandeln(aktion, faehig, lage)
        if plan["antwort"] == "nein":
            self._spur(aktion, "nein", plan.get("grund"))
            return {"ok": False, **plan}
        out = await self.run(plan["werkzeug"], plan["argumente"])
        if not out.get("ok", True):
            grund = out.get("fehler") or "Der Körper hat abgelehnt."
            self._spur(aktion, "nein", grund)
            return {"ok": False, "antwort": "nein", "grund": grund}
        if plan["antwort"] == "ersatz":
            self._spur(aktion, "ersatz", plan["wie"])
        return {"ok": True, "antwort": plan["antwort"], "wie": plan["wie"], "absicht": plan["absicht"]}

    def _spur(self, aktion: str, antwort: str, text: str | None) -> None:
        """Gedankenspur (seit 0.38.44): Abweichungen von der Absicht festhalten – wie gemeint ausgeführt braucht keine Zeile."""
        spur = getattr(self, "gedanken", None)
        if spur is None:
            return
        absicht = (A.AKTIONEN.get(aktion) or {}).get("absicht") or aktion
        if antwort == "ersatz":
            spur.merken(f"wollte {absicht}", "gewünscht", quelle="gespraech", wie=text,
                        ergebnis=f"stattdessen: {text}")
        else:
            spur.merken(f"wollte {absicht}", "gewünscht", quelle="gespraech", ergebnis=f"nicht getan: {text}")

    async def _arm(self, a: dict[str, Any]) -> dict[str, Any]:
        """Arm-Werkzeug (seit 0.38.47, G5). Nach dem Not-Aus bleibt der Arm still, bis die Sperre um ist."""
        be = self.engine.backend
        if bool(getattr(self.engine, "notaus_gesperrt", lambda: False)()):
            return {"ok": False, "fehler": "Nach dem Not-Aus bleibe ich still, bis die Sperre um ist."}
        if a.get("geste"):
            geste = getattr(be, "geste", None)
            if geste is None:
                return {"ok": False, "fehler": "Gesten gibt es für diesen Arm noch nicht – nur einzelne Haltungen."}
            r = await geste(str(a["geste"]))
        else:
            gelenke = dict(ARM.POSEN.get(str(a.get("haltung") or ""), {})) or dict(a.get("gelenke") or {})
            if not gelenke:
                return {"ok": False, "fehler": "geste, haltung oder gelenke angeben"}
            r = await be.haltung(gelenke, float(a.get("sekunden") or 1.0))
        return {"ok": bool(r.accepted), "info" if r.accepted else "fehler": r.reason}

    async def _werkbank(self, name: str, a: dict[str, Any]) -> dict[str, Any]:
        """Greifen und Ablegen (seit 0.38.48). Nach dem Not-Aus bleibt der Arm still, bis die Sperre um ist."""
        be = self.engine.backend
        if bool(getattr(self.engine, "notaus_gesperrt", lambda: False)()):
            return {"ok": False, "fehler": "Nach dem Not-Aus bleibe ich still, bis die Sperre um ist."}
        if not werkbank_werkzeuge(be):
            return {"ok": False, "fehler": "Dieser Körper hat keine Werkbank."}
        r = await (be.greifen(str(a.get("ding") or "")) if name == "greifen" else be.ablegen(str(a.get("ziel") or "")))
        return {"ok": bool(r.accepted), "info" if r.accepted else "fehler": r.reason}

    def _selbstbild(self) -> dict[str, Any]:
        st, faehig, lage = self._lage()
        wb = getattr(self.engine.backend, "werkbank", None)
        extra = {"werkbank": {"haelt": wb.haelt, **wb.namen()}} if wb is not None else None
        return {"ok": True, **A.selbstbild(st, faehig, koerper.KURZ, lage["gesperrt"], extra)}
