"""Kollisionsmodus für die Oberfläche: an- und ausschalten, Stöße, Objekte, Episoden.

Die Physik steckt in `physics/kollision.py` und `backends/physics.py`. Hier: was erlaubt ist (nur Simulator mit
echter Physik, nie am echten Roboter), Episoden speichern, und solange sich etwas bewegt alle 1/15 s die Lage der
Objekte an die Oberfläche (`{"type": "kollision_objekte", …}`), solange die Hand im Raum ist alle 1/30 s.

Die Hand kommt über den WebSocket (zu oft für HTTP): `kollision_hand` {x, y, z} oder {aus: true},
`kollision_greifen` {name?}, `kollision_loslassen` {v?: [vx, vy, vz]} (m/s, Welt). Ziehen an der Ente:
`kollision_zug_start` {x, y, z, koerper?} (Punkt auf ihrer Oberfläche), `kollision_zug` {x, y, z} (Ziel),
`kollision_zug_ende` {}. Während eines Zugs kommt `kollision_objekte` mit 30 Hz und `zug` darin. Fehler gehen als
`{"type": "event", "event": {"type": "kollision", "message": …}}` zurück.
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import TYPE_CHECKING, Any

from . import settings as S
from .aio import spawn

if TYPE_CHECKING:  # pragma: no cover
    from .server.runtime import Runtime

log = logging.getLogger(__name__)

PUSH_HZ = 15.0
PUSH_HAND_HZ = 30.0                 # Hand im Raum: öfter, damit Hand und gehaltenes Ding nicht ruckeln
WURF_AB_MS = 0.3                    # schneller losgelassen: zählt als Wurf (Episode), langsamer nur als Ablegen
NUR_SIM = "Den Kollisionsmodus gibt es nur im Simulator – am echten Roboter nicht."
BRAUCHT_PHYSIK = "Der Kollisionsmodus braucht die echte Physik (Einstellungen → Körper → Echte Physik)."


class KollisionService:
    def __init__(self, rt: "Runtime") -> None:
        self.rt = rt
        self._task: asyncio.Future[Any] | None = None
        self._log: Any = None
        from .protest import ProtestDienst

        self.protest = ProtestDienst(rt)        # ab und zu beschweren – ohne Einfluss aufs Wesen
        self._ep_gesehen: Any = None
        extra = getattr(rt, "ws_extra", None)
        if isinstance(extra, dict):
            extra.update({"kollision_hand": self.ws_hand, "kollision_greifen": self.ws_greifen,
                          "kollision_loslassen": self.ws_loslassen, "kollision_zug_start": self.ws_zug_start,
                          "kollision_zug": self.ws_zug, "kollision_zug_ende": self.ws_zug_ende})

    # ── was geht ─────────────────────────────────────────────────────────
    @property
    def body(self) -> Any:
        return self.rt.backend

    def grund(self) -> str | None:
        """Warum es gerade nicht geht – oder None."""
        if self.rt.config.backend != "sim":
            return NUR_SIM
        if not hasattr(self.body, "kollision"):
            return BRAUCHT_PHYSIK
        return None

    @property
    def log_(self) -> Any:
        if self._log is None:
            from .physics.kollision import EpisodenLog

            self._log = EpisodenLog(S.settings_path().parent)
        return self._log

    def _bind(self) -> None:
        if getattr(self.body, "on_episode", None) is None and hasattr(self.body, "on_episode"):
            self.body.on_episode = self._save

    def _save(self, ep: dict[str, Any]) -> None:
        try:
            self.log_.schreiben(ep)
        except OSError as exc:
            log.warning("Episode nicht gespeichert: %s", exc)
        try:
            self.protest.ende(ep)
        except Exception:
            log.exception("Beschwerde am Episodenende")

    def _neue_episode(self) -> None:
        """Neu begonnene Episode (Stoß, Zug, Hand, Wurf …) an die Beschwerden melden."""
        ep = getattr(self.body, "episode", None)
        if ep is None or ep is self._ep_gesehen:
            return
        self._ep_gesehen = ep
        try:
            self.protest.reiz(ep.art, ep.reiz or {}, ep.t0)
        except Exception:
            log.exception("Beschwerde beim Reiz")

    def aktiv(self) -> bool:
        return self.grund() is None and bool(getattr(self.body, "kollision_aktiv", False))

    # ── Nachrichten ──────────────────────────────────────────────────────
    def status(self) -> dict[str, Any]:
        from_g = self.grund()
        out: dict[str, Any] = {"type": "kollision", "verfuegbar": from_g is None, "grund": from_g,
                               "braucht_physik": from_g == BRAUCHT_PHYSIK,   # Knopf trotzdem zeigen (0.38.24)
                               "aktiv": self.aktiv(), "selbst_aufstehen": bool(self.rt.engine.config.auto_recover),
                               "protest": bool(getattr(self.rt.config, "kollision_protest", True)),
                               "stopp_fenster_s": self.rt.engine.config.recover_delay}
        if from_g is None:
            from .physics.kollision import grenzen

            out["grenzen"] = grenzen()
            out["objekte"] = self.body.kollision.objekte()
            out["hand"] = self.body.kollision.hand_info()
            out["zug"] = self.body.kollision.zug_info()
            ep = self.body.episode
            out["episode"] = {"art": ep.art, "seit_s": round(self.body.t - ep.t0, 2)} if ep is not None else None
        try:
            out["episoden"] = self.log_.stats()
        except OSError:
            out["episoden"] = None
        return out

    def objekte_message(self) -> dict[str, Any]:
        k = self.body.kollision
        return {"type": "kollision_objekte", "objekte": k.objekte(), "t": round(self.body.t, 2), "hand": k.hand_info(),
                "zug": k.zug_info()}

    # ── an / aus ─────────────────────────────────────────────────────────
    async def schalten(self, on: bool) -> dict[str, Any]:
        why = self.grund()
        if why:
            return {"ok": False, "fehler": why}
        self._bind()
        self.body.kollision_an(bool(on))
        if on:
            self._start()
        await self.rt.broadcast(self.status())
        return {"ok": True, **self.status()}

    def _start(self) -> None:
        if self._task is None or self._task.done():
            self._task = spawn(self._loop())

    async def _loop(self) -> None:
        moving_before = True
        while self.aktiv():
            k = self.body.kollision
            hand = bool(getattr(k, "hand_aktiv", False)) or getattr(k, "zug", None) is not None
            moving = k.bewegt() or hand
            self._neue_episode()
            if moving or moving_before:
                await self.rt.broadcast(self.objekte_message())
            moving_before = moving
            await asyncio.sleep(1.0 / (PUSH_HAND_HZ if hand else PUSH_HZ))

    # ── Hand über den WebSocket ──────────────────────────────────────────
    async def _fehler(self, text: str) -> None:
        await self.rt.broadcast({"type": "event", "event": {"type": "kollision", "message": text}})

    async def _ws(self, fn: Any) -> Any:
        from .physics.kollision import KollisionsFehler

        why = self.grund() or (None if self.aktiv() else "Der Kollisionsmodus ist aus")
        if why:
            await self._fehler(why)
            return None
        self._bind()
        try:
            res = fn(self.body.kollision)
        except KollisionsFehler as exc:
            await self._fehler(str(exc))
            return None
        self._start()
        return res

    async def ws_hand(self, msg: dict[str, Any]) -> None:
        """{x, y, z} (Welt, m) – die Hand folgt mit höchstens 2,5 m/s; {aus: true} nimmt sie weg."""
        if msg.get("aus"):
            if await self._ws(lambda k: k.hand_aus()) is not None:
                await self.rt.broadcast(self.objekte_message())
            return
        await self._ws(lambda k: k.hand(msg.get("x"), msg.get("y"), msg.get("z")))

    async def ws_greifen(self, msg: dict[str, Any]) -> None:
        """{name?} – greift dieses Objekt (oder das nächste) an der Hand, wenn es höchstens 0,08 m weg ist."""
        name = msg.get("name")
        if await self._ws(lambda k: self.body.kollision_reiz("objekt", k.greifen, name=name)) is not None:
            await self.rt.broadcast(self.objekte_message())

    async def ws_loslassen(self, msg: dict[str, Any]) -> None:
        """{v?: [vx, vy, vz], fest?: bool} – loslassen; mit v fliegt es genau so los (m/s, Welt, höchstens 6 m/s),
        sonst mit dem Tempo der Hand. Ab 0,3 m/s ist es ein Wurf (Episode). Mit fest (und ohne v) bleibt es in der
        Luft stehen. Hält die Hand nichts, passiert nichts."""
        v = msg.get("v")
        fest = msg.get("fest") is True and v is None

        def los(k: Any) -> Any:
            if k.hand_gehalten is None:
                return None
            if v is not None:
                from .physics.kollision import MAX_WURF_MS, _vektor

                tempo = math.hypot(*_vektor(v, "Wurf", MAX_WURF_MS))   # prüft die Zahlen vorab
            else:
                tempo = float(k.hand_info()["tempo"])
            if fest:
                return self.body.kollision_reiz("objekt", k.hand_loslassen, fest=True)
            art = "wurf" if tempo > WURF_AB_MS else "objekt"
            return self.body.kollision_reiz(art, k.hand_loslassen, v=v)

        if await self._ws(los) is not None:
            await self.rt.broadcast(self.objekte_message())

    # ── Ziehen an der Ente über den WebSocket ────────────────────────────
    async def ws_zug_start(self, msg: dict[str, Any]) -> None:
        """{x, y, z, koerper?} – die Ente an diesem Punkt ihrer Oberfläche anfassen (höchstens 3 cm daneben)."""
        res = await self._ws(lambda k: self.body.kollision_reiz("zug", k.zug_start, x=msg.get("x"), y=msg.get("y"),
                                                                 z=msg.get("z"), koerper=msg.get("koerper")))
        if res is not None:
            await self.rt.broadcast(self.objekte_message())

    async def ws_zug(self, msg: dict[str, Any]) -> None:
        """{x, y, z} – wohin am Anfasspunkt gezogen wird (Feder, höchstens 6 N)."""
        await self._ws(lambda k: k.zug_ziel(msg.get("x"), msg.get("y"), msg.get("z")))

    async def ws_zug_ende(self, msg: dict[str, Any]) -> None:
        if await self._ws(lambda k: k.zug_ende()) is not None:
            await self.rt.broadcast(self.objekte_message())

    # ── Aktionen ─────────────────────────────────────────────────────────
    async def tun(self, art: str, body: dict[str, Any]) -> dict[str, Any]:
        """art: stoss | wurf | rollen | objekt (setzen, halten, loslassen, parken)."""
        from .physics.kollision import KollisionsFehler

        why = self.grund()
        if why:
            return {"ok": False, "fehler": why}
        self._bind()
        k = self.body.kollision
        try:
            if art == "stoss":
                res = self.body.kollision_reiz("stoss", k.stoss, ziel=body.get("ziel") or "rumpf",
                                               staerke=body.get("staerke", 0.5), richtung_grad=body.get("richtung_grad", 0.0),
                                               hoehe=body.get("hoehe", 0.0), vektor=body.get("vektor"), punkt=body.get("punkt"),
                                               seite=body.get("seite"), stufe=body.get("stufe"))
            elif art == "wurf":
                res = self.body.kollision_reiz("wurf", k.werfen, name=body.get("name") or "ball", von=body.get("von"),
                                               geschwindigkeit=body.get("geschwindigkeit"),
                                               staerke=body.get("staerke", 0.5), ziel=body.get("ziel"),
                                               seite=body.get("seite"), stufe=body.get("stufe"))
            elif art == "rollen":
                res = self.body.kollision_reiz("rollen", k.rollen, name=body.get("name") or "ball", von=body.get("von"),
                                               tempo=body.get("tempo", 1.0), richtung_grad=body.get("richtung_grad"),
                                               ziel=body.get("ziel", "ente"), seite=body.get("seite"),
                                               stufe=body.get("stufe"))
            elif art == "objekt":
                aktion = str(body.get("aktion") or "setzen")
                name = body.get("name") or "ball"
                if aktion == "setzen":
                    res = self.body.kollision_reiz("objekt", k.setzen, name=name, pos=body.get("pos"))
                elif aktion == "halten":
                    res = self.body.kollision_reiz("objekt", k.halten, name=name, pos=body.get("pos"))
                elif aktion == "loslassen":
                    vel = body.get("geschwindigkeit")
                    if vel is not None and any(abs(float(v)) > 0.3 for v in vel if isinstance(v, (int, float))):
                        res = self.body.kollision_reiz("wurf", k.loslassen, name=name, geschwindigkeit=vel)
                    else:
                        res = self.body.kollision_reiz("objekt", k.loslassen, name=name, geschwindigkeit=vel)
                elif aktion == "fallen":
                    res = {"gefallen": self.body.kollision_reiz("objekt", k.fallen_lassen, name=body.get("name"))}
                elif aktion == "parken":
                    self.body.kollision_reiz("objekt", k.parken, name=name)
                    res = k.objekt(k._key(name))
                else:
                    raise KollisionsFehler("Aktion: setzen, halten, loslassen, fallen oder parken")
            else:
                raise KollisionsFehler(f"unbekannt: {art}")
        except KollisionsFehler as exc:
            return {"ok": False, "fehler": str(exc)}
        self._start()
        return {"ok": True, "ergebnis": res}
