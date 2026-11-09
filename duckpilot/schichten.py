"""Interner Schnitt der Suite Knowlin: welches Modul gehört zu welcher Schicht (seit 0.33).

duckpilot ist das Microduck-Modul von Knowlin. Damit später weitere Körper (Reachy Mini, „ohne Körper“) dazukommen
können, ist der Code in Schichten geschnitten – vorerst nur als Zuordnung und Import-Regeln, die Dateien bleiben,
wo sie sind (keine neuen Funktionen, alle Importe wie bisher):

- **Kern** = das Gehirn: Gespräch (Claude, lokales Modell, ohne Claude), Gedächtnis, Erfahrungsnetz, Stimme,
  Alltag, Personen, Handy-Kopplung, MCP. Weiß nichts über einen bestimmten Körper.
- **Motorik** = das Kleinhirn: Bewegungs-Engine (Sicherheit, Not-Aus, Warteschlange), Verhalten, Kopf ruhig,
  Gefühle und Leerlauf, das gemeinsame Körper-Interface (`api.py`). Kennt weder Gehirn noch einen bestimmten Körper.
- **Lab** = Knowlin Lab, die Trainingshalle: MuJoCo, Policies, Üben, Parcours, Akrobatik, Stoßreihe, Lernen am PC,
  Kaggle, Hugging Face. Nur für Module, die Bewegung lernen.
- **Körper** = das Microduck-Modul: Simulator, Physik-Körper, robotd, Pollens Robotermodell, Roboter-Pflege,
  Skill-Pakete der Microduck.
- **Basis** = Einstellungen, Hub-Zugriff, Hilfen ohne Fachwissen (dürfen alle benutzen).
- **Verbindung** = Server, Routen, Laufzeit (`server/runtime.py` mit den Bereichen `runtime_kern.py` und
  `runtime_lab.py`), Start – setzt alles zusammen und darf alles benutzen.

`REGELN` legt fest, welche Schicht welche nicht importieren darf; `tests/test_schichten.py` prüft das bei jedem
Testlauf. Neues Modul → hier eintragen.
"""

from __future__ import annotations

SCHICHTEN: dict[str, tuple[str, ...]] = {
    "basis": ("aio", "config", "settings", "desktop", "aktualisieren", "qr", "hub", "schichten", "geplant", "i18n", "suite", "figuren", "koerper"),
    "kern": (
        "brain", "buddy", "erfahrung_service", "voice", "faces", "augen", "nfc", "remote", "tailscale", "mdns",
        "mcp_server", "mcp_bridge", "skills.alltag", "choreo", "musik_struktur", "sichtungen", "knowlets", "knowlet_hub", "sicherungspunkte",
    ),
    "motorik": ("motion", "api", "joints", "protest", "laser", "koerper_pruefung"),
    "lab": (
        "physics", "training", "kaggle_training", "lernschleife", "mission", "acrobatics_service",
        "stossreihe_service", "kollision_service",
    ),
    "koerper": (
        "backends", "modell", "care", "vision", "skills.app_moves", "skills.gaits", "skills.talent", "skills.community",
        "skills.detector", "verbindungstest",
    ),
    "verbindung": ("__main__", "server", "skills"),
}

# Schicht → Schichten, die sie NICHT importieren darf.
REGELN: dict[str, frozenset[str]] = {
    "motorik": frozenset({"kern", "lab", "koerper"}),
    "kern": frozenset({"koerper"}),
    "lab": frozenset({"kern"}),          # Lab trainiert für einen Körper und darf dessen Modell kennen
    "koerper": frozenset({"kern"}),
}


def schicht_von(modul: str) -> str | None:
    """Schicht eines Moduls (`duckpilot.brain.agent` → „kern“); der längste passende Eintrag gewinnt."""
    name = modul.removeprefix("duckpilot").lstrip(".")
    best, best_len = None, -1
    for schicht, eintraege in SCHICHTEN.items():
        for e in eintraege:
            if (name == e or name.startswith(e + ".")) and len(e) > best_len:
                best, best_len = schicht, len(e)
    return best
