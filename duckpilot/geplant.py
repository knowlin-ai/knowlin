"""Was als Nächstes kommt – als Kacheln unter System → Erweiterungen (seit 0.33).

Wunsch des Maintainers (30.10.2026): „Trage geplante Funktionen auch schon bei den Erweiterungen ein – nicht, weil man sie
dort aktivieren kann, sondern als geplant, als Kachel, damit man schon eine Vorstellung davon bekommt (am besten mit
Releasezahl).“

Die Liste wird hier im Code gepflegt und bei jedem Release mit dem Releaseplan des Projekts abgeglichen: Was ausgeliefert ist, fliegt raus; Versionen, die sich verschieben, werden angepasst.
Nur was ohne echten Roboter geht, steht mit Versionsnummer da; was die Ente braucht, trägt „ab Lieferung“.
Öffentlich lesbar – keine persönlichen Daten, keine Termine des Maintainers.
"""

from __future__ import annotations

from typing import Any

# (Version, Name, ein Satz). Reihenfolge = Reihenfolge der Kacheln. Neu geordnet am 15.11.2026 (Maintainer: „Mischung je
# Release“ – je Release ein Thema für den Kopf und eins für einen Körper; echte Roboter erst ab Lieferung).
GEPLANT: tuple[tuple[str, str, str], ...] = (
    ("0.46", "Rundgang und Licht", "Eine Runde mit Meldung aufs Handy, Licht folgt dem Roboter von Raum zu Raum – im Simulator."),
    ("ab Lieferung", "Ari mit LeRobot", "Mit einem zweiten Arm steuern und fertige Policies laden, sobald ein SO-101 da ist."),
    ("ab Lieferung", "Echte Microduck", "Inbetriebnahme mit Trockenlauf, digitaler Zwilling mit Frühwarnung."),
    ("ab Lieferung", "Zubehör der Microduck", "Rollschuh-Gangarten und das NFC-Polaroid, sobald Pollen liefert."),
)


def liste() -> list[dict[str, Any]]:
    return [{"version": v, "name": n, "kurz": k} for v, n, k in GEPLANT]
