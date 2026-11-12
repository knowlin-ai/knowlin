"""Aktionskatalog und Selbstbild (seit 0.38.43, Etappe G2 aus dem Konzept „Knowlins Geist“).

Wunsch des Maintainers: „die Aktion ist klar, ob der Körper sie umsetzen kann, wird dann mit der Hardware abgestimmt“
(Hardware Abstraction Layer). Eine **Aktion** beschreibt, was gemeint ist – nicht, welche Gelenke sich bewegen. Jede
Aktion nennt Umsetzungen in der Reihenfolge, in der sie gemeint sind; jede Umsetzung braucht Fähigkeiten aus dem
Wortschatz der Körperschnittstelle (`duckpilot/koerper.py`). Der Körper antwortet mit

* **kann**   – die erste Umsetzung passt,
* **Ersatz** – eine spätere passt (z. B. ohne Beine Freude nur mit dem Kopf zeigen),
* **nein**   – mit Grund, den das Sprachmodell ehrlich weitersagt (keine passende Fähigkeit, liegt, Sperre nach dem
  Not-Aus, hochgehoben …).

Seit 0.38.47 (G5) hat jede Aktion auch eine Umsetzung für Arme (`arm.GESTEN`) – der SO-101 grüßt mit Winken.
Neue Aktionen sind Daten, kein Code. Das **Selbstbild** fasst zusammen, was der Körper ist, kann und gerade erlebt –
damit „Wie geht's dir?“ aus Daten beantwortet wird statt erfunden.
Diese Datei gehört zur Basis und importiert nichts aus Knowlin.
"""

from __future__ import annotations

from typing import Any

# Umsetzung: (braucht, werkzeug, argumente, kurz in Worten)
AKTIONEN: dict[str, dict[str, Any]] = {
    "gruessen": {"absicht": "jemanden bemerken und freundlich zeigen, dass man ihn sieht", "umsetzungen": [
        ({"kopf"}, "emote", {"emotion": "begruessen"}, "grüßt mit dem Kopf"),
        ({"arm"}, "arm", {"geste": "winken"}, "winkt mit dem Arm"),
        ({"stimmbank"}, "sound", {"tag": "greet"}, "grüßt mit einem Laut")]},
    "zustimmen": {"absicht": "zeigen, dass man einverstanden ist", "umsetzungen": [
        ({"kopf"}, "emote", {"emotion": "nicken"}, "nickt"),
        ({"arm"}, "arm", {"geste": "nicken"}, "nickt mit dem Greifer"),
        ({"stimmbank"}, "sound", {"tag": "chirp"}, "gibt einen zufriedenen Laut")]},
    "ablehnen": {"absicht": "freundlich zeigen, dass man etwas nicht möchte", "umsetzungen": [
        ({"kopf"}, "emote", {"emotion": "nein"}, "schüttelt den Kopf"),
        ({"arm"}, "arm", {"geste": "kopfschuetteln"}, "dreht den Greifer hin und her")]},
    "freuen": {"absicht": "Freude zeigen", "umsetzungen": [
        ({"beine", "kopf"}, "emote", {"emotion": "begeistert"}, "freut sich mit dem ganzen Körper"),
        ({"kopf"}, "emote", {"emotion": "freude"}, "freut sich mit dem Kopf"),
        ({"arm"}, "arm", {"geste": "freuen"}, "reckt den Arm und klappert mit dem Greifer"),
        ({"stimmbank"}, "sound", {"tag": "wheee"}, "jauchzt kurz")]},
    "neugierig": {"absicht": "zeigen, dass einen etwas interessiert", "umsetzungen": [
        ({"kopf"}, "emote", {"emotion": "neugierig"}, "legt neugierig den Kopf schief"),
        ({"arm"}, "arm", {"geste": "neugierig"}, "neigt den Greifer neugierig")]},
    "umsehen": {"absicht": "sich umschauen, was los ist", "umsetzungen": [
        ({"kopf"}, "emote", {"emotion": "umherspaehen"}, "schaut sich um"),
        ({"arm"}, "arm", {"geste": "umsehen"}, "schwenkt den Arm und schaut sich um")]},
    "aufmerksam_machen": {"absicht": "auf sich aufmerksam machen", "umsetzungen": [
        ({"beine", "kopf"}, "emote", {"emotion": "hibbeln"}, "hibbelt auf der Stelle"),
        ({"kopf"}, "emote", {"emotion": "aufhorchen"}, "reckt den Kopf"),
        ({"arm"}, "arm", {"geste": "aufmerksam"}, "winkt mit dem ganzen Arm"),
        ({"stimmbank"}, "sound", {"tag": "greet"}, "ruft mit einem Laut")]},
    "traurig": {"absicht": "zeigen, dass einen etwas bedrückt", "umsetzungen": [
        ({"kopf"}, "emote", {"emotion": "traurig"}, "lässt den Kopf hängen"),
        ({"arm"}, "arm", {"geste": "traurig"}, "lässt den Arm sinken")]},
    "staunen": {"absicht": "Staunen zeigen", "umsetzungen": [
        ({"kopf"}, "emote", {"emotion": "staunen"}, "staunt"),
        ({"arm"}, "arm", {"geste": "staunen"}, "reißt den Arm hoch und öffnet den Greifer")]},
    "ausruhen": {"absicht": "zur Ruhe kommen", "umsetzungen": [
        ({"kopf"}, "emote", {"emotion": "doesen"}, "döst kurz"),
        ({"arm"}, "arm", {"geste": "ruhe"}, "legt den Arm in die Ruhelage")]},
}

# Was in jeder Lage geht, ohne den Körper zu belasten: nur der Kopf (z. B. hochgehoben)
NUR_KOPF = {"kopf", "stimmbank", "antennen"}


def aushandeln(aktion: str, faehigkeiten: set[str], lage: dict[str, bool]) -> dict[str, Any]:
    """Fragt den Körper, ob und wie er eine Aktion umsetzen kann.

    `faehigkeiten`: Wortschatz-Einträge des Körpers. `lage`: gesperrt (Sperre nach dem Not-Aus), gefallen, hochgehoben,
    stromlos. Rückgabe: {antwort: kann|ersatz|nein, werkzeug, argumente, wie, grund}."""
    a = AKTIONEN.get(aktion)
    if a is None:
        return {"antwort": "nein", "grund": f"Die Aktion „{aktion}“ kenne ich nicht.", "bekannt": sorted(AKTIONEN)}
    if lage.get("gesperrt"):
        return {"antwort": "nein", "grund": "Nach dem Not-Aus bleibe ich still, bis die Sperre um ist."}
    if lage.get("stromlos"):
        return {"antwort": "nein", "grund": "Meine Motoren sind gerade aus."}
    if lage.get("gefallen"):
        return {"antwort": "nein", "grund": "Ich liege gerade – erst muss ich wieder stehen."}
    erlaubt = set(faehigkeiten) & NUR_KOPF if lage.get("hochgehoben") else set(faehigkeiten)
    for i, (braucht, werkzeug, argumente, wie) in enumerate(a["umsetzungen"]):
        if braucht <= erlaubt:
            return {"antwort": "kann" if i == 0 else "ersatz", "werkzeug": werkzeug, "argumente": dict(argumente),
                    "wie": wie, "absicht": a["absicht"]}
    fehlt = sorted(a["umsetzungen"][-1][0] - set(faehigkeiten))
    if lage.get("hochgehoben"):
        return {"antwort": "nein", "grund": "Ich werde gerade gehalten – das geht erst wieder am Boden."}
    return {"antwort": "nein", "grund": f"Dafür fehlt mir: {', '.join(fehlt) or 'eine passende Fähigkeit'}."}


def selbstbild(st: Any, faehigkeiten: set[str], kurz: dict[str, str], gesperrt: bool,
               extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Was der Körper ist, kann und gerade erlebt – aus Daten, nicht erfunden."""
    if not getattr(st, "connected", False):
        haltung = "nicht verbunden"
    elif getattr(st, "fallen", False):
        haltung = "liegt (umgefallen)"
    elif getattr(st, "picked_up", False):
        haltung = "wird gehalten"
    elif not getattr(st, "powered", False):
        haltung = "stromlos"
    elif getattr(st, "sitting", False):
        haltung = "sitzt"
    else:
        haltung = "steht"
    akku = getattr(st, "battery", None)
    out: dict[str, Any] = {
        "koerper": getattr(st, "koerper", ""),
        "simulator": getattr(st, "backend", "") == "sim",
        "haltung": haltung,
        "kann": sorted(kurz.get(f, f) for f in faehigkeiten if f in kurz),
        "sperre_nach_notaus": gesperrt,
        "akku_prozent": round(akku * 100) if isinstance(akku, (int, float)) else None,
        "haelt": getattr(st, "holding", None),
        "gerade": getattr(st, "skill", None),
        "unsicher": [],
    }
    if akku is None:
        out["unsicher"].append("Akkustand unbekannt")
    out.update(extra or {})
    return out
