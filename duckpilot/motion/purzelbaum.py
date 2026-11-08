"""Purzelbaum mit Vorbedingung und Nacharbeit (seit 0.37.14).

Befund aus dem Test mit 0.37.13: „Ich habe mich auf dem Weg weit weggedreht und bin am Ende gegen das Sofa gestoßen.“
Pollens Purzelbaum-Policy rollt geradeaus nach vorn und landet oft etwas verdreht. Deshalb – nach dem Bauprinzip aus
0.38 (Vorbedingung, Ergebnisprüfung, Plan B):

- Vorbedingung: vorn muss ≈ 50 cm Platz sein (gemerkte Tiefensensor-Punkte, wie beim Ausweichen). Ist es zu eng,
  dreht sie sich erst zur freiesten Seite; findet sie nirgends Platz, lehnt sie ehrlich ab.
- Ergebnisprüfung: Drehung und Strecke nach der Landung messen.
- Nacharbeit: Ist sie um mehr als 20° verdreht, dreht sie sich zurück in die alte Blickrichtung.
"""

from __future__ import annotations

import math
from typing import Any

from ..api import Twist
from .behaviors import SkillRun, Turn
from .engine import Behavior, Command
from .faehigkeit import Faehigkeit

PLATZ_M = 0.5            # so viel Freiraum braucht die Rolle vorn (Rolle ≈ 25–35 cm plus Landung)
VERDREHT_GRAD = 20.0     # ab hier dreht sie sich nach der Landung zurück
SUCHWINKEL = (90.0, -90.0, 180.0)
RUHE_S = 1.0             # nach Drehen bzw. Landen kurz ruhig stehen – sonst kippt sie beim nächsten Schritt


class Purzelbaum(Faehigkeit):
    faehigkeit = "purzelbaum"
    braucht = frozenset({'beine'})
    braucht_skill = ("roulade",)
    name = "purzelbaum"
    channels = ("base",)

    def __init__(self, skill: str = "roulade") -> None:
        super().__init__()
        self.skill = skill
        self.timeout = 40.0
        self.inner: Behavior | None = None
        self.phase = "pruefen"
        self.yaw0 = 0.0
        self.start: tuple[float, float] = (0.0, 0.0)
        self.gedreht_vorher = 0.0
        self.ergebnis: dict[str, Any] = {}
        self._suche = 0
        self._ruhe_bis = 0.0
        self._landung_bis = 0.0

    def _use(self, b: Behavior) -> None:
        b.engine = self.engine
        self.inner = b

    def freiraum(self, st) -> float:
        aw = getattr(self.engine, "ausweicher", None) if self.engine else None
        if aw is None:
            return 2 * PLATZ_M
        return aw.freiraum(aw._koerper(st), 0.0)

    def _beste_seite(self, st) -> float | None:
        aw = getattr(self.engine, "ausweicher", None) if self.engine else None
        if aw is None:
            return None
        pts = aw._koerper(st)
        seiten = [(aw.freiraum(pts, math.radians(w)), w) for w in SUCHWINKEL[:2]]
        seiten = sorted((f for f in seiten if f[0] >= PLATZ_M), reverse=True)    # die freiere der beiden Seiten
        if seiten:
            return seiten[0][1]
        return SUCHWINKEL[2] if aw.freiraum(pts, math.pi) >= PLATZ_M else None    # sonst umdrehen

    def on_start(self, st):
        self.yaw0 = st.yaw

    def _ruhe(self) -> None:
        self._ruhe_bis = self.elapsed + RUHE_S

    def tick(self, st, dt):
        if self.elapsed < self._ruhe_bis:
            return Command(twist=Twist())
        if self.inner is not None:
            cmd = self.inner._step(st, dt)
            if not self.inner.done:
                return cmd
            fertig, self.inner = self.inner, None
            if self.phase == "platz":                # Drehung zum Platz fertig → kurz ruhig, noch einmal prüfen
                self.phase = "pruefen"
                self._ruhe()
                return Command(twist=Twist())
            elif self.phase == "rolle":
                if getattr(fertig, "failed", False) or fertig.result.startswith(("abgelehnt", "kein Backend")):
                    return self.ablehnen(fertig.result or "Purzelbaum abgelehnt")
                self.phase = "landen"                  # erst richtig aufrecht und ruhig, dann messen
                self._ruhe()
                return Command(twist=Twist())
            elif self.phase == "zurueck":
                return self.finish(self._text())
        if self.phase == "landen":
            if st.fallen and self.elapsed < self._landung_bis:
                return Command(twist=Twist())      # richtet sich gerade auf
            return self._nachher(st)
        if self.phase == "pruefen":
            if self.freiraum(st) >= PLATZ_M:
                self.phase = "rolle"
                self.start = (st.x, st.y)
                self.yaw0 = st.yaw
                self._use(SkillRun(self.skill))
                self._landung_bis = self.elapsed + 25.0
                return Command()
            w = self._beste_seite(st) if self._suche < len(SUCHWINKEL) else None
            if w is None:
                return self.ablehnen("Zu wenig Platz für einen Purzelbaum – vorn und zu den Seiten ist weniger als "
                                 f"{int(PLATZ_M * 100)} cm frei. Stell mich bitte etwas freier hin.")
            self._suche = len(SUCHWINKEL)              # nur eine Suchdrehung
            self.gedreht_vorher = w
            self.phase = "platz"
            self._use(Turn(w, speed=0.8))
            return Command()
        return Command()

    def _nachher(self, st):
        dreh = math.degrees(math.atan2(math.sin(st.yaw - self.yaw0), math.cos(st.yaw - self.yaw0)))
        weg = math.hypot(st.x - self.start[0], st.y - self.start[1])
        self.ergebnis = {"verdreht_grad": round(dreh), "strecke_m": round(weg, 2), "zurueckgedreht": False,
                         "liegt": bool(st.fallen)}
        if st.fallen or abs(dreh) <= VERDREHT_GRAD:
            return self.finish(self._text())
        self.ergebnis["zurueckgedreht"] = True
        self.phase = "zurueck"
        self._ruhe()
        self._use(Turn(-dreh, speed=0.6))
        return Command(twist=Twist())

    def _text(self) -> str:
        e = self.ergebnis
        if not e:
            return "Purzelbaum ausgeführt"
        if e.get("liegt"):
            return f"Purzelbaum: liegt nach der Landung ({e['strecke_m']:.2f} m gerollt)".replace(".", ",")
        teile = [f"Purzelbaum gelandet, {e['strecke_m']:.2f} m gerollt".replace(".", ",")]
        if self.gedreht_vorher:
            teile.append(f"vorher {abs(self.gedreht_vorher):.0f}° zum freien Platz gedreht")
        if e.get("zurueckgedreht"):
            teile.append(f"um {abs(e['verdreht_grad'])}° verdreht gelandet und zurückgedreht")
        return " – ".join(teile)

    def describe(self):
        return "Purzelbaum (mit Platzprüfung)"

    def info(self) -> dict[str, Any]:
        return {"phase": self.phase, **self.ergebnis}
