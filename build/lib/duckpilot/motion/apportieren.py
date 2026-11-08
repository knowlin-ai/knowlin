"""Apportieren: „Bring mir die Socke“ – hin, aufheben, prüfen, zurück, ablegen (seit 0.37).

Aufgebaut wie eine Fähigkeit der späteren Suite-Schnittstelle (0.38): **Vorbedingung** (steht, Schnabel frei),
**Ablauf** aus vorhandenen Bausteinen (`Approach`, `SkillRun("ground_pick")`, `GoTo`), **Ergebnisprüfung** nach jedem
Schritt (hat sie es wirklich im Schnabel? liegt es wieder?) und **Plan B**: Geht das Aufheben daneben, tritt sie einen
Schritt zurück, nähert sich neu und versucht es noch einmal – höchstens `VERSUCHE` Mal, dann sagt sie ehrlich, dass es
nicht geklappt hat.

Wohin sie bringt: zum Menschen, wenn sie ihn sieht (im Simulator die Verkörperung, die die Maus führt), sonst zu einer
mitgegebenen Stelle oder dorthin, wo sie losgelaufen ist. Sie bleibt ≈ 25 cm vor dem Menschen stehen.

Ob etwas im Schnabel ist, weiß nur der Simulator (`DuckState.holding`); am echten Roboter gilt die Prüfung als
„nicht messbar“ und der Ablauf geht weiter (bis die Kamera das kann – 0.37 Teil 2).
"""

from __future__ import annotations

import math
from typing import Any

from ..api import DuckState, Head, Twist
from .behaviors import Approach, GoTo, SkillRun, Walk, _welt, emotion
from .engine import Behavior, Command
from .faehigkeit import Faehigkeit

VERSUCHE = 3                 # Aufheben höchstens so oft (der erste plus zwei Mal Plan B)
VOR_DEM_MENSCHEN_M = 0.25


def _gleich(name: str | None, ding: str) -> bool:
    return bool(name) and (ding in name.lower() or name.lower() in ding)


class Apportieren(Faehigkeit):
    """Ein Ding holen und bringen – mit Ergebnisprüfung und Plan B."""
    faehigkeit = "apportieren"
    braucht = frozenset({'schnabel', 'beine'})
    braucht_skill = ("ground_pick",)

    name = "apportieren"
    channels = ("base", "head")

    UMWEGE = 3                    # so oft sucht sie einen Weg um ein Hindernis (seit 0.37.3)

    def __init__(self, ding: str, zu: tuple[float, float] | None = None, zu_name: str | None = None,
                 karte: Any = None, wo: tuple[float, float] | None = None) -> None:
        super().__init__()
        from .karte import Karte

        # Wegsuche (Hinweis aus dem Test: „wenn auf dem Weg ein Hindernis ist, probiert er nicht wirklich, einen Weg zu
        # finden“): Unterwegs trägt sie ein, was der Tiefensensor sieht; kommt sie nicht näher oder sieht das Ding
        # nicht (verdeckt), plant sie auf dieser Karte einen Umweg zur letzten bekannten Stelle (`wo`: aus den
        # Sichtungen) und setzt dann neu an.
        self.karte = karte if karte is not None else Karte()
        self.wo = wo
        self.umwege = 0
        self._takte = 0
        self.ding = ding.strip().lower() or "socke"
        self.zu = zu
        self.zu_name = zu_name
        self.timeout = 150.0
        self.needs_target = True
        self.phase = "start"
        self.inner: Behavior | None = None
        self.versuche = 0
        self.start: tuple[float, float] | None = None
        self.mensch: tuple[float, float] | None = None
        self.protokoll: list[str] = []          # was passiert ist (Plan B), fürs Ergebnis

    # ── Hilfen ───────────────────────────────────────────────────────────
    def _use(self, b: Behavior) -> None:
        b.engine = self.engine
        self.inner = b

    @staticmethod
    def _messbar(st: DuckState) -> bool:
        return st.backend != "robotd"

    def _haelt(self, st: DuckState) -> bool:
        return _gleich(st.holding, self.ding) if self._messbar(st) else True

    @staticmethod
    def _mensch(st: DuckState) -> tuple[float, float] | None:
        obj = next((o for o in st.perception.objects if o.get("art") == "person"), None)
        return None if obj is None else _welt(st, obj)

    def _ziel(self, st: DuckState) -> tuple[float, float, str]:
        if self.zu is not None:
            return (*self.zu, self.zu_name or "zur Stelle")
        mensch = self._mensch(st) or self.mensch
        if mensch is not None:                   # davor stehen bleiben, nicht auf die Füße laufen
            dx, dy = mensch[0] - st.x, mensch[1] - st.y
            d = math.hypot(dx, dy)
            if d <= VOR_DEM_MENSCHEN_M + 0.05:
                return (st.x, st.y, "zu dir")
            k = (d - VOR_DEM_MENSCHEN_M) / d
            return (st.x + dx * k, st.y + dy * k, "zu dir")
        x, y = self.start or (st.x, st.y)
        return (x, y, "zurück zum Start")

    # ── Ablauf ───────────────────────────────────────────────────────────
    def on_start(self, st):
        self.start = (st.x, st.y)
        self.mensch = self._mensch(st)
        if st.holding and not _gleich(st.holding, self.ding):
            self.failed = True                   # Vorbedingung: Schnabel frei
            self.finish(f"hat schon {st.holding} im Schnabel – erst ablegen")
            return
        if st.holding:                           # hat es schon: gleich bringen
            self._bringen(st)
            return
        sichtbar = any(self.ding in str(o.get("name", "")).lower() or self.ding == o.get("art")
                       for o in st.perception.objects)
        if not sichtbar and self.wo is not None:     # verdeckt, aber sie weiß, wo es zuletzt lag: gleich hin
            self.phase = "hin"
            if self._umweg(st, "nicht zu sehen – zur letzten bekannten Stelle"):
                return
        self._hin()

    def _hin(self) -> None:
        self.phase = "hin"
        self._use(Approach(self.ding, stop_at=0.13, bearing_tol_deg=8.0, vermutet=self.wo))

    def _umweg(self, st: DuckState, warum: str) -> bool:
        """Plan B für den Hinweg: auf der Karte um das Hindernis herum zur letzten bekannten Stelle."""
        from .karte import Route

        ziel = getattr(self.inner, "goal", None) or self.wo
        if ziel is None or self.umwege >= self.UMWEGE:
            return False
        # Standplätze rund ums Ding (22 cm davor, acht Richtungen) – zuerst die von hier aus nächsten; jeder nur
        # einmal, damit sie beim zweiten Mal von einer anderen Seite kommt (z. B. hinter dem Tisch)
        if not hasattr(self, "_seiten"):
            self._seiten: list[tuple[float, float]] = []
        plaetze = [(ziel[0] + 0.22 * math.cos(a), ziel[1] + 0.22 * math.sin(a))
                   for a in (i * math.pi / 4 for i in range(8))]
        plaetze = [q for q in plaetze if all(math.hypot(q[0] - v[0], q[1] - v[1]) > 0.15 for v in self._seiten)]
        plaetze.sort(key=lambda q: math.hypot(q[0] - st.x, q[1] - st.y))
        weg = None
        for q in plaetze:
            if math.hypot(q[0] - st.x, q[1] - st.y) < 0.1:
                continue
            route = self.karte.route((st.x, st.y), q)
            if route is not None and math.hypot(route[-1][0] - q[0], route[-1][1] - q[1]) < 0.08:
                weg = Route(self.karte, q, f"Umweg zu {self.ding}")
                self._seiten.append(q)
                break
        if weg is None:
            return False
        self.umwege += 1
        self.protokoll.append(f"Umweg {self.umwege}: {warum}")
        if self.engine:
            self.engine.note({"type": "apportieren", "message": f"Hindernis – ich suche einen Weg ({warum})"})
        self.phase = "umweg"
        self._use(weg)
        return True

    def _aufheben(self) -> None:
        self.phase = "aufheben"
        self.versuche += 1
        self._use(SkillRun("ground_pick", voice=None))

    def _bringen(self, st: DuckState) -> None:
        self.phase = "bringen"
        x, y, label = self._ziel(st)
        self._use(GoTo(x, y, speed=0.15, label=label))

    def _ablegen(self) -> None:
        self.phase = "ablegen"
        self._use(SkillRun("ground_pick", voice=None))

    def _plan_b(self, st: DuckState, warum: str) -> Command | None:
        if self.versuche >= VERSUCHE:
            self.failed = True
            return self.finish(f"{self.ding} nicht erwischt ({self.versuche} Versuche): {warum}")
        self.protokoll.append(f"Plan B nach Versuch {self.versuche}: {warum}")
        if self.engine:
            self.engine.note({"type": "apportieren", "message": f"Daneben – noch ein Versuch ({warum})"})
        self.phase = "zurueck"
        self._use(Walk(-0.08, 0.1))              # einen Schritt zurück, dann neu anlaufen
        return Command(twist=Twist())

    def tick(self, st, dt):
        if self.inner is None:
            return None
        self._takte += 1
        if self.phase in ("hin", "bringen") and self._takte % 4 == 0 and st.perception.points:
            self.karte.eintragen(st.x, st.y, st.perception.points)
        cmd = self.inner._step(st, dt)
        if not self.inner.done:
            if self.phase == "bringen":          # Kopf hoch, Beute zeigen
                cmd = cmd or Command()
                cmd.head = Head(0.0, -0.05, 0.0, 0.0)
            return cmd
        res = self.inner.result or ""
        if self.phase == "hin":
            if getattr(self.inner, "failed", False):
                if self._umweg(st, res):
                    return Command(twist=Twist())
                self.failed = True
                return self.finish(f"{self.ding}: {res}")
            self._aufheben()
        elif self.phase == "umweg":
            self._hin()                            # angekommen oder nicht: neu ansetzen (sieht es von hier aus)
        elif self.phase == "aufheben":
            if self._haelt(st):
                self._bringen(st)
            elif st.holding:                     # das Falsche erwischt: wieder hinlegen, dann Plan B
                self.phase = "falsch"
                self.falsch = st.holding
                self._use(SkillRun("ground_pick", voice=None))
            else:
                return self._plan_b(st, "nichts im Schnabel")
        elif self.phase == "falsch":
            return self._plan_b(st, f"{getattr(self, 'falsch', 'etwas anderes')} statt {self.ding} erwischt")
        elif self.phase == "zurueck":
            self._hin()
        elif self.phase == "bringen":
            self._ablegen()
        elif self.phase == "ablegen":
            if self._messbar(st) and st.holding:
                self.failed = True
                return self.finish(f"{self.ding} hängt noch im Schnabel")
            self.phase = "freuen"
            self._use(emotion("freude"))
        elif self.phase == "freuen":
            extra = f" ({len(self.protokoll)}× Plan B)" if self.protokoll else ""
            return self.finish(f"{self.ding} gebracht{extra}")
        return Command(twist=Twist())

    def kontakt_ziel(self, st: DuckState) -> tuple[float, float, float] | None:
        if self.inner is not None and self.phase in ("hin", "aufheben"):
            return self.inner.kontakt_ziel(st)
        return None

    def on_stop(self):
        if self.inner is not None and not self.inner.done:
            self.inner.on_stop()
        if not self.result.startswith(f"{self.ding} gebracht"):
            self.failed = True

    def target(self):
        return self.inner.target() if self.inner is not None and self.phase in ("hin", "bringen", "umweg") else None

    def describe(self):
        schritt = {"hin": "hin", "umweg": "Umweg", "aufheben": "aufheben", "zurueck": "Plan B", "bringen": "bringen",
                   "ablegen": "ablegen", "freuen": "fertig", "falsch": "Plan B"}.get(self.phase, "")
        return f"apportieren: {self.ding}" + (f" ({schritt})" if schritt else "")

    def info(self) -> dict[str, Any]:
        return {"ding": self.ding, "phase": self.phase, "versuche": self.versuche, "plan_b": list(self.protokoll)}
