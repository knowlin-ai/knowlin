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
    ("0.39", "Erfahrungsnetz 2", "Weltmodell und Tagesrückblick – Knowlin erinnert sich an mehr und lernt aus Erlebnissen."),
    ("0.39", "Stacki wie ab Werk", "Schau mich an, Tanz mit Licht und Musik, Avatar: Stacki spiegelt dein Gesicht."),
    ("0.40", "Gespräch in Echtzeit", "Ins Wort fallen, Werkzeuge im Gespräch wie Wetter und Uhrzeit."),
    ("0.40", "Reachy wie in Pollens App", "Umherschauen, Gesicht folgen und schlafen gehen."),
    ("0.41", "Mentor 2", "Vorgemachtes als Auftrag merken – mit Webcam oder Handy."),
    ("0.41", "Ari übt selbst", "Reinforcement Learning im Simulator verfeinert, was du ihm vorgemacht hast."),
    ("0.42", "Alltag", "Routinen und Zeitpläne, Kalender-Abo aus einer lokalen Datei."),
    ("0.42", "Ari mit LeRobot", "Mit einem zweiten Arm steuern, fertige Policies laden, Beispiele auf den Hub."),
    ("0.43", "Choreografie", "Tänze im Editor bauen – für jeden Körper."),
    ("0.43", "Bello lernt", "Gangarten mit Reinforcement Learning im offenen Modell von Petoi."),
    ("0.44", "Spiele und VR", "Fußball, Verstecken, „Ente sagt“ – und der Roboter mit der Quest im Wohnzimmer."),
    ("0.45", "Haushalt und Smart Home", "Vor dem Saugroboter aufräumen, Licht und Routinen über Home Assistant."),
    ("ab Lieferung", "Echte Microduck", "Inbetriebnahme mit Trockenlauf, digitaler Zwilling mit Frühwarnung."),
    ("ab Lieferung", "Zubehör der Microduck", "Rollschuh-Gangarten und das NFC-Polaroid, sobald Pollen liefert."),
)


def liste() -> list[dict[str, Any]]:
    return [{"version": v, "name": n, "kurz": k} for v, n, k in GEPLANT]
