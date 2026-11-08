"""Gezielt schießen (seit 0.37.9, Wunsch des Maintainers „beim Schießen soll er sich so zum Ball stellen, dass man ihm sagen kann,
wohin er schießen soll oder auf welches Ziel“).

Ablauf wie beim Apportieren mit Ergebnisprüfung und Plan B:

1. Ball finden (ist er nicht im Blick: suchen und hinlaufen).
2. Anlaufpunkt hinter dem Ball auf der Linie Ziel → Ball; liegt der Ball im Weg, außen herum (mit Rasterkarte, wenn
   eine da ist, sonst über einen Seitenpunkt) – sie soll ihn nicht vorher wegschubsen.
3. Ausrichten: Blick in Schussrichtung, um die Abweichung des Beins korrigiert (der linke Fuß schießt leicht nach rechts).
4. Schuss, dann warten, bis der Ball liegt, und prüfen: Treffer (Ball am Ziel bzw. Richtung stimmt) oder daneben.
5. Plan B: einmal nachkorrigieren – die gemessene Abweichung geht in die Korrektur des Beins ein – und noch ein Schuss.
"""

from __future__ import annotations

import math
from typing import Any

from ..api import DuckState, Head, Twist
from .behaviors import Approach, GoTo, SkillRun, Turn, _welt
from .engine import Behavior, Command
from .faehigkeit import Faehigkeit

# Abweichung je Bein (Bogenmaß, + = nach links): Startwert aus dem einfachen Simulator, lernt bei jedem Schuss nach
KORREKTUR: dict[str, float] = {"kick_left": -0.125, "kick_right": 0.125}


def _winkel(a: float) -> float:
    return math.remainder(a, math.tau)


class GezielterSchuss(Faehigkeit):
    faehigkeit = "schiessen"
    braucht = frozenset({'beine'})
    braucht_skill = ("kick_left", "kick_right")
    name = "gezielt schießen"
    channels = ("base", "head")
    ABSTAND_M = 0.15          # Entenmitte hinter dem Ball beim Schuss
    TRIFFT_M = 0.23           # so nah muss der Ball (Mitte zu Mitte) sein, damit der Fuß ihn erwischt
    UMWEG_M = 0.32            # Seitenabstand, wenn sie um den Ball herum muss
    VERSUCHE = 2
    TREFFER_GRAD = 12.0       # Richtung „passt“ bei Zielen ohne Ausdehnung (z. B. „nach links“)
    # seit 0.37.14 (Befund aus dem Test „sehr ungenau, rammelt andere Objekte weg“):
    DING_ABSTAND_M = 0.15     # so weit bleibt sie beim Umlaufen von anderen Dingen weg (Ding + Rumpf + Luft)
    BALL_ABSTAND_M = 0.25     # … und so weit vom Ball, bis sie hinter ihm auf der Schusslinie steht
    VOR_M = 0.4               # Vorpunkt auf der Schusslinie hinter dem Ball: von dort gerade und langsam heran
    BLICK_GENAU_GRAD = 5.0    # so genau richtet sie sich vor dem Schuss aus …
    NACHDREHEN = 2            # … mit höchstens so vielen Nachdrehungen
    PEIL_MAX_GRAD = 20.0      # Ball muss so gerade vor ihr liegen (vorher 35°: der Fuß traf ihn dann schräg)

    def __init__(self, ziel: tuple[float, float], ziel_name: str, ziel_r: float | None = None,
                 karte: Any = None) -> None:
        super().__init__()
        self.ziel = ziel
        self.ziel_name = ziel_name
        self.ziel_r = ziel_r                  # Ausdehnung des Ziels (Möbel, Ente); None = nur Richtung
        self.karte = karte
        self.timeout = 150.0
        self.inner: Behavior | None = None
        self.phase = "suchen"
        self.versuche = 0
        self.anlaeufe = 0
        self.ball: tuple[float, float] | None = None
        self.skill = "kick_left"
        self.protokoll: list[str] = []
        self._wege: list[tuple[float, float]] = []
        self._liegt_t = 0.0
        self._ball_vorher: tuple[float, float] | None = None
        self._schuss_von: tuple[float, float] | None = None
        self.dinge: dict[str, tuple[float, float, float]] = {}    # andere Dinge, die sie sieht: Name → x, y, r
        self._geplant_mit: set[str] = set()
        self._nachgedreht = 0

    # ── Hilfen ───────────────────────────────────────────────────────────
    @staticmethod
    def _ball_sicht(st: DuckState) -> dict[str, Any] | None:
        return next((o for o in st.perception.objects if o.get("art") == "ball"), None)

    def _ball_welt(self, st: DuckState) -> tuple[float, float] | None:
        b = self._ball_sicht(st)
        if b is not None:
            self.ball = _welt(st, b)
        self._dinge_merken(st)
        return self.ball

    def _dinge_merken(self, st: DuckState) -> None:
        """Andere Dinge am Boden (Socke, Klötzchen …) merken – der Tiefensensor sieht flache Dinge nicht als Hindernis."""
        for o in st.perception.objects:
            art = str(o.get("art") or "")
            if art in ("ball", "möbel", "person", "ente", "laser") or "richtung_grad" not in o:
                continue
            x, y = _welt(st, o)
            self.dinge[str(o.get("name") or art)] = (x, y, float(o.get("r") or 0.04))

    def _meiden(self) -> set[tuple[int, int]]:
        """Rasterzellen um den Ball und die anderen Dinge, um die der Weg herumführt."""
        from .karte import ZELLE, zelle

        aus: set[tuple[int, int]] = set()
        punkte = [(*self.ball, 0.0, self.BALL_ABSTAND_M)] + [(*d, self.DING_ABSTAND_M) for d in self.dinge.values()]
        for x, y, r, abstand in punkte:
            rad = math.ceil((abstand + r * 0.5) / ZELLE)
            ci, cj = zelle(x, y)
            for di in range(-rad, rad + 1):
                for dj in range(-rad, rad + 1):
                    if di * di + dj * dj <= rad * rad:
                        aus.add((ci + di, cj + dj))
        return aus

    def _use(self, b: Behavior) -> None:
        b.engine = self.engine
        self.inner = b

    def _bein(self) -> None:
        if self.engine is not None:
            have = self.engine.backend.skills()
            if have and self.skill not in have and "kick_right" in have:
                self.skill = "kick_right"

    def _richtung(self) -> float:
        """Schussrichtung Ball → Ziel."""
        bx, by = self.ball
        return math.atan2(self.ziel[1] - by, self.ziel[0] - bx)

    def _blick_soll(self) -> float:
        return _winkel(self._richtung() - KORREKTUR.get(self.skill, 0.0))

    def _anlaufpunkt(self) -> tuple[float, float]:
        bx, by = self.ball
        w = self._blick_soll()
        return bx - self.ABSTAND_M * math.cos(w), by - self.ABSTAND_M * math.sin(w)

    def kontakt_ziel(self, st: DuckState) -> tuple[float, float, float] | None:
        letztes_stueck = self.phase == "anlauf" and not self._wege
        if (letztes_stueck or self.phase in ("ausrichten", "schuss", "nachruecken")) and self.ball:
            return (*self.ball, Approach.KONTAKT_R)
        return None

    # ── Ablauf ───────────────────────────────────────────────────────────
    def on_start(self, st):
        self._bein()
        if self._ball_welt(st) is None:
            self.phase = "suchen"
            self._use(Approach("ball", stop_at=0.45, bearing_tol_deg=15.0))
        else:
            self._anlaufen(st)

    def _anlaufen(self, st: DuckState) -> None:
        self.phase = "anlauf"
        self.anlaeufe += 1
        self._geplant_mit = set(self.dinge)
        sx, sy = self._anlaufpunkt()
        bx, by = self.ball
        w = self._blick_soll()
        ux, uy = math.cos(w), math.sin(w)
        # steht sie vor oder neben dem Ball (in Schussrichtung gesehen), muss sie außen herum
        vorne = (st.x - bx) * ux + (st.y - by) * uy > -0.06
        self._wege = []
        from .karte import zelle

        # Seit 0.37.14: erst zu einem Vorpunkt auf der Schusslinie hinter dem Ball – auf der Rasterkarte um den Ball und
        # die anderen Dinge herum (ohne erkundeten Bereich auf einer leeren Karte; Möbel und Wände umgeht dann das
        # Ausweichen mit dem Tiefensensor) –, dann gerade und langsam an den Ball. Vorher führte der Weg dicht am Ball
        # vorbei, sie schubste ihn an und flache Dinge räumte sie unterwegs ab.
        hinten = (st.x - bx) * ux + (st.y - by) * uy
        seitlich = abs(-(st.x - bx) * uy + (st.y - by) * ux)
        if not (-self.VOR_M - 0.05 < hinten < -0.1 and seitlich < 0.08):       # steht nicht schon passend dahinter
            karte = self._wegkarte()
            meiden = self._meiden()
            gesperrt = karte._gesperrt() | meiden
            # Vorpunkt nicht an ein Möbel oder Ding legen: etwas näher oder leicht seitlich versetzt ausweichen
            kandidaten = [(bx - v * ux - s * uy, by - v * uy + s * ux) for v in (self.VOR_M, 0.33, 0.28)
                          for s in (0.0, 0.06, -0.06, 0.12, -0.12)]
            frei = [k for k in kandidaten if zelle(*k) not in gesperrt]
            # das letzte gerade Stück (Vorpunkt → Ball) soll an keinem Ding vorbeistreifen
            vor = max(frei, key=lambda k: min(self._luft(k, (sx, sy)), 0.2) - 0.1 * math.hypot(k[0] - frei[0][0],
                                                                                              k[1] - frei[0][1]),
                      default=None)
            weg = karte.route((st.x, st.y), vor, meiden=meiden) if vor is not None else None
            if weg:
                self._wege = list(weg)
        if not self._wege and hinten > -0.1:
            if vorne:
                nx, ny = -uy, ux                             # Seite, auf der sie schon steht
                if (st.x - bx) * nx + (st.y - by) * ny < 0:
                    nx, ny = -nx, -ny
                if (st.x - bx) * ux + (st.y - by) * uy > 0.1:     # steht klar davor: erst seitlich vorbei
                    self._wege.append((bx + nx * self.UMWEG_M + ux * 0.2, by + ny * self.UMWEG_M + uy * 0.2))
                self._wege.append((bx + nx * self.UMWEG_M - ux * 0.05, by + ny * self.UMWEG_M - uy * 0.05))
                self._wege.append((bx + nx * self.UMWEG_M * 0.6 - ux * self.ABSTAND_M * 1.8,
                                   by + ny * self.UMWEG_M * 0.6 - uy * self.ABSTAND_M * 1.8))
        self._wege.append((sx, sy))
        self._naechster_weg()

    def _luft(self, a: tuple[float, float], b: tuple[float, float]) -> float:
        """Kleinster Abstand der anderen Dinge (Rand) zur Strecke a → b, abzüglich des Rumpfs."""
        ax, ay = a
        dx, dy = b[0] - ax, b[1] - ay
        lang2 = dx * dx + dy * dy or 1e-9
        luft = math.inf
        for x, y, r in self.dinge.values():
            s = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / lang2))
            luft = min(luft, math.hypot(ax + s * dx - x, ay + s * dy - y) - r - 0.09)
        return luft

    def _wegkarte(self) -> Any:
        """Karte für den Weg: der erkundete Bereich – sonst eine leere Karte mit dem, was der Tiefensensor gerade
        gesehen hat (Möbel, Wände der letzten Sekunden), damit der Vorpunkt nicht direkt am Couchtisch liegt."""
        from .karte import GRENZE, Karte, zelle

        if self.karte is not None:
            return self.karte
        k = Karte()
        aw = getattr(self.engine, "ausweicher", None) if self.engine else None
        for _, x, y in (getattr(aw, "_pts", {}) or {}).values():
            k.zellen[zelle(x, y)] = GRENZE
        return k

    def _ding_im_weg(self, st: DuckState) -> bool:
        """Liegt ein erst jetzt gesehenes Ding auf dem Stück bis zum nächsten Wegpunkt? Dann neu planen."""
        if self.phase != "anlauf" or self.inner is None or not isinstance(self.inner, GoTo):
            return False
        neu = set(self.dinge) - self._geplant_mit
        if not neu:
            return False
        self._geplant_mit |= neu
        ax, ay, zx, zy = st.x, st.y, self.inner.tx, self.inner.ty
        lang = math.hypot(zx - ax, zy - ay) or 1e-6
        for n in neu:
            x, y, r = self.dinge[n]
            s = max(0.0, min(1.0, ((x - ax) * (zx - ax) + (y - ay) * (zy - ay)) / (lang * lang)))
            if math.hypot(ax + s * (zx - ax) - x, ay + s * (zy - ay) - y) < self.DING_ABSTAND_M + r:
                return True
        return False

    def _naechster_weg(self) -> None:
        x, y = self._wege.pop(0)
        langsam = not self._wege
        self._use(GoTo(x, y, speed=0.1 if langsam else 0.16, label=f"Anlauf für den Schuss zu {self.ziel_name}"))

    def _ausrichten(self, st: DuckState) -> None:
        self.phase = "ausrichten"
        d = math.degrees(_winkel(self._blick_soll() - st.yaw))
        self._use(Turn(d, speed=0.6))

    def _bereit(self, st: DuckState) -> bool:
        if self._ball_welt(st) is None:
            return False
        bx, by = self.ball
        d = math.hypot(bx - st.x, by - st.y)
        peil = abs(math.degrees(_winkel(math.atan2(by - st.y, bx - st.x) - st.yaw)))
        return d <= self.TRIFFT_M and peil <= self.PEIL_MAX_GRAD

    def _nachdrehen(self, st: DuckState) -> bool:
        """Blick noch nicht genau genug aufs Ziel? Dann (höchstens NACHDREHEN-mal) nachdrehen statt schief schießen."""
        fehler = math.degrees(_winkel(self._blick_soll() - st.yaw))
        if abs(fehler) <= self.BLICK_GENAU_GRAD or self._nachgedreht >= self.NACHDREHEN:
            return False
        self._nachgedreht += 1
        self.phase = "ausrichten"
        self._use(Turn(fehler, speed=0.4))
        return True

    def _beobachten(self, st: DuckState) -> None:
        """Während der Ball rollt: Anfangsrichtung (bevor er irgendwo abprallt) und kleinster Abstand zum Ziel."""
        if self._ball_sicht(st) is None or self._ball_vorher is None or self.ball is None:
            return
        if self._flug is None and math.hypot(self.ball[0] - self._ball_vorher[0],
                                             self.ball[1] - self._ball_vorher[1]) > 0.08:
            self._flug = self.ball
        self._dmin = min(self._dmin, math.hypot(self.ziel[0] - self.ball[0], self.ziel[1] - self.ball[1]))

    def _schiessen(self, st: DuckState) -> None:
        self._flug = None
        self._dmin = math.inf
        self.phase = "schuss"
        self._nachgedreht = 0
        self.versuche += 1
        self._ball_vorher = self.ball
        self._schuss_von = (st.x, st.y)
        self._blick_beim_schuss = st.yaw
        self._use(SkillRun(self.skill))

    def _pruefen(self, st: DuckState) -> Command | None:
        """Ball liegt wieder: Wohin ist er losgerollt, kam er ans Ziel?"""
        b0, b1 = self._ball_vorher, self.ball
        if b0 is None or b1 is None or self._flug is None:
            return self._plan_b(st, "Ball nicht getroffen")
        flug = math.atan2(self._flug[1] - b0[1], self._flug[0] - b0[0])
        soll = math.atan2(self.ziel[1] - b0[1], self.ziel[0] - b0[0])
        fehler = math.degrees(_winkel(flug - soll))
        # dazulernen: so weit schoss dieses Bein wirklich neben die Blickrichtung (sanft gemittelt)
        echt = _winkel(flug - self._blick_beim_schuss)
        if abs(echt) < 0.6:
            KORREKTUR[self.skill] = round(KORREKTUR.get(self.skill, 0.0) * 0.5 + echt * 0.5, 3)
        seite = "links" if fehler > 0 else "rechts"
        nachher = f" ({self.versuche - 1}× nachkorrigiert)" if self.versuche > 1 else ""
        if self.ziel_r is not None and self._dmin <= self.ziel_r + 0.12:
            self.protokoll.append(f"Schuss {self.versuche}: Treffer")
            return self.finish(f"Treffer: Ball ist bei {self.ziel_name} angekommen{nachher}")
        if abs(fehler) <= (8.0 if self.ziel_r is not None else self.TREFFER_GRAD):
            self.protokoll.append(f"Schuss {self.versuche}: Richtung stimmt ({abs(fehler):.0f}°)")
            if self.ziel_r is None:
                return self.finish(f"Treffer: Ball rollte {self.ziel_name}{nachher}")
            kurz = max(0.0, math.hypot(self.ziel[0] - b1[0], self.ziel[1] - b1[1]) - self.ziel_r)
            return self.finish(f"Richtung stimmt, aber der Ball kam nicht bis {self.ziel_name} – {kurz * 100:.0f} cm davor "
                               f"liegen geblieben (zu weit für ihren Schuss oder etwas im Weg){nachher}")
        return self._plan_b(st, f"{abs(fehler):.0f}° {seite} vorbei")

    def _plan_b(self, st: DuckState, warum: str) -> Command | None:
        self.protokoll.append(f"Schuss {self.versuche}: {warum}" if self.phase == "liegt" else f"Anlauf {self.anlaeufe}: {warum}")
        if self.versuche >= self.VERSUCHE or self.anlaeufe >= self.VERSUCHE + 2:
            self.failed = True
            return self.finish(f"daneben: {warum} ({self.versuche} Schüsse)")
        if self.engine:
            self.engine.note({"type": "schuss", "message": f"Knapp daneben ({warum}) – ich korrigiere und schieße noch mal"})
        if self.ball is not None and self._ball_sicht(st) is not None:
            self._anlaufen(st)                     # Ball im Blick: gleich wieder um ihn und die Dinge herum anlaufen
            return Command(twist=Twist())
        self.phase = "suchen"
        self.ball = None
        self._use(Approach("ball", stop_at=0.45, bearing_tol_deg=15.0))
        return Command(twist=Twist())

    def tick(self, st, dt):
        if self.inner is None:
            return None
        if self.phase in ("anlauf", "ausrichten", "nachruecken", "liegt"):
            self._ball_welt(st)
        if self.phase == "liegt":
            # warten, bis der Ball liegt (höchstens 5 s), Kopf schaut ihm nach
            b = self._ball_sicht(st)
            alt = self._ball_jetzt
            self._ball_jetzt = self.ball if b else None
            ruhig = (b is not None and alt is not None
                     and math.hypot(self.ball[0] - alt[0], self.ball[1] - alt[1]) < 0.002)
            self._liegt_t += dt
            self._ruhig_t = self._ruhig_t + dt if ruhig else 0.0
            self._beobachten(st)
            if self._ruhig_t > 0.6 or self._liegt_t > 6.0:
                return self._pruefen(st) or Command(twist=Twist())
            if b is None and self.ball is not None:          # aus dem Blick gerollt: hinterherdrehen
                peil = _winkel(math.atan2(self.ball[1] - st.y, self.ball[0] - st.x) - st.yaw)
                return Command(twist=Twist(0.0, 0.0, max(-0.8, min(0.8, peil * 2.0))), head=Head(0.0, 0.1, 0.0, 0.0))
            yaw = math.radians(max(-60.0, min(60.0, b["richtung_grad"]))) if b else 0.0
            return Command(twist=Twist(), head=Head(0.0, 0.1, yaw, 0.0))
        if self.phase == "schuss":
            self._ball_welt(st)
            self._beobachten(st)                     # der Ball rollt schon, während das Bein noch zurückschwingt
        if self._ding_im_weg(st):                    # Socke & Co. erst jetzt gesehen: drumherum neu planen
            self.anlaeufe -= 1
            self._anlaufen(st)
            return Command(twist=Twist())
        cmd = self.inner._step(st, dt)
        if not self.inner.done:
            return cmd
        failed = getattr(self.inner, "failed", False)
        if self.phase == "suchen":
            if failed or self._ball_welt(st) is None:
                self.failed = True
                return self.finish("Ball nicht gefunden")
            self._anlaufen(st)
        elif self.phase == "anlauf":
            if self._wege and not failed:
                self._naechster_weg()
            elif failed and self.anlaeufe < self.VERSUCHE + 2:   # nicht angekommen: neu planen statt schief schießen
                self._ball_welt(st)
                self._anlaufen(st)
            else:
                self._ausrichten(st)
        elif self.phase == "ausrichten":
            if self._bereit(st):
                if not self._nachdrehen(st):
                    self._schiessen(st)
            else:
                self.phase = "nachruecken"            # noch das letzte Stück an den Ball heran
                self._use(Approach("ball", stop_at=0.11, bearing_tol_deg=8.0))
        elif self.phase == "nachruecken":
            if self._bereit(st):
                if not self._nachdrehen(st):             # beim Heranrücken zum Ball gedreht: Blick wieder aufs Ziel
                    self._schiessen(st)
            else:
                return self._plan_b(st, "kam nicht richtig an den Ball")
        elif self.phase == "schuss":
            self.phase = "liegt"
            self._liegt_t = self._ruhig_t = 0.0
            self._ball_jetzt = None
        return Command(twist=Twist())

    def target(self):
        return self.ball

    def describe(self):
        return f"gezielt schießen zu {self.ziel_name}"

    def info(self) -> dict[str, Any]:
        return {"ziel": self.ziel_name, "phase": self.phase, "versuche": self.versuche, "plan_b": list(self.protokoll)}
