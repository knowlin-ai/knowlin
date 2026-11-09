"""Vorlage für einen eigenen Knowlin-Körper: „Rollbot“, ein kleiner simulierter Roboter auf Rädern mit Kopf.

Kopieren, umbenennen, `Rollbot` durch die Anbindung an deinen Roboter ersetzen – das Profil sagt Knowlin, was er kann.
Prüfen: `python -m duckpilot.koerper_pruefung rollbot` (nach `pip install -e .`).
"""

from __future__ import annotations

import asyncio
import math
import time

from duckpilot.api import DuckBackend, DuckState, Head, IntentResult, Pose, Twist
from duckpilot.koerper import Koerper

TAKT_HZ = 20


class Rollbot(DuckBackend):
    """Ein simulierter Roboter auf Rädern mit drehbarem Kopf. Pflichten (siehe duckpilot.koerper_pruefung):
    relax() = stromlos, stop() hält an, Grenzen aus api.LIMITS, stromlos bewegt sich nichts."""

    name = "rollbot"
    koerper_art = "rollbot"            # muss zur Profil-id (oder Profil.zustand) passen

    def __init__(self) -> None:
        super().__init__()
        self.x = self.y = self.yaw = 0.0
        self.soll = Twist()
        self.ist = Twist()
        self.kopf = Head()
        self.powered = False
        self.enabled = False
        self._task: asyncio.Task | None = None

    def eigenschaften(self) -> frozenset[str]:
        return frozenset({"raeder", "kopf", "simulator"})

    def skills(self) -> list[str]:
        return []

    # ── Lebenszyklus ──────────────────────────────────────────────────────
    async def connect(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._takt(), name="rollbot")

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def _takt(self) -> None:
        dt = 1.0 / TAKT_HZ
        while True:
            ziel = self.soll if self.powered and self.enabled else Twist()
            a = 0.5                                        # träge wie ein echter Antrieb
            self.ist = Twist(self.ist.vx + (ziel.vx - self.ist.vx) * a, self.ist.vy + (ziel.vy - self.ist.vy) * a,
                             self.ist.vyaw + (ziel.vyaw - self.ist.vyaw) * a)
            if ziel.is_zero() and self.ist.is_zero(0.005):
                self.ist = Twist()
            self.yaw += self.ist.vyaw * dt
            self.x += (self.ist.vx * math.cos(self.yaw) - self.ist.vy * math.sin(self.yaw)) * dt
            self.y += (self.ist.vx * math.sin(self.yaw) + self.ist.vy * math.cos(self.yaw)) * dt
            await asyncio.sleep(dt)

    def state(self) -> DuckState:
        return DuckState(t=time.monotonic(), connected=self._task is not None, backend="sim", koerper=self.koerper_art,
                         x=self.x, y=self.y, yaw=self.yaw, twist=self.ist, requested=self.soll, head=self.kopf,
                         powered=self.powered, enabled=self.enabled)

    # ── kontinuierliche Intents ───────────────────────────────────────────
    async def move(self, twist: Twist) -> None:
        self.soll = twist.clamped() if self.powered else Twist()

    async def head(self, head: Head) -> None:
        if self.powered:
            self.kopf = head.clamped()

    async def mouth(self, open_: float) -> None:
        return None

    async def pose(self, pose: Pose, active: bool = True) -> None:
        return None

    # ── diskrete Befehle ──────────────────────────────────────────────────
    async def init(self) -> IntentResult:
        self.powered = True
        return IntentResult(True)

    async def enable(self, on: bool) -> IntentResult:
        self.enabled = bool(on) and self.powered
        return IntentResult(True)

    async def stop(self) -> IntentResult:
        self.soll = Twist()
        return IntentResult(True)

    async def do(self, skill: str) -> IntentResult:
        return IntentResult(False, "Rollbot kann noch keine gelernten Bewegungen")

    async def sound(self, tag: str) -> IntentResult:
        return IntentResult(False, "Rollbot hat keine eigenen Laute")

    async def rest(self) -> IntentResult:
        return await self.relax()

    async def relax(self) -> IntentResult:
        self.powered = self.enabled = False
        self.soll = Twist()
        return IntentResult(True, "stromlos")


def baue(cfg) -> Rollbot:
    """Fabrik: bekommt Knowlins Einstellungen (cfg.backend „sim“ oder „robotd“, cfg.koerper_optionen)."""
    return Rollbot()


def profil() -> Koerper:
    return Koerper("rollbot", "Rollbot", "Beispiel aus der Vorlage", "fahrend", frozenset({"raeder", "kopf"}),
                   baue, quelle="https://github.com/knowlin-ai/knowlin/tree/main/examples/knowlin-koerper-vorlage",
                   lizenz="Apache-2.0")
