"""LeRobot-Roboter als Knowlin-Körper (Körperschnittstelle 1.0, seit 0.38.35).

Hugging Face LeRobot beschreibt jeden Roboter mit derselben Klasse `Robot`: `connect()`, `disconnect()`,
`get_observation() -> dict`, `send_action(dict) -> dict`, dazu `observation_features`/`action_features` (Schlüssel wie
`shoulder_pan.pos`, `gripper.pos`, `x.vel`, `theta.vel`). Dieser Adapter macht daraus ein `DuckBackend`:

- **Fähigkeiten** ergeben sich aus `action_features`: Gelenke `*.pos` → „arm“, `gripper.pos` → „greifer“,
  `x.vel`/`y.vel`/`theta.vel` → „raeder“ (LeKiwi), Bilder in `observation_features` → „kamera“.
- **Fahren** (`move`): m/s und rad/s wie im ganzen Knowlin, für LeRobot `theta.vel` in Grad/s umgerechnet, innerhalb
  der Grenzen aus `api.LIMITS`. Totmann wie robotd: ohne neuen Befehl hält die Engine (20 Hz) ohnehin an.
- **Arm** (`haltung`): Gelenkwerte in den Einheiten des Roboters (LeRobot normiert meist −100…100, Greifer 0…100);
  Knowlin fährt sie in Schritten über die angegebene Zeit an (nie springen) und hält sie.
- **Not-Aus** (`relax`): Geschwindigkeit null, dann Drehmoment aus (`robot.bus.disable_torque()`); gibt es das nicht,
  trennt Knowlin die Verbindung – LeRobot schaltet beim Trennen das Drehmoment ab. Diese Pflicht kennt LeRobots eigener
  Vertrag nicht; Knowlin ergänzt sie.

LeRobot selbst ist keine Pflicht: Ohne Paket meldet der Körper ehrlich, was fehlt. Einen Simulator für LeRobot-Roboter
hat Knowlin noch nicht.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from typing import Any

from ..api import DuckBackend, DuckState, Head, IntentResult, Pose, Twist

log = logging.getLogger(__name__)

TAKT_HZ = 20
GREIFER = "gripper"
RAD_SCHLUESSEL = ("x.vel", "y.vel", "theta.vel")
ARM_GRENZE = 100.0              # LeRobots normierter Bereich (−100…100); Werte darüber werden abgeschnitten
OHNE_BEWEGUNGEN = ("LeRobot-Körper haben in Knowlin noch keine gelernten Bewegungen – "
                   "Policies aus LeRobot folgen mit dem nächsten Schritt.")


def faehigkeiten_aus(action_features: dict[str, Any], observation_features: dict[str, Any]) -> frozenset[str]:
    """Was ein LeRobot-Roboter kann – nur aus seinen Merkmalen gelesen."""
    f: set[str] = set()
    gelenke = [k for k in action_features if k.endswith(".pos")]
    if any(k != f"{GREIFER}.pos" for k in gelenke):
        f.add("arm")
    if f"{GREIFER}.pos" in action_features:
        f.add("greifer")
    if any(k in action_features for k in RAD_SCHLUESSEL):
        f.add("raeder")
    if any(isinstance(v, tuple) and len(v) == 3 for v in observation_features.values()):
        f.add("kamera")
    return frozenset(f)


class NichtVerfuegbar(DuckBackend):
    """Platzhalter, wenn ein Körper nicht gebaut werden kann (Paket fehlt, kein Simulator) – Knowlin bleibt bedienbar
    und sagt ehrlich, warum nichts passiert."""

    name = "nicht_verfuegbar"

    def __init__(self, koerper: str, grund: str) -> None:
        super().__init__()
        self.koerper_art = koerper
        self.grund = grund

    def eigenschaften(self) -> frozenset[str]:
        return frozenset()

    def skills(self) -> list[str]:
        return []

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def state(self) -> DuckState:
        return DuckState(t=time.monotonic(), connected=False, backend="nicht_verfuegbar", koerper=self.koerper_art,
                         limited_by=[self.grund])

    async def move(self, twist: Twist) -> None:
        return None

    async def head(self, head: Head) -> None:
        return None

    async def mouth(self, open_: float) -> None:
        return None

    async def pose(self, pose: Pose, active: bool = True) -> None:
        return None

    async def init(self) -> IntentResult:
        return IntentResult(False, self.grund)

    async def enable(self, on: bool) -> IntentResult:
        return IntentResult(False, self.grund)

    async def stop(self) -> IntentResult:
        return IntentResult(True)

    async def do(self, skill: str) -> IntentResult:
        return IntentResult(False, self.grund)

    async def sound(self, tag: str) -> IntentResult:
        return IntentResult(False, self.grund)

    async def rest(self) -> IntentResult:
        return IntentResult(True)

    async def relax(self) -> IntentResult:
        return IntentResult(True, "nichts verbunden")


class LeRobotKoerper(DuckBackend):
    """Ein LeRobot-`Robot` als Körper. Alle Aufrufe an den Roboter laufen in einem eigenen Faden (LeRobot blockiert)."""

    name = "lerobot"
    koerper_art = "lerobot"

    def __init__(self, robot: Any, typ: str = "") -> None:
        super().__init__()
        self.robot = robot
        self.typ = typ or getattr(robot, "name", "") or type(robot).__name__
        self._lock = threading.Lock()
        self._obs: dict[str, Any] = {}
        self._task: asyncio.Task | None = None
        self._haltung_task: asyncio.Task | None = None
        self.powered = False
        self.enabled = False
        self.applied = Twist()
        self.limited_by: list[str] = []
        self._fehler = ""
        af = dict(getattr(robot, "action_features", {}) or {})
        of = dict(getattr(robot, "observation_features", {}) or {})
        self._faehig = faehigkeiten_aus(af, of)
        self.gelenke = [k[:-4] for k in af if k.endswith(".pos")]

    # ── Beschreibung ──────────────────────────────────────────────────────
    def eigenschaften(self) -> frozenset[str]:
        return self._faehig

    def skills(self) -> list[str]:
        return []

    # ── Lebenszyklus ──────────────────────────────────────────────────────
    async def connect(self) -> None:
        def verbinden() -> None:
            with self._lock:
                if not getattr(self.robot, "is_connected", False):
                    try:
                        self.robot.connect(calibrate=False)
                    except TypeError:
                        self.robot.connect()
        try:
            await asyncio.to_thread(verbinden)
            self._fehler = ""
        except Exception as exc:  # noqa: BLE001 – Port belegt, nicht kalibriert …
            self._fehler = f"Verbindung zum LeRobot-Roboter ging nicht: {exc}"
            log.warning(self._fehler)
            return
        if self._task is None:
            self._task = asyncio.create_task(self._lesen(), name="lerobot-lesen")

    async def close(self) -> None:
        for t in (self._task, self._haltung_task):
            if t:
                t.cancel()
        self._task = self._haltung_task = None
        await self._stillstand()

        def trennen() -> None:
            with self._lock:
                if getattr(self.robot, "is_connected", False):
                    self.robot.disconnect()
        try:
            await asyncio.to_thread(trennen)
        except Exception as exc:  # noqa: BLE001
            log.warning("LeRobot ließ sich nicht sauber trennen: %s", exc)

    async def _lesen(self) -> None:
        while True:
            try:
                obs = await asyncio.to_thread(self._beobachten)
                self._obs = {k: v for k, v in obs.items() if isinstance(v, (int, float))}
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._fehler = f"Roboter antwortet nicht: {exc}"
            await asyncio.sleep(1.0 / TAKT_HZ)

    def _beobachten(self) -> dict[str, Any]:
        with self._lock:
            return dict(self.robot.get_observation())

    def _senden(self, aktion: dict[str, float]) -> None:
        with self._lock:
            self.robot.send_action(aktion)

    def state(self) -> DuckState:
        verbunden = bool(getattr(self.robot, "is_connected", False)) and not self._fehler
        gelenke = [float(self._obs.get(f"{g}.pos", 0.0)) for g in self.gelenke]
        return DuckState(t=time.monotonic(), connected=verbunden, backend="lerobot", koerper=self.koerper_art,
                         powered=self.powered and verbunden, enabled=self.enabled, twist=self.applied,
                         requested=self.applied, joints=gelenke, display_joints=gelenke,
                         limited_by=list(self.limited_by) + ([self._fehler] if self._fehler else []))

    # ── kontinuierliche Intents ───────────────────────────────────────────
    async def move(self, twist: Twist) -> None:
        if "raeder" not in self._faehig:
            return
        t = twist.clamped() if self.powered else Twist()
        if t == self.applied and t.is_zero():
            return
        self.applied = t
        await asyncio.to_thread(self._senden, {"x.vel": t.vx, "y.vel": t.vy, "theta.vel": math.degrees(t.vyaw)})

    async def head(self, head: Head) -> None:
        return None                      # kein Kopf – der Blick bleibt beim Gehirn

    async def mouth(self, open_: float) -> None:
        return None

    async def pose(self, pose: Pose, active: bool = True) -> None:
        return None

    # ── diskrete Befehle ──────────────────────────────────────────────────
    def _drehmoment(self, an: bool) -> bool:
        bus = getattr(self.robot, "bus", None)
        f = getattr(bus, "enable_torque" if an else "disable_torque", None)
        if f is None:
            return False
        with self._lock:
            f()
        return True

    async def init(self) -> IntentResult:
        if self._fehler:
            return IntentResult(False, self._fehler)
        await asyncio.to_thread(self._drehmoment, True)
        self.powered = True
        return IntentResult(True, "Motoren an")

    async def enable(self, on: bool) -> IntentResult:
        self.enabled = bool(on) and self.powered
        return IntentResult(True)

    async def _stillstand(self) -> None:
        if "raeder" in self._faehig:
            self.applied = Twist()
            try:
                await asyncio.to_thread(self._senden, {k: 0.0 for k in RAD_SCHLUESSEL})
            except Exception as exc:  # noqa: BLE001
                log.warning("LeRobot: Stillstand nicht gesendet: %s", exc)

    async def stop(self) -> IntentResult:
        if self._haltung_task:
            self._haltung_task.cancel()
            self._haltung_task = None
        await self._stillstand()
        return IntentResult(True)

    async def do(self, skill: str) -> IntentResult:
        return IntentResult(False, OHNE_BEWEGUNGEN)

    async def haltung(self, gelenke: dict[str, float], sekunden: float) -> IntentResult:
        """Gelenke (Namen wie bei LeRobot; „greifer“ = gripper) in `sekunden` (mindestens 0,5 s) anfahren."""
        if "arm" not in self._faehig and "greifer" not in self._faehig:
            return IntentResult(False, "Dieser LeRobot-Roboter hat keinen Arm")
        if not self.powered:
            return IntentResult(False, "Motoren sind aus – erst einschalten (aufwecken)")
        ziel: dict[str, float] = {}
        for name, wert in gelenke.items():
            g = GREIFER if name == "greifer" else name
            if g not in self.gelenke:
                return IntentResult(False, f"Gelenk „{name}“ gibt es nicht – bekannt: {', '.join(self.gelenke)}")
            ziel[g] = max(-ARM_GRENZE, min(ARM_GRENZE, float(wert)))
        start = {g: float(self._obs.get(f"{g}.pos", ziel[g])) for g in ziel}
        dauer = max(0.5, float(sekunden))
        if self._haltung_task:
            self._haltung_task.cancel()

        async def fahren() -> None:
            schritte = max(1, int(dauer * TAKT_HZ))
            for i in range(1, schritte + 1):
                if not self.powered:
                    return
                a = i / schritte
                await asyncio.to_thread(self._senden, {f"{g}.pos": start[g] + (ziel[g] - start[g]) * a for g in ziel})
                await asyncio.sleep(1.0 / TAKT_HZ)
        self._haltung_task = asyncio.create_task(fahren(), name="lerobot-haltung")
        return IntentResult(True, f"fährt {len(ziel)} Gelenke in {dauer:.1f} s an")

    async def sound(self, tag: str) -> IntentResult:
        return IntentResult(False, "LeRobot-Roboter haben keine eigenen Laute – Knowlin spricht über den PC")

    async def rest(self) -> IntentResult:
        return await self.relax()

    async def relax(self) -> IntentResult:
        """Not-Aus: sofort anhalten und Drehmoment aus; ohne Bus-Zugriff Verbindung trennen."""
        self.powered = False
        self.enabled = False
        if self._haltung_task:
            self._haltung_task.cancel()
            self._haltung_task = None
        await self._stillstand()
        try:
            if await asyncio.to_thread(self._drehmoment, False):
                return IntentResult(True, "stromlos")

            def trennen() -> None:
                with self._lock:
                    self.robot.disconnect()
            await asyncio.to_thread(trennen)
            return IntentResult(True, "stromlos (Verbindung getrennt)")
        except Exception as exc:  # noqa: BLE001
            return IntentResult(False, f"Drehmoment ließ sich nicht abschalten: {exc} – bitte Strom trennen")


def roboter_aus_optionen(optionen: dict[str, Any]) -> Any:
    """Einen LeRobot-Roboter aus `koerper_optionen` bauen: {"typ": "so101_follower", "port": "COM5", "id": "arm"}."""
    from lerobot.robots import RobotConfig, make_robot_from_config  # type: ignore[import-not-found]

    typ = str(optionen.get("typ") or "")
    if not typ:
        raise ValueError("Einstellungen → Körper → LeRobot: Robotertyp fehlt (z. B. so101_follower)")
    klasse = RobotConfig.get_choice_class(typ)
    werte = {k: v for k, v in optionen.items() if k in ("port", "id", "remote_ip") and v}
    return make_robot_from_config(klasse(**werte))


def baue_lerobot(cfg: Any) -> DuckBackend:
    """Fabrik für das Profil „lerobot“. Nur am echten Roboter – einen Simulator gibt es dafür noch nicht."""
    if cfg.backend != "robotd":
        return NichtVerfuegbar("lerobot", "Für LeRobot-Roboter hat Knowlin noch keinen Simulator – unter Einstellungen → "
                                          "Körper „Echter Roboter“ wählen")
    optionen = dict(getattr(cfg, "koerper_optionen", {}) or {})
    try:
        robot = roboter_aus_optionen(optionen)
    except ImportError:
        return NichtVerfuegbar("lerobot", "Das Paket „lerobot“ ist nicht installiert (pip install lerobot)")
    except Exception as exc:  # noqa: BLE001
        return NichtVerfuegbar("lerobot", f"LeRobot-Roboter ließ sich nicht anlegen: {exc}")
    return LeRobotKoerper(robot, typ=str(optionen.get("typ") or ""))
