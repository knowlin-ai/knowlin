"""Open Duck Mini v2 als drittes Modul der Suite Knowlin (seit 0.38.4).

Die Open Duck Mini ist der offene Selbstbau-Vorgänger der Microduck (Antoine Pirrone und Community, Apache-2.0):
gut 40 cm groß, 3D-gedruckt, je Bein fünf Motoren, Hals und Kopf mit vier Gelenken, zwei Antennen, eine IMU. Keinen
Schnabel zum Greifen, keinen Tiefensensor. Kamera, Lautsprecher, Mikrofon und Augen-LEDs hat sie je nach Bau – die
Community nennt sie „expression features“ und baut sie nach und nach ein.

Pollens gelernte Bewegungen (Aufheben, Purzelbaum) gibt es für sie nicht; laufen und drehen kann sie. Schießen zeigt der
Simulator seit 0.38.21 nachgestellt (Wunsch „schießen kann er auch nicht wie die Microduck?“) – die echte Open
Duck hat dafür noch keine gelernte Bewegung.

- `OpenDuckSim` – im einfachen Simulator von duckpilot (gleiches Zimmer, gleiche Dinge); die 3D-Ansicht zeigt das
  offene Modell (`modell/open_duck.py`). Antennen zeigen Gefühle und wackeln beim Sprechen wie bei Reachy Mini.
- Der echte Roboter läuft mit der Open-Duck-Runtime auf einem Raspberry Pi Zero 2 W. Eine Anbindung ist geplant
  („help wanted“): die Runtime hat noch keine Schnittstelle nach außen und ihr Repo keine Lizenzdatei.
"""

from __future__ import annotations

import math

from ..api import DuckState, IntentResult, Perception
from .reachy_ausdruck import ANTENNE_RUHE, antennen_aus_mund
from .sim import SimBackend

KEINE_POLLEN_SKILLS = "Die Open Duck hat Pollens gelernte Bewegungen (Aufheben, Purzelbaum) nicht – laufen, drehen und schießen geht"
SCHUSS = ("kick_left", "kick_right")
EXTRAS = ("kamera", "lautsprecher", "mikrofon", "augen_leds")     # je nach Bau („expression features“)
KAMERA_TIEFE_MAX = 1.5      # m – so weit schätzt ein kleines Tiefenmodell aus dem Kamerabild noch brauchbar
KAMERA_FEHLER = 0.05        # ± Anteil der Entfernung (je Bild)


class OpenDuckSim(SimBackend):
    """Open Duck Mini im einfachen Simulator. Ohne Tiefensensor: Erkunden fehlt; Ausweichen nur mit Kamera (geschätzte Tiefe)."""

    koerper_art = "open_duck_mini"

    def __init__(self, realtime: bool = True, seed: int | None = None, extras: tuple[str, ...] = EXTRAS) -> None:
        super().__init__(realtime=realtime, seed=seed)
        self.extras = frozenset(e for e in extras if e in EXTRAS)
        self.antennen = [-ANTENNE_RUHE, ANTENNE_RUHE]
        self.antennen_ziel: list[float] | None = None
        self._antennen_bis = 0.0
        self._phase = 0.0

    def eigenschaften(self) -> frozenset[str]:
        return frozenset({"beine", "kopf", "antennen", "simulator", "zuruecksetzen", "stimmbank"}) | self.extras

    def skills(self) -> list[str]:
        return ["sit_toggle", *SCHUSS]

    async def do(self, skill: str) -> IntentResult:
        if skill != "sit_toggle" and skill not in SCHUSS:
            return IntentResult(False, KEINE_POLLEN_SKILLS)
        return await super().do(skill)

    async def antennen_setzen(self, rechts: float, links: float, sekunden: float = 1.5) -> IntentResult:
        if not self.powered:
            return IntentResult(False, "schläft – erst aufstehen")
        g = math.radians(80)                                    # Open-Duck-Antennen: ±90° am Servo
        self.antennen_ziel = [max(-g, min(g, rechts)), max(-g, min(g, links))]
        self._antennen_bis = self.t + max(0.2, min(10.0, sekunden))
        return IntentResult(True)

    def _step_actuators(self, dt: float) -> None:
        super()._step_actuators(dt)
        if not self.powered or self.sitting:
            ziel = [-0.6, 0.6]                                  # hängen im Sitzen nach außen
        elif self.antennen_ziel is not None and self.t < self._antennen_bis:
            ziel = self.antennen_ziel
        else:
            self.antennen_ziel = None
            self._phase += dt * 9.0
            ziel = antennen_aus_mund(self.mouth_now, self._phase)
        k = min(1.0, dt / 0.12)
        self.antennen = [a + (b - a) * k for a, b in zip(self.antennen, ziel)]

    def _update_tof(self) -> None:
        """Kein Tiefensensor. Mit Kamera (seit 0.38.25, Hinweis „Odis Kamera kann doch Objekte erkennen und die
        Laufbahn berechnen – sollte doch gehen“): Tiefe aus dem Kamerabild geschätzt – kürzere Reichweite und ein paar
        Prozent Schätzfehler. Die Punkte gehen in dieselbe Ausweich-Schicht wie bei der Microduck, also umläuft sie
        Hindernisse. Am echten Roboter schätzt das später ein kleines Tiefenmodell am PC aus dem Kamerabild (geplant)."""
        if "kamera" not in self.extras:
            self._tof, self._points, self._sectors = [], [], {}
            return
        super()._update_tof()
        weit = KAMERA_TIEFE_MAX
        f = 1 + self.rng.uniform(-KAMERA_FEHLER, KAMERA_FEHLER)    # Schätzung, kein Messwert: je Bild etwas zu nah/zu weit
        punkte = []
        for px, py, pz in self._points:
            d = math.hypot(px - self.x, py - self.y)
            if d > weit:
                continue
            punkte.append([round(self.x + (px - self.x) * f, 4), round(self.y + (py - self.y) * f, 4), pz])
        self._points = punkte
        self._sectors = {k: (v if v is not None and v <= weit else None) for k, v in self._sectors.items()}
        self._tof = []                                          # kein ToF-Bild zum Anzeigen

    def state(self) -> DuckState:
        st = super().state()
        st.koerper = self.koerper_art
        st.antennen = [round(a, 4) for a in self.antennen]
        if "kamera" in self.extras:
            st.perception = Perception(objects=st.perception.objects, sectors=dict(self._sectors), points=list(self._points),
                                       source="kamera_tiefe")
        else:
            st.perception = Perception(source="sim")
        st.mouth = 0.0                                          # kein Schnabel
        return st

    def fassung(self, skill: str) -> dict[str, str]:
        if skill in SCHUSS:
            return {"fassung": "Open Duck Mini im Simulator – Schuss nachgestellt (die echte Open Duck hat dafür noch keine gelernte Bewegung)"}
        return {"fassung": "Open Duck Mini im einfachen Simulator – offenes Modell, Gangart angenähert"}
