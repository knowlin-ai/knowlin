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

Hiwonders Pollen-Spiele (Fußball, Laser …) und eigene Aufrufe (Labyrinth, Hindernisse) nutzt Knowlin noch nicht.
"""

from __future__ import annotations

from ..api import DuckState, IntentResult
from .sim import SimBackend

ART = "wonderduck"
SKILLS = ("sit_toggle", "ground_pick")       # sitzen und mit dem Schnabel greifen – Schuss und Purzelbaum: unbekannt
KEINE_SKILL = "Das zeigt Knowlin bei der WonderDuck noch nicht – sitzen und mit dem Schnabel greifen geht"


class WonderduckSim(SimBackend):
    koerper_art = ART

    def eigenschaften(self) -> frozenset[str]:
        return frozenset({"beine", "kopf", "schnabel", "tiefensensor", "kamera", "mikrofon", "lautsprecher",
                          "simulator", "zuruecksetzen", "stimmbank"})

    def skills(self) -> list[str]:
        return list(SKILLS)

    async def do(self, skill: str) -> IntentResult:
        if skill not in SKILLS:
            return IntentResult(False, KEINE_SKILL)
        return await super().do(skill)

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
