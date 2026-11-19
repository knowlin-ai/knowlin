"""Werkzeuge fürs Erinnern (seit 0.39, Erfahrungsnetz 2): Tagesrückblick und Weltbild.

Teil von `ToolRunner` (Mixin). `self.erfahrung_dienst` (der `ErfahrungService`) und `self.raum` setzt die Laufzeit.

* `tagesrueckblick` – was heute (oder gestern, oder an einem Tag) los war, ohne Sprachmodell zusammengefasst
  (`tagebuch.py`); das Sprachmodell erzählt es nur nach, erfindet nichts dazu.
* `weltbild` – was Knowlin über die Dinge im Zimmer glaubt: wo zuletzt, wo meistens, wie sicher (`sichtungen.py`).
  Nur Dinge und Möbel, nie Menschen.

Personen: In einer Runde vom Handy fallen Momente mit Personen weg (wie im Erfahrungsnetz).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

TAGESRUECKBLICK_TOOL = {
    "name": "tagesrueckblick",
    "description": "Was heute (oder gestern) los war – aus dem eigenen Tagebuch, ohne etwas dazuzuerfinden: wie viel "
    "passiert ist, worum es am meisten ging, was neu war, Lob und Kritik, Stimmung, die stärksten Momente. Für "
    "„Wie war dein Tag?“, „Was hast du heute erlebt?“. Erzähl es kurz in eigenen Worten nach.",
    "input_schema": {"type": "object", "properties": {"tag": {"type": "string",
                                                               "description": "heute (Standard), gestern oder JJJJ-MM-TT"}}},
}
WELTBILD_TOOL = {
    "name": "weltbild",
    "description": "Was du über die Dinge im Zimmer glaubst: je Ding wo zuletzt gesehen, wo es meistens liegt, ob es "
    "gerade woanders liegt als sonst und wie sicher du bist. Nur Dinge und Möbel, nie Menschen. Für „Was weißt du über "
    "das Zimmer?“, „Was liegt wo?“. Für ein einzelnes Ding lieber wo_gesehen.",
    "input_schema": {"type": "object", "properties": {}},
}
ERINNER_TOOLS = (TAGESRUECKBLICK_TOOL, WELTBILD_TOOL)


def tag_aus(text: str, heute: date | None = None) -> str | None:
    heute = heute or date.today()
    t = (text or "").strip().lower()
    if not t or t in ("heute", "today"):
        return heute.isoformat()
    if t in ("gestern", "yesterday"):
        return (heute - timedelta(days=1)).isoformat()
    try:
        return date.fromisoformat(t).isoformat()
    except ValueError:
        return None


class ErinnerWerkzeuge:
    def _erinnern(self, name: str, a: dict[str, Any]) -> dict[str, Any]:
        from ..remote import REMOTE_TURN

        if name == "tagesrueckblick":
            dienst = getattr(self, "erfahrung_dienst", None)
            if dienst is None or not dienst.on:
                return {"ok": False, "fehler": "Das Gedächtnis ist aus – ohne Gedächtnis gibt es kein Tagebuch."}
            tag = tag_aus(str(a.get("tag") or ""))
            if tag is None:
                return {"ok": False, "fehler": "tag: heute, gestern oder JJJJ-MM-TT"}
            r = dienst.rueckblick(tag, remote=bool(REMOTE_TURN.get()))
            return {"ok": True, "tag": r["tag"], "text": r["text"], "anzahl": r["anzahl"],
                    "worum": [f"{h['name']} ({h['n']}×)" for h in r["haeufig"]], "neu": r["neu"],
                    "momente": [f"{m['zeit']} {m['warum']}" for m in r["momente"]], "stimmung": r["stimmung"]}
        raum = getattr(self, "raum", None)
        if raum is None:
            return {"ok": False, "fehler": "Raumwissen nicht verfügbar"}
        bild = raum.sichtungen.weltbild()
        if not bild:
            return {"ok": True, "dinge": [], "text": "Ich habe im Zimmer noch keine Dinge gesehen."}
        return {"ok": True, "dinge": [{k: g[k] for k in ("name", "platz", "typisch", "woanders", "gewissheit", "vor_s")}
                                      for g in bild[:20]]}
