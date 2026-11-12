"""Tischroboter im Simulator (seit 0.38.47 eigene Datei; vorher nur bei Reachy Mini, seit 0.38.10).

Ein Körper ohne Beine steht fest auf einer Fläche – Standard auf dem Couchtisch, Blick zum Sofa – und lässt sich mit der
Hand umstellen (`platzieren`). Er fällt nicht um und schiebt am Boden nichts. Genutzt von Reachy Mini und dem SO-101.
Die Klasse wird vor `SimBackend` geerbt: `class ReachyMiniSim(TischPlatz, SimBackend)`.
"""

from __future__ import annotations

import math
from typing import Any

STELL_RAND_M = 0.01          # so viel Platz rundum braucht der Fuß auf einer Fläche
STELLFLAECHEN = ("tisch", "hocker", "kiste", "regal", "kommode", "schrank", "bank", "stuhl")
STANDARD_FLAECHE = "Couchtisch"


class TischPlatz:
    platz_name = "Der Roboter"
    fuss_m = 0.065
    standard_flaeche = STANDARD_FLAECHE
    stand_z = 0.0
    standflaeche = ""

    def _flaeche(self, name: str) -> Any:
        n = str(name or "").strip().lower()
        return next((m for m in [*self.world_model.boxes, *self.world_model.cylinders] if m.name.lower() == n), None)

    def platz_pruefen(self, flaeche: str) -> str | None:
        """Kann der Tischroboter dort stehen? None = ja, sonst der Grund. „boden“ geht immer."""
        if str(flaeche or "").strip().lower() in ("boden", "fußboden", "floor"):
            return None
        m = self._flaeche(flaeche)
        if m is None:
            return f"Kenne keine Fläche namens „{flaeche}“"
        if not any(w in m.name.lower() for w in STELLFLAECHEN):
            return f"Auf {m.name} kann {self.platz_name} nicht sicher stehen"
        innen = m.r if hasattr(m, "r") else min(m.sx, m.sy) / 2
        if innen < self.fuss_m + STELL_RAND_M:
            return f"{m.name} ist zu klein für den Fuß ({self.platz_name})"
        if not 0.05 <= m.h <= 1.2:
            return f"{m.name} ist zu hoch oder zu niedrig"
        return None

    def _blick_zum_sofa(self, x: float, y: float) -> float:
        """Ausrichtung: zum Sofa (dort sitzen die Menschen), sonst zur Raummitte."""
        sofa = self._flaeche("Sofa")
        zx, zy = (sofa.x, sofa.y) if sofa is not None else (0.0, 0.0)
        return math.atan2(zy - y, zx - x) if math.hypot(zx - x, zy - y) > 0.05 else 0.0

    def _platz_am_boden(self) -> tuple[float, float]:
        """Freier Platz am Boden: vor der Fläche, auf der er gerade steht (Richtung Sofa) – sonst der Startplatz."""
        m = self._flaeche(self.standflaeche) if self.standflaeche else None
        if m is not None:
            richtung = self._blick_zum_sofa(m.x, m.y)
            ausdehnung = m.r if hasattr(m, "r") else max(m.sx, m.sy) / 2
            for d in (0.0, 0.6, -0.6, 1.2, -1.2, 1.8, -1.8, math.pi):
                a = richtung + d
                for r in (ausdehnung + self.fuss_m + 0.08, ausdehnung + self.fuss_m + 0.2):
                    x, y = m.x + r * math.cos(a), m.y + r * math.sin(a)
                    if self.world_model.collide(x, y, self.fuss_m + 0.02) is None:
                        return x, y
        return self.START_POSE[0], self.START_POSE[1]

    def platzieren(self, flaeche: str) -> tuple[bool, str]:
        """Den Tischroboter auf eine Fläche stellen (Mitte, Blick zum Sofa) oder auf den Boden – nur im Simulator, mit der Hand."""
        grund = self.platz_pruefen(flaeche)
        if grund is not None:
            return False, grund
        m = None if str(flaeche).strip().lower() in ("boden", "fußboden", "floor") else self._flaeche(flaeche)
        if m is None:
            x, y = self._platz_am_boden()
            self.stand_z, self.standflaeche = 0.0, ""
            text = f"{self.platz_name} steht jetzt auf dem Boden"
        else:
            x, y = m.x, m.y
            self.stand_z, self.standflaeche = float(m.h), m.name
            text = f"{self.platz_name} steht jetzt auf: {m.name}"
        self._ente_setzen(x, y, self._blick_zum_sofa(x, y))
        return True, text

    def szene_zuruecksetzen(self, ente: bool = True) -> dict[str, Any]:
        out = super().szene_zuruecksetzen(ente=False)
        if ente:                                           # fällt nicht – zurück auf den Standardplatz
            out["ente"] = self.platzieren(self.standard_flaeche)[0]
        return out

    def _push_items(self) -> None:
        if self.stand_z <= 0.0:                            # auf dem Tisch schiebt er nichts am Boden
            super()._push_items()
