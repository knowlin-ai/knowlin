"""Bittle X im Simulator (seit 0.38.59): Petois kleiner Roboterhund.

Bittle X ist ein offener Lern-Roboterhund von Petoi (Software OpenCat unter MIT-Lizenz): etwa 19 × 15 × 11 cm, 270 bis
350 g, neun Gelenke – je Bein Schulter und Knie, dazu ein Gelenk im Hals, das den Kopf seitlich dreht. Auf dem ESP32-Board
sitzen ein Lagesensor und ein Modul für Sprachbefehle; ein Summer spielt Melodien, sprechen kann er nicht. Es gibt ihn
auch mit Greifarm (kommt später).

Hier läuft er im einfachen Simulator wie die Enten: laufen, drehen, sitzen, er fällt bei einem harten Stoß um und steht
nach dem Stopp-Fenster wieder auf (dieselben Regeln wie überall, nie hochgehoben). Er hat keinen Schnabel, keinen
Tiefensensor und keine eigene Stimme – Knowlin spricht für ihn. Gezeichnet wird er in der 3D-Ansicht selbst
(`static/bittle3d.js`), ohne Dateien von Petoi. Der Kopf dreht nur seitlich (±70°), nicken kann er mit dem Körper.

Der echte Bittle X ist noch nicht angebunden; geplant ist Petois serielles Protokoll (OpenCat, über USB oder Bluetooth).
"""

from __future__ import annotations

import math

from ..api import DuckState, Head, IntentResult, Perception
from .sim import SimBackend

EIGENSCHAFTEN = frozenset({"beine", "kopf", "mikrofon"})
KOPF_DREH = math.radians(70)
# Bellos Tricks (seit 0.38.61, nach dem Abgleich mit Petois eingebauten Tricks; Maintainer: „Ja und weiter“):
# Name → (Titel, Dauer in s, kurze Beschreibung). Gezeichnet in static/bittle3d.js, Kacheln auf der Trickseite.
# Salto und Handstand gibt es nur im Simulator – am echten Hund kämen sie erst nach eigener Prüfung dazu.
TRICKS: dict[str, tuple[str, float, str]] = {
    "pfote": ("Pfote geben", 2.6, "setzt sich und winkt mit der Pfote"),
    "strecken": ("Strecken", 2.8, "streckt die Vorderbeine weit nach vorn"),
    "verbeugen": ("Verbeugen", 2.4, "vorn tief, Po hoch – die Spielaufforderung"),
    "liegestuetze": ("Liegestütze", 4.2, "drei Liegestütze auf den Vorderbeinen"),
    "platz": ("Platz", 3.6, "legt sich hin und ruht kurz"),
    "tot_stellen": ("Tot stellen", 3.6, "kippt auf die Seite und bleibt liegen"),
    "boxen": ("Boxen", 3.2, "sitzt und boxt mit beiden Vorderpfoten"),
    "umschauen": ("Umschauen", 3.0, "dreht den Kopf nach links und rechts"),
    "handstand": ("Handstand", 3.4, "auf die Vorderbeine – nur im Simulator"),
    "salto": ("Rückwärtssalto", 2.4, "ein Salto rückwärts – nur im Simulator"),
    # Seit 0.38.64 (Maintainer: „mach männchen“ ging nicht; Abgleich mit Petois OpenCat-Fähigkeiten, MIT):
    "maennchen": ("Männchen", 3.4, "setzt sich auf und hebt beide Vorderpfoten"),  # Petoi „hu“
    "high_five": ("High five", 2.8, "sitzt und hält dir die Pfote hoch hin"),  # Petoi „fiv“
    "jubeln": ("Jubeln", 3.2, "sitzt aufrecht und winkt mit beiden Pfoten"),  # Petoi „chr“
    "nicken": ("Nicken", 2.2, "nickt ein paarmal mit dem Kopf"),  # Petoi „nd“
    "schnueffeln": ("Schnüffeln", 3.4, "schnüffelt mit gesenktem Kopf hin und her"),  # Petoi „snf“
    "kratzen": ("Kratzen", 3.0, "sitzt und kratzt sich mit dem Hinterbein"),  # Petoi „scrh“
    "graben": ("Graben", 3.4, "buddelt mit den Vorderpfoten"),  # Petoi „dg“
    "kicken": ("Auskeilen", 2.4, "tritt mit einem Hinterbein nach hinten"),  # Petoi „kc“
    "springen": ("Springen", 2.0, "geht in die Hocke und hüpft hoch"),  # Petoi „jmp“
    "tisch": ("Tisch", 3.0, "steht mit ganz geraden Beinen still wie ein Tisch"),  # Petoi „tbl“
    "schlafen": ("Schlafen", 5.0, "legt sich hin und lässt den Kopf sinken"),  # Petoi „zz“
    "frontsalto": ("Vorwärtssalto", 2.4, "ein Salto vorwärts – nur im Simulator"),  # Petoi „ff“
}
OHNE = "Bello ist ein Hund ohne Schnabel – aufheben, Purzelbaum und Pollens Tricks gehen nicht; seine eigenen Tricks schon"


def kopf_lage(head: Head) -> dict[str, float]:
    """Kopfbefehl → Bittles Halsgelenk: nur seitlich drehen. Nicken zeigt die 3D-Ansicht mit dem Vorderkörper."""
    return {"yaw": round(max(-KOPF_DREH, min(KOPF_DREH, head.head_yaw)), 4),
            "pitch": round(max(-0.35, min(0.35, head.head_pitch - head.neck_pitch * 0.6)), 4)}


class BittleSim(SimBackend):
    """Bittle X im einfachen Simulator: gleiches Wohnzimmer, läuft auf vier Beinen."""

    koerper_art = "bittle"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.extra_skills = {name: dauer for name, (_, dauer, _) in TRICKS.items()}

    def trick_titel(self) -> dict[str, str]:
        """Für das skill-Werkzeug: was die eigenen Tricks bedeuten (statt „vom Hub geladen“)."""
        return {name: f"{titel} – {text}" for name, (titel, _, text) in TRICKS.items()}

    def eigenschaften(self) -> frozenset[str]:
        return EIGENSCHAFTEN | {"simulator", "zuruecksetzen"}

    def skills(self) -> list[str]:
        return ["sit_toggle", *TRICKS]

    async def do(self, skill: str) -> IntentResult:
        if skill != "sit_toggle" and skill not in TRICKS:
            return IntentResult(False, OHNE)
        return await super().do(skill)

    async def sound(self, tag: str) -> IntentResult:
        return IntentResult(False, "Bello hat keine Entenlaute – Knowlin spricht für ihn")

    def _pick_or_drop(self) -> None:                   # kein Schnabel
        return None

    def _update_tof(self) -> None:
        self._tof, self._points, self._sectors = [], [], {}   # kein Tiefensensor

    def state(self) -> DuckState:
        st = super().state()
        st.koerper = self.koerper_art
        st.holding = None
        st.perception = Perception(objects=st.perception.objects, source="sim")
        ruhig = self.sitting or not self.powered or (self.skill in TRICKS and self.skill != "umschauen")
        st.kopf_lage = {"yaw": 0.0, "pitch": 0.0} if ruhig else kopf_lage(st.head)
        return st

    def fassung(self, skill: str) -> dict[str, str]:
        return {"fassung": "Bittle X im einfachen Simulator von Knowlin – gezeichnete Bewegung, ohne Modell von Petoi"}
