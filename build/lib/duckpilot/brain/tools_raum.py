"""Werkzeuge rund um Raum und Ball: Szene zurücksetzen, Teamarbeit, gezielt schießen (seit 0.38 aus tools.py).

Teil von `ToolRunner` (Mixin) – `self.engine`, `self.raum`, `self.memory`, `self.schwarm` setzt der ToolRunner.
"""

from __future__ import annotations

import math
from typing import Any

from ..motion import behaviors as B
from ..motion.apportieren import Apportieren


class RaumWerkzeuge:
    def szene(self, aktion: str, ding: str = "") -> dict[str, Any]:
        """Simulator aufräumen (seit 0.37.14): alles zurück oder ein Ding an seinen Platz."""
        be = self.engine.backend
        if "zuruecksetzen" not in be.eigenschaften():
            return {"ok": False, "fehler": "Zurücksetzen gibt es nur im Simulator – in echt einfach selbst aufheben."}
        if aktion == "zuruecklegen":
            ok, text = be.zuruecklegen(ding)
            return {"ok": ok, ("text" if ok else "fehler"): text}
        if aktion != "zuruecksetzen":
            return {"ok": False, "fehler": "aktion: zuruecksetzen oder zuruecklegen"}
        self.engine._cancel_all("Szene zurückgesetzt")       # was gerade lief, passt nicht mehr zur neuen Lage
        out = be.szene_zuruecksetzen()
        teile = [f"{len(out['dinge'])} Dinge an ihren Platz gelegt"] + (["Ente zurück am Start"] if out["ente"] else [])
        return {**out, "text": ", ".join(teile)}

    DINGE_ARTEN = {"socke": ("sock",), "sock": ("sock",), "klötz": ("block",), "kloetz": ("block",),
                   "block": ("block",), "baustein": ("baustein",), "brick": ("baustein",), "figur": ("figur",),
                   "schach": ("figur",), "chess": ("figur",)}

    async def _team(self, a: dict[str, Any], eng, started) -> dict[str, Any]:
        """Teamarbeit (seit 0.37.4): die anderen Enten helfen beim Aufräumen oder Suchen."""
        from ..motion import team as TM
        from . import handeln as H

        sw = getattr(self, "schwarm", None)
        aktion = str(a.get("aktion") or "status")
        if sw is None or not sw.enten:
            return {"ok": False, "fehler": "Keine weiteren Enten da – im einfachen Simulator unter Steuern → Team "
                                           "einstellen"}
        if aktion == "stopp":
            art = sw.auftrag_stopp()
            return {"ok": True, "gestoppt": art}
        if aktion == "status":
            return {"ok": True, "auftrag": sw.auftrag.zustand() if sw.auftrag else None, "enten": sw.uebersicht()}
        st = eng.backend.state()
        if aktion == "suchen":
            ding = str(a.get("ding") or "").strip()
            if not ding:
                return {"ok": False, "fehler": "Was sollen sie suchen? (ding)"}
            sw.beauftragen(TM.Suche(sw, ding))
            started(B.LookAround(12))                      # sie schaut sich selbst auch um
            return {"ok": True, "auftrag": "suchen", "ding": ding, "helfer": [e.ente_name for e in sw.enten]}
        # aufräumen: wohin?
        from ..sichtungen import ALIAS

        z = str(a.get("ziel") or "").strip().lower()
        z = ALIAS.get(z, z)                                  # „shelf“ → Regal, „couch“ → Sofa …
        if z in ("", "mir", "zu mir", "dir", "hier", "me", "to me", "here"):
            ziel, ziel_name = (st.x + 0.3 * math.cos(st.yaw), st.y + 0.3 * math.sin(st.yaw)), "dir"
        else:
            d = H.ding_finden(z, eng.backend, sw)
            ort = self.memory.find_place(z, self.body()) if (d is None and self.memory is not None) else None
            if d is not None:
                ziel, ziel_name = (d["x"], d["y"]), d["name"]
            elif ort:
                p = self.memory.data["orte"][ort]
                ziel, ziel_name = (p["x"], p["y"]), ort
            else:
                return {"ok": False, "fehler": f"Wohin? „{a.get('ziel')}“ kenne ich nicht (Möbel, gemerkter Ort oder mir)"}
        wort = str(a.get("dinge") or "alles").lower()
        arten = next((v for k, v in self.DINGE_ARTEN.items() if k in wort), TM.AUFHEBBAR)
        auftrag = TM.Aufraeumen(sw, ziel, ziel_name, arten)
        if auftrag.fertig:
            return {"ok": True, "auftrag": "aufraeumen", "ergebnis": auftrag.ergebnis}
        # die Hauptente packt selbst mit an: das ihr nächste Ding
        frei = auftrag.offen()
        if frei:
            mein = min(frei, key=lambda i: math.hypot(i.x - st.x, i.y - st.y))
            auftrag.vergeben[mein.name] = "haupt"
            zx, zy = auftrag.ziel                          # 15 cm davor stehen bleiben – abgelegt landet es am Ziel
            dx, dy = zx - mein.x, zy - mein.y
            dd = math.hypot(dx, dy) or 1.0
            started(Apportieren(mein.name.lower(), (zx - dx / dd * 0.15, zy - dy / dd * 0.15), ziel_name))
        sw.beauftragen(auftrag)
        return {"ok": True, "auftrag": "aufraeumen", "ziel": ziel_name, "dinge": [i.name for i in frei],
                "helfer": [e.ente_name for e in sw.enten]}

    RICHTUNGEN = {"geradeaus": 0.0, "vor": 0.0, "vorne": 0.0, "links": 90.0, "rechts": -90.0, "zurück": 180.0,
                  "zurueck": 180.0, "hinten": 180.0, "straight": 0.0, "left": 90.0, "right": -90.0, "back": 180.0}

    async def _schiessen(self, a: dict[str, Any], eng, started) -> dict[str, Any]:
        """Gezielt schießen (seit 0.37.9): Ziel auflösen, dann GezielterSchuss mit Prüfung und Plan B."""
        from ..motion.schuss import GezielterSchuss
        from ..sichtungen import ALIAS
        from . import handeln as H

        st = eng.backend.state()
        richtung = str(a.get("richtung") or "").strip().lower()
        z = str(a.get("ziel") or "").strip().lower()
        if not z and not richtung:
            return started(B.KickBall())
        if richtung:
            if richtung not in self.RICHTUNGEN:
                return {"ok": False, "fehler": f"Richtung „{richtung}“ kenne ich nicht (links, rechts, geradeaus, zurück)"}
            w = st.yaw + math.radians(self.RICHTUNGEN[richtung])
            ziel, name, r = (st.x + 3 * math.cos(w), st.y + 3 * math.sin(w)), f"nach {richtung}", None
        elif z in ("mir", "zu mir", "me", "to me", "hier", "here"):
            welt = getattr(eng.backend, "world_model", None)
            p = welt.person_point() if welt is not None and hasattr(welt, "person_point") else None
            if p is None:
                return {"ok": False, "fehler": "Ich weiß gerade nicht, wo du bist – sag ein Möbel oder eine Richtung"}
            ziel, name, r = p, "dir", 0.25
        else:
            z = ALIAS.get(z, z)
            d = H.ding_finden(z, eng.backend, getattr(self, "schwarm", None))
            ort = self.memory.find_place(z, self.body()) if (d is None and self.memory is not None) else None
            if d is not None:
                ziel, name = (d["x"], d["y"]), d["name"]
                r = {"möbel": self._moebel_r(eng, d["name"]), "ente": 0.12}.get(d["art"], 0.1)
            elif ort:
                p = self.memory.data["orte"][ort]
                ziel, name, r = (p["x"], p["y"]), ort, 0.3
            else:
                return {"ok": False, "fehler": f"Wohin? „{a.get('ziel')}“ kenne ich nicht (Möbel, Ente, Ort, mir oder "
                                               "eine Richtung)"}
        karte = getattr(getattr(self, "raum", None), "karte", None)
        if karte is not None and karte.messungen < 20:
            karte = None
        return started(GezielterSchuss(ziel, name, r, karte))

    @staticmethod
    def _moebel_r(eng, name: str) -> float:
        welt = getattr(eng.backend, "world_model", None)
        for m in [*getattr(welt, "boxes", []), *getattr(welt, "cylinders", [])]:
            if m.name.lower() == name.lower():
                return getattr(m, "r", None) or math.hypot(m.sx, m.sy) / 2
        return 0.3
