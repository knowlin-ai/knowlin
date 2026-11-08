"""Reachy Mini als zweites Modul der Suite Knowlin (seit 0.38.1).

Pollens Reachy Mini ist ein kleiner Tischroboter: Kopf auf einer Stewart-Plattform (sechs Freiheitsgrade: vor/zurück,
seitlich, hoch/runter, Nicken, Neigen, Drehen), drehbarer Körper, zwei Antennen, Kamera, vier Mikrofone, Lautsprecher.
Er hat **keine Beine** – Laufen, Schießen, Aufheben und Purzelbaum gibt es hier nicht; die Fähigkeiten lehnen sie über
die Körper-Eigenschaften sauber ab (0.38.0). Das Hoverboard aus Pollens „Level Up“ (Fahren) kommt später.

Zwei Körper:

- `ReachyMiniSim` – im Simulator von duckpilot: steht im selben Wohnzimmer wie die Ente, als Tischroboter auf dem
  Couchtisch (seit 0.38.10; umstellen mit `platzieren`), Drehen wird zur Körperdrehung (±160°), der Kopf folgt den
  Kopfbefehlen, die Antennen zeigen Gefühle und wackeln beim Sprechen. Sehen über die Kamera wie die Ente; keinen
  Tiefensensor.
- `ReachyMiniDaemon` – der echte Reachy Mini (Lite am USB oder Wireless im WLAN) über die REST-Schnittstelle von Pollens
  Daemon (`http://localhost:8000` bzw. `http://reachy-mini.local:8000`). Ohne Pollens SDK als Abhängigkeit – nur HTTP.
  Geprüft gegen Pollens eigenen Testmodus `reachy-mini-daemon --mockup-sim` (Version 1.13), nicht an einem echten Gerät.

Grenzen aus Pollens Doku (core-concept.md): Kopf nicken/neigen ±40°, Kopf drehen ±180°, Körper drehen ±160°, Kopf und
Körper höchstens 65° auseinander. duckpilot bleibt darunter.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
import urllib.request
from typing import Any

from ..api import NICHT_OHNE_BEINE, DuckBackend, DuckState, Head, IntentResult, Perception, Pose, Twist, wrap_angle
from .reachy_apps import PollenApps
from .reachy_ausdruck import ANTENNE_RUHE, ANTENNE_SCHLAF, SCHLAF_LAGE, Aufnahme, Ausdruck, antennen_aus_mund
from .reachy_kinematik import GRENZE as _GRENZE
from .reachy_kinematik import begrenzen, gerundet
from .sim import SimBackend

__all__ = ["ANTENNE_RUHE", "KOERPER_GRAD", "NICHT_OHNE_BEINE", "ReachyMiniDaemon", "ReachyMiniSim", "antennen_aus_mund",
           "kopf_ziel"]

log = logging.getLogger(__name__)

KOERPER_GRAD = 160.0          # Körperdrehung höchstens (Pollen: ±160°)
KOPF_KIPP = math.radians(38)  # Nicken/Neigen (Pollen: ±40°, etwas Luft)
KOPF_DREH = math.radians(60)  # Kopf gegen Körper (Pollen: höchstens 65° auseinander)
KOPF_Z_M = 0.02               # Kopf hoch/runter
SCHLAF_NICKEN = 0.42          # Kopf im Schlaf nach vorn gesenkt (Pollens SLEEP_HEAD_POSE ≈ 24°)
EIGENSCHAFTEN = frozenset({"kopf", "antennen", "koerperdrehung", "kamera", "mikrofon", "lautsprecher",
                           "pollen_bewegungen"})
FUSS_M = 0.065               # Fuß von Reachy Mini ≈ 13 cm Durchmesser (der Körper darüber ist etwas breiter)
STELL_RAND_M = 0.01          # so viel Platz rundum braucht der Fuß auf einer Fläche
# Worauf man Reachy stellen kann (Name enthält …) – Sofa (weich) und Pflanze sind keine Stellflächen
STELLFLAECHEN = ("tisch", "hocker", "kiste", "regal", "kommode", "schrank", "bank", "stuhl")
STANDARD_FLAECHE = "Couchtisch"


def kopf_ziel(head: Head, pose: Pose | None = None) -> dict[str, float]:
    """Kopfbefehl von duckpilot (Microduck-Gelenke) → Kopflage von Reachy Mini (x, y, z in m, roll/pitch/yaw in rad).
    Nicken = Kopf + Hals der Ente; Drehen relativ zum Körper; Hoch/runter aus der Haltung (Pose.z)."""
    pitch = max(-KOPF_KIPP, min(KOPF_KIPP, head.head_pitch - head.neck_pitch * 0.6))
    roll = max(-KOPF_KIPP, min(KOPF_KIPP, head.head_roll * 1.6))
    yaw = max(-KOPF_DREH, min(KOPF_DREH, head.head_yaw))
    z = 0.0 if pose is None else max(-KOPF_Z_M, min(KOPF_Z_M, pose.z * 0.8))
    return {"x": 0.0, "y": 0.0, "z": z, "roll": roll, "pitch": pitch, "yaw": yaw}


def zusammen(basis: dict[str, float], zusatz: dict[str, float]) -> dict[str, float]:
    """Kopflage + Ausdruck (relativ zum Körper) – nur, was die Stewart-Plattform wirklich erreicht, ohne dass der Kopf
    in den Körper taucht (`reachy_kinematik.begrenzen`, eine Stelle für Simulator und echten Reachy)."""
    return begrenzen({k: basis.get(k, 0.0) + zusatz.get(k, 0.0) for k in _GRENZE})


class ReachyMiniSim(SimBackend):
    """Reachy Mini im Simulator von duckpilot (gleiches Wohnzimmer, gleiche Dinge, Kamera statt Tiefensensor)."""

    koerper_art = "reachy_mini"

    def __init__(self, realtime: bool = True, seed: int | None = None) -> None:
        super().__init__(realtime=realtime, seed=seed)
        self.yaw0 = self.yaw
        self.antennen = [-ANTENNE_RUHE, ANTENNE_RUHE]
        self.antennen_ziel: list[float] | None = None      # ausdrücklich gesetzt (Gefühle) – sonst Ausdruck/Mund
        self._antennen_bis = 0.0
        self._sprech_phase = 0.0
        self.ausdruck = Ausdruck()
        self._zusatz: dict[str, float] = {}
        self._bild: dict[str, float] | None = None          # Bild einer laufenden Aufnahme von Pollen
        self.stand_z = 0.0                                  # Höhe der Standfläche (Tischroboter: auf dem Couchtisch)
        self.standflaeche = ""
        self.platzieren(STANDARD_FLAECHE)

    # ── Wo er steht (seit 0.38.10): Tischroboter, Standard auf dem Couchtisch ─────────
    def _flaeche(self, name: str) -> Any:
        n = str(name or "").strip().lower()
        return next((m for m in [*self.world_model.boxes, *self.world_model.cylinders] if m.name.lower() == n), None)

    def platz_pruefen(self, flaeche: str) -> str | None:
        """Kann Reachy dort stehen? None = ja, sonst der Grund. „boden“ geht immer."""
        if str(flaeche or "").strip().lower() in ("boden", "fußboden", "floor"):
            return None
        m = self._flaeche(flaeche)
        if m is None:
            return f"Kenne keine Fläche namens „{flaeche}“"
        if not any(w in m.name.lower() for w in STELLFLAECHEN):
            return f"Auf {m.name} kann Reachy nicht sicher stehen"
        innen = m.r if hasattr(m, "r") else min(m.sx, m.sy) / 2
        if innen < FUSS_M + STELL_RAND_M:
            return f"{m.name} ist zu klein für Reachys Fuß"
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
                for r in (ausdehnung + FUSS_M + 0.08, ausdehnung + FUSS_M + 0.2):
                    x, y = m.x + r * math.cos(a), m.y + r * math.sin(a)
                    if self.world_model.collide(x, y, FUSS_M + 0.02) is None:
                        return x, y
        return self.START_POSE[0], self.START_POSE[1]

    def platzieren(self, flaeche: str) -> tuple[bool, str]:
        """Reachy auf eine Fläche stellen (Mitte, Blick zum Sofa) oder auf den Boden – nur im Simulator, mit der Hand."""
        grund = self.platz_pruefen(flaeche)
        if grund is not None:
            return False, grund
        m = None if str(flaeche).strip().lower() in ("boden", "fußboden", "floor") else self._flaeche(flaeche)
        if m is None:
            x, y = self._platz_am_boden()
            self.stand_z, self.standflaeche = 0.0, ""
            text = "Reachy steht jetzt auf dem Boden"
        else:
            x, y = m.x, m.y
            self.stand_z, self.standflaeche = float(m.h), m.name
            text = f"Reachy steht jetzt auf: {m.name}"
        self._ente_setzen(x, y, self._blick_zum_sofa(x, y))
        return True, text

    def szene_zuruecksetzen(self, ente: bool = True) -> dict[str, Any]:
        out = super().szene_zuruecksetzen(ente=False)
        if ente:                                           # Reachy fällt nicht – zurück auf seinen Standardplatz
            out["ente"] = self.platzieren(STANDARD_FLAECHE)[0]
        return out

    def _push_items(self) -> None:
        if self.stand_z <= 0.0:                            # auf dem Tisch schiebt er nichts am Boden
            super()._push_items()

    # ── Körper ───────────────────────────────────────────────────────────
    def eigenschaften(self) -> frozenset[str]:
        return EIGENSCHAFTEN | {"simulator", "zuruecksetzen"}

    def skills(self) -> list[str]:
        return []

    def gespraech(self, zustand: str | None, sekunden: float = 4.0) -> None:
        self.ausdruck.setze(zustand, sekunden)

    async def pollen_bewegung(self, aufnahme: Aufnahme) -> IntentResult:
        """Eine Aufnahme aus Pollens Bibliothek abspielen (Kopf, Antennen, Körper; der Ton läuft im Browser)."""
        if not self.powered or self.sitting:
            return IntentResult(False, "schläft – erst aufwecken")
        self.ausdruck.spielen(aufnahme)
        return IntentResult(True, f"{aufnahme.name} ({aufnahme.dauer:.1f} s)")

    async def stop(self) -> IntentResult:
        self.ausdruck.abbrechen()
        return await super().stop()

    async def sound(self, tag: str) -> IntentResult:
        return IntentResult(False, "Reachy ist keine Ente – keine Entenlaute (Töne kommen mit Pollens Bewegungen)")

    async def do(self, skill: str) -> IntentResult:
        if skill == "sit_toggle":
            return await (self.init() if self.sitting else self.rest())
        return IntentResult(False, NICHT_OHNE_BEINE)

    async def move(self, twist: Twist) -> None:
        # Kein Laufen: nur Drehen bleibt – als Drehung des Körpers auf dem Sockel
        self.requested = Twist(0.0, 0.0, twist.clamped().vyaw)
        self._last_move = self.t
        if abs(twist.vx) > 0.01 or abs(twist.vy) > 0.01:
            self.limited_by = [NICHT_OHNE_BEINE]

    async def antennen_setzen(self, rechts: float, links: float, sekunden: float = 1.5) -> IntentResult:
        if not self.powered:
            return IntentResult(False, "schläft – erst aufwecken")
        g = math.radians(170)
        self.antennen_ziel = [max(-g, min(g, rechts)), max(-g, min(g, links))]
        self._antennen_bis = self.t + max(0.2, min(10.0, sekunden))
        return IntentResult(True)

    def _step_base(self, dt: float) -> None:
        x, y = self.x, self.y
        super()._step_base(dt)
        self.x, self.y = x, y                                   # steht auf dem Tisch bzw. Boden – bewegt sich nicht
        if self._bild is not None:                              # Aufnahme dreht den Körper (Pollen: gegen den Sockel)
            soll = self.yaw0 + self._bild["koerper"]
            self.yaw = wrap_angle(self.yaw + wrap_angle(soll - self.yaw) * min(1.0, dt / 0.08))
        grenze = math.radians(KOERPER_GRAD)
        rel = wrap_angle(self.yaw - self.yaw0)
        if abs(rel) > grenze:
            self.yaw = wrap_angle(self.yaw0 + math.copysign(grenze, rel))
            self.applied = Twist(0.0, 0.0, 0.0)
            self.limited_by = [f"Körper ist am Anschlag ({KOERPER_GRAD:.0f}°)"]
        self.gait_phase = 0.0

    def _step_actuators(self, dt: float) -> None:
        super()._step_actuators(dt)
        wach = self.powered and not self.sitting
        self._zusatz, aus_ant, self._bild = self.ausdruck.schritt(dt, self.mouth_now, wach)
        if not wach:
            ziel = [-ANTENNE_SCHLAF, ANTENNE_SCHLAF]
        elif self._bild is not None:
            ziel = [self._bild["antenne_r"], self._bild["antenne_l"]]
        elif self.antennen_ziel is not None and self.t < self._antennen_bis:
            ziel = self.antennen_ziel
        else:
            self.antennen_ziel = None
            self._sprech_phase += dt * 9.0
            ziel = aus_ant if aus_ant is not None and self.mouth_now <= 0.02 else \
                antennen_aus_mund(self.mouth_now, self._sprech_phase)
        k = min(1.0, dt / 0.12)
        self.antennen = [a + (b - a) * k for a, b in zip(self.antennen, ziel)]

    def _update_tof(self) -> None:
        self._tof, self._points, self._sectors = [], [], {}    # kein Tiefensensor; Sehen über die Kamera

    def _fall(self, why: str) -> None:                         # steht fest – fällt nicht um
        return None

    def state(self) -> DuckState:
        st = super().state()
        st.koerper = self.koerper_art
        st.antennen = [round(a, 4) for a in self.antennen]
        st.battery = None
        st.gait_phase = 0.0
        st.perception = Perception(objects=st.perception.objects, source="sim")
        if self.sitting or not self.powered:
            st.head = Head(-0.2, SCHLAF_NICKEN, 0.0, 0.0)
            lage = dict(SCHLAF_LAGE)
        elif self._bild is not None:
            lage = gerundet(zusammen({k: v for k, v in self._bild.items() if k in _GRENZE}, {}), 4)
        else:                                                   # nur Erreichbares; Runden schiebt nie über die Grenze
            lage = gerundet(zusammen(kopf_ziel(st.head, st.pose), self._zusatz), 4)
        st.kopf_lage = {**lage, "koerper": round(wrap_angle(self.yaw - self.yaw0), 4)}
        st.stand_z, st.standflaeche = round(self.stand_z, 4), self.standflaeche
        return st

    def fassung(self, skill: str) -> dict[str, str]:
        return {"fassung": "Reachy Mini im Simulator von duckpilot – Kinematik wie Pollens, ohne Pollens MuJoCo-Physik"}

    def _ente_setzen(self, x: float, y: float, yaw: float) -> None:
        super()._ente_setzen(x, y, yaw)
        self.yaw0 = yaw


class ReachyMiniDaemon(DuckBackend):
    """Der echte Reachy Mini über Pollens Daemon (REST). Ungetestet an echter Hardware – „help wanted“.

    Kopf, Körperdrehung und Antennen gehen als `set_target` (bis 20× je Sekunde, nur wenn sich etwas ändert), Zustand
    kommt aus `/api/state/full`. Aufwecken/Schlafen über Pollens eigene Bewegungen, Not-Aus hält die Drehung an.
    """

    name = "reachy_mini"
    koerper_art = "reachy_mini"

    def __init__(self, adresse: str = "http://localhost:8000", timeout: float = 2.0) -> None:
        super().__init__()
        self.adresse = adresse.rstrip("/")
        self.timeout = timeout
        self._task: asyncio.Task | None = None
        self._verbunden = False
        self.fehler: str | None = None
        self._head = Head()
        self._pose = Pose()
        self._mund = 0.0
        self._vyaw = 0.0
        self._body_yaw = 0.0
        self._antennen_ziel: list[float] | None = None
        self._antennen_bis = 0.0
        self._wach = False
        self._schlaeft = False                      # schlafen gelegt: Motoren bleiben an, aber keine Ziele schicken
        self._gesendet: dict[str, Any] | None = None
        self._zustand: dict[str, Any] = {}
        self._last = time.monotonic()
        self._phase = 0.0
        self.ausdruck = Ausdruck()
        self._spielt_bis = 0.0                      # eine Aufnahme läuft auf dem Roboter – so lange keine Ziele
        self._spielt_uuid: str | None = None
        self.apps = PollenApps(self._rufen)          # Pollens Apps (seit 0.38.19)
        self._app_abfrage = 0.0

    def eigenschaften(self) -> frozenset[str]:
        return EIGENSCHAFTEN

    def skills(self) -> list[str]:
        return []

    def gespraech(self, zustand: str | None, sekunden: float = 4.0) -> None:
        self.ausdruck.setze(zustand, sekunden)

    async def pollen_bewegung(self, aufnahme: Aufnahme) -> IntentResult:
        """Pollens Daemon spielt die Aufnahme selbst ab (mit Ton aus dem Lautsprecher des Roboters)."""
        if not self._wach:
            return IntentResult(False, "schläft – erst aufwecken")
        from urllib.parse import quote

        try:
            r = await self._rufen("POST", f"/api/move/play/recorded-move-dataset/{aufnahme.datensatz}/{quote(aufnahme.name)}")
        except Exception as exc:  # noqa: BLE001
            return IntentResult(False, f"Reachy Mini spielt das nicht ab: {exc}")
        self._spielt_uuid = (r or {}).get("uuid") if isinstance(r, dict) else None
        self._spielt_bis = time.monotonic() + aufnahme.dauer + 0.3
        return IntentResult(True, f"{aufnahme.name} ({aufnahme.dauer:.1f} s)")

    # ── HTTP ─────────────────────────────────────────────────────────────
    def _http(self, methode: str, pfad: str, body: dict[str, Any] | None = None) -> Any:
        daten = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(f"{self.adresse}{pfad}", data=daten, method=methode,
                                     headers={"Content-Type": "application/json"} if daten else {})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 – Adresse kommt aus den Einstellungen
            text = r.read().decode() or "null"
        return json.loads(text)

    async def _rufen(self, methode: str, pfad: str, body: dict[str, Any] | None = None) -> Any:
        return await asyncio.to_thread(self._http, methode, pfad, body)

    # ── Lebenszyklus ─────────────────────────────────────────────────────
    async def connect(self) -> None:
        try:
            await self._rufen("GET", "/api/daemon/status")
            self._verbunden, self.fehler = True, None
        except Exception as exc:  # noqa: BLE001
            self._verbunden, self.fehler = False, f"Reachy Mini nicht erreichbar ({self.adresse}): {exc}"
            log.warning(self.fehler)
        self._task = asyncio.get_running_loop().create_task(self._schleife())

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def _schleife(self) -> None:
        while True:
            try:
                self._zustand = await self._rufen("GET", "/api/state/full")
                self._verbunden, self.fehler = True, None
                self._wach = self._zustand.get("control_mode") == "enabled" and not self._schlaeft
                if time.monotonic() > self._app_abfrage:          # läuft eine von Pollens Apps? (alle 2 s)
                    self._app_abfrage = time.monotonic() + 2.0
                    try:
                        await self.apps.status()
                    except Exception:  # noqa: BLE001 – ältere Daemons ohne Apps
                        self.apps.laufend = None
                await self._senden()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._verbunden, self.fehler = False, f"Reachy Mini nicht erreichbar: {exc}"
                await asyncio.sleep(1.0)
            await asyncio.sleep(0.05)

    async def _senden(self) -> None:
        jetzt = time.monotonic()
        dt, self._last = jetzt - self._last, jetzt
        zusatz, aus_ant, _ = self.ausdruck.schritt(dt, self._mund, self._wach)
        if not self._wach:
            return
        if jetzt < self._spielt_bis or self.apps.aktiv:   # Pollens Aufnahme oder App läuft – nicht dazwischenfunken
            if self._zustand.get("body_yaw") is not None:
                self._body_yaw = float(self._zustand["body_yaw"])
            return
        grenze = math.radians(KOERPER_GRAD)
        self._body_yaw = max(-grenze, min(grenze, self._body_yaw + self._vyaw * dt))
        self._phase += dt * 9.0
        if self._antennen_ziel and jetzt < self._antennen_bis:
            antennen = self._antennen_ziel
        elif aus_ant is not None and self._mund <= 0.02:
            antennen = aus_ant
        else:
            antennen = antennen_aus_mund(self._mund, self._phase)
        lage = gerundet(zusammen(kopf_ziel(self._head, self._pose), zusatz), 5)   # nur Erreichbares (0.38.10)
        koerper = round(self._body_yaw, 5)
        lage["yaw"] += koerper                          # Pollen: Kopflage in der Welt, der Kopf dreht mit dem Körper
        ziel = {"target_head_pose": lage,
                "target_antennas": [round(a, 4) for a in antennen], "target_body_yaw": koerper}
        if ziel != self._gesendet:
            antwort = await self._rufen("POST", "/api/move/set_target", ziel)
            # Pollens Daemon verwirft Ziele, solange eine eigene Bewegung läuft ({"status": "ignored", "reason":
            # "move_running"}, Abgleich 6.11.2026) – dann nicht als gesendet merken, sonst bliebe der Kopf danach stehen
            if not (isinstance(antwort, dict) and antwort.get("status") == "ignored"):
                self._gesendet = ziel

    def state(self) -> DuckState:
        z = self._zustand or {}
        kopf = z.get("head_pose") or {}
        ant = z.get("antennas_position") or []
        koerper = float(z.get("body_yaw") or 0.0)
        lage = {k: float(kopf.get(k) or 0.0) for k in ("x", "y", "z", "roll", "pitch", "yaw")}
        lage["yaw"] = wrap_angle(lage["yaw"] - koerper)  # in duckpilot relativ zum Körper
        return DuckState(
            t=time.monotonic(), connected=self._verbunden, backend="robotd", koerper=self.koerper_art,
            yaw=koerper, head=Head(0.0, lage["pitch"], lage["yaw"], lage["roll"]),
            mouth=self._mund, powered=self._wach, enabled=self._wach, sitting=not self._wach,
            antennen=[float(a) for a in ant[:2]], perception=Perception(source="reachy_mini"),
            kopf_lage={**lage, "koerper": koerper},
            limited_by=[self.fehler] if self.fehler else [],
        )

    # ── Intents ──────────────────────────────────────────────────────────
    async def move(self, twist: Twist) -> None:
        self._vyaw = twist.clamped().vyaw

    async def head(self, head: Head) -> None:
        self._head = head.clamped()

    async def mouth(self, open_: float) -> None:
        self._mund = max(0.0, min(1.0, float(open_)))

    async def pose(self, pose: Pose, active: bool = True) -> None:
        self._pose = pose.clamped() if active else Pose()

    async def antennen_setzen(self, rechts: float, links: float, sekunden: float = 1.5) -> IntentResult:
        g = math.radians(170)
        self._antennen_ziel = [max(-g, min(g, rechts)), max(-g, min(g, links))]
        self._antennen_bis = time.monotonic() + max(0.2, min(10.0, sekunden))
        return IntentResult(True)

    async def init(self) -> IntentResult:
        try:
            await self._rufen("POST", "/api/motors/set_mode/enabled")
            await self._rufen("POST", "/api/move/play/wake_up")
            self._schlaeft, self._wach, self._gesendet = False, True, None
            return IntentResult(True, "wacht auf")
        except Exception as exc:  # noqa: BLE001
            return IntentResult(False, f"Aufwecken ging nicht: {exc}")

    async def enable(self, on: bool) -> IntentResult:
        return await (self.init() if on else self.rest())

    async def stop(self) -> IntentResult:
        """Anhalten: Körperdrehung sofort an der gemessenen Stelle anhalten, Antennen-Ziele verwerfen, Aufnahme und App
        stoppen. Der Not-Aus schaltet danach die Motoren ab (`relax`, seit 0.38.24)."""
        self._vyaw = 0.0
        if self._zustand and self._zustand.get("body_yaw") is not None:
            self._body_yaw = float(self._zustand["body_yaw"])
        self._antennen_ziel = None
        if self._spielt_uuid and time.monotonic() < self._spielt_bis:
            try:
                await self._rufen("POST", "/api/move/stop", {"uuid": self._spielt_uuid})
            except Exception as exc:  # noqa: BLE001
                log.warning("Aufnahme ließ sich nicht anhalten: %s", exc)
        self._spielt_bis, self._spielt_uuid = 0.0, None
        if self.apps.aktiv:                             # Not-Aus hält auch Pollens App an (seit 0.38.19)
            try:
                await self.apps.stoppen()
            except Exception as exc:  # noqa: BLE001
                log.warning("Pollens App ließ sich nicht anhalten: %s", exc)
        return IntentResult(True)

    async def relax(self) -> IntentResult:
        """Not-Aus: Motoren sofort aus (Pollens /api/motors/set_mode/disabled) – der Kopf sinkt auf die Plattform."""
        try:
            await self._rufen("POST", "/api/motors/set_mode/disabled")
            self._schlaeft, self._wach = True, False
            return IntentResult(True, "stromlos")
        except Exception as exc:  # noqa: BLE001
            return IntentResult(False, f"Motoren ließen sich nicht abschalten: {exc}")

    async def do(self, skill: str) -> IntentResult:
        if skill == "sit_toggle":
            return await (self.init() if not self._wach else self.rest())
        return IntentResult(False, NICHT_OHNE_BEINE)

    async def sound(self, tag: str) -> IntentResult:
        return IntentResult(False, "Töne der Stimmbank gibt es nur bei der Microduck – Reachy Mini spricht über den PC")

    async def rest(self) -> IntentResult:
        try:
            await self._rufen("POST", "/api/move/play/goto_sleep")
            self._schlaeft, self._wach = True, False
            return IntentResult(True, "schläft")
        except Exception as exc:  # noqa: BLE001
            return IntentResult(False, f"Schlafen ging nicht: {exc}")
