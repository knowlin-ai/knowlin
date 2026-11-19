"""Ballspiel der Enten (seit 0.38.66).

Fund 15.11.: „Ball spielen (mir zuschießen oder mit den anderen Enten spielen) – macht er hier nicht, was ich will.“
Bis dahin konnten die Begleitenten keinen Ball spielen; es gab nur den gezielten Schuss der Hauptente.

Ablauf (einfacher Simulator mit weiteren Enten):

- Wer dem liegenden Ball am nächsten ist, ist **dran**. Sie sucht sich eine Mitspielerin aus (eine andere Ente, die
  Hauptente, wenn sie mitspielt, oder den Menschen, wenn er mitspielt und die Ente weiß, wo er ist), läuft hinter den
  Ball – außen herum, wenn sie davor steht, damit sie ihn nicht wegschubst –, richtet sich aus und schießt.
- Die anderen bleiben stehen und schauen dem Ball nach. Die Empfängerin **nimmt den Ball an** (er bleibt vor ihr
  liegen) und ist als Nächste dran.
- Liegt der Ball beim Menschen, wartet das Spiel kurz („Der Ball ist bei dir“); dann holt ihn die nächste Ente.
- Spielt die Hauptente mit, läuft sie genauso an (`MitBallSpielen`, ihr Verhalten in der Bewegungs-Engine).

Kommt eine nicht an den Ball heran, gibt sie ihn an die Nächste ab; nach mehreren Fehlversuchen endet das Spiel
ehrlich. Not-Aus beendet es wie jede Teamarbeit (alle stromlos, Sperre wie eingestellt).
"""

from __future__ import annotations

import math
from typing import Any

from ..api import Head, Pose, Twist
from .engine import Behavior, Command
from .team import Auftrag

SPIELZEIT_S = 120.0
ABSTAND_M = 0.15          # Entenmitte hinter dem Ball beim Schuss (wie GezielterSchuss)
VOR_M = 0.35              # Vorpunkt auf der Schusslinie, von dort gerade heran
UMWEG_M = 0.3             # Seitenabstand, wenn sie um den Ball herum muss
PLATZ_M = 0.45            # so weit gehen Zuschauerinnen vom liegenden Ball zurück
ANNAHME_M = 0.2           # so nah an der Empfängerin bleibt der Ball liegen
RUHIG_MS = 0.06           # langsamer = der Ball liegt
BEI_DIR_M = 0.5
BEI_DIR_S = 4.0
DRAN_S = 25.0             # so lange darf eine brauchen, bis sie schießt
FEHLVERSUCHE = 4
KORREKTUR = -0.125        # linker Fuß schießt leicht nach rechts (wie schuss.KORREKTUR["kick_left"])
RUHE = (Twist(), Head(0.0, 0.1, 0.0, 0.0), Pose(), 0.0)


def _winkel(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def _hin(x: float, y: float, yaw: float, tx: float, ty: float, blick: float | None = None):
    """Zum Punkt drehen und gehen; angekommen in Blickrichtung drehen (wie Schwarm._hin, ohne Ente)."""
    dist = math.hypot(tx - x, ty - y)
    if dist < 0.06:
        fehler = _winkel(blick - yaw) if blick is not None else 0.0
        return Twist(0.0, 0.0, max(-0.8, min(0.8, 2.0 * fehler))), Head(0.0, 0.1, 0.0, 0.0), Pose(), 0.0
    fehler = _winkel(math.atan2(ty - y, tx - x) - yaw)
    vx = 0.18 * min(1.0, dist / 0.3 + 0.2) * max(0.0, math.cos(fehler)) if abs(fehler) < 0.9 else 0.0
    return Twist(vx, 0.0, max(-1.0, min(1.0, 2.2 * fehler))), Head(0.0, 0.1, 0.0, 0.0), Pose(), 0.0


class Ballspiel(Auftrag):
    art = "ballspiel"

    def __init__(self, schwarm: Any, haupt_spielt: bool = True, mit_mir: bool = False,
                 dauer: float | None = None) -> None:
        super().__init__(schwarm)
        self.haupt_spielt = haupt_spielt
        self.mit_mir = mit_mir
        self.ende = self.sw.t + (dauer or SPIELZEIT_S)
        self.ball = next((i for i in self.welt.items if i.kind == "ball" and not i.held), None)
        self.dran: str | None = None             # Kennung, „haupt“ oder None (Ball rollt / liegt bei dir)
        self.empfaenger: str | None = None
        self.letzte: str | None = None           # wer zuletzt geschossen hat
        self.paesse = 0
        self.fehlversuche = 0
        self._dran_seit = 0.0
        self._bei_dir_seit: float | None = None
        if self.ball is None:
            self.fertig, self.ergebnis = True, "Kein Ball im Zimmer"
        elif len(self.spieler()) + (1 if mit_mir else 0) < 2:
            self.fertig, self.ergebnis = True, "Zum Ballspielen braucht es mindestens zwei"
        else:
            self._weitergeben(self._naechste())

    # ── Wer spielt mit, wo steht wer ─────────────────────────────────────
    def spieler(self) -> list[tuple[str, float, float]]:
        out = [(e.kennung, e.x, e.y) for e in self.sw.enten if not e.fallen and e.powered]
        if self.haupt_spielt:
            h = self.sw.haupt
            out.append(("haupt", h.x, h.y))
        return out

    def _mensch(self) -> tuple[float, float] | None:
        if not self.mit_mir:
            return None
        p = getattr(self.welt, "person_point", None)
        return p() if callable(p) else None

    def name(self, kennung: str | None) -> str:
        if kennung == "mensch":
            return "dir"
        return self.sw._name(kennung) if kennung else "?"

    def wo(self, kennung: str) -> tuple[float, float] | None:
        if kennung == "mensch":
            return self._mensch()
        return next(((x, y) for k, x, y in self.spieler() if k == kennung), None)

    def _naechste(self, ausser: str | None = None) -> str | None:
        b = self.ball
        kand = [(math.hypot(x - b.x, y - b.y), k) for k, x, y in self.spieler() if k != ausser]
        return min(kand)[1] if kand else None

    def ziel_fuer(self, kennung: str) -> tuple[str, tuple[float, float]] | None:
        """Wem sie zuspielt: nicht sich selbst, möglichst nicht zurück an die, die ihr gerade zugespielt hat; die
        Schusslinie braucht Platz für den Anlauf hinter dem Ball."""
        b = self.ball
        kand = [(k, (x, y)) for k, x, y in self.spieler() if k != kennung]
        mensch = self._mensch()
        if mensch is not None:
            kand.append(("mensch", mensch))
        self.sw.rng.shuffle(kand)
        kand.sort(key=lambda kp: (kp[0] == self.letzte and len(kand) > 1, ))
        for k, (x, y) in kand:
            if math.hypot(x - b.x, y - b.y) > 0.35 and self.vor_abstand(math.atan2(y - b.y, x - b.x)) is not None:
                return k, (x, y)
        # Ball liegt an der Wand oder alle zu nah: zur Zimmermitte hin
        return None

    def vor_abstand(self, richtung: float) -> float | None:
        """Wie weit hinter dem Ball Platz für den Anlauf ist (None: keiner – der Ball liegt an Wand oder Möbel)."""
        b = self.ball
        w = richtung - KORREKTUR
        frei = lambda d: not self.welt.collide(b.x - d * math.cos(w), b.y - d * math.sin(w), 0.09)   # noqa: E731
        if not frei(ABSTAND_M):
            return None
        return next((d for d in (VOR_M, 0.28, 0.22) if frei(d)), None)

    # ── Takt (ruft der Schwarm einmal je Schritt) ────────────────────────
    def schritt(self, dt: float) -> None:
        if self.fertig:
            return
        b = self.ball
        if self.sw.t > self.ende:
            return self.beenden(f"Ballspiel vorbei – {self.paesse} Pässe")
        v = math.hypot(b.vx, b.vy)
        if self.empfaenger and self.empfaenger != "mensch" and v > RUHIG_MS:
            p = self.wo(self.empfaenger)
            if p is not None and math.hypot(p[0] - b.x, p[1] - b.y) < ANNAHME_M:
                b.vx *= 0.1                                  # angenommen: bleibt vor ihr liegen
                b.vy *= 0.1
        if self.dran is None and v < RUHIG_MS:
            mensch = self._mensch()
            if mensch is not None and math.hypot(mensch[0] - b.x, mensch[1] - b.y) < BEI_DIR_M:
                if self._bei_dir_seit is None:
                    self._bei_dir_seit = self.sw.t
                    self.melden(None, "Der Ball ist bei dir!")
                if self.sw.t - self._bei_dir_seit < BEI_DIR_S:
                    return
            self._bei_dir_seit = None
            e = self.empfaenger if self.empfaenger in {k for k, _, _ in self.spieler()} else None
            p = self.wo(e) if e else None
            if e is None or p is None or math.hypot(p[0] - b.x, p[1] - b.y) > 0.9:
                e = self._naechste()
            self._weitergeben(e)
        elif self.dran is not None and self.dran != "haupt" and self.sw.t - self._dran_seit > DRAN_S:
            self.fehlversuche += 1
            if self.fehlversuche >= FEHLVERSUCHE:
                return self.beenden("Der Ball liegt zu ungünstig – Ballspiel beendet")
            self.melden(self._ente(self.dran), f"{self.name(self.dran)} kommt nicht an den Ball")
            self._weitergeben(self._naechste(ausser=self.dran))

    def _weitergeben(self, kennung: str | None) -> None:
        self.lage.clear()
        self.dran, self._dran_seit = kennung, self.sw.t
        if kennung is None:
            return
        e = self._ente(kennung)
        if e is not None:
            self.lage[e.nummer] = {"phase": "ball"}

    def geschossen(self, kennung: str, empfaenger: str | None) -> None:
        self.paesse += 1
        self.letzte = kennung
        self.empfaenger = empfaenger
        self.dran = None
        self.lage.clear()
        wer = "Die Ente" if kennung == "haupt" else self.name(kennung)
        wem = {"haupt": "der Ente", "mensch": "dir"}.get(empfaenger or "", self.name(empfaenger))
        self.melden(self._ente(kennung), f"{wer} spielt {wem} zu" if empfaenger else f"{wer} schießt")

    def beenden(self, text: str) -> None:
        self.fertig, self.ergebnis = True, text
        self.dran = None
        self.melden(None, text)

    def _ente(self, kennung: str | None) -> Any:
        return next((e for e in self.sw.enten if e.kennung == kennung), None)

    # ── Begleitenten ─────────────────────────────────────────────────────
    def regel(self, e: Any):
        if self.fertig:
            return None
        if e.skill is not None:                                  # schießt gerade
            return RUHE
        b = self.ball
        s = self.lage.get(e.nummer)
        if s is not None and s.pop("schuss", False) and e.kennung == self.dran:
            if math.hypot(b.vx, b.vy) > 0.2:                     # getroffen: der Ball rollt
                self.geschossen(e.kennung, self.empfaenger)
                return RUHE
            s.pop("ziel", None)                                  # ins Leere getreten: neu anlaufen
        if e.kennung != self.dran:                               # zuschauen: zum Ball drehen
            fehler = _winkel(math.atan2(b.y - e.y, b.x - e.x) - e.yaw)
            dreh = max(-0.8, min(0.8, 2.0 * fehler)) if abs(fehler) > 0.5 else 0.0
            # steht sie der am Ball im Weg (Ball liegt, eine andere ist dran): Platz machen
            platz = (self.dran is not None and math.hypot(b.vx, b.vy) < RUHIG_MS
                     and math.hypot(b.x - e.x, b.y - e.y) < PLATZ_M and abs(fehler) < 0.6)
            return Twist(-0.08 if platz else 0.0, 0.0, dreh), Head(0.0, 0.1, max(-0.7, min(0.7, fehler)), 0.0), \
                Pose(), 0.0
        s = self.lage.setdefault(e.nummer, {"phase": "ball"})
        if "ziel" not in s:
            s["ziel"] = self.ziel_fuer(e.kennung)
            self.empfaenger = s["ziel"][0] if s["ziel"] else None
        tw = self.lauf(e.x, e.y, e.yaw, s["ziel"])
        if tw is None:
            e._start_skill("kick_left")
            s["schuss"] = True                                   # ob er traf, zeigt sich nach dem Schuss
            return RUHE
        return tw

    def lauf(self, x: float, y: float, yaw: float, ziel: tuple[str, tuple[float, float]] | None):
        """Hinter den Ball auf die Schusslinie und ausrichten → (twist, head, pose, mund); None = bereit zum Schuss.
        Für Begleitenten und Hauptente gleich."""
        b = self.ball
        p = (self.wo(ziel[0]) or ziel[1]) if ziel else (0.0, 0.0)          # ohne Ziel: Zimmermitte
        richtung = math.atan2(p[1] - b.y, p[0] - b.x)
        vor = self.vor_abstand(richtung)
        if vor is None:                                          # hinter dem Ball ist kein Platz: zur Mitte spielen
            richtung = math.atan2(-b.y, -b.x)
            vor = self.vor_abstand(richtung) or 0.22
        blick = _winkel(richtung - KORREKTUR)
        ux, uy = math.cos(blick), math.sin(blick)
        hinten = (x - b.x) * ux + (y - b.y) * uy                 # < 0: hinter dem Ball
        quer = -(x - b.x) * uy + (y - b.y) * ux
        if hinten > -0.1 and abs(quer) < UMWEG_M - 0.1:           # steht davor oder daneben: außen herum
            seite = 1.0 if quer >= 0 else -1.0
            for sei in (seite, -seite):
                sx, sy = b.x - uy * sei * UMWEG_M - ux * 0.15, b.y + ux * sei * UMWEG_M - uy * 0.15
                if not self.welt.collide(sx, sy, 0.09):
                    return _hin(x, y, yaw, sx, sy)
        if not (-vor - 0.12 < hinten < -0.08 and abs(quer) < 0.1):
            return _hin(x, y, yaw, b.x - ux * vor, b.y - uy * vor, blick=blick)
        # auf der Linie: ausrichten und langsam heran
        fehler = _winkel(blick - yaw)
        rest = -hinten - ABSTAND_M
        if rest < 0.02 and abs(fehler) < 0.08:
            return None
        c, sn = math.cos(yaw), math.sin(yaw)
        qx, qy = -uy * quer, ux * quer                           # Abweichung von der Linie (Welt)
        vy = max(-0.05, min(0.05, -2.0 * (-sn * qx + c * qy)))
        vx = max(0.0, min(0.07, 1.2 * rest)) if abs(fehler) < 0.3 else 0.0
        return Twist(vx, vy, max(-0.8, min(0.8, 2.5 * fehler))), Head(0.0, 0.25, 0.0, 0.0), Pose(), 0.0

    def zustand(self) -> dict[str, Any]:
        return {**super().zustand(), "dran": self.name(self.dran) if self.dran else None, "paesse": self.paesse}


class MitBallSpielen(Behavior):
    """Die Hauptente spielt mit: Ist sie dran, läuft sie wie die anderen hinter den Ball und schießt zu der, die sie
    sich aussucht; sonst schaut sie dem Ball nach. (Mit demselben Anlauf wie die Begleitenten – der gezielte Schuss mit
    Prüfung war für ein flüssiges Spiel zu langsam: bis zu 40 s je Pass.)"""

    name = "Ballspiel"
    channels = ("base", "head")

    def __init__(self, spiel: Ballspiel) -> None:
        super().__init__()
        self.spiel = spiel
        self.timeout = (spiel.ende - spiel.sw.t) + 60.0
        self.inner: Behavior | None = None
        self._ziel: tuple[str, tuple[float, float]] | None = None

    def kontakt_ziel(self, st):
        b = self.spiel.ball                                      # der Ball ist kein Hindernis, sie will an ihn heran
        return (b.x, b.y, 0.12) if self.spiel.dran == "haupt" else None

    def tick(self, st, dt):
        sp = self.spiel
        if sp.fertig:
            return self.finish(sp.ergebnis or "Ballspiel vorbei")
        b = sp.ball
        if self.inner is not None:                               # schießt gerade
            cmd = self.inner._step(st, dt)
            if not self.inner.done:
                return cmd
            self.inner = None
            if sp.dran == "haupt":
                if math.hypot(b.vx, b.vy) > 0.2:
                    sp.geschossen("haupt", sp.empfaenger)
                else:
                    self._ziel = None                            # ins Leere: neu anlaufen
            return Command(twist=Twist())
        if sp.dran == "haupt":
            if self._ziel is None:
                self._ziel = sp.ziel_fuer("haupt")
                sp.empfaenger = self._ziel[0] if self._ziel else None
            r = sp.lauf(st.x, st.y, st.yaw, self._ziel)
            if r is None:
                from .behaviors import SkillRun

                self.inner = SkillRun("kick_left")
                self.inner.engine = self.engine
                return Command(twist=Twist())
            tw, head, _pose, _mund = r
            return Command(twist=tw, head=head)
        self._ziel = None
        fehler = _winkel(math.atan2(b.y - st.y, b.x - st.x) - st.yaw)
        dreh = max(-0.8, min(0.8, 2.0 * fehler)) if abs(fehler) > 0.5 else 0.0
        return Command(twist=Twist(0.0, 0.0, dreh), head=Head(0.0, 0.1, max(-0.7, min(0.7, fehler)), 0.0))

    def on_stop(self) -> None:
        if not self.spiel.fertig:
            self.spiel.beenden("Ballspiel beendet")

    def describe(self) -> str:
        return "Ballspiel mit den anderen"
