"""Beschwerden beim Spielen: Im Kollisionsmodus quakt die Ente ab und zu, schüttelt den Kopf oder sagt etwas,
wenn man sie schubst, zieht oder umwirft – ohne dass es ihr Wesen verändert.

Regeln (Wunsch des Maintainers, 0.30.1):
* **Manchmal, nicht immer:** Wahrscheinlichkeit 35–80 % je nach Stärke (Sturz am ehesten), höchstens eine
  Beschwerde je Episode, mindestens `ABSTAND_S` zwischen zwei, nie zweimal dieselbe Geste oder derselbe Satz
  hintereinander.
* **Erst das Gleichgewicht:** Gesten frühestens `VERZUG_S` nach dem Reiz, nur im Stehen (nicht liegend, nicht im
  Aufrichten, nicht während eines Skills) und nur mit Kopf und Schnabel – die Körperhaltung der Geste wird
  weggelassen, damit Pollens Policy ungestört balanciert.
* **Kein Einfluss aufs Wesen:** Die Geste läuft als Einlage (`play_overlay`) ohne „gefuehl“-Ereignis, das
  Ereignis `protest` trägt `kollision: True` – Stimmung, Erfahrungsnetz und Pannen-Protokoll ignorieren es. Die
  Sätze sind ein kurzes „Hey!“, kein Vorwurf, der hängen bleibt.
* **Sicherheit:** Im Stopp-Fenster (Mikrofon offen) weder Ton noch Satz – sonst hört die Spracherkennung die Ente
  statt „Stopp“. Nicht innerhalb von 120 s nach einem Not-Aus, nicht hochgehoben, nicht in Ruhe (Motoren aus),
  nur bei eingeschaltetem Kollisionsmodus und Einstellung `kollision_protest`.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Callable

from .aio import spawn

log = logging.getLogger(__name__)

ABSTAND_S = 5.0          # mindestens so lange zwischen zwei Beschwerden
VERZUG_S = 1.2           # nach dem Reiz: erst fängt die Policy das Gleichgewicht, dann die Beschwerde
NACH_AUFSTEHEN_S = 0.6   # nach dem Wieder-Aufstehen kurz warten
SATZ_P = 0.45            # Anteil der Beschwerden mit Satz (nach einem Sturz öfter)
GESTE_P = 0.7            # Anteil mit Kopfgeste (wenn sie steht); sonst nur ein Quak
ESTOP_SPERRE_S = 120.0   # wie die Sperre fürs Selbst-Aufstehen

# Was je Lage passt. Gesten sind Pollens Emotionen bzw. eigene Kopfgesten (Kopf und Schnabel, mit ihrem Ton).
GESTEN = {
    "leicht": ("was_was", "hmm", "noe"),
    "kraeftig": ("grummelig", "wer_sagt_das", "ungeduldig", "noe", "trotzig"),
    "zug": ("noe", "ungeduldig", "was_was"),
    "sturz": ("schuetteln", "grummelig", "seufzen"),
    "goofy": ("lachen", "naeaeae", "schuetteln"),
    "ruhig": ("hmm", "seufzen", "nein"),
}
TOENE = {"leicht": "inquire", "kraeftig": "alarm", "zug": "inquire", "sturz": "coo", "goofy": "wheee", "ruhig": "coo"}
SAETZE = {
    "leicht": ("Hey!", "Huch!", "Quak?", "Na nu?"),
    "kraeftig": ("Quak – nicht schubsen!", "Na hör mal!", "Ich stand doch gerade so schön.", "He, ich wackel ja!"),
    "zug": ("Hey, nicht ziehen!", "Quak! Wo soll's denn hin?", "Ich komm ja schon …"),
    "sturz": ("Puh. Quak!", "Hoppla – wieder oben.", "Uff. Alles noch dran."),
    "goofy": ("Wheee – nochmal?", "Quak! Das war lustig!", "Huiii!", "Nochmal, nochmal!"),
    "ruhig": ("Hm.", "Quak.", "Na gut."),
}


@dataclass
class Reaktion:
    art: str                      # leicht | kraeftig | zug | sturz | goofy | ruhig
    geste: str | None = None
    ton: str | None = None
    satz: str | None = None


class Protest:
    """Entscheidet, ob und wie sie sich beschwert (ohne Seiteneffekte, gut testbar)."""

    def __init__(self, rng: random.Random | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.rng = rng or random.Random()
        self.clock = clock
        self.letzte = -1e9
        self._keys: list[Any] = []
        self._zuletzt: dict[str, str | None] = {"geste": None, "satz": None}

    @staticmethod
    def staerke(art: str, reiz: dict[str, Any]) -> float:
        """0…1 aus dem Reiz: Stoß nach Stärke/Impuls, Hand nach Tempo, Zug nach Kraft."""
        try:
            if art == "stoss":
                if "staerke" in reiz:
                    return float(reiz["staerke"])
                return float(reiz.get("impuls_ns", 0.3)) / 0.6
            if art == "hand":
                return float(reiz.get("tempo", 0.0)) / 2.5
            if art == "zug":
                return float(reiz.get("kraft_n", 3.0)) / 6.0
            if art in ("wurf", "rollen"):
                return 0.6
        except (TypeError, ValueError):
            pass
        return 0.5

    def wahrscheinlichkeit(self, staerke: float, sturz: bool = False) -> float:
        if sturz:
            return 0.8
        return 0.35 + 0.4 * max(0.0, min(1.0, staerke))

    def soll(self, key: Any, staerke: float, sturz: bool = False) -> bool:
        """Je Episode höchstens einmal fragen; Abstand und Zufall entscheiden."""
        if key in self._keys:
            return False
        self._keys = [*self._keys[-31:], key]
        if self.clock() - self.letzte < ABSTAND_S:
            return False
        return self.rng.random() < self.wahrscheinlichkeit(staerke, sturz)

    def _pick(self, was: str, pool: tuple[str, ...]) -> str:
        frei = [p for p in pool if p != self._zuletzt.get(was)] or list(pool)
        wahl = self.rng.choice(frei)
        self._zuletzt[was] = wahl
        return wahl

    def waehle(self, lage: str, steht: bool, goofy: bool = False, ruhig: bool = False,
               satz_ok: bool = True) -> Reaktion:
        """lage: leicht | kraeftig | zug | sturz. Charakter färbt: Goofy albern, ruhige Enten knapp."""
        art = "goofy" if goofy and lage != "zug" else ("ruhig" if ruhig and lage != "sturz" else lage)
        r = Reaktion(art)
        if steht and self.rng.random() < GESTE_P:
            r.geste = self._pick("geste", GESTEN[art])
        else:
            r.ton = TOENE[art]
        if satz_ok and self.rng.random() < (0.75 if lage == "sturz" else SATZ_P):
            r.satz = self._pick("satz", SAETZE[art])
        self.letzte = self.clock()
        return r


def nur_kopf(spec: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Die Geste ohne Körperhaltung – nur Kopf, Schnabel und Ton (stört das Balancieren nicht)."""
    return [{k: v for k, v in step.items() if k != "koerper"} for step in spec]


class ProtestDienst:
    """Hängt am Kollisionsdienst: bekommt Reize und Episodenenden, prüft die Sicherheitsregeln und führt aus."""

    def __init__(self, rt: Any, protest: Protest | None = None) -> None:
        self.rt = rt
        self.protest = protest or Protest()
        self._key: Any = None             # Episode, die gerade läuft (Start-Schlüssel)
        self._gemeldet: set[Any] = set()  # Episoden, zu denen sie sich schon beschwert hat

    # ── darf sie gerade? ─────────────────────────────────────────────────
    def an(self) -> bool:
        return bool(getattr(self.rt.config, "kollision_protest", True)) and \
            bool(getattr(self.rt.backend, "kollision_aktiv", False))

    def hindernis(self) -> str | None:
        """Warum gerade nicht – oder None."""
        if not self.an():
            return "aus"
        eng = self.rt.engine
        if getattr(eng, "_window_open", False):
            return "Stopp-Fenster offen"
        # die eingestellte Sperre (2, 5 oder 10 min) gilt, nicht fest zwei Minuten (0.38.14)
        sperre = max(ESTOP_SPERRE_S, float(getattr(eng, "sperre_s", ESTOP_SPERRE_S) or ESTOP_SPERRE_S))
        if time.monotonic() - getattr(eng, "estop_at", -1e9) <= sperre:
            return "Not-Aus-Sperre läuft"
        st = self.rt.backend.state()
        if st.picked_up:
            return "hochgehoben"
        if not st.powered:
            return "in Ruhe"
        return None

    def steht(self) -> bool:
        st = self.rt.backend.state()
        return bool(st.powered and not st.fallen and not st.skill and not st.picked_up)

    # ── Reize ─────────────────────────────────────────────────────────────
    def reiz(self, art: str, reiz: dict[str, Any], key: Any) -> None:
        """Episodenstart. Direkter Kontakt (Stoß, Zug, Hand) → vielleicht gleich beschweren; Würfe erst am Ende,
        wenn klar ist, ob sie getroffen wurde."""
        self._key = key
        if art not in ("stoss", "zug", "hand"):
            return
        st = Protest.staerke(art, reiz)
        lage = "zug" if art == "zug" else ("kraeftig" if st >= 0.55 else "leicht")
        self._planen(key, lage, st, VERZUG_S)

    def ende(self, ep: dict[str, Any]) -> None:
        """Episodenende: gewackelt, gefallen und wieder aufgestanden – oder ein Wurf, der sie getroffen hat."""
        key = self._key
        ausgang = ep.get("ausgang")
        if key is None or key in self._gemeldet or ausgang not in ("wackelt", "steht_wieder_auf"):
            return
        if ausgang == "steht_wieder_auf":
            self._planen(key, "sturz", 1.0, NACH_AUFSTEHEN_S, sturz=True)
        else:
            self._planen(key, "kraeftig", Protest.staerke(str(ep.get("art")), ep.get("reiz") or {}), 0.0)

    def _planen(self, key: Any, lage: str, staerke: float, verzug: float, sturz: bool = False) -> None:
        if self.hindernis() and not sturz:          # nach dem Sturz liegt sie noch: Hindernis erst beim Ausführen
            return
        if not self.protest.soll(key, staerke, sturz):
            return
        self._gemeldet = {*list(self._gemeldet)[-31:], key}
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        spawn(self._spaeter(lage, verzug))

    async def _spaeter(self, lage: str, verzug: float) -> None:
        if verzug > 0:
            await asyncio.sleep(verzug)
        await self.ausfuehren(lage)

    async def ausfuehren(self, lage: str) -> Reaktion | None:
        why = self.hindernis()
        if why:
            log.debug("keine Beschwerde: %s", why)
            return None
        cfg = self.rt.engine.config
        goofy = bool(getattr(cfg, "goofy", False))
        ruhig = float(getattr(cfg, "energie", 0.5)) < 0.3 and not goofy
        steht = self.steht()
        if lage != "sturz" and not steht:
            return None                             # liegt: das übernimmt das Stopp-Fenster und danach „sturz“
        r = self.protest.waehle(lage, steht, goofy=goofy, ruhig=ruhig)
        played = False
        if r.geste and getattr(cfg, "emotions", True):
            from .motion.behaviors import EMOTIONS

            spec = EMOTIONS.get(r.geste)
            played = bool(spec) and self.rt.engine.play_overlay(nur_kopf(spec))
        if not played:
            r.geste = None
            r.ton = r.ton or TOENE[r.art]
            try:
                await self.rt.backend.sound(r.ton)
            except Exception:
                log.debug("Quak", exc_info=True)
        text = " · ".join(x for x in (r.geste and f"Geste {r.geste}", r.ton and f"quakt ({r.ton})", r.satz) if x)
        self.rt.engine.note({"type": "protest", "kollision": True, "message": f"Beschwert sich beim Spielen: {text}"})
        if r.satz:
            speech = None
            try:
                speech = self.rt._speech(r.satz)
            except Exception:
                log.debug("Sprechen vorbereiten", exc_info=True)
            await self.rt.broadcast({"type": "chat", "role": "duck", "text": r.satz, "source": "spiel", "seconds": 0,
                                     "sprache": speech})
        return r
