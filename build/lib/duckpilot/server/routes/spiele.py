"""Spiele mit der Webcam für Reachy Mini (seit 0.38.13, ausgebaut 0.38.14).

- „Rotes Licht, grünes Licht“ mit Stufen (leicht, mittel, schwer), Punkten und Bestzeit je Stufe,
- „Hand folgen“ (Handerkennung oder – ohne Modell – Bewegung),
- „Mach mir nach“: Reachy macht Kopf- und Antennenbewegungen vor (links, rechts, oben, unten), du zeigst sie mit der
  Hand nach; je nach Stufe wird die Folge länger, drei Leben,
- „Schere, Stein, Papier“: nur mit geladener Handerkennung (die Geste liest der Browser aus den Handpunkten).

Die Webcam wertet nur der Browser am PC aus (`static/kamera_spiele.js`, `static/hand.js`) – hierher kommen keine
Bilder, nur Zahlen und Wörter: eine Blickrichtung in Grad (relativ zur Grundrichtung des Sockels, + = links, Nicken
+ = nach unten), eine Stärke 0 … 1, die Phase der Ampel, eine Richtung („links“ …) oder eine Geste („stein“ …).
Gespeichert werden nur Bestwerte (Zahlen) in `<daten>/spiele.json`.

Bewegt wird über die Engine (`motion/reachy_spiel.SpielHaltung`) mit allen Sicherheitsregeln: nur, wenn Reachy der
aktive Körper ist und wach; nie während der Sperre nach einem Not-Aus (`engine.notaus_gesperrt()`); der Not-Aus
(Knopf, Esc, „Stopp“, stop-Werkzeug) beendet das Spiel sofort – das Verhalten endet mit `stop_all`, laufende
Vorführungen hören beim nächsten Schritt auf, und jede weitere Anfrage wird abgelehnt, bis jemand neu startet.
Nur am PC (`remote.PC_ONLY`).

Reachy spricht über den normalen Weg seiner Verkörperung (Chat mit `source: "spiel"`, eigene Stimme, keine
Entenlaute). Seine Sätze wechseln ab und sagen nie „Stopp“ (das Mikrofon könnte es als Not-Aus hören).
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...aio import spawn
from ...motion.reachy_gesten import geste
from ...motion.reachy_spiel import KOERPER_MAX, KOPF_PITCH_MAX, NUR_KOPF, SpielHaltung, begrenzt
from ..runtime import Runtime

ARTEN = ("ampel", "folgen", "spiegel", "ssp")
FRIST_S = {"ampel": 40.0, "folgen": 8.0, "spiegel": 60.0, "ssp": 90.0}   # so lange ohne Nachricht → Spiel endet
FOLGEN_YAW_MAX = 90.0                          # Grad – weiter folgt Reachy der Hand vor der Kamera nicht
BLICK_MIN_S = 0.06                             # höchstens ≈ 16 Ziele je Sekunde annehmen (die Oberfläche schickt ≤ 8)
STUFEN = {"leicht": 1, "mittel": 2, "schwer": 3}        # Stufe → Punkte-Faktor

# Rotes Licht, grünes Licht: Sätze mit Abwechslung (nie „Stopp“ – das Mikrofon hört mit)
SAETZE: dict[str, tuple[str, ...]] = {
    "gruen": ("Grünes Licht!", "Grünes Licht – los!", "Grün! Schleich dich an!", "Grünes Licht, ich schau weg."),
    "rot": ("Rotes Licht!", "Rot! Keiner rührt sich!", "Rotes Licht – erstarren!", "Rot! Ich schau genau hin."),
    "ueberlebt": ("Du warst mucksmäuschenstill!", "Hm, nichts gesehen.", "Gut erstarrt!", "Wie eine Statue!"),
    "erwischt": ("Erwischt! Du hast dich bewegt – zurück an den Start.", "Ha, gesehen! Zurück an den Start.",
                 "Da hat was gewackelt! Noch mal von vorn."),
    "geschafft": ("Geschafft! Du hast gewonnen.", "Du hast mich erreicht – gewonnen!",
                  "Wow, geschafft! Du warst richtig leise."),
}

# Mach mir nach: Richtung aus Sicht des Menschen → Reachys Kopf (Grad) und Antennen (rechts, links; + = nach außen).
# Reachy steht dem Menschen gegenüber: „links“ für den Menschen ist Reachys rechte Seite (Drehen −).
RICHTUNGEN: dict[str, dict[str, Any]] = {
    "links": {"yaw": -25.0, "pitch": 0.0, "antennen": (70.0, 10.0)},
    "rechts": {"yaw": 25.0, "pitch": 0.0, "antennen": (10.0, 70.0)},
    "oben": {"yaw": 0.0, "pitch": -14.0, "antennen": (0.0, 0.0)},
    "unten": {"yaw": 0.0, "pitch": 14.0, "antennen": (110.0, 110.0)},
}
SPIEGEL_LAENGE = {"leicht": (1, 1), "mittel": (1, 3), "schwer": (2, 5)}  # Stufe → (Start, höchstens)
SPIEGEL_RUNDEN = 6
SPIEGEL_LEBEN = 3
SPIEGEL_SCHRITT_S = {"leicht": 1.6, "mittel": 1.3, "schwer": 1.0}
SPIEGEL_SAETZE: dict[str, tuple[str, ...]] = {
    "start": ("Pass gut auf und mach mir nach!", "Schau genau hin – dann bist du dran.", "Ich mach's vor!"),
    "richtig": ("Richtig!", "Genau so!", "Super nachgemacht!", "Prima!"),
    "falsch": ("Fast! Ich hatte nach {r} geschaut.", "Knapp daneben – es war {r}.", "Hoppla, das war {r}."),
    "gewonnen": ("Du hast alles nachgemacht – gewonnen!", "Wow, du bist ein echter Spiegel!"),
    "vorbei": ("Das war lustig! Du hast {p} Punkte.", "Spiel vorbei – {p} Punkte, nicht schlecht!"),
}
RICHTUNG_WORT = {"links": "links", "rechts": "rechts", "oben": "oben", "unten": "unten"}

# Schere, Stein, Papier
SSP = ("schere", "stein", "papier")
SSP_SCHLAEGT = {"stein": "schere", "schere": "papier", "papier": "stein"}
SSP_WARUM = {"stein": "Stein schleift die Schere", "schere": "Schere schneidet Papier",
             "papier": "Papier wickelt den Stein ein"}
SSP_NAME = {"schere": "Schere", "stein": "Stein", "papier": "Papier"}
SSP_ZIEL = 3                                   # wer zuerst drei Runden gewinnt
SSP_ZAEHL_S = 1.8                              # „Schnick, Schnack, Schnuck“
# Reachy zeigt seine Wahl mit den Antennen (rechts, links) und dem Kopf (Nicken in Grad)
SSP_HALTUNG = {"stein": ((0.0, 0.0), 8.0), "papier": ((90.0, 90.0), -6.0), "schere": ((40.0, 40.0), 0.0)}
SSP_SAETZE: dict[str, tuple[str, ...]] = {
    "reachy": ("Ich hatte {r}. {w} – Punkt für mich!", "{r}! {w}. Diesmal ich!"),
    "mensch": ("Ich hatte {r}. {w} – Punkt für dich!", "Oh, {r} verliert. {w}. Gut gemacht!"),
    "gleich": ("Wir hatten beide {r} – unentschieden!", "Beide {r}! Noch mal!"),
    "unklar": ("Das hab ich nicht erkannt – zeig mir deine Hand noch mal.",
               "Hm, war das Schere, Stein oder Papier? Noch mal bitte."),
}


def _dauer_text(sekunden: float) -> str:
    minuten = max(2, round(sekunden / 60))
    return "zwei Minuten" if minuten == 2 else f"{minuten} Minuten"


class SpielDienst:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self.art: str | None = None
        self.haltung: SpielHaltung | None = None
        self.seit = 0.0
        self.runde = 0
        self.phase: str | None = None
        self.stufe = "mittel"
        self.punkte = 0
        self.t_start: float | None = None
        self._blick_at = 0.0
        self._antenne_at = 0.0
        self._zuletzt: dict[str, str] = {}
        # Mach mir nach
        self.folge: list[str] = []
        self.index = 0
        self.leben = SPIEGEL_LEBEN
        self._neue_folge = True
        # Schere, Stein, Papier
        self.stand = {"mensch": 0, "reachy": 0}

    # ── Bestwerte (nur Zahlen) ───────────────────────────────────────────
    @staticmethod
    def _bestwerte_pfad() -> Path:
        from ... import settings as S

        return S.settings_path().parent / "spiele.json"

    def bestwerte(self) -> dict[str, Any]:
        try:
            data = json.loads(self._bestwerte_pfad().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _bestwert_merken(self, spiel: str, stufe: str, werte: dict[str, float], kleiner_besser: str | None = None
                         ) -> dict[str, bool]:
        """Merkt bessere Werte (Punkte: mehr ist besser; `kleiner_besser`: z. B. Bestzeit). Gibt zurück, was neu ist."""
        alle = self.bestwerte()
        bisher = alle.setdefault(spiel, {}).setdefault(stufe, {})
        neu: dict[str, bool] = {}
        for key, wert in werte.items():
            alt = bisher.get(key)
            besser = alt is None or (wert < alt if key == kleiner_besser else wert > alt)
            if besser:
                bisher[key] = wert
            neu[key] = bool(besser)
        self._speichern(alle)
        return neu

    def _hochzaehlen(self, spiel: str, stufe: str, key: str) -> int:
        alle = self.bestwerte()
        bisher = alle.setdefault(spiel, {}).setdefault(stufe, {})
        bisher[key] = int(bisher.get(key) or 0) + 1
        self._speichern(alle)
        return bisher[key]

    def _speichern(self, alle: dict[str, Any]) -> None:
        try:
            pfad = self._bestwerte_pfad()
            pfad.parent.mkdir(parents=True, exist_ok=True)
            tmp = pfad.with_name(pfad.name + ".teil")
            tmp.write_text(json.dumps(alle, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(pfad)
        except OSError:
            pass

    # ── was geht ─────────────────────────────────────────────────────────
    def grund(self) -> str | None:
        """Warum gerade kein Spiel starten darf – oder None."""
        if not self.rt.ist_reachy():
            return "Die Kamera-Spiele gibt es nur, wenn Reachy Mini der Körper ist."
        eng = self.rt.engine
        if eng.notaus_gesperrt():
            return f"Nach dem Not-Aus ruht Reachy {_dauer_text(eng.sperre_s)} – danach geht das Spiel wieder."
        st = self.rt.backend.state()
        if not st.powered or st.sitting:
            return "Reachy schläft – erst aufwecken."
        return None

    def simulator(self) -> bool:
        try:
            return "simulator" in self.rt.backend.eigenschaften()
        except Exception:  # noqa: BLE001 – ein Körper ohne Eigenschaften ist kein Simulator
            return False

    def laeuft(self) -> str | None:
        """Art des laufenden Spiels – None, wenn keins läuft oder der Not-Aus es beendet hat."""
        if self.art is None:
            return None
        h = self.haltung
        if self.rt.engine.estop_at >= self.seit or h is None or h.done or self.rt.engine.current is not h:
            self._aus()
            return None
        return self.art

    def _darf(self, h: SpielHaltung, art: str) -> bool:
        """Darf eine laufende Vorführung weitermachen? Nicht nach Not-Aus, Körperwechsel oder neuem Spiel."""
        return self.haltung is h and self.laeuft() == art and not self.rt.engine.notaus_gesperrt()

    def status(self) -> dict[str, Any]:
        return {"ok": True, "aktiv": self.rt.ist_reachy(), "laeuft": self.laeuft(), "runde": self.runde,
                "phase": self.phase, "grund": self.grund(), "simulator": self.simulator(), "punkte": self.punkte,
                "stufe": self.stufe, "bestwerte": self.bestwerte()}

    def _satz(self, tabelle: dict[str, tuple[str, ...]], key: str, **werte: Any) -> str:
        """Ein Satz aus der Liste – nie zweimal hintereinander derselbe."""
        auswahl = [s for s in tabelle[key] if s != self._zuletzt.get(key)] or list(tabelle[key])
        satz = random.choice(auswahl)
        self._zuletzt[key] = satz
        return satz.format(**werte) if werte else satz

    def _antennen(self, rechts_grad: float, links_grad: float, dauer: float = 0.35) -> None:
        setzen = getattr(self.rt.backend, "antennen_setzen", None)
        if setzen is None or self.rt.engine.notaus_gesperrt():
            return
        self.rt.engine.fire(setzen(-math.radians(rechts_grad), math.radians(links_grad), dauer))

    def _geste(self, *namen: str, meldung: str) -> None:
        if self.rt.engine.notaus_gesperrt():
            return
        spec = geste(random.choice(namen))
        if spec:
            self.rt.engine.play_overlay(spec, meldung, force=True)

    # ── Ablauf ───────────────────────────────────────────────────────────
    def start(self, art: str, stufe: str | None = None) -> dict[str, Any]:
        if art not in ARTEN:
            return {"ok": False, "fehler": f"Unbekanntes Spiel „{art}“"}
        warum = self.grund()
        if warum:
            return {"ok": False, "fehler": warum}
        if art == "ssp":
            hand = getattr(self.rt, "hand", None)
            if hand is None or not hand.bereit():
                return {"ok": False, "fehler": "„Schere, Stein, Papier“ braucht die Handerkennung – erst laden."}
        self.rt.alltag.touch()
        h = SpielHaltung(art, FRIST_S[art])
        h.beendet = lambda ergebnis, h=h: self._beendet(h, ergebnis)
        self.art, self.haltung, self.seit = art, h, time.monotonic()
        self.runde, self.phase, self.punkte, self.t_start = 0, None, 0, None
        self.stufe = stufe if stufe in STUFEN else "mittel"
        self.folge, self.index, self.leben, self._neue_folge = [], 0, SPIEGEL_LEBEN, True
        self.stand = {"mensch": 0, "reachy": 0}
        self.rt.engine.run(h)
        h.setze(0.0, 0.0, koerper=0.0)                 # zuerst zum Menschen schauen
        return {"ok": True, "art": art, "stufe": self.stufe, "simulator": self.simulator(),
                "bestwerte": self.bestwerte().get(art, {})}

    def stopp(self, grund: str = "beendet") -> dict[str, Any]:
        h = self.haltung
        self._aus()
        eng = self.rt.engine
        if h is not None and eng.current is h:
            eng.cancel_current(grund)
        return {"ok": True}

    def _aus(self) -> None:
        self.art, self.haltung, self.phase = None, None, None

    def _beendet(self, h: SpielHaltung, ergebnis: str) -> None:
        """Das Verhalten ist zu Ende (Not-Aus, Frist, anderes Verhalten) – die Oberfläche hört sofort auf."""
        if h is not self.haltung:
            return                                      # ein neueres Spiel läuft schon
        notaus = self.rt.engine.estop_at >= self.seit
        self._aus()
        spawn(self.rt.broadcast({"type": "spiel", "laeuft": None, "notaus": notaus,
                                 "grund": "Not-Aus – Spiel beendet" if notaus else ergebnis}))

    def _abgelehnt(self, art: str) -> dict[str, Any] | None:
        if self.laeuft() != art:
            return {"ok": False, "laeuft": None, "fehler": "Das Spiel läuft nicht (mehr) – neu starten."}
        return None

    # ── Hand folgen ──────────────────────────────────────────────────────
    def blick(self, yaw_grad: float, pitch_grad: float, staerke: float) -> dict[str, Any]:
        """Hand folgen: Blickziel in Grad (relativ), begrenzt und sanft über die Engine."""
        if (nein := self._abgelehnt("folgen")) is not None:
            return nein
        jetzt = time.monotonic()
        h = self.haltung
        assert h is not None
        if jetzt - self._blick_at < BLICK_MIN_S:
            h.lebt()
            return {"ok": True, "gedrosselt": True}
        self._blick_at = jetzt
        yaw = math.radians(begrenzt(yaw_grad, FOLGEN_YAW_MAX))
        pitch = begrenzt(math.radians(begrenzt(pitch_grad, 90.0)), KOPF_PITCH_MAX)
        h.setze(yaw, pitch)
        staerke = max(0.0, min(1.0, float(staerke or 0.0)))
        if staerke > 0.05 and jetzt - self._antenne_at > 0.3:
            self._antenne_at = jetzt                    # Antennen zucken leicht mit – die Seite der Bewegung mehr
            grund = 10.0 + 30.0 * staerke
            links, rechts = (grund + 10.0, grund) if yaw > 0 else (grund, grund + 10.0)
            self._antennen(rechts, links)
        return {"ok": True, "yaw": round(math.degrees(h.blick_yaw), 1), "pitch": round(math.degrees(h.pitch), 1),
                "koerper": round(math.degrees(h.koerper_ziel), 1)}

    # ── Rotes Licht, grünes Licht ────────────────────────────────────────
    async def ampel(self, phase: str) -> dict[str, Any]:
        """Reachy dreht sich weg (grün) oder um (rot), erwischt dich oder freut sich mit dir. Punkte: je
        überstandenem roten Licht 10 × Stufe, beim Ziel ein Zeitbonus; Bestzeit je Stufe."""
        if phase not in ("gruen", "rot", "erwischt", "geschafft"):
            return {"ok": False, "fehler": f"Unbekannte Phase „{phase}“"}
        if (nein := self._abgelehnt("ampel")) is not None:
            return nein
        h = self.haltung
        assert h is not None
        eng = self.rt.engine
        faktor = STUFEN[self.stufe]
        jetzt = time.monotonic()
        ueberlebt = self.phase == "rot" and phase in ("gruen", "geschafft")
        if ueberlebt:
            self.punkte += 10 * faktor
        if self.t_start is None:
            self.t_start = jetzt
        self.phase = phase
        extra: dict[str, Any] = {}
        if phase == "gruen":                            # wegdrehen: Körper fast ganz herum, Kopf den Rest
            seite = random.choice((-1.0, 1.0))
            h.setze(seite * (KOERPER_MAX + NUR_KOPF), 0.0, koerper=seite * KOERPER_MAX)
            self._antennen(35.0, 35.0, 0.6)            # entspannt
            satz = self._satz(SAETZE, "gruen")
            if ueberlebt:
                satz = f"{self._satz(SAETZE, 'ueberlebt')} {satz}"
        elif phase == "rot":
            self.runde += 1
            h.setze(0.0, 0.0, koerper=0.0)
            self._antennen(0.0, 0.0, 0.3)               # aufmerksam: Antennen senkrecht
            satz = self._satz(SAETZE, "rot")
        elif phase == "erwischt":
            self.runde = 0
            h.setze(0.0, 0.0, koerper=0.0)
            self._geste("nein", "stolz", meldung="hat dich erwischt")
            satz = self._satz(SAETZE, "erwischt")
        else:                                           # geschafft
            h.setze(0.0, -math.radians(6), koerper=0.0)
            if eng.notaus_gesperrt() or not eng.express("freude", force=True):
                self._geste("begeistert", "freude", meldung="freut sich mit dir")
            zeit = round(jetzt - self.t_start, 1)
            self.punkte += max(0, round(90 - zeit)) * faktor
            neu = self._bestwert_merken("ampel", self.stufe, {"bestzeit_s": zeit, "punkte": self.punkte},
                                        kleiner_besser="bestzeit_s")
            best = self.bestwerte().get("ampel", {}).get(self.stufe, {})
            extra = {"zeit_s": zeit, "bestzeit_s": best.get("bestzeit_s"), "neue_bestzeit": neu["bestzeit_s"]}
            satz = self._satz(SAETZE, "geschafft")
            if neu["bestzeit_s"]:
                satz += f" Neue Bestzeit: {round(zeit)} Sekunden!"
        await self._sagen(satz)
        dreh = abs(h.koerper_ziel - h.koerper_jetzt(self.rt.backend.state()))
        return {"ok": True, "phase": phase, "runde": self.runde, "dreh_s": round(dreh / 0.9 + 0.3, 1),
                "punkte": self.punkte, "ueberlebt": ueberlebt, "satz": satz, **extra}

    # ── Mach mir nach ────────────────────────────────────────────────────
    def _naechste_folge(self) -> list[str]:
        start, hoechstens = SPIEGEL_LAENGE[self.stufe]
        laenge = min(hoechstens, start + self.runde)
        if self.stufe == "leicht" or not self.folge:
            folge = []
        else:
            folge = list(self.folge)                    # wie beim Merkspiel: die alte Folge plus eine neue Bewegung
        while len(folge) < laenge:
            moeglich = [r for r in RICHTUNGEN if not folge or r != folge[-1]]
            folge.append(random.choice(moeglich))
        return folge[:laenge]

    async def spiegel_zeigen(self) -> dict[str, Any]:
        """Reachy macht die (nächste) Folge vor. Nach einem Fehler dieselbe Folge noch einmal."""
        if (nein := self._abgelehnt("spiegel")) is not None:
            return nein
        h = self.haltung
        assert h is not None
        h.lebt()
        if self._neue_folge or not self.folge:
            self.folge = self._naechste_folge()
            self._neue_folge = False
        self.index = 0
        schritt = SPIEGEL_SCHRITT_S[self.stufe]
        if self.runde == 0 and self.leben == SPIEGEL_LEBEN:
            await self._sagen(self._satz(SPIEGEL_SAETZE, "start"))
        spawn(self._vormachen(h, list(self.folge), schritt))
        return {"ok": True, "folge": list(self.folge), "schritt_s": schritt, "runde": self.runde,
                "runden": SPIEGEL_RUNDEN, "leben": self.leben, "punkte": self.punkte}

    async def _vormachen(self, h: SpielHaltung, folge: list[str], schritt: float) -> None:
        """Kopf und Antennen zeigen jede Richtung; nach jedem Schritt kurz zurück zur Mitte."""
        for richtung in folge:
            if not self._darf(h, "spiegel"):
                return
            r = RICHTUNGEN[richtung]
            h.setze(math.radians(r["yaw"]), math.radians(r["pitch"]), koerper=0.0)
            self._antennen(*r["antennen"], 0.3)
            await asyncio.sleep(schritt * 0.65)
            if not self._darf(h, "spiegel"):
                return
            h.setze(0.0, 0.0, koerper=0.0)
            self._antennen(10.0, 10.0, 0.3)
            await asyncio.sleep(schritt * 0.35)

    async def spiegel_antwort(self, richtung: str) -> dict[str, Any]:
        """Eine nachgemachte Richtung prüfen (`keine` = nicht rechtzeitig)."""
        if (nein := self._abgelehnt("spiegel")) is not None:
            return nein
        if not self.folge or self.index >= len(self.folge):
            return {"ok": False, "fehler": "Reachy hat noch nichts vorgemacht."}
        h = self.haltung
        assert h is not None
        h.lebt()
        faktor = STUFEN[self.stufe]
        erwartet = self.folge[self.index]
        res: dict[str, Any] = {"ok": True, "erwartet": erwartet, "richtung": richtung}
        if richtung == erwartet:
            self.index += 1
            self.punkte += 10 * faktor
            fertig = self.index >= len(self.folge)
            res |= {"richtig": True, "fertig": fertig}
            self._antennen(60.0, 60.0, 0.25)            # kurz freuen
            if fertig:
                self.runde += 1
                self.punkte += 5 * faktor
                self._neue_folge = True
                if self.runde >= SPIEGEL_RUNDEN:
                    res |= self._spiegel_ende(gewonnen=True)
                    if not self.rt.engine.notaus_gesperrt() and not self.rt.engine.express("freude", force=True):
                        self._geste("begeistert", meldung="freut sich mit dir")
                    await self._sagen(self._satz(SPIEGEL_SAETZE, "gewonnen"))
                else:
                    self._geste("ja", meldung="nickt – richtig nachgemacht")
                    await self._sagen(self._satz(SPIEGEL_SAETZE, "richtig"))
        else:
            self.leben -= 1
            self.index = 0
            res |= {"richtig": False, "fertig": False}
            if self.leben <= 0:
                res |= self._spiegel_ende(gewonnen=False)
                self._geste("einfuehlsam", meldung="tröstet dich")
                await self._sagen(self._satz(SPIEGEL_SAETZE, "vorbei", p=self.punkte))
            else:
                self._geste("verlegen", "einfuehlsam", meldung="war das knapp")
                await self._sagen(self._satz(SPIEGEL_SAETZE, "falsch", r=RICHTUNG_WORT.get(erwartet, erwartet)))
        return res | {"runde": self.runde, "runden": SPIEGEL_RUNDEN, "leben": self.leben, "punkte": self.punkte}

    def _spiegel_ende(self, gewonnen: bool) -> dict[str, Any]:
        neu = self._bestwert_merken("spiegel", self.stufe, {"punkte": self.punkte})
        best = self.bestwerte().get("spiegel", {}).get(self.stufe, {})
        return {"vorbei": True, "gewonnen": gewonnen, "bestpunkte": best.get("punkte"), "neuer_rekord": neu["punkte"]}

    # ── Schere, Stein, Papier ────────────────────────────────────────────
    async def ssp_zaehlen(self) -> dict[str, Any]:
        """„Schnick, Schnack, Schnuck“: Reachy nickt dreimal im Takt, danach zeigt der Mensch seine Hand."""
        if (nein := self._abgelehnt("ssp")) is not None:
            return nein
        h = self.haltung
        assert h is not None
        h.lebt()
        h.setze(0.0, 0.0, koerper=0.0)
        self._antennen(10.0, 10.0, 0.3)
        spawn(self._nicken(h))
        await self._sagen("Schnick, Schnack, Schnuck!")
        return {"ok": True, "zaehl_s": SSP_ZAEHL_S}

    async def _nicken(self, h: SpielHaltung) -> None:
        takt = SSP_ZAEHL_S / 3
        for _ in range(3):
            if not self._darf(h, "ssp"):
                return
            h.setze(0.0, math.radians(10), koerper=0.0)
            await asyncio.sleep(takt * 0.5)
            if not self._darf(h, "ssp"):
                return
            h.setze(0.0, math.radians(-4), koerper=0.0)
            await asyncio.sleep(takt * 0.5)

    async def ssp_zug(self, geste_mensch: str) -> dict[str, Any]:
        """Der Mensch zeigt seine Geste (vom Browser aus den Handpunkten gelesen); Reachy wählt zufällig."""
        if (nein := self._abgelehnt("ssp")) is not None:
            return nein
        h = self.haltung
        assert h is not None
        h.lebt()
        if geste_mensch not in SSP:
            await self._sagen(self._satz(SSP_SAETZE, "unklar"))
            return {"ok": True, "unklar": True, "stand": dict(self.stand)}
        wahl = random.choice(SSP)
        (rechts, links), nicken = SSP_HALTUNG[wahl]
        h.setze(0.0, math.radians(nicken), koerper=0.0)
        self._antennen(rechts, links, 0.25)
        if wahl == geste_mensch:
            sieger = "gleich"
        elif SSP_SCHLAEGT[wahl] == geste_mensch:
            sieger = "reachy"
        else:
            sieger = "mensch"
        if sieger != "gleich":
            self.stand[sieger] += 1
        gewinner_geste = wahl if sieger == "reachy" else geste_mensch
        satz = self._satz(SSP_SAETZE, sieger, r=SSP_NAME[wahl], w=SSP_WARUM[gewinner_geste])
        res: dict[str, Any] = {"ok": True, "reachy": wahl, "mensch": geste_mensch, "sieger": sieger,
                               "stand": dict(self.stand), "ziel": SSP_ZIEL}
        vorbei = max(self.stand.values()) >= SSP_ZIEL
        if vorbei:
            gewonnen = self.stand["mensch"] >= SSP_ZIEL
            self.punkte = self.stand["mensch"]
            siege = self._hochzaehlen("ssp", "alle", "siege") if gewonnen else int(
                self.bestwerte().get("ssp", {}).get("alle", {}).get("siege") or 0)
            res |= {"vorbei": True, "gewonnen": gewonnen, "siege": siege}
            satz += " Du hast das Spiel gewonnen!" if gewonnen else " Ich hab das Spiel gewonnen – Revanche?"
            self.stand = {"mensch": 0, "reachy": 0}       # eine Revanche fängt bei null an
        spawn(self._ssp_reaktion(h, sieger, vorbei))
        await self._sagen(satz)
        return res | {"satz": satz}

    async def _ssp_reaktion(self, h: SpielHaltung, sieger: str, vorbei: bool) -> None:
        await asyncio.sleep(1.2)                        # erst die Wahl zeigen, dann das Gefühl
        if not self._darf(h, "ssp"):
            return
        if sieger == "reachy":
            self._geste("stolz", "freude", meldung="freut sich über den Punkt")
        elif sieger == "mensch":
            self._geste("verlegen", "frustriert", meldung="hat die Runde verloren")
        else:
            self._geste("neugierig", meldung="staunt – unentschieden")

    async def _sagen(self, text: str) -> None:
        await self.rt.broadcast({"type": "chat", "role": "duck", "text": text, "source": "spiel", "seconds": 0,
                                 "sprache": self.rt._speech(text)})


def register(app: FastAPI, runtime: Runtime) -> None:
    dienst = SpielDienst(runtime)
    runtime.spiele = dienst                             # für Tests und spätere Werkzeuge

    async def body(request: Request) -> dict[str, Any]:
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001 – leerer oder kaputter Körper
            return {}
        return data if isinstance(data, dict) else {}

    def antwort(res: dict[str, Any]) -> JSONResponse:
        return JSONResponse(res, status_code=200 if res.get("ok") else 409)

    def zahl(d: dict[str, Any], key: str) -> float:
        try:
            v = float(d.get(key) or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return 0.0 if math.isnan(v) or math.isinf(v) else v

    def wort(d: dict[str, Any], key: str) -> str:
        return str(d.get(key) or "")[:20]

    @app.get("/api/spiele")
    async def spiele_status() -> JSONResponse:
        return JSONResponse(dienst.status())

    @app.post("/api/spiele/start")
    async def spiele_start(request: Request) -> JSONResponse:
        d = await body(request)
        return antwort(dienst.start(wort(d, "art"), wort(d, "stufe") or None))

    @app.post("/api/spiele/stopp")
    async def spiele_stopp() -> JSONResponse:
        return antwort(dienst.stopp())

    @app.post("/api/spiele/blick")
    async def spiele_blick(request: Request) -> JSONResponse:
        d = await body(request)
        return antwort(dienst.blick(zahl(d, "yaw"), zahl(d, "pitch"), zahl(d, "staerke")))

    @app.post("/api/spiele/ampel")
    async def spiele_ampel(request: Request) -> JSONResponse:
        return antwort(await dienst.ampel(wort(await body(request), "phase")))

    @app.post("/api/spiele/spiegel")
    async def spiele_spiegel(request: Request) -> JSONResponse:
        d = await body(request)
        aktion = wort(d, "aktion")
        if aktion == "zeigen":
            return antwort(await dienst.spiegel_zeigen())
        if aktion == "antwort":
            return antwort(await dienst.spiegel_antwort(wort(d, "richtung")))
        return antwort({"ok": False, "fehler": f"Unbekannte Aktion „{aktion}“"})

    @app.post("/api/spiele/ssp")
    async def spiele_ssp(request: Request) -> JSONResponse:
        d = await body(request)
        aktion = wort(d, "aktion")
        if aktion == "zaehlen":
            return antwort(await dienst.ssp_zaehlen())
        if aktion == "zug":
            return antwort(await dienst.ssp_zug(wort(d, "geste")))
        return antwort({"ok": False, "fehler": f"Unbekannte Aktion „{aktion}“"})
