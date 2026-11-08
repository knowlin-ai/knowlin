"""Stoßreihe für die Oberfläche (Lernen → Training, Karte „Robustheit gegen Stöße“): starten, abbrechen, Profile.

Gerechnet wird in `physics/stossreihe.py` – in einem eigenen Rechenprozess, unsichtbar, schneller als Echtzeit; die
sichtbare Ente (oder der echte Roboter) merkt davon nichts. Hier: was erlaubt ist (nur mit echter Physik; die Routen
gehen nur am PC und nie über MCP), Episoden und Profil speichern, Fortschritt an die Fenster am PC:
`{"type": "stossreihe", "lauf": {…}, "fertig": n, "gesamt": N, "letztes": {…} | null}`.

Stimmung, Beschwerden und Erfahrungsnetz bleiben unberührt: die Episoden gehen direkt ins Episoden-Protokoll.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import settings as S
from .aio import spawn
from .physics import stossreihe as R

if TYPE_CHECKING:  # pragma: no cover
    from .server.runtime import Runtime

log = logging.getLogger(__name__)

START_WARTEN_S = 300.0          # so lange darf der Rechenprozess zum Aufbauen brauchen
STOPP_WARTEN_S = 10.0           # nach „Abbrechen“: dann wird der Prozess beendet
STATUS_WORTE = {"startet": "startet …", "laeuft": "läuft", "fertig": "fertig", "abgebrochen": "abgebrochen",
                "fehler": "Fehler"}


class StossreiheDienst:
    def __init__(self, rt: "Runtime") -> None:
        self.rt = rt
        self.lauf: dict[str, Any] | None = None
        self.letztes: dict[str, Any] | None = None
        self._task: asyncio.Future[Any] | None = None
        self._stopp: Any = None                  # Stopp-Signal des Rechenprozesses
        self._stopp_seit: float | None = None
        self._log: Any = None

    @property
    def root(self) -> Path:
        return S.settings_path().parent

    def grund(self) -> str | None:
        return R.physik_grund()

    @property
    def laeuft(self) -> bool:
        return bool(self.lauf and self.lauf.get("laeuft"))

    # ── Nachrichten ──────────────────────────────────────────────────────
    def nachricht(self) -> dict[str, Any]:
        lauf = self.lauf or {}
        return {"type": "stossreihe", "lauf": self.lauf, "fertig": int(lauf.get("fertig") or 0),
                "gesamt": int(lauf.get("gesamt") or 0), "letztes": self.letztes}

    def status(self) -> dict[str, Any]:
        from .physics.kollision import STUFEN

        g = self.grund()
        try:
            from .physics.lernen import quellen

            qs = quellen(self.root) if g is None else []
        except Exception:
            qs = []
        return {**self.nachricht(), "verfuegbar": g is None, "grund": g, "quellen": qs,
                "raster": {"richtungen": R.RICHTUNG_NAMEN, "stufen": STUFEN, "hoehen": R.HOEHE_NAMEN,
                           "versuche": len(R.raster()), "einschwingen_s": R.EINSCHWINGEN_S, "nachlauf_s": R.NACHLAUF_S}}

    async def _melden(self) -> None:
        try:
            await self.rt.broadcast_local(self.nachricht())
        except Exception:
            log.exception("Stoßreihe: Fortschritt nicht gesendet")

    # ── Policy ───────────────────────────────────────────────────────────
    def _policy(self, quelle: str) -> tuple[Path, float, dict[str, Any]]:
        from .physics.lernen import LernFehler, aufloesen

        quelle = str(quelle or "standard").strip()
        try:
            path, scale, name = aufloesen(self.root, quelle)
        except LernFehler as exc:
            raise R.ReiheFehler(str(exc)) from exc
        if quelle in ("standard", "walk"):
            # wie das Physik-Backend und robotd: ohne Angabe im Manifest 0,9
            from .physics.core import ROBOT_ACTION_SCALE
            from .physics.policies import PolicyStore

            e = PolicyStore(self.root).roles()["walk"]["eintrag"]
            scale = float(e.get("action_scale") or ROBOT_ACTION_SCALE)
        info = {"quelle": quelle, "name": name, "datei": path.name, "sha256": R.pruefsumme(path),
                "action_scale": scale}
        return path, scale, info

    # ── Start / Abbruch ──────────────────────────────────────────────────
    async def start(self, body: dict[str, Any]) -> dict[str, Any]:
        g = self.grund()
        if g is not None:
            return {"ok": False, "fehler": g}
        if self.laeuft:
            return {"ok": False, "fehler": "Eine Stoßreihe läuft schon – erst abwarten oder abbrechen."}
        try:
            rast = R.raster(body.get("richtungen"), body.get("stufen"), body.get("hoehen"), body.get("wiederholungen"))
            path, scale, info = await asyncio.to_thread(self._policy, str(body.get("policy") or "standard"))
        except R.ReiheFehler as exc:
            return {"ok": False, "fehler": str(exc)}
        auftrag = {"policy_pfad": str(path), "action_scale": scale, "policy_name": info["name"], "raster": rast,
                   "einschwingen_s": R.EINSCHWINGEN_S, "nachlauf_s": R.NACHLAUF_S}
        self.lauf = {"id": R.neue_id(self.root), "laeuft": True, "status": "startet", "policy": info,
                     "fertig": 0, "gesamt": len(rast), "start": time.strftime("%Y-%m-%dT%H:%M:%S"),
                     "fehler": None, "profil": None, "zusammenfassung": None}
        self.letztes = None
        self._stopp_seit = None
        self._task = spawn(self._rechnen(auftrag, info))
        await self._melden()
        return {"ok": True, **self.nachricht()}

    async def stopp(self) -> dict[str, Any]:
        if not self.laeuft:
            return {"ok": False, "fehler": "Gerade läuft keine Stoßreihe."}
        self._stopp_seit = time.monotonic()
        if self._stopp is not None:
            self._stopp.set()
        return {"ok": True, **self.nachricht()}

    def _episode(self, ep: dict[str, Any]) -> None:
        kol = getattr(self.rt, "kollision", None)       # dasselbe Protokoll (Zähler) wie der Kollisionsmodus
        try:
            if kol is not None:
                kol.log_.schreiben(ep)
            else:
                if self._log is None:
                    from .physics.kollision import EpisodenLog

                    self._log = EpisodenLog(self.root)
                self._log.schreiben(ep)
        except OSError as exc:
            log.warning("Stoßreihe: Episode nicht gespeichert: %s", exc)

    async def _rechnen(self, auftrag: dict[str, Any], info: dict[str, Any]) -> None:
        lauf = self.lauf
        assert lauf is not None
        t0 = time.monotonic()
        versuche: list[dict[str, Any]] = []
        motor = None
        proc = conn = None
        try:
            proc, conn, self._stopp = await asyncio.to_thread(R.starte_prozess, auftrag)
            if self._stopp_seit is not None:
                self._stopp.set()
            while True:
                da = await asyncio.to_thread(conn.poll, 0.5)
                if not da:
                    if not proc.is_alive():
                        raise R.ReiheFehler("Der Rechenprozess hat sich unerwartet beendet.")
                    if self._stopp_seit is not None and time.monotonic() - self._stopp_seit > STOPP_WARTEN_S:
                        raise _Abbruch()
                    if lauf["status"] == "startet" and time.monotonic() - t0 > START_WARTEN_S:
                        raise R.ReiheFehler("Der Rechenprozess startet nicht.")
                    continue
                art, data = conn.recv()
                if art == "bereit":
                    motor = (data or {}).get("motor")
                    lauf["status"] = "laeuft"
                    await self._melden()
                elif art == "versuch":
                    await asyncio.to_thread(self._episode, data.pop("episode"))
                    versuche.append(data)
                    lauf["fertig"] = len(versuche)
                    self.letztes = data
                    await self._melden()
                elif art == "abgebrochen":
                    raise _Abbruch()
                elif art == "fertig":
                    break
                else:
                    raise R.ReiheFehler(str(data or "unbekannter Fehler im Rechenprozess"))
            dauer = round(time.monotonic() - t0, 1)
            prof = await asyncio.to_thread(R.schreibe_profil, self.root, lauf["id"], info, auftrag, versuche,
                                           {"dauer_s": dauer, "motor": motor})
            lauf.update(status="fertig", profil=lauf["id"], zusammenfassung=prof["ergebnis"]["text"], dauer_s=dauer)
        except _Abbruch:
            lauf.update(status="abgebrochen")
        except (R.ReiheFehler, OSError, EOFError) as exc:
            lauf.update(status="fehler", fehler=str(exc))
        except Exception as exc:          # noqa: BLE001
            log.exception("Stoßreihe")
            lauf.update(status="fehler", fehler=f"{type(exc).__name__}: {exc}")
        finally:
            lauf["laeuft"] = False
            self._stopp = None
            if conn is not None:
                conn.close()
            if proc is not None:
                await asyncio.to_thread(proc.join, 2.0)
                if proc.is_alive():
                    proc.terminate()                    # nur der eigene Rechenprozess
            await self._melden()

    # ── Profile ──────────────────────────────────────────────────────────
    def profile(self) -> dict[str, Any]:
        return {"ok": True, "profile": R.liste(self.root)}

    def profil(self, pid: str) -> dict[str, Any]:
        try:
            return {"ok": True, "profil": R.lade_profil(self.root, pid)}
        except R.ReiheFehler as exc:
            return {"ok": False, "fehler": str(exc)}


class _Abbruch(Exception):
    pass
