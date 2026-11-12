"""Verbindet das Erfahrungsnetz (brain/erfahrung.py) mit dem, was die Ente erlebt.

Quellen: Ereignisse der Bewegung (Ball getroffen, Sturz, Anstoßen …), gezeigte Gefühle, Tricks, was der Mensch
sagt (Lob, Kritik, Stimme gehört), erkannte Personen (nur angelernte), berührte NFC-Tags, und als leiser Rahmen
Tageszeit, Wochentag, der nächste gemerkte Ort und der Modus (Ruhe/Aktiv).

Lernt nur, wenn das Gedächtnis eingeschaltet ist. Personen-Knoten gehen nie an ein Handy, und in Antworten an
ein Handy fallen der Ente keine Personen ein.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from typing import TYPE_CHECKING, Any

from . import remote as R
from . import settings as S
from .brain.erfahrung import Erfahrungsnetz, key

if TYPE_CHECKING:  # pragma: no cover
    from .server.runtime import Runtime

log = logging.getLogger(__name__)

LOB = re.compile(r"\b(super|toll|klasse|prima|brav|gut gemacht|sehr gut|großartig|grossartig|wunderbar|cool|lieb)\b", re.I)
KRITIK = re.compile(r"\b(nein|falsch|schlecht|zu wild|lass das|hör auf|hoer auf|nicht so|böse|boese)\b", re.I)
DINGE = {"ball": "Ball", "socke": "Socke", "würfel": "Würfel", "wuerfel": "Würfel", "laser": "Laserpunkt"}

# Ereignis der Bewegung → (Knoten, Salienz)
EREIGNIS = {
    "kick": ({"ding:ball": "Ball", "taetigkeit:spielen": "spielen", "gefuehl:freude": "Freude"}, 1.2),
    "kick_miss": ({"ding:ball": "Ball", "taetigkeit:spielen": "spielen", "gefuehl:frustriert": "Frust"}, 0.8),
    "pick": ({"taetigkeit:aufheben": "aufheben", "gefuehl:stolz": "Stolz"}, 1.0),
    "pick_miss": ({"taetigkeit:aufheben": "aufheben", "gefuehl:frustriert": "Frust"}, 0.7),
    "bump": ({"sinn:anstossen": "angestoßen", "gefuehl:schreck": "Schreck"}, 1.0),
    "fall": ({"sinn:sturz": "gestürzt", "gefuehl:schreck": "Schreck"}, 1.6),
    "recover": ({"taetigkeit:aufstehen": "aufstehen"}, 0.8),
    "pickup": ({"sinn:hochgehoben": "hochgehoben"}, 1.2),
}


def tageszeit(h: int) -> tuple[str, str]:
    for bis, name in ((5, "nachts"), (10, "morgens"), (12, "vormittags"), (14, "mittags"), (18, "nachmittags"), (22, "abends")):
        if h < bis:
            return key("zeit", name), name
    return key("zeit", "nachts"), "nachts"


class ErfahrungService:
    def __init__(self, rt: "Runtime") -> None:
        self.rt = rt
        self.netz = Erfahrungsnetz(S.settings_path().parent / "erfahrung.json")
        self._last_push = 0.0
        self._last_save = time.monotonic()
        self._last_drift = 0.0
        self._was_picked = False
        self._sleeping_since: float | None = None

    @property
    def on(self) -> bool:
        return self.rt.memory is not None

    def herkunft(self) -> str | None:
        """Wo gerade gelernt wird (seit 0.38.10): der Kopf (siehe `memory.HERKUNFT`) oder die Verkörperung im Körper."""
        from .brain.memory import HERKUNFT

        cfg = getattr(self.rt, "config", None)
        if HERKUNFT.get() or cfg is None:
            return HERKUNFT.get()
        return f"{cfg.modul}:{'sim' if cfg.backend == 'sim' else 'echt'}"

    # ── Quellen ───────────────────────────────────────────────────────────
    def on_event(self, ev: dict[str, Any]) -> None:
        if not self.on:
            return
        kind = ev.get("type")
        msg = str(ev.get("message") or "")
        if ev.get("kollision"):
            return                       # Kollisionsmodus ist Spiel – das Erfahrungsnetz lernt daraus nichts
        if kind in EREIGNIS:
            ids, sal = EREIGNIS[kind]
            ids = dict(ids)
            what = str(ev.get("what") or ev.get("item") or "").lower()
            for k, label in DINGE.items():
                if k in what:
                    ids[key("ding", label)] = label
            self.netz.erleben(ids, sal, warum=msg or kind, herkunft=self.herkunft())
        elif kind == "gefuehl" and ev.get("name"):
            name = str(ev["name"])
            self.netz.erleben({key("gefuehl", name): name}, 0.9, warum=msg, herkunft=self.herkunft())
        elif kind == "trick" and msg:
            from .brain.erfahrung import lesbarer_name

            name = lesbarer_name(msg.split("„")[-1].split("“")[0]) if "„" in msg else "Trick"
            self.netz.erleben({key("taetigkeit", name): name}, 1.0, warum=msg, herkunft=self.herkunft())

    def hear(self, text: str, via: str) -> None:
        """Was der Mensch sagt: Stimme gehört, Lob, Kritik, genannte Dinge."""
        if not self.on:
            return
        ids: dict[str, str] = {key("sinn", "stimme"): "Stimme gehört"} if via in ("sprache", "voice", "mikro") else {}
        sal = 0.8
        if LOB.search(text):
            ids[key("rueckmeldung", "lob")] = "Lob"
            sal = 1.5
        elif KRITIK.search(text):
            ids[key("rueckmeldung", "kritik")] = "Kritik"
            sal = 1.3
        low = text.lower()
        for k, label in DINGE.items():
            if k in low:
                ids[key("ding", label)] = label
        if ids:
            self.netz.erleben(ids, sal, warum=f"„{text[:60]}“", herkunft=self.herkunft())

    def person(self, name: str) -> None:
        if self.on and name:
            self.netz.erleben({key("person", name): name}, 1.2, warum=f"{name} gesehen", herkunft=self.herkunft())

    def nfc(self, tag: dict[str, Any]) -> None:
        if self.on and tag.get("name"):
            self.netz.erleben({key("ding", f"Tag {tag['name']}"): f"Tag {tag['name']}"}, 1.0, warum="Tag berührt", herkunft=self.herkunft())

    # ── Rahmen, Ticken, Prägung ───────────────────────────────────────────
    def _rahmen(self) -> dict[str, str]:
        from .buddy import now_local

        now = now_local()
        out = dict([tageszeit(now.hour)])
        wk = "Wochenende" if now.weekday() >= 5 else "Werktag"
        out[key("zeit", wk)] = wk
        if self.rt.alltag.on and self.rt.alltag.mode == "ruhe":
            out[key("taetigkeit", "ausruhen")] = "ausruhen"
        mem = self.rt.memory
        st = self.rt.engine.last_state
        if mem is not None:
            best = None
            for name, p in mem.places_for(st.backend or "sim").items():
                d = math.hypot(p["x"] - st.x, p["y"] - st.y)
                if d < 1.0 and (best is None or d < best[0]):
                    best = (d, name)
            if best:
                out[key("ort", best[1])] = best[1]
        return out

    async def run(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            try:
                self._step(1.0)
                await self._push()
            except Exception:
                log.exception("Erfahrungsnetz")

    def _step(self, dt: float) -> None:
        if not self.on:
            return
        st = self.rt.engine.last_state
        if st.picked_up and not self._was_picked:
            self.on_event({"type": "pickup"})
        self._was_picked = bool(st.picked_up)
        self.netz.set_rahmen(self._rahmen())
        self.netz.tick(dt)
        now = time.monotonic()
        if now - self._last_drift > 60:
            self._last_drift = now
            self.apply_praegung()
        if now - self._last_save > 60:
            self._last_save = now
            self.netz.save()
        # Schlaf: nach einer Stunde Ruhe einmal festigen und aufräumen
        resting = self.rt.alltag.on and self.rt.alltag.mode == "ruhe"
        self._sleeping_since = (self._sleeping_since or now) if resting else None
        if self._sleeping_since and now - self._sleeping_since > 3600 and time.time() - self.netz.gelernt_bis > 12 * 3600:
            res = self.netz.consolidate()
            log.info("Erfahrungsnetz gefestigt: %s", res)

    def apply_praegung(self) -> None:
        """Das eingestellte Temperament bleibt der Anker – Erfahrung verschiebt es höchstens um ± 0,1."""
        drift = self.netz.praegung()["energie"] if self.on else 0.0
        base = float(getattr(self.rt.config, "energie", 0.55))
        self.rt.engine.config.energie = round(max(0.0, min(1.0, base + drift)), 3)

    async def _push(self) -> None:
        now = time.monotonic()
        busy = bool(self.netz.akt)
        if now - self._last_push < (1.0 if busy else 10.0):
            return
        self._last_push = now
        msg = self.message()
        await self.rt.broadcast_local(msg)        # mit Personen: nur an die Fenster am PC

    def message(self, remote: bool = False) -> dict[str, Any]:
        if not self.on:
            return {"type": "erfahrung", "an": False}
        return {**self.netz.message(ohne_personen=remote), "an": True, "herkuenfte": self.rt.herkunft_namen()}

    # ── für Claude ────────────────────────────────────────────────────────
    def context(self, text: str = "") -> dict[str, Any] | None:
        """Was ihr gerade einfällt – kleiner Ausschnitt. Personen nie in einer Runde vom Handy."""
        if not self.on:
            return None
        ohne = ("person",) if R.REMOTE_TURN.get() else ()
        low = text.lower()
        genannt = {k for k, kn in self.netz.knoten.items() if len(kn["name"]) > 2 and kn["name"].lower() in low}
        aktiv = self.netz._aktiv()
        cue = {**{k: 0.5 * v for k, v in aktiv.items()}, **{k: 1.0 for k in genannt}}
        # Was genannt ist oder gerade stark passiert, „fällt ihr nicht ein“ – es ist ja da
        jetzt = genannt | {k for k, v in self.netz.akt.items() if v > 0.6}
        einfall = self.netz.recall(cue, k=5, ohne=ohne, skip=jetzt)
        if not einfall:
            return None
        out: dict[str, Any] = {"faellt_ihr_ein": [f"{e['name']} ({e['art']}, {e['staerke']})" for e in einfall]}
        pr = self.netz.praegung()
        if abs(pr["energie"]) > 0.02:
            out["praegung"] = f"durch {pr['grund']} etwas {'lebhafter' if pr['energie'] > 0 else 'ruhiger'} geworden"
        return out
