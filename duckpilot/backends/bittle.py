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
OHNE = "Bello ist ein Hund ohne Schnabel – aufheben, Purzelbaum und Pollens Tricks gehen nicht; laufen, drehen und sitzen schon"


def kopf_lage(head: Head) -> dict[str, float]:
    """Kopfbefehl → Bittles Halsgelenk: nur seitlich drehen. Nicken zeigt die 3D-Ansicht mit dem Vorderkörper."""
    return {"yaw": round(max(-KOPF_DREH, min(KOPF_DREH, head.head_yaw)), 4),
            "pitch": round(max(-0.35, min(0.35, head.head_pitch - head.neck_pitch * 0.6)), 4)}


class BittleSim(SimBackend):
    """Bittle X im einfachen Simulator: gleiches Wohnzimmer, läuft auf vier Beinen."""

    koerper_art = "bittle"

    def eigenschaften(self) -> frozenset[str]:
        return EIGENSCHAFTEN | {"simulator", "zuruecksetzen"}

    def skills(self) -> list[str]:
        return ["sit_toggle"]

    async def do(self, skill: str) -> IntentResult:
        if skill != "sit_toggle":
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
        st.kopf_lage = {"yaw": 0.0, "pitch": 0.0} if (self.sitting or not self.powered) else kopf_lage(st.head)
        return st

    def fassung(self, skill: str) -> dict[str, str]:
        return {"fassung": "Bittle X im einfachen Simulator von Knowlin – gezeichnete Bewegung, ohne Modell von Petoi"}
