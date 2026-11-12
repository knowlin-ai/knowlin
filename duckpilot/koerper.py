"""Die Körperschnittstelle von Knowlin (Version 1.0, seit 0.38.35): ein Kopf, viele Körper.

Knowlin trennt das Gehirn (Gedächtnis, Charakter, Gespräch, Raumwissen) vom Körper. Ein Körper ist alles, was das
Gehirn bewegen kann – ein Simulator, ein echter Roboter, ein Roboter aus einem anderen Ökosystem (LeRobot). Damit ein
neuer Körper dazukommen kann, ohne dass der Kern angefasst wird, beschreibt sich jeder Körper mit einem **Profil**:

- wer er ist (`id`, `name`, `hersteller`, `familie`),
- was er kann – aus einem festen **Wortschatz** (`FAEHIGKEITEN`, Erweiterungen mit `x-`),
- wie er gebaut wird (`fabrik`: „modul:funktion“ oder eine Funktion, bekommt die Einstellungen).

Das Laufzeit-Objekt eines Körpers ist ein `duckpilot.api.DuckBackend` (Vokabular wie Pollens robotd, Einheiten nach
ROS REP-103: Meter, Sekunden, Radiant; x vorwärts, y links). Die **Sicherheitspflichten** (Not-Aus = stromlos, Stopp
hält an, Grenzen, stromlos bewegt sich nichts) prüft `duckpilot.koerper_pruefung` – jeder kann sie für seinen Körper
laufen lassen: `python -m duckpilot.koerper_pruefung <id>`.

Fremde Körper kommen als eigenes Python-Paket mit einem Entry Point in der Gruppe `knowlin.koerper`, der ein `Koerper`
(oder eine Funktion, die eines liefert) zeigt – wie Pollens Reachy-Mini-Apps (`reachy_mini_apps`). Knowlin installiert
solche Pakete nie selbst; Knowlets enthalten nie Code. Spezifikation: `docs/koerper-schnittstelle.md`.

Diese Datei gehört zur Basis: Sie importiert keinen Körper, Fabriken werden erst beim Bauen geladen.
"""

from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

SCHNITTSTELLE = "1.0"
ENTRY_POINT_GRUPPE = "knowlin.koerper"

# ── Wortschatz ───────────────────────────────────────────────────────────────
# Was ein Körper kann. Das Gehirn prüft damit Vorbedingungen („braucht Beine“), die Oberfläche blendet danach aus.
# Neue Wörter nur mit Bedeutung und Pflicht; eigene Erweiterungen eines Herstellers beginnen mit „x-“.
FAEHIGKEITEN: dict[str, str] = {
    "beine": "Läuft auf Beinen: move(Twist) bewegt den Körper; meldet fallen und picked_up im Zustand.",
    "raeder": "Fährt auf Rädern oder Rollen: move(Twist) bewegt den Körper.",
    "kopf": "Richtet Kopf und Blick aus: head(Head), look(x, y, z).",
    "koerperdrehung": "Dreht den Körper auf der Stelle, ohne sich fortzubewegen (move mit nur vyaw).",
    "schnabel": "Schnabel öffnen und schließen: mouth(0…1); greift kleine Dinge (do('ground_pick')).",
    "arm": "Arm mit Gelenken: haltung(gelenke, sekunden) fährt eine Haltung an und hält sie.",
    "greifer": "Greifer am Arm: Gelenk 'greifer' in haltung(), 0 = zu, 1 = offen.",
    "antennen": "Antennen als Ausdruck (Reachy Mini, Open Duck Mini).",
    "augen_leds": "Leuchtende Augen als Ausdruck (Open Duck Mini, je nach Bau).",
    "stimmbank": "Eigene Laute im Körper: sound(tag) mit den Ton-Tags aus api.SOUND_TAGS.",
    "tiefensensor": "Tiefensensor: state().perception mit tof_mm und points.",
    "kamera": "Kamera am Körper (Bild für Erkennen und Beschreiben, nie gespeichert).",
    "mikrofon": "Mikrofon am Körper.",
    "lautsprecher": "Lautsprecher am Körper.",
    "pollen_bewegungen": "Pollens Bewegungsbibliothek (Emotionen und Tänze des Reachy Mini).",
}
# Kurz in Worten, für Sätze an die KI („Dein Körper kann: laufen, sehen …“)
KURZ: dict[str, str] = {
    "beine": "laufen", "raeder": "fahren", "kopf": "Kopf und Blick bewegen", "koerperdrehung": "sich auf der Stelle drehen",
    "schnabel": "mit dem Schnabel greifen", "arm": "einen Arm bewegen", "greifer": "greifen", "antennen": "Antennen bewegen",
    "augen_leds": "die Augen leuchten lassen", "stimmbank": "eigene Laute", "tiefensensor": "Abstände messen",
    "kamera": "sehen", "mikrofon": "hören", "lautsprecher": "Töne ausgeben", "pollen_bewegungen": "Pollens Bewegungen abspielen",
}
assert KURZ.keys() == FAEHIGKEITEN.keys()
# Wie der Körper gerade betrieben wird – kommt zur Laufzeit dazu, steht nicht im Profil.
BETRIEB: dict[str, str] = {
    "simulator": "Simulierter Körper – nichts kann kaputtgehen.",
    "zuruecksetzen": "Die Szene lässt sich zurücksetzen (nur Simulator).",
    "physik": "Simulator mit echter Physik (MuJoCo).",
    "policies": "Führt gelernte Policies aus (do(skill) mit Policies vom Hub).",
}
FAMILIEN = ("ente", "stationaer", "fahrend", "arm", "vierbeiner", "humanoid", "andere")
FORTBEWEGUNG = frozenset({"beine", "raeder"})

_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


def wort_gueltig(w: str) -> bool:
    return w in FAEHIGKEITEN or w in BETRIEB or bool(re.fullmatch(r"x-[a-z0-9][a-z0-9_-]{0,39}", w))


@dataclass(frozen=True)
class Koerper:
    """Profil eines Körpers. `id` ist der Wert der Einstellung `modul` und bleibt für immer gleich (gespeichert)."""

    id: str
    name: str
    hersteller: str
    familie: str
    faehigkeiten: frozenset[str]
    fabrik: str | Callable[[Any], Any] = field(compare=False, repr=False)
    zustand: str = ""                       # DuckState.koerper, den der Körper meldet (Standard: id)
    skills: tuple[str, ...] = ()            # gelernte Bewegungen, die er ohne Zusatz kann (do(skill))
    echt: str = ""                          # wie der echte Roboter angebunden ist; leer = nur Simulator
    simulator: bool = True                  # gibt es einen Simulator für ihn?
    quelle: str = ""                        # Projektseite (https)
    lizenz: str = ""                        # Lizenz des Körper-Moduls
    schnittstelle: str = SCHNITTSTELLE
    eingebaut: bool = False                 # gehört zu Knowlin selbst (sonst Erweiterung aus einem Paket)
    lab: bool = False                       # hat eine Trainingshalle (Policies vom Hub, Parcours, Training, Akrobatik)

    @property
    def koerper_zustand(self) -> str:
        return self.zustand or self.id

    def fehler(self) -> list[str]:
        """Was am Profil nicht stimmt (leer = gültig)."""
        f = []
        if not _ID.match(self.id):
            f.append(f"id „{self.id}“: 2–40 Zeichen, a–z, 0–9, _; beginnt mit einem Buchstaben")
        if not self.name.strip():
            f.append("name fehlt")
        if self.familie not in FAMILIEN:
            f.append(f"familie „{self.familie}“: erlaubt sind {', '.join(FAMILIEN)}")
        unbekannt = sorted(w for w in self.faehigkeiten if not (w in FAEHIGKEITEN or w.startswith("x-")) or not wort_gueltig(w))
        if unbekannt:
            f.append(f"unbekannte Fähigkeiten: {', '.join(unbekannt)} (eigene mit „x-“)")
        if self.schnittstelle.split(".")[0] != SCHNITTSTELLE.split(".")[0]:
            f.append(f"Schnittstelle {self.schnittstelle} passt nicht zu {SCHNITTSTELLE}")
        if not (callable(self.fabrik) or (isinstance(self.fabrik, str) and ":" in self.fabrik)):
            f.append("fabrik: „modul:funktion“ oder eine Funktion")
        if self.quelle and not self.quelle.startswith("https://"):
            f.append("quelle: nur https")
        return f

    def bauen(self, cfg: Any) -> Any:
        """Den Körper bauen (ein DuckBackend). Die Fabrik bekommt die Einstellungen."""
        fab = self.fabrik
        if isinstance(fab, str):
            modul, _, name = fab.partition(":")
            fab = getattr(importlib.import_module(modul), name)
        return fab(cfg)

    def als_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "hersteller": self.hersteller, "familie": self.familie,
                "faehigkeiten": sorted(self.faehigkeiten), "skills": list(self.skills), "echt": self.echt,
                "simulator": self.simulator, "quelle": self.quelle, "lizenz": self.lizenz,
                "schnittstelle": self.schnittstelle, "eingebaut": self.eingebaut, "zustand": self.koerper_zustand,
                "lab": self.lab}


# ── Die Körper, die Knowlin mitbringt ────────────────────────────────────────
EINGEBAUT: tuple[Koerper, ...] = (
    Koerper("duckpilot", "Microduck", "Pollen Robotics / Hugging Face", "ente",
            frozenset({"beine", "kopf", "schnabel", "tiefensensor", "stimmbank", "kamera"}),
            "duckpilot.backends:baue_microduck", zustand="microduck",
            skills=("sit_toggle", "ground_pick", "kick_left", "kick_right", "roulade"),
            echt="Pollens robotd (JSON-RPC)", quelle="https://github.com/pollen-robotics/microduck",
            lizenz="Apache-2.0", eingebaut=True, lab=True),
    Koerper("reachy_mini", "Reachy Mini", "Pollen Robotics / Hugging Face", "stationaer",
            frozenset({"kopf", "antennen", "koerperdrehung", "kamera", "mikrofon", "lautsprecher", "pollen_bewegungen"}),
            "duckpilot.backends:baue_reachy_mini", echt="Pollens Daemon (HTTP)",
            quelle="https://github.com/pollen-robotics/reachy_mini", lizenz="Apache-2.0", eingebaut=True),
    Koerper("open_duck_mini", "Open Duck Mini v2", "Open-Source-Selbstbau (apirrone)", "ente",
            frozenset({"beine", "kopf", "antennen", "stimmbank", "kamera", "mikrofon", "lautsprecher", "augen_leds"}),
            "duckpilot.backends:baue_open_duck", skills=("sit_toggle", "kick_left", "kick_right"),
            quelle="https://github.com/apirrone/Open_Duck_Mini", lizenz="Apache-2.0", eingebaut=True),
    Koerper("so101", "SO-101", "TheRobotStudio / Hugging Face (LeRobot)", "arm",
            frozenset({"arm", "greifer"}),
            "duckpilot.backends:baue_so101",
            echt="LeRobot so101_follower (Robot.connect / send_action)",
            quelle="https://github.com/TheRobotStudio/SO-ARM100", lizenz="Apache-2.0", eingebaut=True),
    Koerper("lerobot", "LeRobot-Roboter", "Hugging Face LeRobot (SO-101, LeKiwi, Koch …)", "arm",
            frozenset({"arm", "greifer", "raeder", "kamera"}),
            "duckpilot.backends.lerobot:baue_lerobot", zustand="lerobot",
            echt="LeRobot (Robot.connect / get_observation / send_action)", simulator=False,
            quelle="https://github.com/huggingface/lerobot", lizenz="Apache-2.0", eingebaut=True),
)

_REGISTER: dict[str, Koerper] = {k.id: k for k in EINGEBAUT}
_ERWEITERUNGEN_GELADEN = False
_ABGELEHNT: dict[str, str] = {}             # Erweiterung → Grund (für die Oberfläche und die Prüfung)


def registrieren(k: Koerper) -> None:
    """Einen Körper aufnehmen. Eingebaute gewinnen immer; ungültige Profile werden abgelehnt (mit Grund)."""
    f = k.fehler()
    if f:
        raise ValueError(f"Körper „{k.id}“: " + "; ".join(f))
    alt = _REGISTER.get(k.id)
    if alt is not None and alt.eingebaut and not k.eingebaut:
        raise ValueError(f"Körper „{k.id}“ gibt es schon in Knowlin – bitte eine eigene id wählen")
    _REGISTER[k.id] = k


def erweiterungen_laden(eintraege: Any = None) -> dict[str, str]:
    """Körper aus installierten Paketen (Entry Points `knowlin.koerper`) aufnehmen – einmal je Lauf. Ein kaputtes Paket
    darf Knowlin nicht stören: Fehler landen in `abgelehnt()`."""
    global _ERWEITERUNGEN_GELADEN
    if _ERWEITERUNGEN_GELADEN and eintraege is None:
        return dict(_ABGELEHNT)
    _ERWEITERUNGEN_GELADEN = True
    if eintraege is None:
        try:
            from importlib.metadata import entry_points

            eintraege = entry_points(group=ENTRY_POINT_GRUPPE)
        except Exception as exc:  # noqa: BLE001 – kaputte Paket-Metadaten
            log.warning("Körper-Erweiterungen nicht lesbar: %s", exc)
            return {}
    for ep in eintraege:
        name = getattr(ep, "name", "?")
        try:
            obj = ep.load()
            k = obj() if callable(obj) and not isinstance(obj, Koerper) else obj
            if not isinstance(k, Koerper):
                raise TypeError("liefert kein Koerper-Profil")
            registrieren(Koerper(**{**k.__dict__, "eingebaut": False}))
        except Exception as exc:  # noqa: BLE001
            _ABGELEHNT[name] = f"{type(exc).__name__}: {exc}"
            log.warning("Körper-Erweiterung „%s“ abgelehnt: %s", name, exc)
    return dict(_ABGELEHNT)


def alle() -> list[Koerper]:
    erweiterungen_laden()
    return list(_REGISTER.values())


def ids() -> tuple[str, ...]:
    return tuple(k.id for k in alle())


def holen(kid: str) -> Koerper:
    erweiterungen_laden()
    k = _REGISTER.get(kid)
    if k is None:
        raise KeyError(f"Unbekannter Körper „{kid}“ – bekannt: {', '.join(sorted(_REGISTER))}")
    return k


def zu_zustand(zustand: str) -> Koerper | None:
    """Das Profil zu dem, was ein Körper als `state().koerper` bzw. `koerper_art` meldet."""
    return next((k for k in alle() if k.koerper_zustand == zustand), None)


def abgelehnt() -> dict[str, str]:
    erweiterungen_laden()
    return dict(_ABGELEHNT)


def wortschatz() -> dict[str, Any]:
    return {"schnittstelle": SCHNITTSTELLE, "faehigkeiten": FAEHIGKEITEN, "betrieb": BETRIEB, "familien": list(FAMILIEN),
            "entry_point": ENTRY_POINT_GRUPPE}


def _zuruecksetzen_fuer_tests() -> None:
    global _ERWEITERUNGEN_GELADEN
    _REGISTER.clear()
    _REGISTER.update({k.id: k for k in EINGEBAUT})
    _ABGELEHNT.clear()
    _ERWEITERUNGEN_GELADEN = False
