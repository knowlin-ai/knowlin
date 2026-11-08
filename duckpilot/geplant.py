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

# (Version, Name, ein Satz). Reihenfolge = Reihenfolge der Kacheln.
GEPLANT: tuple[tuple[str, str, str], ...] = (
    ("0.39", "Rollen und Polaroid", "Pollens Zubehör für die Microduck: Rollschuh-Gangarten und das NFC-Polaroid."),
    ("0.39", "Hoverboard und NFC-Hüte", "Reachy Mini fährt mit Pollens Hoverboard, Hüte wechseln die Persönlichkeit."),
    ("0.40", "Erfahrungsnetz 2", "Weltmodell und Selbstbild – Knowlin erinnert sich an mehr und lernt aus Erlebnissen."),
    ("0.41", "Natürlicher sprechen", "Ins Wort fallen, Werkzeuge im Gespräch wie Wetter und Uhrzeit."),
    ("0.42", "Choreografie und VR", "Tänze im Editor bauen, Bewegungen vormachen, der Roboter mit der Quest im Wohnzimmer."),
    ("0.43", "Spiele", "Fußball – auch mit mehreren Enten –, Verstecken und „Ente sagt“."),
    ("0.44", "Ohne Roboter", "Knowlin als Begleiter am PC und Handy, ganz ohne Roboter."),
    ("0.45", "Alltag", "Routinen und Zeitpläne, Kalender-Abo aus einer lokalen Datei."),
    ("0.46", "Aufräumen und Smart Home", "Vor dem Saugroboter aufräumen, Licht und Alexa-Routinen."),
    ("ab Lieferung", "Digitaler Zwilling", "Der echte Roboter live im Simulator – mit Frühwarnung und Probelauf."),
    ("ab Lieferung", "Echte Open Duck", "Anbindung an die Open-Duck-Runtime – mit Testern aus der Community."),
)


def liste() -> list[dict[str, Any]]:
    return [{"version": v, "name": n, "kurz": k} for v, n, k in GEPLANT]
