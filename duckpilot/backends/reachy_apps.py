"""Pollens Reachy-Mini-Apps aus Knowlin starten (seit 0.38.19).

Pollens Daemon verwaltet Apps selbst (`/api/apps/…`, geprüft gegen reachy-mini 1.13): installierte Apps auflisten,
eine starten, die laufende anhalten, neue aus Pollens Katalog auf Hugging Face installieren. Knowlin ruft nur diese
Schnittstelle auf – die App läuft auf dem Roboter (Wireless) bzw. neben dem Daemon (Lite), nicht in Knowlin.

Sicherheit: Solange eine App läuft, schickt Knowlin keine eigenen Ziele (sonst kämpfen zwei Steuerungen um den Kopf).
Der Not-Aus hält die App an. Installiert wird nur, was in Pollens Katalog steht – nie eine beliebige Adresse.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable
from urllib.parse import quote

Rufen = Callable[[str, str, "dict[str, Any] | None"], Awaitable[Any]]

LAEUFT = ("starting", "running", "stopping")
KATALOG_S = 600.0                      # Pollens Katalog höchstens alle zehn Minuten neu holen


def _app(info: dict[str, Any]) -> dict[str, Any]:
    """Pollens AppInfo → was die Oberfläche zeigt (Name, Beschreibung, Seite, Beliebtheit)."""
    extra = info.get("extra") or {}
    return {"name": str(info.get("name") or ""), "beschreibung": str(info.get("description") or "")[:240],
            "url": info.get("url") or None, "likes": extra.get("likes"), "art": info.get("source_kind")}


class PollenApps:
    """Apps über Pollens Daemon. `rufen(methode, pfad, body)` ist der HTTP-Aufruf des Körpers."""

    def __init__(self, rufen: Rufen) -> None:
        self._rufen = rufen
        self.laufend: dict[str, Any] | None = None       # {"name", "zustand", "fehler"} oder None
        self._katalog: tuple[float, list[dict[str, Any]]] | None = None

    @property
    def aktiv(self) -> bool:
        return bool(self.laufend and self.laufend.get("zustand") in LAEUFT)

    async def status(self) -> dict[str, Any] | None:
        """Laufende App beim Daemon nachfragen (merkt sich das Ergebnis für `aktiv`)."""
        r = await self._rufen("GET", "/api/apps/current-app-status", None)
        if isinstance(r, dict) and isinstance(r.get("info"), dict):
            self.laufend = {"name": r["info"].get("name"), "zustand": r.get("state"), "fehler": r.get("error")}
        else:
            self.laufend = None
        return self.laufend

    async def installiert(self) -> list[dict[str, Any]]:
        r = await self._rufen("GET", "/api/apps/list-available/installed", None)
        return [_app(a) for a in r if isinstance(a, dict)] if isinstance(r, list) else []

    async def katalog(self) -> list[dict[str, Any]]:
        """Pollens App-Katalog (Hugging Face), beliebteste zuerst. Der Daemon holt ihn; wir merken ihn uns kurz."""
        if self._katalog and time.monotonic() - self._katalog[0] < KATALOG_S:
            return self._katalog[1]
        r = await self._rufen("GET", "/api/apps/list-available/hf_space", None)
        roh = [a for a in r if isinstance(a, dict)] if isinstance(r, list) else []
        self._roh = {str(a.get("name")): a for a in roh}
        liste = sorted((_app(a) for a in roh), key=lambda a: -(a["likes"] or 0))
        self._katalog = (time.monotonic(), liste)
        return liste

    async def starten(self, name: str) -> dict[str, Any]:
        r = await self._rufen("POST", f"/api/apps/start-app/{quote(name, safe='')}", None)
        self.laufend = {"name": name, "zustand": (r or {}).get("state", "starting") if isinstance(r, dict) else "starting",
                        "fehler": (r or {}).get("error") if isinstance(r, dict) else None}
        return self.laufend

    async def stoppen(self) -> None:
        await self._rufen("POST", "/api/apps/stop-current-app", None)
        self.laufend = None

    async def installieren(self, name: str) -> str:
        """Eine App aus Pollens Katalog installieren – nur mit genau den Angaben, die der Katalog liefert. Gibt die
        Auftragsnummer des Daemons zurück (Fortschritt über `auftrag`)."""
        await self.katalog()
        info = getattr(self, "_roh", {}).get(name)
        if info is None:
            raise ValueError(f"„{name}“ steht nicht in Pollens Katalog")
        r = await self._rufen("POST", "/api/apps/install", info)
        job = (r or {}).get("job_id") if isinstance(r, dict) else None
        if not job:
            raise RuntimeError("Pollens Daemon hat keinen Auftrag angelegt")
        return str(job)

    async def auftrag(self, job: str) -> dict[str, Any]:
        r = await self._rufen("GET", f"/api/apps/job-status/{quote(job, safe='')}", None)
        if not isinstance(r, dict):
            return {"zustand": "unbekannt", "zeilen": []}
        return {"zustand": r.get("status"), "zeilen": [str(z) for z in (r.get("logs") or [])][-6:]}
