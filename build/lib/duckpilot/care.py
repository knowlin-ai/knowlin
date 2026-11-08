"""Roboter-Pflege: Zustand, WLAN, Updates und Protokolle – über Pollens eigene Dienste.

Was sonst `robotctl` in der SSH-Konsole macht, hier mit Knöpfen:

* `robotd`   → `robot.health`   (Akku, Motortemperaturen, Regelschleife, IMU), `robot.vetbook` (Pflegeheft je Motor)
* `configd`  → `system.info`, `net.status`, `system.services`, `system.logs`
* `updaterd` → `update.status`, `update.check`, `update.apply` (erst Probelauf, dann echt)

Tunnel-Konvention (wie für robotd/tofd/updaterd): 7900 robotd, 7901 tofd, 7902 updaterd,
7903 mediad, 7904 configd. Updates einspielen verlangt auf dem Roboter Root-Rechte – lehnt
updaterd über den Tunnel ab, nennt duckpilot den Befehl für die SSH-Konsole.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from .backends.robotd import API_VERSION, RpcConnection

COMPONENT = "daemon"
LOG_UNITS = ("robotd", "mediad", "updaterd", "configd", "tofd", "padd", "btd")


def guess(robot_address: str, offset: int) -> str | None:
    if robot_address and robot_address.startswith("tcp:"):
        host, _, port = robot_address[4:].rpartition(":")
        if port.isdigit():
            return f"tcp:{host}:{int(port) + offset}"
    return None


async def call(address: str | None, name: str, method: str, params: dict[str, Any] | None = None,
               timeout: float = 8.0) -> Any:
    if not address:
        raise RuntimeError(f"Keine Adresse für {name}")
    conn = RpcConnection(address, name)
    await asyncio.wait_for(conn.connect(), 4.0)
    try:
        try:
            await conn.call("hello", {"api_version": API_VERSION}, timeout=3.0)
        except Exception:
            pass
        return await conn.call(method, params or {}, timeout=timeout)
    finally:
        await conn.close()


def root_hint(exc: Exception, command: str) -> str:
    msg = str(exc)
    if re.search(r"permission|root|denied|unauthori|forbidden|EPERM", msg, re.I):
        return f"{msg} – auf dem Roboter mit Root ausführen: ssh microduck@<IP> sudo {command}"
    return msg


class RobotCare:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.job: dict[str, Any] = {}

    @property
    def robot(self) -> str:
        return self.config.robot

    @property
    def updater(self) -> str | None:
        return self.config.updater or guess(self.robot, 2)

    @property
    def configd(self) -> str | None:
        return getattr(self.config, "configd", None) or guess(self.robot, 4)

    async def overview(self) -> dict[str, Any]:
        async def safe(coro):
            try:
                return {"ok": True, "daten": await coro}
            except Exception as exc:
                return {"ok": False, "fehler": f"{type(exc).__name__}: {exc}"}

        health, info, net, update, vet = await asyncio.gather(
            safe(call(self.robot, "robotd", "robot.health")),
            safe(call(self.configd, "configd", "system.info")),
            safe(call(self.configd, "configd", "net.status")),
            safe(call(self.updater, "updaterd", "update.status")),
            safe(call(self.robot, "robotd", "robot.vetbook")),
        )
        if vet.get("ok"):
            from .joints import vetbook_summary

            vet["daten"] = vetbook_summary(vet["daten"])
        return {"gesundheit": health, "system": info, "netz": net, "updates": update, "pflegeheft": vet,
                "job": self.job,
                "adressen": {"robotd": self.robot, "configd": self.configd, "updaterd": self.updater}}

    async def check(self) -> Any:
        return await call(self.updater, "updaterd", "update.check", {"component": COMPONENT}, timeout=60.0)

    async def apply(self, dry_run: bool) -> dict[str, Any]:
        self.job = {"laeuft": True, "probe": dry_run, "ergebnis": None, "fehler": None}
        try:
            res = await call(self.updater, "updaterd", "update.apply",
                             {"component": COMPONENT, "target": "latest", "options": {"dry_run": dry_run}},
                             timeout=1800.0)
            self.job.update(laeuft=False, ergebnis=res)
        except Exception as exc:
            self.job.update(laeuft=False, fehler=root_hint(exc, "robotctl update apply daemon"))
        return self.job

    async def logs(self, unit: str, lines: int = 200) -> dict[str, Any]:
        if unit not in LOG_UNITS:
            raise ValueError(f"Unbekannter Dienst – erlaubt: {', '.join(LOG_UNITS)}")
        lines = max(10, min(500, int(lines)))
        return await call(self.configd, "configd", "system.logs", {"unit": unit, "lines": lines, "boot": 0})

    async def services(self) -> Any:
        return await call(self.configd, "configd", "system.services")
