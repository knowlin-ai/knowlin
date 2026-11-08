"""Weitere Enten im einfachen Simulator (seit 0.36.3, Wunsch des Maintainers: „den Mehr-Enten-Modus unabhängig von der Musik
müssen wir supporten – Interaktion untereinander“).

Jede Begleitente ist ein eigener einfacher Simulator-Körper mit eigener Position, eigenem Gang, Kopf und Schnabel – in
**derselben Welt** wie die Hauptente (Möbel, Ball). Die Welt selbst (Dinge, Tiefensensor) rechnet nur die Hauptente;
die Begleiter brauchen keinen Tiefensensor, sie kennen die Möbel direkt. Gesteuert werden sie von
`motion/schwarm.py` – synchron über `steuern()`, ohne eigene Bewegungs-Engine.
"""

from __future__ import annotations

import hashlib
from typing import Any

from ..api import Head, Pose, Twist
from .sim import SimBackend
from .world import World

NAMEN = ("Kiki", "Pip", "Lotte", "Bruno", "Fiete", "Nele", "Jojo", "Hugo")


def stimme_aus_kennung(kennung: str) -> tuple[float, float]:
    """Eigene, feste Stimme aus der Kennung – wie Microduck „audio identity“ aus der Seriennummer: Tonhöhe −4…+4
    Halbtöne, Klangfarbe −0,8…+0,8. Gleiche Kennung, gleiche Stimme."""
    h = hashlib.sha256(kennung.encode()).digest()
    return round((h[0] / 255 * 8 - 4) * 2) / 2, round((h[1] / 255 * 1.6 - 0.8), 1)


class Begleitente(SimBackend):
    name = "sim"

    def __init__(self, welt: World, nummer: int, x: float, y: float, yaw: float = 0.0) -> None:
        super().__init__(world=welt, realtime=False, seed=1000 + nummer)
        self.nummer = nummer
        self.kennung = f"ente-{nummer + 1}"
        self.ente_name = NAMEN[nummer % len(NAMEN)]
        self.klang = stimme_aus_kennung(self.kennung)
        self.x, self.y, self.yaw = x, y, yaw
        self.powered = self.enabled = True       # steht gleich bereit

    def step(self, dt: float) -> None:
        """Nur der eigene Körper – Dinge und Tiefensensor rechnet die Hauptente."""
        self.t += dt
        self._step_skill(dt)
        self._step_base(dt)
        self._step_actuators(dt)

    def steuern(self, twist: Twist, head: Head | None = None, pose: Pose | None = None, mund: float | None = None) -> None:
        self.requested = twist.clamped()
        self._last_move = self.t
        if head is not None:
            self.head_target = head.clamped()
        if pose is not None:
            self.pose_target = pose.clamped()
        if mund is not None:
            self.mouth_target = max(0.0, min(1.0, mund))

    def setzen(self, sitzen: bool) -> None:
        if self.sitting != sitzen and self.skill is None and not self.fallen:
            self.requested = Twist()
            self._start_skill("sit_toggle")

    def wecken(self) -> None:
        """Nach dem Not-Aus (stromlos) wieder aufstehen – ruft der Schwarm erst, wenn die Sperre vorbei ist."""
        if not self.powered and not self.fallen and self.skill is None:
            self._start_skill("_init")

    def aufstehen(self) -> None:
        if self.fallen and self.skill is None:
            self._start_skill("_recover")

    def anzeige(self) -> dict[str, Any]:
        """Was die 3D-Ansicht braucht – klein gehalten (20 Hz an jedes Fenster)."""
        st = self.state().to_dict()
        out = {k: st.get(k) for k in ("x", "y", "yaw", "display_joints", "body", "pose", "fallen", "fall_side", "skill",
                                      "skill_progress", "sitting")}
        out.update(id=self.kennung, name=self.ente_name)
        return out
