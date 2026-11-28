"""Ein Kopf, viele Körper (seit 0.56): was alle Verkörperungen gemeinsam wissen – und was eine von der anderen übernimmt.

Knowlins Gedächtnis (`memory.py`) ist schon eins für alle: Wissen, Vorlieben und Orte teilen sich alle Verkörperungen,
jeder Eintrag merkt sich, wo er gelernt wurde (`von`: „<modul>:sim|echt“ oder „kopf“). Nur Tricks gehören der
Verkörperung, weil sie aus Gelenkstellungen bestehen. Diese Datei macht das sichtbar und nutzbar:

* `uebersicht()` – was geteilt ist (mit Herkunft je Verkörperung), welche Orte in welchem Zimmer gelten (Simulator
  oder echter Roboter) und welche Tricks die anderen kennen – übertragbar nur innerhalb derselben Familie (Microduck,
  WonderDuck und Open Duck sind alle „ente“ mit denselben Gelenknamen; ein Kopf-Trick passt nicht auf einen Arm).
* `trick_uebernehmen()` – kopiert einen Trick einer anderen Verkörperung derselben Familie in die eigenen Tricks, mit
  Vermerk, woher er kommt. Das Original bleibt bei der anderen.

So fängt ein zweiter Roboter nicht bei null an: Wondi kennt dein Zuhause, deine Vorlieben und – auf Wunsch – Quackis
Tricks. Alles bleibt auf diesem PC.
"""

from __future__ import annotations

import copy
from typing import Any

from .. import figuren, koerper
from .memory import Memory, clean_name


def _name(modul: str) -> str:
    return str(figuren.figur(modul).get("name") or modul)


def _familie(modul: str) -> str | None:
    k = next((p for p in koerper.alle() if p.id == modul), None)
    return getattr(k, "familie", None)


def _herkunft(eintraege: list[dict[str, Any]]) -> dict[str, int]:
    """Wie viele Einträge wo gelernt wurden – nach Verkörperung (Name), „Knowlin“ für den Kopf, „früher“ ohne Angabe."""
    out: dict[str, int] = {}
    for e in eintraege:
        von = str(e.get("von") or "")
        wer = "Knowlin" if von == "kopf" else (_name(von.split(":")[0]) if von else "früher")
        out[wer] = out.get(wer, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _tricks_je_figur(mem: Memory) -> dict[str, dict[str, Any]]:
    je = dict(mem.data.get("tricks_je_figur") or {})
    je[mem.figur] = mem.data.get("tricks") or {}
    return je


def uebersicht(mem: Memory, aktuell: str) -> dict[str, Any]:
    orte = mem.data.get("orte") or {}
    zimmer: dict[str, int] = {}
    for p in orte.values():
        z = "echt" if p.get("koerper") in ("robotd", "echt") else "simulator"
        zimmer[z] = zimmer.get(z, 0) + 1
    fam = _familie(aktuell)
    andere = []
    for modul, tricks in _tricks_je_figur(mem).items():
        if modul == aktuell or not tricks:
            continue
        passt = fam is not None and _familie(modul) == fam
        eigene = set((mem.data.get("tricks") or {}) if mem.figur == aktuell else {})
        andere.append({"modul": modul, "name": _name(modul), "art": figuren.figur(modul).get("art", modul),
                       "passt": passt,
                       "tricks": [{"name": n, "schon_da": n in eigene} for n in sorted(tricks)]})
    return {
        "ok": True, "aktuell": {"modul": aktuell, "name": _name(aktuell), "familie": fam},
        "geteilt": {
            "wissen": {"anzahl": len(mem.data.get("wissen") or []), "von": _herkunft(mem.data.get("wissen") or [])},
            "vorlieben": {"anzahl": len(mem.data.get("vorlieben") or []),
                          "von": _herkunft(mem.data.get("vorlieben") or [])},
            "orte": {"anzahl": len(orte), "zimmer": zimmer},
        },
        "andere": sorted(andere, key=lambda a: (not a["passt"], a["name"])),
    }


def trick_uebernehmen(mem: Memory, aktuell: str, von: str, name: str) -> str:
    """Trick `name` der Verkörperung `von` in die eigenen Tricks kopieren. Wirft ValueError mit einem Satz für Menschen."""
    if von == aktuell:
        raise ValueError("Den Trick kennt sie schon.")
    if mem.figur != aktuell:
        raise ValueError("Erst diese Verkörperung wecken.")
    if _familie(von) is None or _familie(von) != _familie(aktuell):
        raise ValueError(f"{_name(von)} hat einen anderen Körper – der Trick passt nicht auf {_name(aktuell)}.")
    tricks = _tricks_je_figur(mem).get(von) or {}
    t = tricks.get(name)
    if not t or not t.get("keyframes"):
        raise ValueError("Diesen Trick gibt es nicht (mehr).")
    neu = clean_name(name)
    if neu in (mem.data.get("tricks") or {}):
        raise ValueError(f"{_name(aktuell)} kennt schon einen Trick „{neu}“.")
    beschreibung = (str(t.get("beschreibung") or "").strip() + f" (von {_name(von)} übernommen)").strip()
    key = mem.remember_trick(neu, copy.deepcopy(t["keyframes"]), int(t.get("loops") or 1), beschreibung[:200])
    mem.data["tricks"][key]["uebernommen_von"] = von
    mem.save()
    return key
