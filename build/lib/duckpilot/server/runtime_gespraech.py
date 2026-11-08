"""Laufzeit, Bereich Gespräch: Chat mit Knowlin und den Verkörperungen, Sprache, Blick, Laser, Personen und NFC-Tags.

Teil der Klasse `Runtime` (server/runtime.py), seit 0.38.17 ausgelagert wie `runtime_reachy.py` – nicht allein benutzbar.
"""

from __future__ import annotations

import logging
import math
import re
import time
from typing import Any

from .. import remote as R
from ..aio import spawn
from ..api import Head
from ..brain.fallback import parse as quick_parse

log = logging.getLogger(__name__)


class GespraechTeil:
    """Mischklasse für `Runtime` – nicht allein benutzbar."""

    # ── NFC-Tags ─────────────────────────────────────────────────────────
    async def nfc_touched(self, uid: Any, remote: bool = False) -> dict[str, Any]:
        """Ein Tag wurde berührt (Handy, Probe-Knopf, später der Roboter): seinen Satz wie einen Befehl ausführen."""
        res = self.nfc.touched(uid)
        if not res.get("ok"):
            return res
        tag = res["tag"]
        self.erfahrung.nfc(tag)
        await self.broadcast({"type": "nfc_beruehrt", "tag": tag, "neu": res["neu"]})
        await self.broadcast(self.nfc.message())
        if res["satz"]:
            async def run() -> None:
                tok = R.REMOTE_TURN.set(remote)          # „wer ist da“ nie an ein Handy
                try:
                    await self.chat(res["satz"], via="nfc")
                finally:
                    R.REMOTE_TURN.reset(tok)
            spawn(run())
        return res

    # ── Chat ─────────────────────────────────────────────────────────────
    async def chat(self, text: str, via: str = "text", an: str = "figur", cid: str | None = None) -> None:
        text = text.strip()[:2000]
        if not text:
            return
        if cid:                              # schickt der Browser nach einem Verbindungsabbruch erneut: nur einmal
            gesehen = self.__dict__.setdefault("_chat_ids", [])
            if cid in gesehen:
                return
            gesehen.append(cid)
            del gesehen[:-64]
        kopf = an == "kopf"                  # auf Knowlins Startseite: der Kopf antwortet, nicht die Verkörperung (0.38.8)
        if kopf:                             # was hier gelernt wird, stammt vom Kopf (0.38.10; gilt nur für diese Aufgabe)
            from ..brain.memory import HERKUNFT

            HERKUNFT.set("kopf")
        wohin = {"an": "kopf"} if kopf else {}
        await self.broadcast({"type": "chat", "role": "user", "text": text, "via": via, **wohin,
                              **({"cid": cid} if cid else {})})
        self.erfahrung.hear(text, via)
        # Sicherheit zuerst: "Stopp" wirkt sofort, ohne auf Claude zu warten – auch, wenn es der Kopf hört.
        if quick_parse(text) == [("stop", {})]:
            self.alltag.emergency_stop()
            await self.engine.not_aus("Stopp (Sprache)")
            await self.broadcast({"type": "chat", "role": "duck", "text": "Angehalten.", "source": "reflex", "seconds": 0,
                                  "sprache": self._speech("Angehalten.", ernst=True, kopf=kopf), **wohin})
            return
        if kopf:
            await self._kopf_antwortet(text)
            return
        from ..skills.alltag import quick as alltag_quick

        q = alltag_quick(text)
        self.engine.angesprochen()                         # „still bis angesprochen“ (nach dem Not-Aus) endet hier
        self.alltag.touch(wake=not (q and q.get("aktion") in ("ruhe", "aktiv")))  # Ansprechen weckt sie auf
        async with self.chat_lock:
            if self.agent.online:
                self.engine.hear(text, show=False)   # Claude zeigt das Gefühl selbst – Stimmung steht im Kontext
            await self.broadcast({"type": "thinking", "on": True})
            self.engine.denkt(True)
            from ..brain.handeln import mit_auswahl

            auswahl = getattr(self, "auswahl", None)        # in der 3D-Ansicht angewählt („heb das auf“), seit 0.37.3
            if auswahl and time.monotonic() - auswahl.get("seit", 0) > 600:
                auswahl = None
            try:
                reply = await self.agent.handle(mit_auswahl(text, auswahl), notify=self.broadcast)
            finally:
                self.engine.denkt(False)
                await self.broadcast({"type": "thinking", "on": False})
            if not self.agent.online or reply.source not in ("claude", "lokal"):
                self.engine.hear(text, show=True)
        if reply.source not in ("claude", "lokal"):
            for action in reply.actions:
                await self.broadcast({"type": "action", **action})
        from ..voice.speech import spoken_text

        feeling = self.engine.mood.feeling().name
        await self.broadcast({
            "type": "chat", "role": "duck", "text": self._ohne_ente(spoken_text(reply.text) or reply.text), "source": reply.source,
            "seconds": round(reply.seconds, 2), "error": self.agent.last_error if reply.source != "lokal" else None,
            "gefuehl": feeling, "sprache": self._speech(reply.text, feeling),
        })

    async def _kopf_antwortet(self, text: str) -> None:
        """Knowlins Kopf antwortet auf der Startseite: eigener Verlauf, keine Körperwerkzeuge, keine Entenlaute."""
        async with self.kopf_lock:
            await self.broadcast({"type": "thinking", "on": True, "an": "kopf"})
            try:
                reply = await self.kopf.handle(text)
            except Exception:
                log.exception("Kopf antwortet")
                from ..brain.agent import Reply

                reply = Reply("Da ist bei mir gerade etwas schiefgegangen." if getattr(self.config, "sprache", "de") != "en"
                              else "Something went wrong on my side.", [], "einfach")
            finally:
                await self.broadcast({"type": "thinking", "on": False, "an": "kopf"})
        for a in reply.actions:
            await self.broadcast({"type": "action", "an": "kopf", **a})
        satz = self._ohne_ente(reply.text, kopf=True)
        await self.broadcast({"type": "chat", "role": "duck", "an": "kopf", "text": satz, "source": reply.source,
                              "seconds": round(reply.seconds, 2), "error": self.kopf.last_error, **reply.extra,
                              "sprache": self._speech(satz, kopf=True)})

    def _ohne_ente(self, text: str, kopf: bool = False) -> str:
        """Verkörperungen, die keine Ente sind (Reachy), quaken nicht – auch nicht in festen Sätzen der einfachen Befehle.
        Knowlins Kopf (`kopf`) ist nie eine Ente."""
        from ..figuren import figur

        if (not kopf and figur(self.config.modul).get("ente", True)) or not text:
            return text

        t = re.sub(r"\*[^*]{0,20}\*", "", text)                                    # *quak*, *gurr* …
        t = re.sub(r"\b(?:Qu+a+k+|qu+a+k+)(?:[ -]?(?:qu+a+k+))*[!?.,]*\s*", "", t)  # „Quak!“, „quak quak“
        t = re.sub(r"\s{2,}", " ", t).strip().lstrip(",;:– ")
        return (t[:1].upper() + t[1:]) if t else "Okay."       # „Quak, mach ich!“ → „Mach ich!“

    def _speech(self, text: str, feeling: str = "ausgeglichen", ernst: bool = False,
                kopf: bool = False) -> dict[str, Any] | None:
        """Die Abfolge zum Sprechen (Sätze und Entenlaute) – oder None, wenn Vorlesen aus ist."""
        text = self._ohne_ente(text, kopf=kopf)
        if not self.config.tts:
            return None
        try:
            if kopf:      # der Kopf hat seine eigene, tiefe, ruhige Stimme (seit 0.38.9)
                return self.speaker.prepare_kopf(text, ernst=ernst)
            return self.speaker.prepare(text, feeling, self.config.goofy, self.config.energie, ernst=ernst)
        except Exception:
            log.exception("Sprechen vorbereiten")
            return None

    def camera_address(self) -> str | None:
        from ..care import guess

        if self.config.backend != "robotd":
            return None
        return self.config.media or guess(self.config.robot, 3)

    async def _duck_says(self, text: str) -> None:
        # seit 0.37.6 auch in der eigenen Stimme (vorher sprach die Ente hier immer mit der Browser-Stimme)
        await self.broadcast({"type": "chat", "role": "duck", "text": text, "source": "system", "seconds": 0,
                              "sprache": self._speech(text)})

    async def _gaze_message(self, kind: str, msg: dict[str, Any]) -> None:
        """Klick und Ziehen in der 3D-Ansicht: hinschauen, Blick von Hand halten, hinlaufen."""
        def num(key: str, lo: float, hi: float, default: float | None = None) -> float | None:
            try:
                v = float(msg.get(key, default))
            except (TypeError, ValueError):
                return default
            return max(lo, min(hi, v)) if math.isfinite(v) else default

        if time.monotonic() - getattr(self.engine, "stopped_at", 0.0) < 0.6:
            return                       # nach Not-Aus keine nachzüglerischen Klicks ausführen
        secs = num("sekunden", 0, 60, 8.0) or 0.0
        x, y = num("x", -50, 50), num("y", -50, 50)
        if kind == "hingehen" and x is not None and y is not None and "beine" not in self.backend.eigenschaften():
            # Reachy Mini steht fest (seit 0.38.3): Doppelklick dreht ihn zum Punkt und er schaut hin
            st = self.backend.state()
            grad = math.degrees(math.atan2(y - st.y, x - st.x) - st.yaw)
            grad = (grad + 180) % 360 - 180
            self.engine.look_at(point=(x, y, 0.05), seconds=8)
            result = await self.runner.run("turn", {"degrees": round(grad)})
            await self.broadcast({"type": "action", "tool": "turn", "input": {"degrees": round(grad)}, "result": result})
            return
        if kind == "hingehen" and x is not None and y is not None:
            self.engine.look_at(point=(x, y, 0.05), seconds=30)
            result = await self.runner.run("go_to", {"x": x, "y": y})
            await self.broadcast({"type": "action", "tool": "go_to", "input": {"x": round(x, 2), "y": round(y, 2)},
                                  "result": result, "via": "klick"})
            return
        if x is not None and y is not None:
            res = self.engine.look_at(point=(x, y, num("z", -0.5, 3, 0.0) or 0.0), seconds=secs)
            if not res.get("kopf_reicht", True) and msg.get("drehen", True) and not self.engine.busy():
                deg = res["richtung_grad"]
                await self.runner.run("turn", {"degrees": deg - math.copysign(35, deg)})   # Körper dreht nach, Kopf folgt
            return
        yaw, pitch = num("yaw", -1.1, 1.1), num("pitch", -0.7, 0.7)
        if yaw is None and pitch is None:
            self.engine.look_at(seconds=0)
            return
        self.engine.look_at(head=Head(0.0, pitch or 0.0, yaw or 0.0, 0.0), seconds=secs)

    def _laser_message(self, msg: dict[str, Any]) -> None:
        """Laserpointer in der 3D-Ansicht (nur Simulator/Physik): Punkt setzen, verschieben oder ausschalten."""
        from ..motion.behaviors import FollowLaser

        setter = getattr(self.backend, "set_laser", None)    # echter Roboter: keiner, dort zeigt der echte Pointer
        if msg.get("aus"):
            if setter is not None:
                setter(None, None)
            if isinstance(self.engine.current, FollowLaser):
                self.engine.cancel_current("Laser aus")
            self.engine.queue = type(self.engine.queue)(b for b in self.engine.queue if not isinstance(b, FollowLaser))
            return
        try:
            x, y = float(msg.get("x")), float(msg.get("y"))
        except (TypeError, ValueError):
            return                                        # kaputter Punkt: ignorieren, nicht ausschalten
        try:
            z = float(msg.get("z") or 0.0)
        except (TypeError, ValueError):
            z = 0.0
        if setter is not None and math.isfinite(x) and math.isfinite(y):
            setter(max(-50.0, min(50.0, x)), max(-50.0, min(50.0, y)), z if math.isfinite(z) else 0.0)

    def _person_message(self, msg: dict[str, Any]) -> None:
        """Follow-me im Simulator: die Maus führt eine Markierung über den Boden, „aus“ beendet das Folgen."""
        from ..motion.behaviors import FollowMe

        setter = getattr(self.backend, "set_person", None)   # echter Roboter: keiner, dort sieht die Kamera den Menschen
        if msg.get("aus"):
            if setter is not None:
                setter(None, None)
            if isinstance(self.engine.current, FollowMe):
                self.engine.cancel_current("Folgen aus")
            self.engine.queue = type(self.engine.queue)(b for b in self.engine.queue if not isinstance(b, FollowMe))
            return
        try:
            x, y = float(msg.get("x")), float(msg.get("y"))
        except (TypeError, ValueError):
            return
        if setter is not None and math.isfinite(x) and math.isfinite(y):
            setter(max(-50.0, min(50.0, x)), max(-50.0, min(50.0, y)))
