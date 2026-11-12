"""SO-101 im Simulator (seit 0.38.47, Etappe G5 aus dem Konzept „Knowlins Geist“).

Ein Arm ohne Kopf, ohne Beine und ohne Stimme: Er steht wie Reachy fest auf dem Couchtisch (`TischPlatz`) und bewegt
sechs Gelenke (`duckpilot/arm.py`). Gezeigt wird, dass derselbe Geist mit einem ganz anderen Körper zurechtkommt – der
Aktionskatalog handelt „grüßen“ hier als Winken aus, nicht als Nicken.

Kinematik ohne Physik, wie bei Reachy: Haltungen werden in der angegebenen Zeit linear angefahren. Not-Aus: Motoren aus,
der Arm sackt in die Ruhelage (nur fürs Bild); bewegt wird erst wieder nach dem Aufwecken.
Am echten SO-101 übernimmt das Profil „lerobot“ (`backends/lerobot.py`).
"""

from __future__ import annotations

import math
from typing import Any

from .. import arm as A
from ..api import DuckState, Head, IntentResult, Perception, Pose, Twist
from .sim import SimBackend
from .tischplatz import TischPlatz

EIGENSCHAFTEN = frozenset({"arm", "greifer", "simulator", "zuruecksetzen"})
OHNE = "Der SO-101 ist ein Arm – er hat keine Beine, keinen Kopf und keine Stimme"
SACKEN_S = 1.2                # so lange sackt der Arm nach dem Not-Aus in die Ruhelage


class So101Sim(TischPlatz, SimBackend):
    koerper_art = "so101"
    platz_name = "Der SO-101"
    fuss_m = 0.06

    def __init__(self, realtime: bool = True, seed: int | None = None) -> None:
        super().__init__(realtime=realtime, seed=seed)
        self.gelenke: dict[str, float] = dict(A.POSEN["ruhe"])        # Grad
        self._von: dict[str, float] = dict(self.gelenke)
        self._ziel: dict[str, float] = dict(self.gelenke)
        self._dauer = 0.0
        self._zeit = 0.0
        self._folge: list[tuple[dict[str, float], float]] = []
        self.geste_name: str | None = None
        self.sitting = True                                             # beginnt in der Ruhelage, Motoren aus
        self.powered = False
        self.enabled = False
        self.platzieren(self.standard_flaeche)

    # ── Körper ───────────────────────────────────────────────────────────
    def eigenschaften(self) -> frozenset[str]:
        return EIGENSCHAFTEN

    def skills(self) -> list[str]:
        return []

    def fassung(self, skill: str) -> dict[str, str]:
        return {"fassung": "SO-101 im Simulator von Knowlin – Kinematik ohne Physik, Modell von TheRobotStudio"}

    # ── Bewegung ─────────────────────────────────────────────────────────
    def _anfahren(self, ziel: dict[str, float], sekunden: float) -> None:
        self._von = dict(self.gelenke)
        self._ziel = {**self.gelenke, **ziel}
        self._dauer = max(0.05, float(sekunden))
        self._zeit = 0.0

    def _step_actuators(self, dt: float) -> None:
        if self._zeit < self._dauer:
            self._zeit = min(self._dauer, self._zeit + dt)
            a = self._zeit / self._dauer
            a = a * a * (3 - 2 * a)                                     # weich anfahren und abbremsen
            self.gelenke = {g: self._von[g] + (self._ziel[g] - self._von[g]) * a for g in A.GELENKE}
        elif self._folge:
            haltung, s = self._folge.pop(0)
            self._anfahren(haltung, s)
        else:
            self.geste_name = None

    def _step_base(self, dt: float) -> None:
        self.applied = Twist()                                          # steht fest
        self.gait_phase = 0.0

    def _update_tof(self) -> None:
        self._tof, self._points, self._sectors = [], [], {}

    def _fall(self, why: str) -> None:                                  # steht fest – fällt nicht um
        return None

    async def haltung(self, gelenke: dict[str, Any], sekunden: float = 1.0) -> IntentResult:
        """Gelenke in Grad (Namen wie in `arm.GELENKE`, auch deutsch) in `sekunden` anfahren."""
        if not self.powered:
            return IntentResult(False, "Motoren sind aus – erst aufwecken")
        ziel, unbekannt = A.begrenzen(gelenke)
        if unbekannt:
            return IntentResult(False, f"Gelenk unbekannt: {', '.join(unbekannt)} – bekannt: {', '.join(A.GELENKE)}")
        self._folge, self.geste_name = [], None
        self.sitting = False
        self._anfahren(ziel, max(0.3, min(10.0, float(sekunden))))
        return IntentResult(True, f"fährt {len(ziel)} Gelenke in {self._dauer:.1f} s an")

    async def geste(self, name: str) -> IntentResult:
        if name not in A.GESTEN:
            return IntentResult(False, f"Geste unbekannt – bekannt: {', '.join(A.GESTEN)}")
        if not self.powered:
            return IntentResult(False, "Motoren sind aus – erst aufwecken")
        folge = [(dict(h), s) for h, s in A.GESTEN[name]]
        self.sitting = name == "ruhe"
        self._folge = folge[1:]
        self._anfahren(*folge[0])
        self.geste_name = name
        return IntentResult(True, f"{name} ({A.dauer(name):.1f} s)")

    # ── Intents, die ein Arm nicht hat ───────────────────────────────────
    async def move(self, twist: Twist) -> None:
        self.requested = Twist()
        if abs(twist.vx) > 0.01 or abs(twist.vy) > 0.01 or abs(twist.vyaw) > 0.01:
            self.limited_by = [OHNE]

    async def head(self, head: Head) -> None:
        return None

    async def mouth(self, open_: float) -> None:
        return None

    async def pose(self, pose: Pose, active: bool = True) -> None:
        return None

    async def do(self, skill: str) -> IntentResult:
        return IntentResult(False, OHNE)

    async def sound(self, tag: str) -> IntentResult:
        return IntentResult(False, "Der SO-101 hat keine eigenen Laute – Knowlin spricht über den PC")

    # ── Wach, Ruhe, Not-Aus ──────────────────────────────────────────────
    async def init(self) -> IntentResult:
        if self.powered and not self.sitting:
            return IntentResult(True, "ist schon bereit")
        self.powered = self.enabled = True
        await self.geste("bereit")
        return IntentResult(True, "Motoren an, Arm bereit")

    async def enable(self, on: bool) -> IntentResult:
        if on and not self.powered:
            return await self.init()
        self.enabled = bool(on) and self.powered
        return IntentResult(True)

    async def rest(self) -> IntentResult:
        if not self.powered:
            return IntentResult(True, "ist schon aus")
        await self.geste("ruhe")
        self.enabled = False
        return IntentResult(True, "legt sich in die Ruhelage")

    async def stop(self) -> IntentResult:
        self._folge, self.geste_name = [], None
        self._von = self._ziel = dict(self.gelenke)
        self._dauer = self._zeit = 0.0
        self.requested = Twist()
        return IntentResult(True)

    def lahm(self) -> None:
        """Not-Aus: Motoren sofort aus; ohne Kraft sackt der Arm in die Ruhelage (nur fürs Bild)."""
        self.powered = self.enabled = False
        self._folge, self.geste_name = [], None
        self._anfahren(A.POSEN["ruhe"], SACKEN_S)
        self.sitting = True

    async def relax(self) -> IntentResult:
        self.lahm()
        return IntentResult(True, "stromlos")

    # ── Zustand ──────────────────────────────────────────────────────────
    def state(self) -> DuckState:
        st = super().state()
        st.koerper = self.koerper_art
        st.battery = None
        st.gait_phase = 0.0
        st.perception = Perception(objects=st.perception.objects, source="sim")
        rad = [round(math.radians(self.gelenke[g]), 4) for g in A.GELENKE]
        st.joints = rad
        st.display_joints = rad
        st.skill = None                                                 # Gesten sind keine Skills (keine Anzeige „geste:…“)
        st.stand_z, st.standflaeche = round(self.stand_z, 4), self.standflaeche
        return st
