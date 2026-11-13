"""Laufzeit, Bereich eigenständiges Verhalten (Wunsch des Maintainers 5.11.): Kommt eine Weile nichts vom Menschen, sucht sich
die Verkörperung selbst eine Beschäftigung – passend zum Charakter und zum Körper.

Teil der Klasse `Runtime` (server/runtime.py), ausgelagert wie `runtime_reachy.py`. Die Entscheidung steht in
`motion/eigenstaendig.py`; hier wird die Lage gesammelt und über dieselben Werkzeuge ausgeführt wie für die KI
(`ToolRunner.run` mit `fehlt_dem_koerper`). Alles, was dabei startet, ist als eigenständig markiert – jeder Befehl, jedes
Ansprechen und der Not-Aus beenden es sofort (`MotionEngine.kontakt`, `stop_all`).

Seit 0.38.44 (Etappe G3): Der Antrieb (`duckpilot/antrieb.py`) gewichtet, *was* sie tut – nie, *wie oft*; jede eigene
Handlung bekommt eine Zeile in der Gedankenspur (`duckpilot/gedankenspur.py`).
Seit 0.38.45 (Etappe G4): Nach `RUECKBLICK_RUHE_S` Ruhe schaut sie höchstens stündlich auf die Spur zurück und legt
Lehren ab (`duckpilot/rueckblick.py`); die wirken nur auf die Gewichte – dokumentiert, korrigierbar, nie erzählt.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from typing import Any

log = logging.getLogger(__name__)

TAKT_S = 1.0
SATZ_ANTEIL = 0.35          # so oft sagt ein verspielter Charakter etwas dazu
RUECKBLICK_RUHE_S = 600.0   # so lange kein Kontakt → Ruhephase für den Rückblick (seit 0.38.45)
RUECKBLICK_ABSTAND_S = 3600.0


class EigenstaendigTeil:
    """Mischklasse für `Runtime` – nicht allein benutzbar."""

    def _eigen_uhr(self):
        from ..motion.eigenstaendig import Eigenstaendig

        if getattr(self, "_eigen", None) is None:
            self._eigen = Eigenstaendig()
        return self._eigen

    @property
    def antrieb(self):
        from ..antrieb import Antrieb

        if getattr(self, "_antrieb", None) is None:
            self._antrieb = Antrieb()
        return self._antrieb

    @property
    def lehrbuch(self):
        from ..rueckblick import Lehrbuch
        from ..settings import data_dir

        if getattr(self, "_lehrbuch", None) is None:
            self._lehrbuch = Lehrbuch(data_dir() / "rueckblick.json")
        return self._lehrbuch

    def zurueckblicken(self) -> list[dict[str, Any]]:
        """Rückblick jetzt (Ruhephase oder Knopf am PC): Lehren aus der Gedankenspur ablegen – Knowlin sagt nichts dazu."""
        self._rueckblick_mono = time.monotonic()
        return self.lehrbuch.zurueckblicken(self.gedanken.liste(), self.config.modul, self.backend.eigenschaften())

    @property
    def gedanken(self):
        from ..gedankenspur import Gedankenspur

        if getattr(self, "_gedanken", None) is None:
            self._gedanken = Gedankenspur()
        return self._gedanken

    async def _eigenstaendig(self) -> None:
        """Hintergrundschleife: einmal je Sekunde prüfen, ob Zeit für eine eigene Beschäftigung ist."""
        while True:
            await asyncio.sleep(TAKT_S)
            try:
                await self.eigenstaendig_takt()
            except Exception:  # noqa: BLE001 – eigenes Verhalten darf nie etwas anderes stören
                log.debug("Eigenständiges Verhalten", exc_info=True)

    def eigenstaendig_sperre(self) -> str | None:
        from ..motion.eigenstaendig import sperre

        spiele = getattr(self, "spiele", None)
        return sperre(self.engine, haeufigkeit=self.config.eigenstaendig, im_koerper=self.im_koerper,
                      ruhe=bool(self.alltag.on and self.alltag.mode == "ruhe"),
                      spiel=bool(spiele is not None and spiele.laeuft()),
                      gespraech=self.chat_lock.locked())

    async def eigenstaendig_takt(self, jetzt: float | None = None) -> dict[str, Any] | None:
        """Ein Takt der Uhr – handelt, wenn genug Ruhe war. Rückgabe: was sie getan hat, sonst None."""
        cfg, eng = self.config, self.engine
        from ..motion.eigenstaendig import an

        if not an(cfg.eigenstaendig):
            eng.eigenstaendig_unterbrechen("ausgeschaltet")
        uhr = self._eigen_uhr()
        jetzt = time.monotonic() if jetzt is None else jetzt
        st = eng.last_state
        kontakt = eng.kontakt_at > getattr(self, "_antrieb_kontakt", 0.0)
        self._antrieb_kontakt = eng.kontakt_at
        self.antrieb.takt(jetzt, aktiv=bool(eng.busy() or st.skill), kontakt=kontakt,
                          akku=getattr(st, "battery", None), energie=cfg.energie)
        los = uhr.takt(jetzt, self.eigenstaendig_sperre(), warten=eng.overlay is not None, energie=cfg.energie,
                       humor=cfg.humor, haeufigkeit=cfg.eigenstaendig, kontakt_at=eng.kontakt_at)
        if not los and not eng.busy() and self._rueckblick_faellig(jetzt):
            self.zurueckblicken()
        return await self.eigenstaendig_handeln() if los else None

    def _rueckblick_faellig(self, jetzt: float) -> bool:
        """Ruhephase: lange kein Kontakt, letzter Rückblick lange her, und es gibt Neues in der Spur."""
        letzter = getattr(self, "_rueckblick_mono", None)
        if jetzt - self.engine.kontakt_at < RUECKBLICK_RUHE_S or (letzter is not None and jetzt - letzter < RUECKBLICK_ABSTAND_S):
            return False
        zeilen = self.gedanken.liste()
        return bool(zeilen) and zeilen[0]["zeit"] > self.lehrbuch.zuletzt

    def eigenstaendig_lage(self):
        from ..brain.tools import fehlt_dem_koerper
        from ..figuren import gestalt_standard
        from ..motion.eigenstaendig import Lage

        be = self.backend
        st = be.state()
        tricks: dict[str, list[dict[str, Any]]] = {}
        if self.memory is not None:
            for name, t in (self.memory.data.get("tricks") or {}).items():
                if isinstance(t, dict) and t.get("keyframes") and not (t.get("probe") is False and st.backend != "sim"):
                    tricks[name] = t["keyframes"]
        pollen: tuple[str, ...] = ()
        if self.ist_reachy():
            pollen = tuple(x["name"] for x in self.reachy_bewegungen.liste() if x["art"] == "emotionen")
        gestalt = self.config.eigenschaften
        return Lage(
            koerper=getattr(be, "koerper_art", "microduck"),
            echt=st.backend != "sim" or self.config.backend != "sim",
            eigenschaften=frozenset(be.eigenschaften()), skills=tuple(be.skills() or ()), sitzt=st.sitting,
            tricks=tricks, dinge=self._eigen_dinge(), pollen=pollen,
            gestalt=tuple(gestalt_standard(self.config.modul) if gestalt is None else gestalt),
            fehlt=lambda name: fehlt_dem_koerper(name, be))

    def _eigen_dinge(self) -> list[dict[str, Any]]:
        """Dinge im Zimmer mit Richtung und Entfernung: was sie sieht, im Simulator auch, was sie nicht im Blick hat."""
        st = self.backend.state()
        out = {o["name"]: dict(o) for o in st.perception.objects if o.get("name")}
        welt = getattr(self.backend, "world_model", None)

        def eintrag(name: str, art: str, x: float, y: float) -> None:
            if name in out:
                return
            rel = math.atan2(y - st.y, x - st.x) - st.yaw
            rel = (rel + math.pi) % (2 * math.pi) - math.pi
            out[name] = {"name": name, "art": art, "entfernung_m": round(math.hypot(x - st.x, y - st.y), 2),
                         "richtung_grad": round(math.degrees(rel))}

        if welt is not None:
            for i in getattr(welt, "items", ()):
                if not getattr(i, "held", False):
                    eintrag(i.name, i.kind, i.x, i.y)
            mensch = welt.person_point() if hasattr(welt, "person_point") else None
            if mensch is not None:
                eintrag("Mensch", "person", mensch[0], mensch[1])
        return list(out.values())

    async def eigenstaendig_handeln(self, art: str | None = None) -> dict[str, Any] | None:
        """Eine Beschäftigung wählen (oder die Art `art`, für Tests) und ausführen. Gibt zurück, was getan wurde."""
        from ..motion.eigenstaendig import EIGEN, angebot, waehlen

        cfg, eng, uhr = self.config, self.engine, self._eigen_uhr()
        lage = self.eigenstaendig_lage()
        angebote = angebot(lage, cfg.energie, cfg.humor, uhr.rng)
        if art is not None:
            angebote = [b for b in angebote if b.art == art]
        for b in angebote:                                     # der Antrieb gewichtet, was sie tut (nicht wie oft) …
            b.gewicht *= self.antrieb.faktor(b.art, b.ort) * self.lehrbuch.faktor(cfg.modul, b.art)   # … und Lehren
        wahl = waehlen(angebote, uhr.rng, uhr.zuletzt)
        if wahl is None:
            return None
        token = EIGEN.set(True)
        try:
            ok = await self._eigen_ausfuehren(wahl, lage)
        finally:
            EIGEN.reset(token)
        warum = self.antrieb.grund(wahl.art)
        person = wahl.nachricht.endswith(" dir") or wahl.args.get("ding") == "Mensch"
        if eng.notaus_gesperrt():                              # Not-Aus kam dazwischen: nichts davon bleibt
            eng.eigenstaendig_unterbrechen("Not-Aus")
            self.gedanken.merken(wahl.nachricht, warum, wie=wahl.werkzeug, ergebnis="vom Not-Aus beendet", person=person,
                                 art=wahl.art,
                                 koerper=self.config.modul)
            return None
        if not ok:
            self.gedanken.merken(wahl.nachricht, warum, wie=wahl.werkzeug, ergebnis="ging nicht", person=person, art=wahl.art,
                                 koerper=self.config.modul)
            return {"ok": False, "art": wahl.art}
        nachricht = ok if isinstance(ok, str) else wahl.nachricht    # z. B. statt der Geste umgeschaut
        self.gedanken.merken(nachricht, warum, wie=wahl.werkzeug, person=person, art=wahl.art,
                                 koerper=self.config.modul)
        self.antrieb.gestillt(wahl.art)
        uhr.zuletzt = wahl.art
        if not (wahl.art == "geste" and ok is True):     # die Geste meldet sich selbst im Ticker (mit eigenstaendig)
            eng.note({"type": "charakter", "message": nachricht, "eigenstaendig": True, "art": wahl.art})
        from ..antrieb import STILLT

        # Nähe drängt nie: wer aus Nähe handelt, bleibt still (Wertekern „nicht manipulieren“, seit 0.38.44)
        if wahl.satz and STILLT.get(wahl.art) != "naehe" and cfg.humor >= 0.5 and uhr.rng.random() < SATZ_ANTEIL:
            from .. import i18n

            await self._duck_says(i18n.t(wahl.satz))      # Reachy: `_speech` nimmt jedes Quaken heraus
        return {"ok": True, "art": wahl.art, "nachricht": nachricht, "werkzeug": wahl.werkzeug, "args": wahl.args}

    async def _eigen_ausfuehren(self, wahl, lage) -> bool | str:
        """Ausführen; True = wie angekündigt, ein Text = etwas anderes getan (steht dann im Ticker), False = ging nicht."""
        eng = self.engine
        if wahl.art == "geste":
            name = eng.idle_gesture()
            if name is None:                                   # keine Geste frei („Ausgeglichen“, Pause): umschauen
                ok = (await self.runner.run("look_around", {"seconds": 6})).get("ok")
                return "schaut sich von sich aus um" if ok else False
            return True
        if wahl.art == "pollen":                               # Reachy: Aufnahme aus Pollens Bibliothek
            res = await self.reachy_spielen(str(wahl.args.get("name")), ton=self.config.humor >= 0.5)
            if res.get("ok"):
                eng.eigen_extern_bis = time.monotonic() + float(res.get("dauer_s") or 3.0)
            return bool(res.get("ok"))
        vorher = eng.current
        res = await self.runner.run(str(wahl.werkzeug), dict(wahl.args))
        if not (isinstance(res, dict) and res.get("ok")):
            return False
        neu = eng.current if eng.current is not vorher else None
        if neu is not None and getattr(neu, "failed", False) and neu.done:
            return False
        if wahl.art == "ding":                                 # danach anstupsen (Schnabel) bzw. neugierig schauen
            from ..motion import behaviors as B

            spec = B.ANTICS["boden_picken"]["spec"] if "schnabel" in lage.eigenschaften else B.EMOTIONS["neugierig"]
            ch = B.Choreography.from_spec(spec, title="anstupsen", scale=eng.config.expressiveness)
            ch.needs_target = True                             # nicht ins Leere picken, wenn sie nicht ankam
            eng.run(ch, then=True)
        elif wahl.art == "zuwenden":                           # Reachy: hingedreht – kurz den Kopf neigen
            from ..api import Head
            from ..motion.behaviors import HoldHead

            eng.run(HoldHead(Head(0.0, -0.12, 0.0, random.choice((-0.15, 0.15))), 2.5), then=True)
        return True
