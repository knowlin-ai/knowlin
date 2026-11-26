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
# 26.11.2026: Hiwonders WonderDuck (Shenzhen, 599,99 $, Auslieferung ab 7.12.2026) – ihre Software baut auf Pollens
# Microduck auf (github.com/Hiwonder/wonderduck, Apache-2.0, Protokoll 62, dieselben 15 Gelenke und Sockets). Im
# Simulator geht das ohne Gerät; ihr 3D-Modell steht unter CC BY-NC-SA und wird wie Pollens erst beim Start geladen.
GEPLANT: tuple[tuple[str, str, str], ...] = (
    ("ab Lieferung", "Echte Microduck", "Inbetriebnahme mit Trockenlauf, digitaler Zwilling mit Frühwarnung."),
    ("ab Lieferung", "Echte WonderDuck", "Hiwonders Software baut auf Pollens auf – Knowlin spricht sie über denselben Weg wie die Microduck."),
    ("ab Lieferung", "Ari mit LeRobot", "Mit einem zweiten Arm steuern und fertige Policies laden, sobald ein SO-101 da ist."),
    ("ab Lieferung", "Rollen und Polaroid am Gerät", "Pollens Rollschuh-Policies auf der echten Microduck und das Polaroid über NFC."),
)


def liste() -> list[dict[str, Any]]:
    return [{"version": v, "name": n, "kurz": k} for v, n, k in GEPLANT]
