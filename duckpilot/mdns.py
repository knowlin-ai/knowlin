"""Knowlin im Heimnetz unter einem festen Namen finden: `http://knowlin.local:8766` (T2, seit 0.38.28).

Wunsch: Knowlin soll auf Tablet und Handy ohne Hürde laufen. Bis 0.38.27 stand im QR-Code nur die Zahl des PCs
im WLAN (z. B. 192.168.178.23) – die ändert sich, wenn der Router neu verteilt, und abtippen will sie niemand. Jetzt
sagt Knowlin seinen Namen per mDNS (Bonjour) im Heimnetz an, solange die Handy-Fernbedienung an ist:

* iPhone, iPad, Mac, Windows und Linux finden `knowlin.local` von selbst. Android-Browser oft nicht – dort bleibt die
  Zahl im QR-Code der sichere Weg (die Oberfläche sagt das so).
* Nur solange „Vom Handy aus bedienen“ an ist; aus heißt: keine Ansage mehr.
* Koppeln bleibt Pflicht: Der Name öffnet nur die Tür zum Koppeln, nicht Knowlin selbst.
* Der Name gilt als Host-Zeile nur, solange ihn dieser PC wirklich ansagt (Schutz vor DNS-Rebinding wie bei IPs).

Braucht das Paket `zeroconf` (LGPL-2.1, in requirements.txt). Fehlt es, bleibt alles wie vorher – ohne Namen.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Any

log = logging.getLogger(__name__)

NAME = "knowlin"
DIENST = "_http._tcp.local."

_angesagt: set[str] = set()          # „knowlin.local“, solange die Ansage läuft – für security._host_ok


def name_erlaubt(host: str) -> bool:
    """Ist `host` (ohne Port) der Name, den dieser PC gerade ansagt?"""
    return host.lower().rstrip(".") in _angesagt


def verfuegbar() -> bool:
    try:
        import zeroconf  # noqa: F401
    except ImportError:
        return False
    return True


class Ansage:
    """Sagt `knowlin.local` und den Dienst „Knowlin“ (http, Port der Fernbedienung) im Heimnetz an."""

    def __init__(self) -> None:
        self._zc: Any = None
        self._info: Any = None
        self.name: str | None = None
        self.fehler: str | None = None

    async def start(self, port: int, adressen: list[str]) -> str | None:
        await self.stop()
        self.fehler = None
        ips = [a for a in adressen if _privat_v4(a)]
        if not ips:
            return None
        try:
            from zeroconf import IPVersion
            from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf
        except ImportError:
            self.fehler = "zeroconf fehlt"
            return None
        host = f"{NAME}.local"
        try:
            info = AsyncServiceInfo(DIENST, f"Knowlin.{DIENST}", addresses=[socket.inet_aton(ip) for ip in ips], port=port,
                                    server=f"{host}.", properties={"path": "/"})
            zc = AsyncZeroconf(ip_version=IPVersion.V4Only)
            await zc.async_register_service(info, allow_name_change=True)
        except Exception as exc:  # noqa: BLE001 – Netzwerk ohne Multicast, Firewall …: dann eben ohne Namen
            self.fehler = f"{type(exc).__name__}: {exc}"[:160]
            log.info("knowlin.local nicht angesagt: %s", self.fehler)
            return None
        self._zc, self._info, self.name = zc, info, host
        _angesagt.add(host)
        log.info("Im Heimnetz angesagt: http://%s:%s", host, port)
        return host

    async def stop(self) -> None:
        if self.name:
            _angesagt.discard(self.name)
        zc, info = self._zc, self._info
        self._zc = self._info = self.name = None
        if zc is None:
            return
        try:
            if info is not None:
                await zc.async_unregister_service(info)
            await zc.async_close()
        except Exception as exc:  # noqa: BLE001
            log.info("Ansage beenden: %s", exc)


def _privat_v4(adresse: str) -> bool:
    """„http://192.168.1.5:8766“ oder „192.168.1.5“ → nur private IPv4 im Heimnetz."""
    roh = adresse.split("//")[-1].split(":")[0]
    try:
        ip = ipaddress.ip_address(roh)
    except ValueError:
        return False
    return ip.version == 4 and ip.is_private and not ip.is_loopback
