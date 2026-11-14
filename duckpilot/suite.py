"""Die Suite Knowlin (seit 0.38): Module für die Startseite.

Wunsch des Maintainers (4.11.2026): „Die Suite hat dann so wie Adobe einen Launcher unter dem Namen Knowlin, wo duckpilot drin
ist, und später die anderen“ – „merke schon die anderen Anwendungen vor, nicht direkt in duckpilot starten“.

Anders als bei Adobe sind die Module keine eigenen Programme: Der Kern (Gedächtnis, Charakter, Stimme, Alltag) gehört
allen Körpern („one mind, many bodies“). Eine Modul-Verknüpfung öffnet deshalb nur eine Ansicht auf einen Körper im
selben laufenden Knowlin. Geplante Module stehen ehrlich als „geplant“ da – nichts davon ist anklickbar, das nicht geht.
Öffentlich lesbar; die Versionen werden bei jedem Release mit dem Releaseplan abgeglichen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

FIGUREN_BILDER = Path(__file__).resolve().parent / "server" / "static" / "figuren"
BILD_DATEI = {"duckpilot": "microduck.png", "reachy-mini": "reachy-mini.png", "open-duck-mini": "open-duck-mini.png",
              "so101": "so101.png", "stackchan": "stackchan.png", "bittle": "bittle.png"}


def eigenes_portraet(kid: str) -> Path:
    """Auf diesem PC gerendertes Porträt (seit 0.38.51, `routes/portraet.py`)."""
    from .settings import data_dir

    return data_dir() / "portraets" / f"{kid}.png"


def portraet_pfad(kid: str) -> Path | None:
    """Mitgeliefertes Porträt vor dem hier gerenderten; None, wenn es noch keins gibt."""
    if kid not in BILD_DATEI:
        return None
    for p in (FIGUREN_BILDER / BILD_DATEI[kid], eigenes_portraet(kid)):
        if p.is_file():
            return p
    return None

# id, Name, Körper, Stand („fertig“ | „geplant“ | „anleitung“), Version, ein Satz
MODULE: tuple[tuple[str, str, str, str, str, str], ...] = (
    ("duckpilot", "duckpilot", "von Pollen Robotics und Hugging Face", "fertig", "",
     "Steuern, Tricks, Tanzen, Team, Training – im Simulator, in der Physik und am echten Roboter."),
    ("reachy-mini", "Reachy Mini", "Desktop-Roboter von Pollen Robotics und Hugging Face", "fertig", "",
     "Pollens Originalmodell, Emotionen und Tänze, zuhören und mitsprechen – im Simulator; echter Reachy über Pollens Daemon (ungetestet)."),
    ("open-duck-mini", "Open Duck Mini", "offener Selbstbau-Vorgänger (Antoine Pirrone)", "fertig", "",
     "Laufen, Kopf und Antennen im Simulator, mit dem offenen 3D-Modell; Ausstattung je Bau. Echte Open Duck geplant."),
    # seit 0.38.51: Ari bekommt seine Kachel (Fund 12.11.: der Arm war nur über Einstellungen → Körper zu finden)
    ("so101", "SO-101", "offener Roboterarm (TheRobotStudio, LeRobot)", "fertig", "",
     "Greifen und Räumen an der eigenen Werkbank im Simulator, mit dem offenen 3D-Modell; echter Arm über LeRobot "
     "(ungetestet)."),
    # seit 0.38.58: Stack-chan, der günstigste Körper mit Gesicht (Maintainer: „Ok mach“ auf den Vorschlag StackChan)
    ("stackchan", "Stack-chan", "offener Schreibtisch-Roboter (Community, M5Stack)", "fertig", "",
     "Ein Kopf mit Gesicht: dreht und nickt, zeigt Gefühle mit Augen und Mund und spricht – im Simulator; echter "
     "Stack-chan geplant."),
    # seit 0.38.59: Bittle X, ein Roboterhund (Maintainer: „Ok mach“ – erst StackChan, dann Bittle X)
    ("bittle", "Bittle X", "offener Roboterhund (Petoi, OpenCat)", "fertig", "",
     "Ein Hund auf vier Beinen: läuft, dreht sich, sitzt und schaut sich um – im Simulator; echter Bittle über Petois "
     "serielles Protokoll geplant."),
    ("knowlets", "Knowlets", "Verkörperungen, Tricks und Tänze teilen", "fertig", "",
     "Charakter, Tricks und Tänze als Paket speichern, auf Hugging Face teilen und laden – nur Daten, nie Personen."),
    ("lab", "Knowlin Lab", "Trainingshalle für Module, die Bewegung lernen", "geplant", "Januar",
     "Training, Parcours und Policies als eigener Bereich – heute bei der Microduck unter Lernen."),
    # seit 0.38.55 „Mentor“ statt „Ohne Körper“ (Maintainer: Knowlin ist über Tailscale und Sprachchat ohnehin überall –
    # neu ist, dass der Mensch der Körper und Lehrer ist; Konzept „Mentor – Lernen durch Zuschauen“)
    ("mentor", "Mentor", "Du zeigst, Knowlin lernt – mit Handy, Webcam oder Brille", "geplant", "0.44",
     "Mach Bewegungen und Abläufe vor, zeig Dinge und Orte – Knowlin lernt durch Zuschauen."),
    ("eigenes-modul", "Eigenes Modul", "für die Community", "anleitung", "",
     "Körperschnittstelle 1.0: Vorlage und Prüfung – ein weiterer Roboter bekommt Knowlin als eigenes Paket."),
)

# Was alle Verkörperungen teilen (seit 0.38.3): (Name, Ansicht, Abschnitt). Charakter gehört der Verkörperung, nicht hierher.
KERN: tuple[tuple[str, str, str], ...] = (
    ("Wissen über die Umwelt", "memory", ""), ("Umgebung", "umgebung", ""), ("Alltag", "alltag", ""),
    ("Einstellungen", "settings", ""),
)

# Jeder Körper hat seine Verkörperung (seit 0.38.3): Name des Körpers auf der Kachel, und ob es überhaupt ein Körper ist
# (Lab und „Eigenes Modul“ sind Werkzeuge, keine Körper)
KOERPER_NAME = {"duckpilot": "Microduck", "reachy-mini": "Reachy Mini", "open-duck-mini": "Open Duck Mini v2",
                "so101": "SO-101", "stackchan": "Stack-chan", "bittle": "Bittle X", "mentor": "Mentor"}

# Werkzeug-Kacheln, die eine Seite in Knowlin öffnen (seit 0.38.5)
ANSICHT = {"knowlets": "knowlets"}

# Modul-Kachel → Einstellung `modul` (welcher Körper dranhängt); seit 0.38.1 auch Reachy Mini
KOERPER_MODUL = {"duckpilot": "duckpilot", "reachy-mini": "reachy_mini", "open-duck-mini": "open_duck_mini",
                 "so101": "so101", "stackchan": "stackchan", "bittle": "bittle"}


def module(koerper: str = "", aktiv: str = "duckpilot") -> list[dict[str, Any]]:
    """Kacheln der Startseite; `koerper`: woran der Körper gerade hängt (sim, physik, robotd), `aktiv`: Einstellung
    `modul`. Nur das aktive Modul ist „verbunden“, die anderen fertigen lassen sich mit „Öffnen“ umschalten."""
    out = []
    for mid, name, art, stand, version, satz in MODULE:
        m = {"id": mid, "name": name, "koerper": art, "stand": stand, "version": version, "kurz": satz,
             "art": "koerper" if mid in KOERPER_NAME else "werkzeug", "koerper_name": KOERPER_NAME.get(mid, name)}
        if mid in BILD_DATEI:                   # Porträt mitgeliefert oder hier gerendert (seit 0.38.51); sonst rendert die Startseite
            m["bild"] = portraet_pfad(mid) is not None
        if mid in ANSICHT:
            m["ansicht"] = ANSICHT[mid]
        if mid in KOERPER_MODUL:
            m["modul"] = KOERPER_MODUL[mid]
            m["aktiv"] = KOERPER_MODUL[mid] == aktiv
        if m.get("aktiv") and koerper:
            m["verbunden"] = {"sim": "Simulator", "physik": "Physik-Simulator", "robotd": "echter Roboter"}.get(koerper, koerper)
        out.append(m)
    # Körper aus Erweiterungen (Körperschnittstelle, seit 0.38.35): je ein Modul vor den Werkzeugen
    from . import koerper as K

    for k in K.alle():
        if k.eingebaut:
            continue
        m = {"id": k.id, "name": k.name, "koerper": k.hersteller, "stand": "fertig" if k.simulator else "anleitung",
             "version": "", "kurz": f"Erweiterung (Paket) · {', '.join(sorted(k.faehigkeiten))}", "art": "koerper",
             "koerper_name": k.name, "modul": k.id, "aktiv": k.id == aktiv, "erweiterung": True}
        if m["aktiv"] and koerper:
            m["verbunden"] = {"sim": "Simulator", "physik": "Physik-Simulator", "robotd": "echter Roboter"}.get(koerper, koerper)
        out.insert(len(KOERPER_MODUL), m)
    return out


def kern() -> list[dict[str, str]]:
    return [{"name": n, "ansicht": v, "teil": t} for n, v, t in KERN]
