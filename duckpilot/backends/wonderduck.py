"""WonderDuck von Hiwonder als siebter Körper (seit 0.53).

Hiwonders WonderDuck (Shenzhen, Auslieferung ab 7.12.2026) baut laut ihrem README auf Pollens Microduck auf
(github.com/Hiwonder/wonderduck, Apache-2.0): 15 Gelenke mit denselben Namen, `robotd` mit Pollens Zeilen-JSON-RPC
(duck-ipc-proto, Protokoll 62), dieselben Unix-Sockets (`/run/robotd.sock`, `/run/tofd/tof.sock` …). Von den 35
Aufrufen, die Knowlin an robotd, configd und updaterd schickt, kennt sie 28 (Abgleich 26.11.); es fehlen Fotos
(`photo.*`), Lautstärke und das Pflegeheft – das sagt der Verbindungstest über `fehlende_funktionen`.

- `WonderduckSim` – im einfachen Simulator (Gelenkwinkel in der Konvention der Microduck, die Ansicht verschiebt sie auf
  die Ruhelage der WonderDuck, `modell/wonderduck.py`). Ihr Physikmodell gibt es noch nicht als MJCF bei Knowlin –
  „Echte Physik“ bleibt deshalb der Microduck vorbehalten.
- Am echten Roboter: `RobotdBackend` wie bei der Microduck, nur mit eigenem Namen im Zustand. **Ungeprüft** – es gibt
  noch keine WonderDuck bei Knowlin.

Bewegungen (seit 0.54, abgeglichen mit Hiwonders robotd am 27.11.): sitzen/stehen, mit dem Schnabel aufheben, Schuss
links und rechts (`kick_left`/`kick_right`, Policies `ball_kick_*`) und der Kopfstand (`headstand`): sie rollt nach vorn
auf den Kopf, hält ihn und rollt weiter auf die Füße. Hiwonders robotd erlaubt ihn nur aus dem Stand – hier genauso.
Einen eigenen Purzelbaum (`roulade`) hat die WonderDuck nicht; ihre Rolle gehört zum Kopfstand.

Hiwonders eigene Aufrufe (Linie folgen, Labyrinth, Person folgen) nutzt Knowlin noch nicht.
"""

from __future__ import annotations

from ..api import DuckState, IntentResult, Twist
from .sim import SimBackend

ART = "wonderduck"
SKILLS = ("sit_toggle", "ground_pick", "kick_left", "kick_right", "headstand")
KEINE_SKILL = ("Das kann die WonderDuck nicht – sie kann sitzen, mit dem Schnabel aufheben, links oder rechts schießen "
               "und einen Kopfstand machen")
KOPFSTAND_S = 6.0            # rollen (≈ 1,8 s), Kopf halten (≈ 2,7 s), weiterrollen auf die Füße
# Abschnitte des Kopfstands (Anteil der Dauer) – Ansicht (duckmodel.js, ente3d.js) und Bewegung nutzen dieselben
ROLLE_HIN, ROLLE_ZURUECK = 0.3, 0.75


class WonderduckSim(SimBackend):
    koerper_art = ART

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.extra_skills["headstand"] = KOPFSTAND_S

    def eigenschaften(self) -> frozenset[str]:
        return frozenset({"beine", "kopf", "schnabel", "tiefensensor", "kamera", "mikrofon", "lautsprecher",
                          "simulator", "zuruecksetzen", "stimmbank"})

    def skills(self) -> list[str]:
        return list(SKILLS)

    async def do(self, skill: str) -> IntentResult:
        if skill not in SKILLS:
            return IntentResult(False, KEINE_SKILL)
        return await super().do(skill)

    def _skill_twist(self) -> Twist | None:
        """Beim Kopfstand rollt sie ein Stück nach vorn auf den Kopf und beim Abrollen noch einmal."""
        if self.skill == "headstand":
            p = self._skill_progress()
            rollt = 0.05 < p < ROLLE_HIN or p > ROLLE_ZURUECK
            return Twist(0.12 if rollt else 0.0, 0.0, 0.0)
        return super()._skill_twist()

    def state(self) -> DuckState:
        st = super().state()
        st.koerper = ART
        return st


def echt(cfg):
    """Die echte WonderDuck über Hiwonders robotd – derselbe Weg wie bei der Microduck."""
    from .robotd import RobotdBackend

    class WonderduckRobotd(RobotdBackend):
        koerper_art = ART

        def state(self) -> DuckState:
            st = super().state()
            st.koerper = ART
            return st

    return WonderduckRobotd(cfg.robot, tof=cfg.tof, head_signs=cfg.head_signs, updater=cfg.updater)
