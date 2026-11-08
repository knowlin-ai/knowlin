"""Anwählen und Handeln (seit 0.37.3, Wunsch des Maintainers): Was kann die Ente mit einem Ding tun?

„Kann es eine Art Objekterkennung geben, dass ich die Sachen anwählen und dann einen Befehl äußern oder auswählen kann
(z. B. aufheben, reden, ärgern, schießen)?“ – Im Simulator weiß duckpilot, was wo liegt; am echten Roboter kommt das
aus der Kamera (R2). Jedes Ding bietet die Handlungen an, die zu seiner Art passen (wie „Affordances“ in der Robotik).
Das ist das erste Stück der Fähigkeiten-Schnittstelle aus 0.38: eine Handlung = Name + Werkzeug + Argumente; die
Werkzeuge bringen Vorbedingung, Ergebnisprüfung und Plan B selbst mit (z. B. Apportieren).
"""

from __future__ import annotations

from typing import Any

# Art → [(Handlung, Beschriftung)]
AKTIONEN: dict[str, tuple[tuple[str, str], ...]] = {
    "ball": (("zielen", "Schießen auf …"), ("schiessen", "Schießen"), ("hinlaufen", "Hinlaufen"),
             ("anschauen", "Anschauen"), ("zuruecklegen", "Zurücklegen")),
    "aufhebbar": (("aufheben", "Aufheben"), ("bringen", "Bring es mir"), ("hinlaufen", "Hinlaufen"),
                  ("anschauen", "Anschauen"), ("zuruecklegen", "Zurücklegen")),
    "ente": (("begruessen", "Begrüßen"), ("aergern", "Ärgern"), ("folgen", "Hinterherlaufen"), ("anschauen", "Anschauen")),
    "möbel": (("hinlaufen", "Hinlaufen"), ("anschauen", "Anschauen")),
}
AUFHEBBAR = ("sock", "block", "baustein", "figur")


def gruppe(art: str) -> str | None:
    if art in AUFHEBBAR:
        return "aufhebbar"
    return art if art in AKTIONEN else None


# Was eine Handlung vom Körper braucht (seit 0.38.25, Frage „manche Funktionen wie Aufheben kann sie doch gar
# nicht?“): Alle Handlungen laufen über Beine (Werkzeug „handeln“); Aufheben und Bringen brauchen dazu den Schnabel.
# Die Open Duck hat keinen, Reachy Mini hat keine Beine – das Menü bietet nur an, was der Körper wirklich kann.
BRAUCHT = {"aufheben": {"beine", "schnabel"}, "bringen": {"beine", "schnabel"}}


def kann(aktion: str, backend: Any) -> bool:
    eig = set(backend.eigenschaften()) if backend is not None and hasattr(backend, "eigenschaften") else None
    if eig is None:
        return True
    return BRAUCHT.get(aktion, {"beine"}) <= eig


def aktionen(art: str, backend: Any = None) -> list[dict[str, str]]:
    g = gruppe(art)
    return [{"id": a, "label": label} for a, label in AKTIONEN.get(g or "", ()) if kann(a, backend)]


def werkzeug(name: str, art: str, aktion: str) -> tuple[str, dict[str, Any]] | None:
    """Welches Werkzeug eine Handlung ausführt – None, wenn sie zu dieser Art nicht passt."""
    g = gruppe(art)
    if g is None or aktion not in {a for a, _ in AKTIONEN[g]}:
        return None
    ziel = name.lower()
    if aktion == "schiessen":
        return ("skill", {"name": "kick_left"})                 # KickBall läuft selbst hin
    if aktion == "zielen":                                       # Ziel kommt mit dem zweiten Klick (seit 0.37.9)
        return ("schiessen", {})
    if aktion == "aufheben":
        return ("_pick", {"target": ziel})
    if aktion == "bringen":
        return ("apportieren", {"ding": ziel})
    if aktion == "hinlaufen":
        return ("approach", {"target": ziel})
    if aktion == "anschauen":
        return ("_anschauen", {"ziel": name})
    if aktion in ("begruessen", "aergern"):
        return ("_begegnung", {"ente": name, "art": "gruss" if aktion == "begruessen" else "aergern"})
    if aktion == "folgen":
        return ("_hinterher", {"ziel": name, "sekunden": 30})
    if aktion == "zuruecklegen":                                 # nur im Simulator (seit 0.37.14)
        return ("_zuruecklegen", {})
    return None


# Reachy Mini im Simulator (seit 0.38.10): mit der Hand auf eine Fläche stellen – Couchtisch, Hocker … oder Boden
REACHY_STELLEN = ("reachy_stellen", "Reachy hierhin stellen")
REACHY_BODEN = ("reachy_boden", "Reachy auf den Boden stellen")


def reachy_aktionen(ding: dict[str, Any], backend: Any) -> list[dict[str, str]]:
    """Zusätzliche Einträge im Menü eines Möbelstücks – nur, wenn Reachy im Simulator der Körper ist."""
    pruefen = getattr(backend, "platz_pruefen", None)
    if pruefen is None or ding.get("art") != "möbel":
        return []
    if getattr(backend, "standflaeche", "") == ding.get("name"):
        return [{"id": REACHY_BODEN[0], "label": REACHY_BODEN[1]}]
    if pruefen(ding["name"]) is None:
        return [{"id": REACHY_STELLEN[0], "label": REACHY_STELLEN[1]}]
    return []


def reachy_platzieren(backend: Any, ding: str, aktion: str) -> dict[str, Any]:
    """Reachy auf das Möbelstück (oder davor auf den Boden) stellen – abgelehnt, wo er nicht stehen kann."""
    platzieren = getattr(backend, "platzieren", None)
    if platzieren is None:
        return {"ok": False, "fehler": "Umstellen geht nur mit Reachy Mini im Simulator"}
    ok, text = platzieren("boden" if aktion == REACHY_BODEN[0] else ding)
    return {"ok": True, "text": text} if ok else {"ok": False, "fehler": text}


def ding_finden(name: str, backend: Any, schwarm: Any = None) -> dict[str, Any] | None:
    """Name → {name, art, x, y} aus der Welt des Simulators und den weiteren Enten."""
    n = str(name or "").strip().lower()
    if not n:
        return None
    if schwarm is not None:
        e = schwarm.ente(n)
        if e is not None:
            return {"name": e.ente_name, "art": "ente", "x": e.x, "y": e.y}
    welt = getattr(backend, "world_model", None)
    if welt is None:
        return None
    for i in welt.items:
        if i.name.lower() == n:
            return {"name": i.name, "art": i.kind, "x": i.x, "y": i.y}
    for m in [*welt.boxes, *welt.cylinders]:
        if m.name.lower() == n:
            return {"name": m.name, "art": "möbel", "x": m.x, "y": m.y}
    return None


# Deiktische Wörter im Chat: „heb das auf“, „schieß den“, „ärger sie“ – dann ist das angewählte Ding gemeint
ZEIGEWOERTER = ("das", "den", "die", "dem", "der", "es", "ihn", "ihm", "ihr", "sie", "dies", "diese", "dieses", "diesen",
                "this", "that", "it", "him", "her", "them")


def mit_auswahl(text: str, auswahl: dict[str, Any] | None) -> str:
    """Chattext fürs Gehirn um das angewählte Ding ergänzen, wenn der Text darauf zeigt („heb das auf“)."""
    if not auswahl or not auswahl.get("name"):
        return text
    import re

    woerter = set(re.findall(r"\w+", text.lower()))
    if auswahl["name"].lower() in woerter or not woerter & set(ZEIGEWOERTER):
        return text
    return f"{text} (gemeint: {auswahl['name']})"
