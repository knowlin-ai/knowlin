"""Verkörperungen von Knowlin (seit 0.38.3): jeder Körper hat seine eigene Verkörperung.

das Bild (5.11.2026): „Menschen sind ja auch verschieden in Sprache, Aussehen, Verhalten, können aber gleiches
Wissen und Umgebung haben.“ Deshalb:

- **Gemeinsam** (Knowlin): Wissen über die Umwelt (Personen, Dinge, Abläufe, Situationen), Umgebung (Orte,
  erkundeter Bereich), Alltag, Erlebnisse (Erfahrungsnetz, Protokoll).
- **Je Verkörperung**: Name, Aussehen, Stimme, Sprechweise, Persönlichkeit, Stimmung, Verhalten im Leerlauf, gelernte Tricks
  und wer sonst noch im Simulator herumläuft.

Die Einstellungen (`settings.json`) halten immer die Werte der Verkörperung, die gerade einen Körper hat – so liest der
übrige Code sie wie bisher. Die der anderen Verkörperungen liegen in `figuren.json` daneben und werden beim Wechsel getauscht.
Bisherige Einstellungen gehören Quacki (Microduck).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
VERSION = 3          # 2 = seit 0.38.6 (Reparatur geerbter Reachy-Profile), 3 = seit 0.38.10 (keine weiteren Enten)

# Was zur Verkörperung gehört (Einstellungsschlüssel) – alles andere ist gemeinsam oder gehört zum Gerät
# Seit 0.38.10 (Wunsch des Maintainers): Knowlin hat einen eigenen Grundcharakter (`grund_energie`, `grund_humor`; `emotions`
# gilt für alle). Seit Wunsch des Maintainers vom 5.11. wirkt er nur auf Knowlin selbst: Jede Verkörperung hat ihren eigenen
# Charakter (`energie`/`humor`, anfangs passend zum Körper verteilt, siehe `start`) – einzeln anpassbar in ihrem Körper
# oder als Punkt in Knowlins Feld – dazu die Eigenschaften ihrer Gestalt (`eigenschaften`, siehe `GESTALT`) und wie
# eigenständig sie sich ohne Befehle beschäftigt (`eigenstaendig`).
FIGUR_KEYS = ("duck_name", "wake_word", "energie", "humor", "eigenschaften", "idle_life", "eigenstaendig", "plaudern", "tts",
              "stimme_motor", "stimme_piper", "stimme_qwen", "qwen_qualitaet", "entenhaft", "entenlaute", "klang_hoehe",
              "klang_farbe", "weitere_enten", "model_style", "farbe")

# Verkörperungen je Körper (Modul): Name, Art, Gruß (i18n-Schlüssel) und womit eine neue Verkörperung beginnt. Charakter passend zum Körper
# (5.11.): Quacki lebhaft-verspielt, Reachy ruhig-neugierig, Odi tollpatschig-verspielt.
FIGUREN: dict[str, dict[str, Any]] = {
    "duckpilot": {"name": "Quacki", "art": "Microduck", "ente": True, "gruss": "gruss.duckpilot", "start": {
        "energie": 0.7, "humor": 0.45}},
    "reachy_mini": {"name": "Reachy", "art": "Reachy Mini", "ente": False, "gruss": "gruss.reachy_mini", "start": {
        "duck_name": "Reachy", "wake_word": "reachy", "energie": 0.3, "humor": 0.3,
        "entenhaft": 0.0, "entenlaute": "aus",                   # keine Ente: keine Entenstimme, keine Entenlaute
        "klang_hoehe": 0.0, "klang_farbe": 0.3, "stimme_piper": "thorsten", "stimme_qwen": "",
        "weitere_enten": 0,                                      # im Zimmer standardmäßig nur die eigene Art
    }},
    "open_duck_mini": {"name": "Odi", "art": "Open Duck Mini v2", "ente": True, "gruss": "gruss.open_duck_mini", "start": {
        "duck_name": "Odi", "wake_word": "odi", "energie": 0.5, "humor": 0.65,
        "entenhaft": 0.3, "entenlaute": "selten",                # eine Ente, aber eine größere, tiefere
        "klang_hoehe": -2.0, "klang_farbe": -0.2, "stimme_piper": "thorsten", "stimme_qwen": "",
        "weitere_enten": 0,
    }},
    # SO-101 (seit 0.38.47, Etappe G5): ein Arm – keine Ente, keine Entenlaute, eine ruhige Stimme
    "so101": {"name": "Ari", "art": "SO-101", "ente": False, "gruss": "gruss.so101", "start": {
        "duck_name": "Ari", "wake_word": "ari", "energie": 0.4, "humor": 0.35,
        "entenhaft": 0.0, "entenlaute": "aus", "klang_hoehe": 0.0, "klang_farbe": 0.2, "stimme_piper": "thorsten",
        "stimme_qwen": "", "weitere_enten": 0,
    }},
}


# Eigenschaften je Gestalt (seit 0.38.10): nur, was die Gestalt hat. Sie wirken über das Gehirn – die KI zeigt sie mit
# den Werkzeugen des Körpers. `standard` = bei einer neuen Verkörperung an.
GESTALT: dict[str, list[dict[str, Any]]] = {
    "duckpilot": [
        {"id": "schnabel", "name": "Schnabelklappern", "text": "klappert vor Freude oder Aufregung gern mit dem Schnabel",
         "standard": True},
        {"id": "watscheln", "name": "Watscheln", "text": "watschelt beim Gehen ein wenig mehr als nötig", "standard": True},
        {"id": "neugier", "name": "Neugieriges Umsehen", "text": "schaut sich neugierig nach Dingen im Raum um",
         "standard": True},
        {"id": "kuscheln", "name": "Anschmiegsam", "text": "sucht gern Nähe, wenn der Mensch traurig oder müde klingt",
         "standard": False},
    ],
    "reachy_mini": [
        {"id": "antennen", "name": "Antennenspiel", "text": "zeigt Stimmungen gern mit den Antennen", "standard": True},
        {"id": "zuhoeren", "name": "Kopf neigen beim Zuhören", "text": "neigt beim Zuhören den Kopf leicht zur Seite",
         "standard": True},
        {"id": "trocken", "name": "Trockener Humor", "text": "hat einen leisen, trockenen Humor", "standard": True},
        {"id": "beobachter", "name": "Aufmerksamer Beobachter", "text": "sagt, wenn ihm etwas auffällt",
         "standard": False},
    ],
    "open_duck_mini": [
        {"id": "tollpatsch", "name": "Tollpatschig", "text": "ist ein bisschen tollpatschig (nur gespielt, nie gefährlich)",
         "standard": True},
        {"id": "bastlerstolz", "name": "Bastlerstolz", "text": "erzählt gern, dass sie selbst gebaut ist", "standard": True},
        {"id": "antennen", "name": "Antennenspiel", "text": "zeigt Stimmungen gern mit den Antennen", "standard": False},
    ],
    "so101": [
        {"id": "winken", "name": "Winken", "text": "winkt zur Begrüßung gern mit dem ganzen Arm", "standard": True},
        {"id": "genau", "name": "Genau", "text": "arbeitet gern genau und ordentlich", "standard": True},
        {"id": "greifer", "name": "Greiferklappern", "text": "klappert vor Freude gern mit dem Greifer", "standard": False},
    ],
}


def gestalt_standard(modul: str) -> list[str]:
    return [e["id"] for e in GESTALT.get(modul, []) if e["standard"]]


def gestalt_text(modul: str, an: list[str] | tuple[str, ...] | None) -> str:
    """Die gewählten Eigenschaften als Satz fürs Gehirn – leer, wenn keine."""
    an = gestalt_standard(modul) if an is None else list(an)
    teile = [f"{e['name']} ({e['text']})" for e in GESTALT.get(modul, []) if e["id"] in an]
    return (f"- Eigenheiten deiner Gestalt – zeig sie ab und zu, passend zur Lage: {'; '.join(teile)}.\n"
            if teile else "")


def start_ergaenzen(modul: str, gesetzt: dict[str, Any]) -> dict[str, Any]:
    """Startwerte der Verkörperung, die in den Einstellungen fehlen (Prüfbefund 5.11.): Eine frische `settings.json` mit
    nur `modul = reachy_mini` hieß sonst „Quacki“ mit Weckwort „ente“ – die Grundwerte von `Config` gehören der
    Microduck. Nur, was der Mensch nicht selbst gesetzt hat; die Microduck braucht nichts (ihre Werte sind die Grundwerte)."""
    if modul == "duckpilot":
        return {}
    return {k: v for k, v in figur(modul)["start"].items() if k not in gesetzt}


def _aus_profil(modul: str) -> dict[str, Any] | None:
    """Verkörperung für einen Körper ohne eigenen Eintrag hier (Erweiterung, LeRobot – seit 0.38.35): Name aus seinem
    Profil, keine Ente, wenn er keine ist – vorher hieß jeder fremde Körper „Quacki“ mit Weckwort „ente“."""
    from . import koerper

    try:
        p = koerper.holen(modul)
    except KeyError:
        return None
    name = (p.name.split()[0] if p.name.split() else p.id)[:24]
    ente = p.familie == "ente"
    start: dict[str, Any] = {"duck_name": name, "wake_word": name.lower(), "energie": 0.5, "humor": 0.4, "weitere_enten": 0}
    if not ente:
        start.update({"entenhaft": 0.0, "entenlaute": "aus"})
    return {"name": name, "art": p.name, "ente": ente, "gruss": "gruss.allgemein", "start": start}


def figur(modul: str) -> dict[str, Any]:
    if modul in FIGUREN:
        return FIGUREN[modul]
    return _aus_profil(modul) or FIGUREN["duckpilot"]


def ist_ente(modul: str) -> bool:
    """Nur Enten quaken: Entenlaute, Entenfilter und Klangsignatur gibt es nur bei ihnen (seit 0.38.6 hart)."""
    return bool(figur(modul).get("ente", True))


class FigurenStore:
    """Profile der Verkörperungen, die gerade keinen Körper haben (`figuren.json` neben den Einstellungen)."""

    def __init__(self, root: Path) -> None:
        self.path = root / "figuren.json"

    def _lesen(self) -> dict[str, dict[str, Any]]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return {k: v for k, v in (raw.get("profile") or {}).items() if k in FIGUREN and isinstance(v, dict)}
        except (OSError, ValueError, AttributeError):
            return {}

    def _version(self) -> int:
        try:
            return int(json.loads(self.path.read_text(encoding="utf-8")).get("version", 1))
        except (OSError, ValueError, AttributeError, TypeError):
            return 0

    def _schreiben(self, profile: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": VERSION, "profile": profile}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def reparieren(self, aktiv_modul: str, jetzt: dict[str, Any]) -> dict[str, Any] | None:
        """Einmal beim Start (seit 0.38.6): Wer vor 0.38.3 schon Reachy Mini eingestellt hatte, dessen bisherige
        Einstellungen (Name, Entenlaute, weitere Enten …) landeten bei Reachy statt bei der Microduck-Verkörperung. Erkennbar
        an Entenlauten bei einer Verkörperung, die keine Ente ist. Dann bekommt die Microduck-Verkörperung diese Werte zurück (wenn sie
        noch keine eigenen hat) und die Nicht-Ente ihre Startwerte. Gibt die neuen Werte für die Einstellungen zurück,
        wenn sich die aktive Verkörperung ändert – sonst None."""
        version = self._version()
        if version >= VERSION:
            return None
        profile = self._lesen()
        neu_aktiv: dict[str, Any] | None = None
        for modul, f in (FIGUREN.items() if version < 2 else ()):
            if f.get("ente", True):
                continue
            werte = {k: jetzt[k] for k in FIGUR_KEYS if k in jetzt} if modul == aktiv_modul else profile.get(modul)
            if not werte or (werte.get("entenlaute", "aus") == "aus" and not werte.get("entenhaft")):
                continue
            quacki = jetzt if aktiv_modul == "duckpilot" else profile.get("duckpilot", {})
            if not quacki.get("duck_name") or quacki.get("duck_name") == FIGUREN["duckpilot"]["name"]:
                if aktiv_modul == "duckpilot":
                    neu_aktiv = {**(neu_aktiv or {}), **{k: v for k, v in werte.items() if k in FIGUR_KEYS}}
                else:
                    profile["duckpilot"] = {**profile.get("duckpilot", {}), **werte}
            start = dict(f["start"])
            if modul == aktiv_modul:
                neu_aktiv = start
            else:
                profile[modul] = start
            log.info("Verkörperung %s repariert: Werte der Ente zurück zur Microduck-Verkörperung", modul)
        # Version 3 (0.38.10, Hinweis aus dem Test): Standard sind keine weiteren Enten im Zimmer – auch alte Profile (z. B. „2
        # weitere“ aus der Zeit vor 0.38.3) einmalig auf 0; im Team lassen sie sich wieder dazuholen.
        for modul in FIGUREN:
            if modul == aktiv_modul:
                if (neu_aktiv or jetzt).get("weitere_enten"):
                    neu_aktiv = {**(neu_aktiv or {}), "weitere_enten": 0}
            elif profile.get(modul, {}).get("weitere_enten"):
                profile[modul] = {**profile[modul], "weitere_enten": 0}
        self._schreiben(profile)
        if neu_aktiv is None:
            return None
        from . import settings as S

        return S.validate({k: v for k, v in neu_aktiv.items() if k in FIGUR_KEYS})

    def profil(self, modul: str, aktiv: dict[str, Any] | None = None) -> dict[str, Any]:
        """Werte einer Verkörperung: die aktive aus `aktiv` (laufende Einstellungen), sonst gespeichert oder Startwerte."""
        if aktiv is not None:
            return {k: aktiv[k] for k in FIGUR_KEYS if k in aktiv}
        return {**figur(modul)["start"], **self._lesen().get(modul, {})}

    def wechsel(self, alt: str, neu: str, jetzt: dict[str, Any]) -> dict[str, Any]:
        """Körperwechsel: Werte der bisherigen Verkörperung sichern, die der neuen zurückgeben (für die Einstellungen)."""
        from . import settings as S

        profile = self._lesen()
        # Weitere Enten gelten nur für die Sitzung (seit 0.38.24, Fund „wieso startet die Microduck gleich wieder
        # mit mehreren Enten?“): Das Profil holte die alte Zahl beim Wechsel zurück – jetzt kommt jede Verkörperung allein.
        profile[alt] = {k: jetzt[k] for k in FIGUR_KEYS if k in jetzt and k != "weitere_enten"}
        neu_werte = {"eigenschaften": None, **figur(neu)["start"], **profile.pop(neu, {}), "weitere_enten": 0}
        if jetzt.get("stimme_motor") == "qwen" and not neu_werte.get("stimme_qwen") and "stimme_motor" not in neu_werte:
            neu_werte["stimme_motor"] = "piper"                # entworfene Stimmen gehören ihrer Verkörperung
        self._schreiben(profile)
        try:
            return S.validate({k: v for k, v in neu_werte.items() if k in FIGUR_KEYS})
        except ValueError as exc:                              # kaputtes Profil: lieber Startwerte als gar nichts
            log.warning("Profil von %s ungültig (%s) – Startwerte", neu, exc)
            return S.validate(dict(figur(neu)["start"]))

    def setze(self, modul: str, werte: dict[str, Any]) -> None:
        """Werte einer Verkörperung ohne Körper ändern (z. B. aus einem Knowlet, seit 0.38.5)."""
        profile = self._lesen()
        profile[modul] = {**{**figur(modul)["start"], **profile.get(modul, {})},
                          **{k: v for k, v in werte.items() if k in FIGUR_KEYS}}
        self._schreiben(profile)

    def alle(self, aktiv_modul: str, jetzt: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Name und Persönlichkeit aller Verkörperungen (für die Startseite)."""
        out = {}
        for modul, f in FIGUREN.items():
            p = self.profil(modul, jetzt if modul == aktiv_modul else None)
            out[modul] = {"name": p.get("duck_name") or f["name"], "art": f["art"], "energie": p.get("energie", 0.5),
                          "humor": p.get("humor", 0.25), "aktiv": modul == aktiv_modul}
        return out
