"""Roboter-Pflege: Zustand, WLAN, Updates und Protokolle – über Pollens eigene Dienste.

Was sonst `robotctl` in der SSH-Konsole macht, hier mit Knöpfen:

* `robotd`   → `robot.health`   (Akku, Motortemperaturen, Regelschleife, IMU), `robot.vetbook` (Pflegeheft je Motor)
* `configd`  → `system.info`, `net.status`, `system.services`, `system.logs`
* `updaterd` → `update.status`, `update.check`, `update.apply` (erst Probelauf, dann echt)
* `nfcd`     → `photo.list`, `photo.get`, `photo.delete` (v64), `photo.take` (v68) – die Fotos der Ente (seit 0.52)
* `robotd`   → `robot.volume`, `robot.setVolume` (v66), `robot.mode` (welche Spiele an sind, v67)

Tunnel-Konvention (wie für robotd/tofd/updaterd): 7900 robotd, 7901 tofd, 7902 updaterd,
7903 mediad, 7904 configd, 7905 nfcd (`-L 7905:/run/nfcd/nfc.sock`). Updates einspielen verlangt auf dem Roboter Root-Rechte – lehnt
updaterd über den Tunnel ab, nennt duckpilot den Befehl für die SSH-Konsole.
"""

from __future__ import annotations

import asyncio
import base64
import re
from typing import Any

from .backends.robotd import API_VERSION, RpcConnection

COMPONENT = "daemon"
LOG_UNITS = ("robotd", "mediad", "updaterd", "configd", "tofd", "padd", "btd", "nfcd", "autod")
FOTO_NAME = re.compile(r"^[0-9][0-9_-]{8,40}$")     # Pollens Name: Ortszeit, z. B. 2026-11-11_14-03-27 oder …-2
FOTO_MAX_BYTES = 8 * 1024 * 1024                    # mehr hat ein Foto der Kopfkamera nie
FOTO_STUECK = 16 * 1024                             # Pollens PhotoGetParams::MAX_LEN


def foto_name(name: Any) -> str:
    """Nur Pollens Fotonamen – kein Pfad, kein „..“ (nfcd lehnt das auch ab, wir fragen gar nicht erst)."""
    name = str(name or "").strip()
    if not FOTO_NAME.match(name):
        raise ValueError("Diesen Fotonamen kenne ich nicht")
    return name


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

    @property
    def nfcd(self) -> str | None:
        return getattr(self.config, "nfcd", None) or guess(self.robot, 5)

    async def overview(self) -> dict[str, Any]:
        async def safe(coro):
            try:
                return {"ok": True, "daten": await coro}
            except Exception as exc:
                return {"ok": False, "fehler": f"{type(exc).__name__}: {exc}"}

        health, info, net, update, vet, modus, laut = await asyncio.gather(
            safe(call(self.robot, "robotd", "robot.health")),
            safe(call(self.configd, "configd", "system.info")),
            safe(call(self.configd, "configd", "net.status")),
            safe(call(self.updater, "updaterd", "update.status")),
            safe(call(self.robot, "robotd", "robot.vetbook")),
            safe(call(self.robot, "robotd", "robot.mode")),
            safe(call(self.robot, "robotd", "robot.volume")),
        )
        if vet.get("ok"):
            from .joints import vetbook_summary

            vet["daten"] = vetbook_summary(vet["daten"])
        if modus.get("ok"):
            from .backends.robotd import pollen_schalter

            modus["daten"] = {**(modus["daten"] or {}), "spiele": pollen_schalter(modus["daten"])}
        return {"gesundheit": health, "system": info, "netz": net, "updates": update, "pflegeheft": vet,
                "modus": modus, "lautstaerke": laut, "job": self.job,
                "adressen": {"robotd": self.robot, "configd": self.configd, "updaterd": self.updater,
                             "nfcd": self.nfcd}}

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

    # ── Lautstärke (robotd, v66) ─────────────────────────────────────────
    async def set_volume(self, prozent: Any) -> Any:
        wert = max(0, min(100, int(round(float(prozent)))))
        return await call(self.robot, "robotd", "robot.setVolume", {"volume": wert})

    # ── Fotos der Ente (nfcd, v64/v68) – Bilder aus der Wohnung: nur am PC ──
    async def photos(self) -> list[dict[str, Any]]:
        res = await call(self.nfcd, "nfcd", "photo.list") or {}
        return [{"name": str(p.get("name")), "bytes": int(p.get("bytes") or 0), "taken_s": int(p.get("taken_s") or 0)}
                for p in (res.get("photos") or []) if isinstance(p, dict) and FOTO_NAME.match(str(p.get("name") or ""))]

    async def photo(self, name: Any, preview: bool = False) -> bytes:
        """Ein Foto (oder Pollens 360-Pixel-Vorschau) Stück für Stück holen, wie Pollens App über Bluetooth."""
        name = foto_name(name)
        if not self.nfcd:
            raise RuntimeError("Keine Adresse für nfcd")
        conn = RpcConnection(self.nfcd, "nfcd")
        await asyncio.wait_for(conn.connect(), 4.0)
        daten = bytearray()
        try:
            try:
                await conn.call("hello", {"api_version": API_VERSION}, timeout=3.0)
            except Exception:
                pass
            while True:
                params: dict[str, Any] = {"name": name, "offset": len(daten), "len": FOTO_STUECK}
                if preview:
                    params["preview"] = True
                stueck = await conn.call("photo.get", params, timeout=8.0) or {}
                roh = base64.b64decode(stueck.get("data") or "", validate=True)
                total = int(stueck.get("total") or 0)
                if total > FOTO_MAX_BYTES:
                    raise ValueError("Das Foto ist größer, als ein Foto der Kopfkamera sein kann")
                daten += roh
                if not roh or len(daten) >= total:
                    return bytes(daten[:total] if total else daten)
        finally:
            await conn.close()

    async def delete_photo(self, name: Any) -> bool:
        res = await call(self.nfcd, "nfcd", "photo.delete", {"name": foto_name(name)}) or {}
        return bool(res.get("deleted"))

    async def take_photo(self) -> Any:
        """photo.take (v68): Pose, Blitz-Countdown, Bild – etwa sieben Sekunden später steht es in photo.list."""
        return await call(self.nfcd, "nfcd", "photo.take", timeout=10.0)

    async def services(self) -> Any:
        return await call(self.configd, "configd", "system.services")
