"""Mehrere Enten im Simulator (seit 0.36.3): eigene Position, eigenes Verhalten, Interaktion untereinander.

Wunsch des Maintainers: „den Mehr-Enten-Modus unabhängig von der Musik müssen wir supporten – Interaktion untereinander“ und
„bisher sind die anderen Enten einfach Clone, die sich fest an der Drehachse der Hauptente ausrichten“.

Was es bei Pollen und in der Community gibt (1.11.2026): keine Gruppenfunktionen bei Pollen; „Microduck audio identity“
leitet je Ente eine feste Stimme aus der Seriennummer ab und synchronisiert einen Chor per Takt-Signal; OpenCastor
findet mehrere Enten im Netz (Übersicht), koordiniert sie aber nicht. Übernommen: feste Stimme je Kennung, gemeinsamer
Takt, Übersicht mit Gruppenbefehlen. Neu: eigenes Verhalten und Begegnungen.

Die Begleitenten laufen wirklich: Sie drehen sich zum Ziel und gehen, stoßen an Möbel (die Welt ist dieselbe) und
weichen einander aus. Modi für die ganze Gruppe:
- **frei** – herumlaufen, stehen bleiben, die anderen anschauen; trifft eine Ente eine andere, begrüßt sie sie
  (zuwenden, nicken, Quak mit eigener Stimme), höchstens einmal je Paar und Minute.
- **folgen** – hinter der Hauptente her, jede auf ihrem Platz in einer lockeren Formation.
- **tanzen** – jede an ihrem Platz; tanzt die Hauptente, im selben Takt und mit ihrer Bewegung (wie ein Chor).
- **sitzen** – hinsetzen.
Tanzt die Hauptente, tanzen die anderen von selbst mit (abschaltbar). Not-Aus gilt für alle: 120 s Stillstand.
"""

from __future__ import annotations

import math
import random
import time
from typing import Any, Callable

from ..api import Head, Pose, Twist
from .tanz import GehoerTanz, MusikTanz

MODI = ("frei", "folgen", "tanzen", "sitzen")
MAX_ENTEN = 8               # seit 0.38.24 (vorher 4): Frage „wieso auf 4 begrenzt?“ – das Zimmer trägt acht Gäste
GRUSS_ABSTAND_M = 0.5
GRUSS_PAUSE_S = 60.0
ABSTAND_M = 0.32            # ab hier weichen sich zwei Enten aus
KOERPER_M = 0.24            # näher geht es nicht – Körper stoßen aneinander (wie an Möbeln)
DING_ABSTAND_M = 0.17       # so nah an liegende Dinge, dann sanft drumherum (seit 0.37.5)
ESTOP_S = 120.0
PLAETZE = ((-0.45, 0.3), (-0.45, -0.3), (-0.85, 0.15), (-0.85, -0.45),    # Formation hinter der Hauptente (m)
           (-0.85, 0.6), (-1.25, -0.15), (-1.25, 0.35), (-1.25, -0.65))


def _winkel(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


class Schwarm:
    def __init__(self, haupt: Any, engine: Any, fabrik: Callable[[int, float, float, float], Any], seed: int = 7) -> None:
        self.haupt = haupt            # der Simulator der Hauptente (Welt, Position, Laute)
        self.engine = engine          # für Takt und Not-Aus
        self.fabrik = fabrik          # (nummer, x, y, yaw) → Begleitente
        self.enten: list[Any] = []
        self.modus = "frei"
        self.mittanzen = True
        self.t = 0.0
        self.rng = random.Random(seed)
        self._ziel: dict[int, tuple[float, float, float]] = {}          # Nummer → (x, y, bis)
        self._platz: dict[int, tuple[float, float]] = {}                # Tanzplatz
        self._gruss: dict[int, tuple[float, float, float]] = {}         # Nummer → (bis, x, y) wem sie sich zuwendet
        self._gegruesst: dict[tuple[str, str], float] = {}
        self._gefallen_seit: dict[int, float] = {}
        self._tanz = MusikTanz({"bpm": 110, "schritte": []}, {}, "Schwarm")   # nur für die Tanzbewegungen
        self._reaktion: dict[int, tuple[str, float, float, float]] = {}   # Nummer → (art, bis, x, y) – seit 0.37.3
        self.auftrag: Any = None          # Teamarbeit (seit 0.37.4): Aufräumen oder Suchen – motion/team.py
        self._auftrag_ende = 0.0
        self._haupt_blick = 0.0
        if hasattr(haupt, "weitere_koerper"):
            haupt.weitere_koerper = self.koerper_liste     # die Hauptente sieht die anderen (Anwählen, Folgen)

    # ── Gruppe ────────────────────────────────────────────────────────────
    def anzahl(self, n: int) -> int:
        n = max(0, min(MAX_ENTEN, int(n)))
        while len(self.enten) > n:
            e = self.enten.pop()
            for d in (self._ziel, self._platz, self._gruss, self._gefallen_seit, self._reaktion):
                d.pop(e.nummer, None)
        while len(self.enten) < n:
            i = len(self.enten)
            x, y = self._freier_platz(i)
            self.enten.append(self.fabrik(i, x, y, self.haupt.yaw))
        return len(self.enten)

    def koerper_liste(self) -> list[tuple[str, float, float]]:
        return [(e.ente_name, e.x, e.y) for e in self.enten]

    def ente(self, name: str) -> Any:
        n = str(name or "").strip().lower()
        return next((e for e in self.enten if e.ente_name.lower() == n or e.kennung == n), None)

    REAKTION_S = {"gruss": 1.8, "aergern": 2.6}

    def reagiere(self, name: str, art: str, von: tuple[float, float]) -> str | None:
        """Die Hauptente begrüßt oder ärgert eine andere (seit 0.37.3, „Anwählen und Handeln“) – die antwortet:
        Gruß: zuwenden, nicken, Quak. Ärgern: zuwenden, Kopf schütteln, empörter Laut, ein Stück zurückweichen."""
        e = self.ente(name)
        if e is None or e.fallen or art not in self.REAKTION_S:
            return None
        self._reaktion[e.nummer] = (art, self.t + self.REAKTION_S[art], von[0], von[1])
        self._gruss.pop(e.nummer, None)
        tag, text = ("greet", f"{e.ente_name} grüßt zurück") if art == "gruss" else ("alarm", f"{e.ente_name} protestiert")
        self.haupt.emit("sound", tag=tag, ente=e.ente_name, klang=list(e.klang),
                           x=round(e.x, 2), y=round(e.y, 2))
        self.haupt.emit("schwarm", message=text)
        return text

    def setze_modus(self, modus: str) -> bool:
        if modus not in MODI:
            return False
        self.modus = modus
        self._platz.clear()
        self._ziel.clear()
        return True

    def uebersicht(self) -> list[dict[str, Any]]:
        out = []
        for e in self.enten:
            a = self.auftrag
            lage = a.lage.get(e.nummer) if a is not None and not a.fertig else None
            if lage is not None:
                tun = {"hin": f"holt {lage.get('ding', '')}", "tragen": f"trägt {lage.get('ding', '')}",
                       "suchen": "sucht", "gucken": "kommt gucken"}.get(lage.get("phase"), "hilft")
                out.append({"id": e.kennung, "name": e.ente_name, "klang": list(e.klang), "tut": tun})
                continue
            tun = ("liegt" if e.fallen else "sitzt" if e.sitting
                   else ("grüßt zurück" if self._reaktion[e.nummer][0] == "gruss" else "protestiert")
                   if e.nummer in self._reaktion else "begrüßt" if e.nummer in self._gruss
                   else {"folgen": "folgt", "tanzen": "tanzt", "frei": "läuft herum", "sitzen": "setzt sich"}[self.modus])
            if self._takt() and self.mittanzen and self.modus in ("frei", "folgen") and not e.fallen:
                tun = "tanzt mit"
            out.append({"id": e.kennung, "name": e.ente_name, "klang": list(e.klang), "tut": tun})
        return out

    def anzeige(self) -> list[dict[str, Any]]:
        return [{**e.anzeige(), "klang": list(e.klang)} for e in self.enten]

    # ── Takt ──────────────────────────────────────────────────────────────
    def beauftragen(self, auftrag: Any) -> None:
        """Teamarbeit starten (ersetzt einen laufenden Auftrag); alle stehen dafür auf und laufen frei."""
        self.auftrag = auftrag
        if self.modus in ("sitzen", "tanzen"):
            self.modus = "frei"

    def auftrag_stopp(self) -> str | None:
        a, self.auftrag = self.auftrag, None
        for e in self.enten:
            if e.holding:
                e._pick_or_drop()                        # was sie tragen, legen sie ab
        return a.art if a is not None else None

    def step(self, dt: float) -> None:
        if not self.enten:
            return
        self.t += dt
        a = self.auftrag
        if a is not None:
            if a.fertig:
                if not self._auftrag_ende:
                    self._auftrag_ende = self.t
                elif self.t - self._auftrag_ende > 4.0:  # Meldung stehen lassen, dann wieder frei
                    self.auftrag, self._auftrag_ende = None, 0.0
            elif hasattr(a, "haupt_sieht") and self.t - self._haupt_blick > 0.2:
                self._haupt_blick = self.t
                a.haupt_sieht(self.haupt._visible_objects())
        takt = self._takt()
        gesperrt = getattr(self.engine, "notaus_gesperrt", None)     # die eingestellte Sperre (≥ 120 s) gilt auch hier
        still = gesperrt() if callable(gesperrt) else time.monotonic() - getattr(self.engine, "estop_at", -1e9) <= ESTOP_S
        if still and self.auftrag is not None:
            self.auftrag_stopp()                         # Not-Aus beendet die Teamarbeit (alle legen ab)
        for e in self.enten:
            twist, head, pose, mund = self._regel(e, takt, still)
            twist = self._ausweichen(e, twist)
            e.steuern(twist, head, pose, mund)
            e.step(dt)
        self._koerper()
        self._begegnungen()

    def _takt(self) -> tuple[float, float, str] | None:
        cur = getattr(self.engine, "current", None)
        if isinstance(cur, (MusikTanz, GehoerTanz)) and not cur.done:
            return cur.takt()
        return None

    def _regel(self, e: Any, takt: tuple[float, float, str] | None, still: bool):
        ruhe = (Twist(), Head(0.0, 0.05, 0.0, 0.0), Pose(), 0.0)
        if e.fallen:
            seit = self._gefallen_seit.setdefault(e.nummer, self.t)
            if not still and self.t - seit > 3.0:          # wie die Hauptente: erst nach einer Weile wieder aufstehen
                e.aufstehen()
            return ruhe
        self._gefallen_seit.pop(e.nummer, None)
        if still:
            if e.powered:
                e.lahm()                                   # Not-Aus gilt für alle Enten im Zimmer: stromlos
            return ruhe
        if not e.powered:
            e.wecken()                                     # Sperre vorbei: die Gäste stehen wieder auf
            return ruhe
        if self.modus == "sitzen":
            e.setzen(True)
            return ruhe
        if e.sitting:
            e.setzen(False)
            return ruhe
        if e.nummer in self._reaktion:                       # Antwort auf Gruß oder Ärgern der Hauptente
            art, bis, gx, gy = self._reaktion[e.nummer]
            rest = bis - self.t
            if rest <= 0:
                self._reaktion.pop(e.nummer)
            else:
                fehler = _winkel(math.atan2(gy - e.y, gx - e.x) - e.yaw)
                dreh = max(-1.0, min(1.0, 2.5 * fehler))
                if art == "gruss":
                    return Twist(0.0, 0.0, dreh), Head(-0.1, 0.35 * math.sin(rest * 9), 0.0, 0.0), Pose(), 0.4
                if rest > 1.2:                               # empört: Kopf schütteln, Schnabel auf
                    return Twist(0.0, 0.0, dreh), Head(0.0, -0.1, 0.45 * math.sin(rest * 14), 0.0), Pose(), 0.8
                return Twist(-0.12, 0.0, dreh), Head(0.0, -0.15, 0.0, 0.0), Pose(-0.01, 0.0, -0.08), 0.2   # weicht zurück
        if self.auftrag is not None and not self.auftrag.fertig:     # Teamarbeit geht vor
            r = self.auftrag.regel(e)
            if r is not None:
                return r
        if e.nummer in self._gruss:                          # Begrüßung: zuwenden und nicken
            bis, gx, gy = self._gruss[e.nummer]
            if self.t > bis:
                self._gruss.pop(e.nummer)
            else:
                fehler = _winkel(math.atan2(gy - e.y, gx - e.x) - e.yaw)
                nick = 0.35 * math.sin((bis - self.t) * 9)
                return Twist(0.0, 0.0, max(-1.0, min(1.0, 2.5 * fehler))), Head(-0.1, nick, 0.0, 0.0), Pose(), 0.4
        if self.modus == "tanzen" or (takt and self.mittanzen and self.modus in ("frei", "folgen")):
            return self._tanzen(e, takt)
        if self.modus == "folgen":
            h = self.haupt
            dx, dy = PLAETZE[e.nummer % len(PLAETZE)]
            c, s = math.cos(h.yaw), math.sin(h.yaw)
            return self._hin(e, h.x + c * dx - s * dy, h.y + s * dx + c * dy, blick=(h.x, h.y))
        return self._frei(e)

    def _tanzen(self, e: Any, takt: tuple[float, float, str] | None):
        if takt is None:                                    # ohne Musik: eigener Takt, 110 BPM
            takt = (110.0, self.t * 110.0 / 60.0, ("schritt", "wiegen", "drehen", "wiegen")[int(self.t * 110 / 480) % 4])
        bpm, beat, art = takt
        if art not in ("schritt", "wiegen", "drehen", "nicken", "wippen", "wackeln"):
            art = "wiegen"                                  # Gesten und Posen der Hauptente: wiegen im Takt
        platz = self._platz.setdefault(e.nummer, (e.x, e.y))
        self._tanz.bpm = bpm
        richtung = 1.0 if (int(beat // 8) + e.nummer) % 2 == 0 else -1.0
        cmd = self._tanz._bewegung(art, beat, 0.5 if (beat % 1.0) < 0.2 and int(beat) % 2 == 0 else 0.0, richtung, 2)
        dx, dy = platz[0] - e.x, platz[1] - e.y               # am eigenen Platz bleiben
        c, s = math.cos(e.yaw), math.sin(e.yaw)
        k = 0.8
        tw = Twist(cmd.twist.vx + max(-0.06, min(0.06, k * (c * dx + s * dy))),
                   cmd.twist.vy + max(-0.06, min(0.06, k * (-s * dx + c * dy))), cmd.twist.vyaw)
        return tw, cmd.head, cmd.pose, cmd.mouth or 0.0

    def _frei(self, e: Any):
        ziel = self._ziel.get(e.nummer)
        if ziel is None or self.t > ziel[2] or math.hypot(ziel[0] - e.x, ziel[1] - e.y) < 0.08:
            if ziel is not None and self.rng.random() < 0.5:   # kurz stehen bleiben und umschauen
                self._ziel[e.nummer] = (e.x, e.y, self.t + self.rng.uniform(2.0, 5.0))
            else:
                x, y = self._zufallsziel(e)
                self._ziel[e.nummer] = (x, y, self.t + 12.0)
            ziel = self._ziel[e.nummer]
        nah = self._naechste(e, 1.2)
        return self._hin(e, ziel[0], ziel[1], blick=nah, langsam=True)

    def _hin(self, e: Any, tx: float, ty: float, blick: tuple[float, float] | None = None, langsam: bool = False):
        """Echt hinlaufen: zum Ziel drehen, dann gehen; angekommen zum Blickziel drehen."""
        dist = math.hypot(tx - e.x, ty - e.y)
        if dist < 0.08:
            if blick is None:
                return Twist(), Head(0.0, 0.05, 0.0, 0.0), Pose(), 0.0
            fehler = _winkel(math.atan2(blick[1] - e.y, blick[0] - e.x) - e.yaw)
            return Twist(0.0, 0.0, max(-0.8, min(0.8, 2.0 * fehler)) if abs(fehler) > 0.15 else 0.0), \
                Head(0.0, 0.1, 0.0, 0.0), Pose(), 0.0
        fehler = _winkel(math.atan2(ty - e.y, tx - e.x) - e.yaw)
        vyaw = max(-1.0, min(1.0, 2.2 * fehler))
        vmax = 0.12 if langsam else 0.2
        vx = vmax * min(1.0, dist / 0.3) * max(0.0, math.cos(fehler)) if abs(fehler) < 0.9 else 0.0
        kopf = 0.0
        if blick is not None and langsam:                   # beim Schlendern die anderen anschauen
            kopf = max(-0.6, min(0.6, _winkel(math.atan2(blick[1] - e.y, blick[0] - e.x) - e.yaw)))
        return Twist(vx, 0.0, vyaw), Head(0.0, 0.05, kopf, 0.0), Pose(), 0.0

    # ── Miteinander ───────────────────────────────────────────────────────
    def _alle(self, boden: bool = False) -> list[tuple[str, float, float]]:
        """Alle Körper; `boden`: nur die am Boden (Reachy auf dem Couchtisch ist kein Hindernis für die Gäste)."""
        haupt = [] if boden and getattr(self.haupt, "stand_z", 0.0) > 0.0 else [("haupt", self.haupt.x, self.haupt.y)]
        return haupt + [(e.kennung, e.x, e.y) for e in self.enten]

    def _naechste(self, e: Any, bis_m: float) -> tuple[float, float] | None:
        beste = None
        for k, x, y in self._alle():
            d = math.hypot(x - e.x, y - e.y)
            if k != e.kennung and d < bis_m and (beste is None or d < beste[0]):
                beste = (d, x, y)
        return (beste[1], beste[2]) if beste else None

    def _ausweichen(self, e: Any, tw: Twist) -> Twist:
        """Einander nicht anrempeln: von jeder Ente, die näher als 32 cm ist, sanft wegdrücken (im Körper-Rahmen)."""
        px = py = 0.0
        for k, x, y in self._alle(boden=True):
            if k == e.kennung:
                continue
            d = math.hypot(e.x - x, e.y - y)
            if 1e-6 < d < ABSTAND_M:
                stoss = (ABSTAND_M - d) / ABSTAND_M * 0.12
                px += (e.x - x) / d * stoss
                py += (e.y - y) / d * stoss
        # liegende Dinge nicht vor sich herschieben (seit 0.37.5) – außer dem, das sie gerade holen soll
        a = self.auftrag
        ziel = (a.lage.get(e.nummer, {}).get("ding") if a is not None and not a.fertig else None)
        for i in self.haupt.world_model.items:
            if i.held or i.name == ziel or i.kind == "ball":
                continue
            d = math.hypot(e.x - i.x, e.y - i.y)
            if 1e-6 < d < DING_ABSTAND_M:
                stoss = (DING_ABSTAND_M - d) / DING_ABSTAND_M * 0.1
                px += (e.x - i.x) / d * stoss
                py += (e.y - i.y) / d * stoss
        if not px and not py:
            return tw
        c, s = math.cos(e.yaw), math.sin(e.yaw)
        return Twist(tw.vx + c * px + s * py, tw.vy - s * px + c * py, tw.vyaw)

    def _koerper(self) -> None:
        """Feste Körper: Überlappen zwei Enten, wird die Begleitente herausgeschoben – die Hauptente lenkt die Engine."""
        for e in self.enten:
            for k, x, y in self._alle(boden=True):
                if k == e.kennung:
                    continue
                d = math.hypot(e.x - x, e.y - y)
                if d < KOERPER_M:
                    if d < 1e-6:
                        e.x += KOERPER_M
                        continue
                    schieben = (KOERPER_M - d) if k == "haupt" else (KOERPER_M - d) / 2
                    e.x += (e.x - x) / d * schieben
                    e.y += (e.y - y) / d * schieben

    def _begegnungen(self) -> None:
        if self.modus == "sitzen" or self._takt() or (self.auftrag is not None and not self.auftrag.fertig):
            return
        for e in self.enten:
            if e.nummer in self._gruss or e.fallen or e.sitting:
                continue
            for k, x, y in self._alle():
                if k == e.kennung or math.hypot(x - e.x, y - e.y) > GRUSS_ABSTAND_M:
                    continue
                paar = tuple(sorted((k, e.kennung)))
                if self.t - self._gegruesst.get(paar, -1e9) < GRUSS_PAUSE_S:
                    continue
                self._gegruesst[paar] = self.t
                self._gruss[e.nummer] = (self.t + 1.6, x, y)
                self.haupt.emit("sound", tag="greet", ente=e.ente_name, klang=list(e.klang),
                           x=round(e.x, 2), y=round(e.y, 2))
                self.haupt.emit("schwarm", message=f"{e.ente_name} begrüßt {self._name(k)}")
                break

    def _name(self, kennung: str) -> str:
        if kennung == "haupt":
            return "die Ente"
        return next((e.ente_name for e in self.enten if e.kennung == kennung), kennung)

    # ── Plätze ────────────────────────────────────────────────────────────
    def _frei_hier(self, x: float, y: float, ausser: int | None = None) -> bool:
        welt = self.haupt.world_model
        if welt.collide(x, y, 0.14):
            return False
        return all(math.hypot(x - ox, y - oy) > ABSTAND_M for k, ox, oy in self._alle()
                   if ausser is None or k != f"ente-{ausser + 1}")

    def _freier_platz(self, i: int) -> tuple[float, float]:
        h = self.haupt
        for r in (0.5, 0.75, 1.0, 1.3):
            for k in range(12):
                a = h.yaw + math.pi + (i * 1.3 + k * 0.52)
                x, y = h.x + r * math.cos(a), h.y + r * math.sin(a)
                if self._frei_hier(x, y):
                    return x, y
        return h.x - 0.5, h.y + 0.4 * (i + 1)

    def _zufallsziel(self, e: Any) -> tuple[float, float]:
        for _ in range(20):
            a = self.rng.uniform(-math.pi, math.pi)
            r = self.rng.uniform(0.3, 1.2)
            x, y = e.x + r * math.cos(a), e.y + r * math.sin(a)
            if self._frei_hier(x, y, ausser=e.nummer):
                return x, y
        return e.x, e.y
