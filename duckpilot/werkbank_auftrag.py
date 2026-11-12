"""Aufträge an der Werkbank (seit 0.38.54, Wunsch des Maintainers nach Anwendungen, wie sie die SO-101-Gemeinde zeigt):
Aufräumen, nach Farben sortieren, einen Turm bauen.

Ein Auftrag ist **nur Daten** – ein Titel und eine bekannte Regel mit ein paar Angaben, oder eine feste Liste von
Schritten (`{"ding": …, "ziel": …}`). Deshalb lässt er sich auch nachladen und teilen (Knowlets), ohne dass fremder
Code läuft. `planen` macht daraus die Schritte für den aktuellen Stand der Werkbank; ausgeführt werden sie einzeln
nacheinander (`So101Sim.auftrag_starten`), jeder mit eigener Prüfung – klappt einer nicht, endet der Auftrag mit Grund.
"""

from __future__ import annotations

import json
import re
from typing import Any

REGELN = ("zurueck", "farbe", "turm", "schritte")
TURM_HOECHSTENS = 3          # höher reicht der Arm nicht (Spitze über 0,105 m nicht mehr senkrecht erreichbar)
GROESSTE_LISTE = 20

# Eingebaute Aufträge – dasselbe Format wie nachgeladene
AUFTRAEGE: dict[str, dict[str, Any]] = {
    "aufraeumen": {"titel": "Aufräumen", "beschreibung": "Alle Würfel zurück an ihren Platz", "regel": "zurueck"},
    "sortieren": {"titel": "Nach Farben sortieren", "beschreibung": "Warme Farben in die linke Kiste, kalte in die rechte",
                  "regel": "farbe", "links": ["rot", "orange", "gelb"], "rechts": ["blau", "grün"]},
    "turm": {"titel": "Turm bauen", "beschreibung": "Drei Würfel aufeinander, unten der blaue",
             "regel": "turm", "basis": "blauer Würfel", "hoehe": 3},
}


MAX_EIGENE = 30


def _datei():
    from .settings import data_dir

    return data_dir() / "auftraege.json"


def schluessel(titel: str) -> str:
    """„Rot nach links!“ → „rot_nach_links“ (Name, unter dem der Kopf den Auftrag aufruft)."""
    s = re.sub(r"[^a-z0-9äöüß]+", "_", str(titel).lower()).strip("_")[:40]
    return s or "auftrag"


def eigene() -> dict[str, dict[str, Any]]:
    """Gemerkte und aus Knowlets übernommene Aufträge – jeder noch einmal geprüft."""
    try:
        roh = json.loads(_datei().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for k, v in (roh.items() if isinstance(roh, dict) else []):
        geprueft, _ = pruefen(v)
        if geprueft is not None:
            out[schluessel(k)] = geprueft
    return out


def speichern(auftrag: dict[str, Any]) -> tuple[str | None, str]:
    """Einen Auftrag merken (Name aus dem Titel; eingebaute Namen bleiben eingebaut)."""
    geprueft, grund = pruefen(auftrag)
    if geprueft is None:
        return None, grund
    alle_eigenen = eigene()
    k = schluessel(geprueft["titel"])
    if k in AUFTRAEGE:
        k = f"{k}_eigen"
    if k not in alle_eigenen and len(alle_eigenen) >= MAX_EIGENE:
        return None, f"Schon {MAX_EIGENE} eigene Aufträge – erst einen löschen."
    alle_eigenen[k] = geprueft
    pfad = _datei()
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_suffix(".tmp")
    tmp.write_text(json.dumps(alle_eigenen, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(pfad)
    return k, ""


def alle() -> dict[str, dict[str, Any]]:
    """Eingebaute und eigene Aufträge (gemerkt oder aus Knowlets, seit 0.38.54)."""
    return {**eigene(), **AUFTRAEGE}


def pruefen(auftrag: Any) -> tuple[dict[str, Any] | None, str]:
    """Nimmt nur, was wie ein Auftrag aussieht: bekannte Regel, kurze Texte, höchstens 20 Schritte."""
    if not isinstance(auftrag, dict):
        return None, "Ein Auftrag ist ein Objekt mit Titel und Regel."
    regel = auftrag.get("regel")
    if regel not in REGELN:
        return None, f"Unbekannte Regel – bekannt: {', '.join(REGELN)}."
    titel = str(auftrag.get("titel") or "").strip()[:60]
    if not titel:
        return None, "Der Auftrag braucht einen Titel."
    out: dict[str, Any] = {"titel": titel, "beschreibung": str(auftrag.get("beschreibung") or "")[:200], "regel": regel}
    if regel == "farbe":
        for seite in ("links", "rechts"):
            werte = auftrag.get(seite) or []
            if not isinstance(werte, list) or not all(isinstance(w, str) for w in werte):
                return None, f"„{seite}“ ist eine Liste von Farben."
            out[seite] = [w.strip().lower()[:20] for w in werte][:10]
    elif regel == "turm":
        out["basis"] = str(auftrag.get("basis") or "")[:40]
        out["hoehe"] = max(2, min(TURM_HOECHSTENS, int(auftrag.get("hoehe") or TURM_HOECHSTENS)))
    elif regel == "schritte":
        schritte = auftrag.get("schritte")
        if not isinstance(schritte, list) or not schritte or len(schritte) > GROESSTE_LISTE:
            return None, f"„schritte“: 1 bis {GROESSTE_LISTE} Einträge mit ding und ziel."
        if not all(isinstance(s, dict) and s.get("ding") and s.get("ziel") for s in schritte):
            return None, "Jeder Schritt braucht „ding“ und „ziel“."
        out["schritte"] = [{"ding": str(s["ding"])[:40], "ziel": str(s["ziel"])[:40]} for s in schritte]
    return out, ""


def _farbe(name: str) -> str:
    w = name.split()[0].lower()
    return w[:-2] if w.endswith("er") else w                 # „roter Würfel“ → „rot“, „oranger Würfel“ → „orang“


def _obenauf_zuerst(dinge: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reihenfolge, in der sich Würfel nehmen lassen: wer etwas auf sich trägt, kommt später."""
    rest, out = list(dinge), []
    while rest:
        frei = [d for d in rest if not any(x.get("auf") == d["name"] for x in rest)]
        frei = frei or rest[:1]
        out.extend(frei)
        rest = [d for d in rest if d not in frei]
    return out


def planen(auftrag: dict[str, Any], wb: Any) -> tuple[list[tuple[str, str]], str]:
    """Schritte („greifen“, Ding) / („ablegen“, Ziel) für den jetzigen Stand – oder leere Liste mit Grund."""
    regel = auftrag["regel"]
    schritte: list[tuple[str, str]] = []
    if wb.haelt:                                       # erst loswerden, was er hält
        schritte.append(("ablegen", "platz"))
    if regel == "zurueck":
        for d in _obenauf_zuerst([d for d in wb.dinge if [d["x"], d["y"]] != d["start"] or d.get("in") or d.get("auf")]):
            if d["name"] != wb.haelt:
                schritte += [("greifen", d["name"]), ("ablegen", "platz")]
        return (schritte, "") if schritte else ([], "Alles liegt schon an seinem Platz.")
    if regel == "farbe":
        kisten = {k["name"].split()[0]: k["name"] for k in wb.kisten}          # „linke“, „rechte“
        ziel_fuer = {f: kisten.get("linke") for f in auftrag.get("links", [])}
        ziel_fuer.update({f: kisten.get("rechte") for f in auftrag.get("rechts", [])})
        for d in _obenauf_zuerst(list(wb.dinge)):
            ziel = next((z for f, z in ziel_fuer.items() if f.startswith(_farbe(d["name"]))), None)
            if ziel and d.get("in") != ziel:
                if d["name"] == wb.haelt:
                    schritte[0] = ("ablegen", ziel)
                else:
                    schritte += [("greifen", d["name"]), ("ablegen", ziel)]
        return (schritte, "") if schritte else ([], "Ist schon sortiert.")
    if regel == "turm":
        basis = wb.ding(auftrag.get("basis") or "") or next((d for d in wb.dinge if not d.get("in")), None)
        if basis is None:
            return [], "Kein Würfel für den Boden des Turms da."
        if basis.get("in") or basis.get("auf"):
            schritte += [("greifen", basis["name"]), ("ablegen", "platz")]
        oben = basis["name"]
        andere = _obenauf_zuerst([d for d in wb.dinge if d["name"] != basis["name"]])
        for d in andere[: int(auftrag.get("hoehe") or TURM_HOECHSTENS) - 1]:
            schritte += [("greifen", d["name"]), ("ablegen", "auf " + oben)]
            oben = d["name"]
        return schritte, ""
    return [x for s in auftrag["schritte"] for x in (("greifen", s["ding"]), ("ablegen", s["ziel"]))], ""
