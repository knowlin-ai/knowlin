"""Backend für den echten Microduck – spricht robotd's JSON-RPC.

Das Protokoll ist das von `duck-ipc-proto` (pollen-robotics/microduck):
JSON-RPC 2.0, ein Objekt pro Zeile, über einen Unix-Socket (`/run/robotd.sock`
auf dem Roboter). Dasselbe spricht `robotctl`, das Gamepad (`padd`) und die
Konsole – dieses Backend ist einfach ein weiterer Client.

Erreichen des Roboters vom PC aus (auch unter Windows):

    ssh -N -L 7900:/run/robotd.sock microduck@<ip-der-ente>
    python -m duckpilot --backend robotd --robot tcp:127.0.0.1:7900

OpenSSH leitet dabei einen lokalen TCP-Port auf den Unix-Socket des Roboters
um. Gegen Pollens Simulator (`scripts/duck-sim` unter Linux/macOS/WSL) geht es
direkt: `--robot unix:~/.cache/duck-sim/duck.sock`.

Kontinuierliche Intents (robot.move/head/mouth/pose) gehen als Notification
raus – ohne id, ohne Antwort, so wie robotd es vorsieht. Diskrete Befehle
(robot.do, robot.init, …) sind Requests mit Antwort `{accepted, reason}`.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import math
import os
import sys
import time
from typing import Any

from ..api import DEFAULT_SKILLS, DuckBackend, DuckState, Head, IntentResult, Perception, Pose, Twist, tof_points
from .sim import display_joints

log = logging.getLogger(__name__)

API_VERSION = 50          # duck-ipc-proto, Stand 6.11.2026 – robotd meldet die Version nur, lehnt nicht ab
MOVING_POLICIES = {"walk", "stand", "held", "roller", ""}
SEATED_POLICIES = {"seated"}
CAM_HEIGHT = 0.21         # m, ToF über dem Boden im Stand (Schätzung)


def parse_address(address: str) -> tuple[str, Any]:
    address = os.path.expanduser(address.strip())
    if address.startswith("tcp:"):
        host, _, port = address[4:].rpartition(":")
        return "tcp", (host or "127.0.0.1", int(port))
    if address.startswith("unix:"):
        return "unix", os.path.expanduser(address[5:])
    if address.startswith("/") or address.startswith("~"):
        return "unix", address
    if ":" in address:
        host, _, port = address.rpartition(":")
        return "tcp", (host, int(port))
    raise ValueError(f"Adresse nicht verstanden: {address} (tcp:host:port oder unix:/pfad)")


async def open_line_stream(address: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    kind, target = parse_address(address)
    if kind == "tcp":
        return await asyncio.open_connection(*target, limit=4 * 1024 * 1024)
    if sys.platform == "win32":
        raise OSError("Unix-Sockets gehen unter Windows nicht direkt – per ssh -L auf einen TCP-Port umleiten")
    return await asyncio.open_unix_connection(target, limit=4 * 1024 * 1024)


class RpcError(Exception):
    pass


class RpcConnection:
    """Eine Leitung: Requests mit id, Notifications ohne, Antworten per Zeile."""

    def __init__(self, address: str, name: str) -> None:
        self.address = address
        self.name = name
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.ids = itertools.count(1)
        self.pending: dict[int, asyncio.Future] = {}
        self.on_notification = None
        self._reader_task: asyncio.Task | None = None

    @property
    def open(self) -> bool:
        return self.writer is not None and not self.writer.is_closing()

    async def connect(self) -> None:
        self.reader, self.writer = await open_line_stream(self.address)
        self._reader_task = asyncio.create_task(self._read_loop(), name=f"rpc-{self.name}")

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
        self.writer = None
        self._fail_all("Verbindung geschlossen")

    def _fail_all(self, why: str) -> None:
        for fut in self.pending.values():
            if not fut.done():
                fut.set_exception(RpcError(why))
        self.pending.clear()

    async def _read_loop(self) -> None:
        assert self.reader
        try:
            while True:
                line = await self.reader.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except ValueError:
                    log.warning("%s: unlesbar: %.120s", self.name, line)
                    continue
                if "id" not in msg or msg.get("id") is None:
                    if self.on_notification and "method" in msg:
                        self.on_notification(msg["method"], msg.get("params"))
                    continue
                fut = self.pending.pop(msg["id"], None)
                if fut is None or fut.done():
                    continue
                if msg.get("error"):
                    fut.set_exception(RpcError(msg["error"].get("message", "abgelehnt")))
                else:
                    fut.set_result(msg.get("result"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("%s: Verbindung verloren: %s", self.name, exc)
        finally:
            if self.writer:
                self.writer.close()
            self.writer = None
            self._fail_all("Verbindung verloren")

    async def _write(self, obj: dict[str, Any]) -> None:
        if not self.open:
            raise RpcError(f"{self.name}: nicht verbunden")
        assert self.writer
        self.writer.write((json.dumps(obj) + "\n").encode())
        await self.writer.drain()

    async def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 5.0) -> Any:
        call_id = next(self.ids)
        fut = asyncio.get_running_loop().create_future()
        self.pending[call_id] = fut
        await self._write({"jsonrpc": "2.0", "id": call_id, "method": method, "params": params or {}})
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self.pending.pop(call_id, None)

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self._write({"jsonrpc": "2.0", "method": method, "params": params})


def _intent(result: Any) -> IntentResult:
    if isinstance(result, dict) and "accepted" in result:
        return IntentResult(bool(result["accepted"]), result.get("reason"))
    return IntentResult(True)


class RobotdBackend(DuckBackend):

    runs_policies = True
    name = "robotd"

    def eigenschaften(self) -> frozenset[str]:
        """Der echte Roboter: Policies ja, Zurücksetzen nie; Tiefensensor nur mit tofd (seit 0.38)."""
        return frozenset({"beine", "kopf", "schnabel", "policies", "stimmbank"} | ({"tiefensensor"} if self.tof_conn else set()))

    def __init__(self, address: str, tof: str | None = None, state_hz: int = 25,
                 head_signs: list[float] | None = None, updater: str | None = None) -> None:
        super().__init__()
        self.stabilizer.use_servo_tuning()      # wie in der Physik gemessen (am Roboter noch ungeprüft)
        self.address = address
        self.tof_address = tof
        self.state_hz = state_hz
        self.head_signs = list(head_signs or [1.0, 1.0, 1.0, 1.0])
        self.cmd = RpcConnection(address, "robotd")
        self.stream = RpcConnection(address, "robotd-state")
        self.tof_conn = RpcConnection(tof, "tofd") if tof else None
        self.updater_address = updater or _guess_updater(address)
        self._raw: dict[str, Any] = {}
        self._raw_at = 0.0
        self._policies: dict[str, Any] = {}
        self._skills: list[str] = list(DEFAULT_SKILLS)
        self._tof: list[int] | None = None
        self._seen: list[dict[str, Any]] = []      # was die Kamera gerade erkennt (z. B. Laserpunkt)
        self._seen_at = 0.0
        self._tof_status: list[int] | None = None
        self._battery: float | None = None
        self._tasks: list[asyncio.Task] = []
        self._was_fallen = False
        self._last_skill: str | None = None
        self._closing = False
        self.info: dict[str, Any] = {}
        self._phase = 0.0
        self._phase_at = time.monotonic()

    # ── Verbindung ────────────────────────────────────────────────────────
    async def connect(self) -> None:
        self._closing = False
        self._tasks.append(asyncio.create_task(self._keep_connected(), name="robotd-connect"))

    async def close(self) -> None:
        self._closing = True
        for t in self._tasks:
            t.cancel()
        for c in (self.cmd, self.stream, self.tof_conn):
            if c:
                await c.close()

    async def _keep_connected(self) -> None:
        while not self._closing:
            try:
                if not self.cmd.open:
                    await self.cmd.connect()
                    self.info = await self.cmd.call("hello", {"api_version": API_VERSION}) or {}
                    log.info("robotd verbunden: %s", self.info)
                    self.emit("connected", message=f"Mit robotd verbunden ({self.address})")
                if not self.stream.open:
                    await self.stream.connect()
                    self.stream.on_notification = self._on_state
                    await self.stream.call("hello", {"api_version": API_VERSION})
                    await self.stream.call("robot.subscribe", {"hz": self.state_hz})
                if self.tof_conn and not self.tof_conn.open:
                    try:
                        await self.tof_conn.connect()
                        self.tof_conn.on_notification = self._on_tof
                        await self.tof_conn.call("tof.stream", {})
                    except Exception as exc:
                        log.warning("tofd nicht erreichbar: %s", exc)
                        await self.tof_conn.close()
                await self._poll_policies()
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self.cmd.open or self.stream.open:
                    self.emit("disconnected", message=f"robotd: {exc}")
                await self.cmd.close()
                await self.stream.close()
                log.warning("robotd (%s) nicht erreichbar: %s – neuer Versuch in 2 s", self.address, exc)
                await asyncio.sleep(2.0)

    async def _poll_policies(self) -> None:
        try:
            self._policies = await self.cmd.call("robot.policies", timeout=3.0) or {}
            if self._policies.get("skills"):
                built_in = [s for s in ("sit_toggle", "ground_pick") if s not in self._policies["skills"]]
                self._skills = list(dict.fromkeys([*built_in, *self._policies["skills"]]))
        except Exception as exc:
            if not self.cmd.open:
                raise
            log.debug("robot.policies: %s", exc)
        if int(time.monotonic()) % 5 == 0:
            try:
                health = await self.cmd.call("robot.health", timeout=3.0)
                self._battery = _find_fraction(health)
            except Exception:
                pass

    def _on_state(self, method: str, params: Any) -> None:
        if method != "robot.state" or not isinstance(params, dict):
            return
        self._raw = params
        now = time.monotonic()
        dt, self._raw_at = now - self._raw_at, now
        self._stabilize_from(params, dt)
        fallen = bool((params.get("safety") or {}).get("fallen"))
        if fallen and not self._was_fallen:
            self.emit("fall", message="Umgefallen (robotd meldet fallen)")
        self._was_fallen = fallen
        skill = self._skill_from(params.get("policy", ""))
        if skill != self._last_skill:
            if skill:
                self.emit("skill_start", skill=skill)
            elif self._last_skill:
                self.emit("skill_end", skill=self._last_skill)
            self._last_skill = skill

    def _stabilize_from(self, params: dict[str, Any], dt: float) -> None:
        """Kopf-Stabilisator am Roboter: Rumpflage aus der IMU (robot.state.imu.quat, w zuerst, Rumpf→Welt)
        und den Kopf sofort mit Ausgleich neu schicken – nicht erst beim nächsten 20-Hz-Takt der Engine."""
        if not self.stabilizer.enabled:
            return
        safety = params.get("safety") or {}
        if safety.get("fallen") or safety.get("limp", False) or params.get("policy", "") not in MOVING_POLICIES:
            # gestürzt, Motoren aus oder ein Skill/eine Policy führt: nicht am Kopf ziehen
            self.stabilizer.reset()
            return
        quat = ((params.get("imu") or {}).get("quat")) if isinstance(params.get("imu"), dict) else None
        if not (isinstance(quat, list) and len(quat) == 4 and all(isinstance(v, (int, float)) for v in quat)):
            return
        from ..motion.stabilizer import euler_from_quat

        imu = params.get("imu") or {}
        gyro = imu.get("gyro")
        gyro = tuple(float(g) for g in gyro) if isinstance(gyro, list) and len(gyro) == 3 else None
        pos = ((params.get("odom") or {}).get("position")) or []
        extra = {"x": float(pos[0]), "y": float(pos[1])} if len(pos) >= 2 else {}
        self.stabilizer.update(*euler_from_quat(*map(float, quat)), dt, gyro=gyro, **extra)
        wanted = getattr(self, "_head_wanted", None)
        now = time.monotonic()
        busy = getattr(self, "_stab_task", None)
        if wanted is None or (busy is not None and not busy.done()) or now - getattr(self, "_stab_sent", 0.0) < 0.02:
            return                       # höchstens 50-mal je Sekunde und nie mehr als ein Kopfbefehl unterwegs
        self._stab_sent = now
        try:
            self._stab_task = asyncio.get_running_loop().create_task(self.head(wanted))
        except RuntimeError:
            pass

    def _on_tof(self, method: str, params: Any) -> None:
        if method == "tof.frame" and isinstance(params, dict):
            self._tof = list(params.get("distance_mm") or [])
            self._tof_status = list(params.get("status") or [])

    @staticmethod
    def _skill_from(policy: str) -> str | None:
        if policy in MOVING_POLICIES or policy in SEATED_POLICIES:
            return None
        return "sit_toggle" if policy == "sitstand" else policy

    # ── Zustand ───────────────────────────────────────────────────────────
    def state(self) -> DuckState:
        r = self._raw
        fresh = self.stream.open and time.monotonic() - self._raw_at < 1.0
        mv = r.get("movement") or {}
        req = mv.get("requested") or [0, 0, 0]
        app = mv.get("applied") or [0, 0, 0]
        odom = r.get("odom") or {}
        pos = odom.get("position") or [0, 0, 0]
        safety = r.get("safety") or {}
        head = list(r.get("head") or [0, 0, 0, 0])
        head = [h * s for h, s in zip(head + [0] * (4 - len(head)), self.head_signs)]
        joints = list(r.get("joints") or [])
        policy = r.get("policy", "")
        skill = self._skill_from(policy)
        sitting = bool(self._policies.get("sitting")) or policy in SEATED_POLICIES
        twist = Twist(*map(float, app[:3]))
        powered = not bool(safety.get("limp", True))
        fallen = bool(safety.get("fallen"))
        now = time.monotonic()
        dt = min(0.2, now - self._phase_at)
        self._phase_at = now
        if math.hypot(twist.vx, twist.vy) > 0.01 or abs(twist.vyaw) > 0.08:
            freq = 2.0 + 2.0 * min(1.0, math.hypot(twist.vx, twist.vy) / 0.25)
            self._phase = (self._phase + 2 * math.pi * freq * dt) % (2 * math.pi)
        mouth = float(joints[9]) if len(joints) > 9 else 0.0
        head_obj = Head(*head[:4])
        shown = display_joints(sitting=sitting, skill=skill, progress=0.5, powered=powered, fallen=fallen,
                               twist=twist, phase=self._phase, head=head_obj, mouth=mouth)
        # Gemessene Winkel des echten Roboters (gleiche Konvention wie das 3D-Modell) haben Vorrang.
        if len(joints) == 15 and all(isinstance(v, (int, float)) and math.isfinite(v) and abs(v) < 3.3 for v in joints):
            shown = [float(v) for v in joints]
            shown[9] = max(0.0, min(1.0, mouth))
        return DuckState(
            t=float(r.get("t", 0.0)),
            connected=bool(fresh),
            backend="robotd",
            kopf_stabil=self.stabilizer.enabled,
            x=float(pos[0]), y=float(pos[1]), yaw=float(odom.get("yaw", 0.0)),
            twist=twist,
            requested=Twist(*map(float, req[:3])),
            limited_by=list(mv.get("limited_by") or []),
            head=head_obj,
            mouth=mouth,
            powered=powered,
            enabled=policy not in ("held", ""),
            sitting=sitting,
            fallen=fallen,
            picked_up=bool(safety.get("picked_up")),
            skill=skill,
            battery=self._battery,
            perception=self._with_seen(self._perception(float(pos[0]), float(pos[1]), float(odom.get("yaw", 0.0)),
                                                        head[2])),
            joints=joints,
            display_joints=shown,
            gait_phase=self._phase,
        )

    def joint_report(self) -> dict[str, Any]:
        """Aus robot.state: joints (gemessen), targets (Soll der Policy), currents_ma (Motorstrom)."""
        from ..joints import build

        r = self._raw
        safety = r.get("safety") or {}
        fresh = self.stream.open and time.monotonic() - self._raw_at < 1.0
        aktiv = fresh and not safety.get("limp", True) and not safety.get("fallen")
        hinweis = None if fresh else "Keine frischen Daten vom Roboter."
        return build(list(r.get("joints") or []), list(r.get("targets") or []) or None, None,
                     list(r.get("currents_ma") or []) or None, quelle="robotd", aktiv=bool(aktiv), hinweis=hinweis)

    async def vetbook(self) -> Any:
        """Pollens Pflegeheft: Verschleiß und Auslöser je Motor (robot.vetbook)."""
        return await self._call("robot.vetbook", {}, timeout=5.0)

    # ── Was die Kamera erkennt (Laserpunkt) ──────────────────────────────
    def see_objects(self, objects: list[dict[str, Any]]) -> None:
        self._seen = list(objects)
        self._seen_at = time.monotonic()

    def gaze(self) -> tuple[float, float]:
        """(Blickneigung + = nach unten, Kopfdrehung + = links) in rad – wie im ToF-Teil von _perception."""
        head = list(self._raw.get("head") or [0, 0, 0, 0]) + [0, 0, 0, 0]
        tilt = head[0] * self.head_signs[0] + head[1] * self.head_signs[1]
        return tilt, head[2] * self.head_signs[2]

    def _with_seen(self, p: Perception) -> Perception:
        from ..laser import fresh

        p.objects = fresh(self._seen, self._seen_at)
        return p

    def _perception(self, x: float = 0.0, y: float = 0.0, yaw: float = 0.0, head_yaw: float = 0.0) -> Perception:
        if not self._tof or len(self._tof) < 64:
            return Perception(source="robotd")
        status = self._tof_status or []
        head = list(self._raw.get("head") or [0, 0, 0, 0]) + [0, 0, 0, 0]
        # Blickneigung (Nacken + Kopf, + = nach unten). Vorzeichen ggf. per head_signs kalibrieren.
        tilt = head[0] * self.head_signs[0] + head[1] * self.head_signs[1]
        fov = math.radians(45)
        cols: list[float | None] = [None] * 8
        for row in range(6):
            elev = (3.5 - row) / 8 * fov - tilt
            floor = CAM_HEIGHT / math.sin(-elev) if elev < -0.02 else None
            for col in range(8):
                i = row * 8 + col
                d = self._tof[i]
                ok = not status or status[i] in (5, 9)
                if not ok or not 40 < d < 2000:
                    continue
                m = d / 1000.0
                if floor is not None and m > 0.85 * floor:
                    continue  # das ist der Boden, kein Hindernis
                horiz = m * math.cos(elev)
                cols[col] = horiz if cols[col] is None else min(cols[col], horiz)

        def mn(vals):
            v = [x for x in vals if x is not None]
            return round(min(v), 3) if v else None

        return Perception(
            tof_mm=list(self._tof[:64]),
            sectors={"links": mn(cols[0:3]), "mitte": mn(cols[3:5]), "rechts": mn(cols[5:8])},
            source="tofd",
            points=tof_points(self._tof, x=x, y=y, yaw=yaw, head_yaw=head_yaw, tilt=tilt,
                              cam_h=CAM_HEIGHT, status=status or None),
        )

    async def load_gait(self, repo: str, slot: str = "walk", file: str | None = None) -> IntentResult:
        """Wie `robotctl policy load walk <repo>`: updaterd holt die Datei, robotd tauscht den Platz."""
        if not self.cmd.open:
            return IntentResult(False, "nicht mit dem Roboter verbunden")
        repo, _, revision = repo.strip().partition("@")
        params: dict[str, Any] = {"repo": repo}
        if revision:
            params["revision"] = revision
        if file:
            params["file"] = file
        try:
            got = await self._updater("policy.fetch", params, timeout=180.0) or {}
        except Exception as exc:
            return IntentResult(False, f"Laden vom Hub fehlgeschlagen: {exc}")
        if got.get("kind") not in (None, "perpetual"):
            return IntentResult(False, "Das ist keine Gangart, sondern ein einmaliger Trick.")
        if not got.get("path"):
            return IntentResult(False, "updaterd hat keinen Dateipfad geliefert")
        res = await self._intent_call("robot.loadPolicy", {"slot": slot, "path": got["path"]}, timeout=30.0)
        if res.accepted:
            self.emit("trick", message=f"Neue Gangart von {repo}", name=slot, repo=repo)
            return IntentResult(True, f"Gangart „{slot}“ kommt jetzt von {repo} ({got.get('origin', 'community')})")
        return res

    async def reset_gait(self, slot: str = "walk") -> IntentResult:
        # Kein Pfad = zurück auf Pollens Satz (so macht es `robotctl policy reset`)
        res = await self._intent_call("robot.loadPolicy", {"slot": slot}, timeout=30.0)
        if res.accepted:
            self.emit("trick", message="Wieder Pollens Standard-Gangart", name=slot, repo="")
            return IntentResult(True, "wieder Pollens Standard-Gangart")
        return res

    def skills(self) -> list[str]:
        return list(self._skills)

    # ── Intents ───────────────────────────────────────────────────────────
    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        if self.cmd.open:
            try:
                await self.cmd.notify(method, params)
            except Exception as exc:
                log.debug("%s: %s", method, exc)

    async def move(self, twist: Twist) -> None:
        t = twist.clamped()
        await self._notify("robot.move", {"vx": t.vx, "vy": t.vy, "vyaw": t.vyaw})

    async def head(self, head: Head) -> None:
        self._head_wanted = head
        h = self.stabilizer.apply(head).clamped()
        s = self.head_signs
        await self._notify("robot.head", {
            "neck_pitch": h.neck_pitch * s[0], "head_pitch": h.head_pitch * s[1],
            "head_yaw": h.head_yaw * s[2], "head_roll": h.head_roll * s[3],
        })

    async def mouth(self, open_: float) -> None:
        await self._notify("robot.mouth", {"open": max(0.0, min(1.0, float(open_)))})

    async def pose(self, pose: Pose, active: bool = True) -> None:
        p = pose.clamped()
        await self._notify("robot.pose", {"z": p.z, "roll": p.roll, "pitch": p.pitch, "active": active})

    async def look(self, x: float, y: float, z: float) -> Head:
        # robotd rechnet die Blick-IK selbst gegen sein MJCF-Modell
        res = await self._call("robot.look", {"x": x, "y": y, "z": z, "neck_pitch": 0.0})
        head = (res or {}).get("head") if isinstance(res, dict) else None
        if head:
            return Head(head.get("neck_pitch", 0), head.get("head_pitch", 0), head.get("head_yaw", 0), head.get("head_roll", 0))
        return await super().look(x, y, z)

    # ── diskrete Befehle ──────────────────────────────────────────────────
    async def _call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 5.0) -> Any:
        if not self.cmd.open:
            raise RpcError("nicht mit robotd verbunden")
        return await self.cmd.call(method, params, timeout)

    async def _intent_call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 5.0) -> IntentResult:
        try:
            return _intent(await self._call(method, params, timeout))
        except Exception as exc:
            return IntentResult(False, str(exc))

    async def init(self) -> IntentResult:
        return await self._intent_call("robot.init", {}, timeout=10.0)

    async def enable(self, on: bool) -> IntentResult:
        return await self._intent_call("robot.enable", {"on": on, "toggle": False})

    async def stop(self) -> IntentResult:
        self._head_wanted = None
        self.stabilizer.reset()
        return await self._intent_call("robot.stop", {})

    async def relax(self) -> IntentResult:
        """Not-Aus: robot.relax – robotd schaltet das Drehmoment ab, die Ente sackt zusammen (robotctl robot relax)."""
        self._head_wanted = None
        self.stabilizer.reset()
        return await self._intent_call("robot.relax", {})

    async def do(self, skill: str) -> IntentResult:
        return await self._intent_call("robot.do", {"skill": skill})

    async def sound(self, tag: str) -> IntentResult:
        res = await self._intent_call("robot.sound", {"tag": tag})
        if res.accepted:
            self.emit("sound", tag=tag, on_robot=True)
        return res

    async def rest(self) -> IntentResult:
        self._head_wanted = None
        self.stabilizer.reset()
        return await self._intent_call("robot.rest", {}, timeout=15.0)

    # ── Tricks vom Hugging Face Hub ───────────────────────────────────────
    async def _updater(self, method: str, params: dict[str, Any], timeout: float) -> Any:
        """policy.* beantwortet updaterd, nicht robotd – eigener Socket, eigene Verbindung."""
        if not self.updater_address:
            raise RpcError("updaterd-Adresse fehlt (Tunnel: -L 7902:/run/updaterd.sock)")
        conn = RpcConnection(self.updater_address, "updaterd")
        await conn.connect()
        try:
            try:
                await conn.call("hello", {"api_version": API_VERSION}, timeout=3.0)
            except Exception:
                pass
            return await conn.call(method, params, timeout=timeout)
        finally:
            await conn.close()

    async def search_tricks(self, query: str) -> list[dict[str, Any]]:
        res = await self._updater("policy.search", {"query": query}, timeout=30.0)
        return list((res or {}).get("models") or [])

    async def add_trick(self, repo: str, name: str | None = None, seconds: float | None = None,
                        file: str | None = None) -> IntentResult:
        from ..hub import trick_name

        if not self.cmd.open:
            return IntentResult(False, "nicht mit dem Roboter verbunden")
        repo, _, revision = repo.strip().partition("@")
        params: dict[str, Any] = {"repo": repo}
        if revision:
            params["revision"] = revision
        if file:
            params["file"] = file
        try:
            got = await self._updater("policy.fetch", params, timeout=180.0) or {}
        except Exception as exc:
            return IntentResult(False, f"Laden vom Hub fehlgeschlagen: {exc}")
        enc = got.get("encoding") or got.get("command_encoding")
        if enc in ("phase", "posture_flag"):
            return IntentResult(False, "Diese Policy gehört in einen festen Platz des Roboters "
                                       "(Picken bzw. Hinsetzen) und lässt sich nicht als Trick hinzufügen.")
        skill = trick_name(repo, name or got.get("name"))
        duration = got.get("duration_s") or seconds
        if not duration:
            if got.get("kind") == "perpetual":
                return IntentResult(False, "Dieser Trick hält, bis man ihn beendet – sag mir, wie viele Sekunden.")
            duration = 4.0
        skill_params: dict[str, Any] = {"name": skill, "path": got.get("path"), "duration": float(duration)}
        if got.get("idle"):
            skill_params["unwind"] = got["idle"]
        if got.get("unwind_s"):
            skill_params["unwind_s"] = got["unwind_s"]
        if got.get("action_scale"):
            skill_params["action_scale"] = got["action_scale"]
        res = await self._intent_call("robot.setSkill", skill_params, timeout=10.0)
        if not res.accepted:
            return res
        await self._poll_policies()
        if skill not in self._skills:
            self._skills.append(skill)
        what = got.get("description") or ""
        self.emit("trick", message=f"Neuer Trick „{skill}“ von {repo}", name=skill, repo=repo)
        return IntentResult(True, f"als „{skill}“ geladen ({got.get('origin', 'community')}, {float(duration):.1f} s)"
                                  + (f" – {what}" if what else ""))


def _guess_updater(robot_address: str) -> str | None:
    """Tunnel-Konvention: 7900 robotd, 7901 tofd, 7902 updaterd."""
    if robot_address.startswith("tcp:"):
        host, _, port = robot_address[4:].rpartition(":")
        if port.isdigit():
            return f"tcp:{host}:{int(port) + 2}"
    return None


def _find_fraction(health: Any) -> float | None:
    """robot.health ist ausführlich; wir suchen nur den Akkustand (0–1).

    robotd meldet `battery: {volts, percent}` (duck-ipc-proto `Battery`, percent 0–100; 0 % = robotd setzt die Ente
    hin und schaltet ab). Fehlt `battery`, ist der Stand *unbekannt* – nie als leerer Akku anzeigen (Pollens Regel).
    Abgleich mit Pollens Quellen 6.11.2026: vorher suchten wir nur „fraction“ und sahen am echten Roboter nie einen Akku."""
    if not isinstance(health, dict):
        return None
    battery = health.get("battery")
    if isinstance(battery, dict):
        v = battery.get("percent")
        if isinstance(v, (int, float)) and not math.isnan(v):
            return max(0.0, min(1.0, float(v) / 100.0))
        for key in ("fraction", "charge", "level"):
            v = battery.get(key)
            if isinstance(v, (int, float)) and not math.isnan(v):
                return float(v)
    for value in health.values():
        if isinstance(value, dict) and "battery" in value:
            found = _find_fraction(value)
            if found is not None:
                return found
    return None
