"""Eine aufgenommene Kopfbewegung abspielen (seit 0.48, Marionette): „Sie macht es nach.“

Die Punkte (t, Nicken, Drehen, Neigen) kommen aus `marionette.Bewegungen`; dazwischen wird linear übergeblendet. Nur
der Kanal „head“ – Beine, Räder und Arm bleiben, wo sie sind. Der Not-Aus bricht ab wie jedes Verhalten.
"""

from __future__ import annotations

from ..api import Head
from .engine import Behavior, Command


class Nachspielen(Behavior):
    name = "Bewegung nachmachen"
    channels = ("head",)

    def __init__(self, titel: str, punkte: list[list[float]]) -> None:
        super().__init__()
        self.titel = titel
        self.punkte = [p for p in punkte if len(p) == 4]
        self.timeout = (self.punkte[-1][0] if self.punkte else 0.0) + 2.0
        self.t = 0.0

    def tick(self, st, dt):
        self.t += dt
        pts = self.punkte
        if not pts or self.t > pts[-1][0]:
            return self.finish(f"„{self.titel}“ nachgemacht")
        i = next((k for k, p in enumerate(pts) if p[0] >= self.t), len(pts) - 1)
        a, b = pts[max(0, i - 1)], pts[i]
        k = 0.0 if b[0] <= a[0] else (self.t - a[0]) / (b[0] - a[0])
        werte = [a[j] + (b[j] - a[j]) * k for j in (1, 2, 3)]
        return Command(head=Head(0.0, werte[0], werte[1], werte[2]).clamped())

    def describe(self):
        return f"macht „{self.titel}“ nach"
