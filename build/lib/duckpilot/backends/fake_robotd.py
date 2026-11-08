"""Der Lite-Simulator als robotd-kompatibler JSON-RPC-Server.

Zum Testen des Roboter-Pfads, bevor die Ente da ist:

    python -m duckpilot --fake-robotd tcp:127.0.0.1:7900
    python -m duckpilot --backend robotd --robot tcp:127.0.0.1:7900 --tof tcp:127.0.0.1:7900

Gesprochen wird dasselbe Zeilen-JSON-RPC wie von robotd (und tofd für
`tof.stream`). Es ist eine Teilmenge – genug für duckpilot, nicht für robotctl.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import Any

from ..api import DEFAULT_SKILLS, Head, Pose, Twist
from .robotd import API_VERSION, parse_address
from .sim import SimBackend

log = logging.getLogger(__name__)

NOTIFY_METHODS = {"robot.move", "robot.head", "robot.mouth", "robot.pose"}


class FakeRobotd:
    def __init__(self, sim: SimBackend | None = None) -> None:
        self.sim = sim or SimBackend()

    def policy_name(self) -> str:
        s = self.sim
        if s.skill and not s.skill.startswith("_"):
            return "sitstand" if s.skill == "sit_toggle" else s.skill
        if s.sitting:
            return "seated"
        if not s.powered or not s.enabled or s.fallen:
            return "held"
        moving = math.hypot(s.applied.vx, s.applied.vy) > 0.01 or abs(s.applied.vyaw) > 0.05
        return "walk" if moving else "stand"

    def robot_state(self) -> dict[str, Any]:
        st = self.sim.state()
        g = [0.0, 0.0, -1.0] if not st.fallen else [st.fall_side * 0.95, 0.0, -0.3]
        return {
            "t": st.t,
            "movement": {
                "requested": [st.requested.vx, st.requested.vy, st.requested.vyaw],
                "applied": [st.twist.vx, st.twist.vy, st.twist.vyaw],
                **({"limited_by": st.limited_by} if st.limited_by else {}),
            },
            "head": st.head.as_list(),
            "policy": self.policy_name(),
            "safety": {"fallen": st.fallen, "limp": not st.powered, "gravity": g, "gain": None, "picked_up": False},
            "control_loop": {"hz": 50.0},
            "joints": st.joints,
            "targets": st.joints,
            "velocities": [],
            "currents_ma": [],
            "odom": {"position": [st.x, st.y, 0.12], "yaw": st.yaw},
            "t_ns": int(st.t * 1e9),
        }

    async def dispatch(self, method: str, p: dict[str, Any]) -> Any:
        s = self.sim

        def res(r):
            return {"accepted": r.accepted, **({"reason": r.reason} if r.reason else {})}

        if method == "hello":
            return {"api_version": API_VERSION, "daemon_version": "0.0.0-duckpilot-sim", "revision": None}
        if method == "robot.move":
            await s.move(Twist(p.get("vx", 0), p.get("vy", 0), p.get("vyaw", 0)))
            return None
        if method == "robot.head":
            await s.head(Head(p.get("neck_pitch", 0), p.get("head_pitch", 0), p.get("head_yaw", 0), p.get("head_roll", 0)))
            return None
        if method == "robot.mouth":
            await s.mouth(p.get("open", 0))
            return None
        if method == "robot.pose":
            await s.pose(Pose(p.get("z", 0), p.get("roll", 0), p.get("pitch", 0)), p.get("active", True))
            return None
        if method == "robot.look":
            h = await s.look(p.get("x", 1), p.get("y", 0), p.get("z", 0))
            return {"head": vars(h), "clamped": False}
        if method == "robot.init":
            return res(await s.init())
        if method == "robot.enable":
            return res(await s.enable(bool(p.get("on", True)) if not p.get("toggle") else not s.enabled))
        if method == "robot.stop":
            return res(await s.stop())
        if method == "robot.do":
            return res(await s.do(str(p.get("skill"))))
        if method == "robot.sound":
            return res(await s.sound(str(p.get("tag"))))
        if method == "robot.rest":
            return res(await s.rest())
        if method == "robot.relax":
            s.powered = s.enabled = False
            return {"accepted": True}
        if method == "robot.policies":
            return {
                "mode": "walk", "enabled": True, "slots": [],
                "skills": [k for k in DEFAULT_SKILLS if k not in ("sit_toggle", "ground_pick")] + list(s.extra_skills),
                "homed": s.powered and s.skill is None, "sitting": s.sitting,
            }
        if method == "robot.skills":
            return {"skills": [{"name": k} for k in ("kick_left", "kick_right", "roulade")], "built_in": ["ground_pick", "sit_toggle"]}
        if method == "policy.fetch":   # eigentlich updaterd – der Test-Roboter beantwortet beides
            repo = str(p.get("repo", ""))
            if "/" not in repo:
                raise ValueError("repo muss org/name sein")
            return {"path": f"/var/lib/microduck/policies/{repo.replace('/', '--')}/policy.onnx", "repo": repo,
                    "revision": p.get("revision") or "main", "file": p.get("file") or "policy.onnx",
                    "origin": "official" if repo.startswith("pollen-robotics/") else "community",
                    "name": None, "description": "Testtrick aus dem Simulator",
                    "kind": "perpetual" if any(w in repo for w in ("walk", "sprint", "hill")) else "episodic",
                    "duration_s": 2.5, "idle": [0.0, 0.0, 0.0],
                    "encoding": "phase" if "pick" in repo else None, "chain": False}
        if method == "robot.setSkill":
            name = str(p.get("name", ""))
            if not name or not p.get("duration"):
                return {"accepted": False, "reason": "name und duration nötig"}
            s.extra_skills[name] = float(p["duration"])
            return {"accepted": True}
        if method == "robot.loadPolicy":
            slot = str(p.get("slot", ""))
            if slot not in ("walk", "stand", "sitstand", "ground_pick", "kick_left", "kick_right", "roulade"):
                return {"accepted": False, "reason": f"kein Platz '{slot}'"}
            s.slots[slot] = p.get("path")       # None = Standard
            return {"accepted": True}
        if method == "robot.health":
            return {"healthy": True, "battery": {"percent": round(100 * s.battery, 1), "volts": 6.4 + 2 * s.battery},
                    "cpu_temp_c": 52.0, "control_loop": {"target_hz": 50.0, "achieved_hz": 49.8},
                    "motors": {"max_temp_c": 41.0}}
        if method == "robot.vetbook":
            from ..api import JOINT_NAMES

            motors = [{"id": i + 1, "joint": n, "installed": "2026-05-01",
                       "wear": {"torqued_s": 36000.0 + 600 * i, "travel_rad": 4000.0 + 50 * i, "charge_as": 900.0,
                                "hottest_c": 48.0 + (i % 4), "hot_s": 30.0 * (i % 3),
                                "trips": {"overheat": 1 if n == "right_knee" else 0, "encoder": 0, "shock": 0,
                                          "overload": 2 if n == "right_knee" else 0}},
                       "identity": {}, "retired": False}
                      for i, n in enumerate(JOINT_NAMES) if n != "mouth"]
            return {"motors": motors, "events": [{"at": "2026-10-01T10:00:00Z", "kind": "note", "text": "Testeintrag"}],
                    "life": {}}
        # configd und updaterd – der Test-Roboter beantwortet alles auf einem Anschluss
        if method == "system.info":
            return {"name": "duck-test", "serial": "SIM00001", "uptime_seconds": int(s.t), "simulated": True}
        if method == "net.status":
            return {"state": "connected", "ssid": "Heimnetz", "signal": 72, "ip4": "192.168.1.42",
                    "ip6": None, "mac": "02:00:00:00:00:01", "iface": "wlan0"}
        if method == "system.services":
            return {"services": [{"unit": u, "state": "active"} for u in ("robotd", "mediad", "updaterd", "configd", "tofd")]}
        if method == "system.logs":
            unit = str(p.get("unit", "robotd"))
            return {"unit": unit, "lines": [f"{unit}: Testzeile {i}" for i in range(int(p.get("lines") or 5))][-50:],
                    "truncated": False}
        if method == "update.status":
            return {"components": [{"component": "daemon", "installed": "0.9.2", "phase": "idle", "healthy": True}]}
        if method == "update.check":
            return {"state": "available", "installed": "0.9.2", "candidate": "0.9.3", "mandatory": False,
                    "changelog": "Testversion"}
        if method == "update.apply":
            if (p.get("options") or {}).get("dry_run"):
                return {"outcome": "dry_run_passed", "candidate": "0.9.3"}
            raise PermissionError("update.apply needs root")
        raise KeyError(method)

    @staticmethod
    def media_frame(width: int = 64, height: int = 48) -> tuple[dict[str, Any], bytes]:
        """Ein Testbild im Format UYVY: grauer Verlauf."""
        row = bytearray()
        for x in range(0, width, 2):
            luma = 16 + int(219 * x / width)
            row += bytes((128, luma, 128, luma))
        data = bytes(row) * height
        return {"width": width, "height": height, "format": "UYVY", "bytes": len(data),
                "captured_at_unix_us": 0, "rotate": 0}, data

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        stream_task: asyncio.Task | None = None
        peer = writer.get_extra_info("peername")
        log.info("Client verbunden: %s", peer)

        async def send(obj: dict[str, Any]) -> None:
            writer.write((json.dumps(obj) + "\n").encode())
            await writer.drain()

        async def stream_state(hz: int) -> None:
            while True:
                await send({"jsonrpc": "2.0", "method": "robot.state", "params": self.robot_state()})
                await asyncio.sleep(1.0 / max(1, hz))

        async def stream_tof() -> None:
            while True:
                st = self.sim.state()
                frame = st.perception.tof_mm or [2000] * 64
                await send({"jsonrpc": "2.0", "method": "tof.frame", "params": {
                    "seq": int(st.t * 10), "at_us": int(st.t * 1e6), "t_ns": int(st.t * 1e9),
                    "rows": 8, "cols": 8, "distance_mm": frame, "status": [5] * 64,
                }})
                await asyncio.sleep(0.1)

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                method, params, msg_id = msg.get("method"), msg.get("params") or {}, msg.get("id")
                if method == "robot.subscribe" and stream_task is None:
                    await send({"jsonrpc": "2.0", "id": msg_id, "result": {"accepted": True, "walk": "lite-sim"}})
                    stream_task = asyncio.create_task(stream_state(int(params.get("hz") or 50)))
                    continue
                if method == "media.frame":
                    head, data = self.media_frame()
                    await send({"jsonrpc": "2.0", "id": msg_id, "result": head})
                    writer.write(data)
                    await writer.drain()
                    break
                if method == "tof.stream" and stream_task is None:
                    await send({"jsonrpc": "2.0", "id": msg_id, "result": {"accepted": True, "sensor": "VL53L5CX (sim)"}})
                    stream_task = asyncio.create_task(stream_tof())
                    continue
                try:
                    result = await self.dispatch(method, params)
                    if msg_id is not None:
                        await send({"jsonrpc": "2.0", "id": msg_id, "result": result})
                except PermissionError as exc:
                    if msg_id is not None:
                        await send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32000, "message": str(exc)}})
                except KeyError:
                    if msg_id is not None:
                        await send({"jsonrpc": "2.0", "id": msg_id,
                                    "error": {"code": -32601, "message": f"{method}: keine solche Methode (Lite-Sim)"}})
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            if stream_task:
                stream_task.cancel()
            writer.close()
            log.info("Client getrennt: %s", peer)


async def start_server(address: str, fake: FakeRobotd | None = None):
    fake = fake or FakeRobotd()
    await fake.sim.connect()
    kind, target = parse_address(address)
    if kind == "tcp":
        server = await asyncio.start_server(fake.handle, *target)
    else:
        server = await asyncio.start_unix_server(fake.handle, target)
    return server, fake


async def serve(address: str) -> None:
    server, _fake = await start_server(address)
    print(f"  🦆 Fake-robotd (Lite-Simulator) lauscht auf {address} – Strg+C beendet")
    async with server:
        await server.serve_forever()
