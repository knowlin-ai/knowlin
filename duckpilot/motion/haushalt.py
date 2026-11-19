"""Haushalt im Simulator (seit 0.45): vor dem Saugroboter aufräumen und bei knappem Akku zum Ladeplatz.

- **`VorDemSauger`**: trägt Kleines vom Boden (Socke, Klötzchen, Klemmbaustein, Schachfigur) nacheinander zu einem Platz
  (z. B. dem gemerkten Ort „Korb“). Jedes Ding über `Apportieren` – mit Ergebnisprüfung und Plan B. Was nicht klappt,
  bleibt liegen und steht im Bericht. Ob danach der Saugroboter startet, entscheidet die Laufzeit (nie in der Sperre
  nach einem Not-Aus, nur wenn etwas aufgeräumt wurde oder schon alles lag).
- **`Heimkehr`**: zum Ladeplatz gehen, dort hinsetzen (wenn der Körper das kann) und um einen Akkuwechsel bitten –
  die Microduck hat einen Wechselakku, eine Ladestation gibt es nicht.

- **`Rundgang`** (seit 0.46): nacheinander zu Wegpunkten (Raumpunkte, gemerkte Orte oder die Ecken des Zimmers), an
  jedem kurz umschauen. Was dabei auffällt, stellt die Laufzeit aus dem Weltbild zusammen (nur Wörter, keine Bilder).

Der Not-Aus bricht alles sofort ab wie jedes Verhalten (`MotionEngine._cancel_all`).
"""

from __future__ import annotations

import math
from typing import Any

from .apportieren import Apportieren
from .behaviors import GoTo, LookAround, SkillRun
from .engine import Behavior, Command
from .faehigkeit import Faehigkeit

ABLAGE_ABSTAND_M = 0.12        # die Dinge landen rund um den Platz, nicht alle auf einem Haufen
VOR_DEM_PLATZ_M = 0.15         # sie lässt ein Ding ≈ 15 cm vor sich fallen
GEBRACHT_M = 0.35              # so nah am Platz zählt ein Ding als aufgeräumt


class VorDemSauger(Faehigkeit):
    faehigkeit = "aufraeumen_vor_dem_sauger"
    braucht = frozenset({"schnabel", "beine"})
    braucht_skill = ("ground_pick",)
    name = "aufräumen vor dem Saugroboter"
    channels = ("base", "head")

    def __init__(self, dinge: list[dict[str, Any]], ziel: tuple[float, float], ziel_name: str, karte: Any = None) -> None:
        super().__init__()
        self.dinge = [dict(d) for d in dinge]          # {"name", "x", "y"}
        self.ziel, self.ziel_name = ziel, ziel_name
        self.karte = karte
        self.timeout = 150.0 * max(1, len(self.dinge)) + 30.0
        self.nr = -1
        self.gebracht: list[str] = []
        self.liegen: list[str] = []

    def ablage(self, i: int) -> tuple[float, float]:
        a = i * 1.6
        return (self.ziel[0] + ABLAGE_ABSTAND_M * math.cos(a), self.ziel[1] + ABLAGE_ABSTAND_M * math.sin(a))

    def _naechstes(self, st) -> Command | None:
        self.nr += 1
        if self.nr >= len(self.dinge):
            return self._ende()
        d = self.dinge[self.nr]
        ax, ay = self.ablage(self.nr)
        dx, dy = ax - d["x"], ay - d["y"]
        dd = math.hypot(dx, dy) or 1.0
        stand = (ax - dx / dd * VOR_DEM_PLATZ_M, ay - dy / dd * VOR_DEM_PLATZ_M)
        if self.engine:
            self.engine.note({"type": "haushalt", "message": f"Aufräumen: {d['name']} ({self.nr + 1}/{len(self.dinge)})"})
        self._use(Apportieren(str(d["name"]).lower(), stand, self.ziel_name, karte=self.karte, wo=(d["x"], d["y"])))
        return Command()

    def _ende(self) -> Command | None:
        if not self.dinge:
            return self.erfolg("Hier liegt nichts mehr herum – frei für den Saugroboter.")
        text = f"{len(self.gebracht)} von {len(self.dinge)} Dingen zu {self.ziel_name} gebracht"
        if self.liegen:
            text += f"; liegen geblieben: {', '.join(self.liegen)}"
        return self.erfolg(text) if self.gebracht else self.fehlschlag(text)

    def on_start(self, st) -> None:
        self._naechstes(st)

    def tick(self, st, dt):
        if self.inner is None:
            return None
        cmd = self.inner._step(st, dt)
        if not self.inner.done:
            return cmd
        name = self.dinge[self.nr]["name"]
        if getattr(self.inner, "failed", False):
            self.liegen.append(name)
            self.plan_b(f"{name}: {self.inner.result}")
        else:
            self.gebracht.append(name)
        self.inner = None
        return self._naechstes(st)

    def info(self) -> dict[str, Any]:
        return {"gebracht": list(self.gebracht), "liegen": list(self.liegen), "ziel": self.ziel_name,
                "von": len(self.dinge)}

    def describe(self) -> str:
        return f"aufräumen vor dem Saugroboter ({max(0, self.nr) + (1 if self.nr >= 0 else 0)}/{len(self.dinge)})"

    def target(self):
        return getattr(self.inner, "target", lambda: None)() if self.inner else self.ziel


class Heimkehr(Behavior):
    """Zum Ladeplatz, hinsetzen, um einen Akkuwechsel bitten."""

    name = "zum Ladeplatz"
    channels = ("base", "head")

    def __init__(self, ziel: tuple[float, float], ziel_name: str = "Ladeplatz") -> None:
        super().__init__()
        self.ziel, self.ziel_name = ziel, ziel_name
        self.timeout = 90.0
        self.inner: Behavior | None = None
        self.phase = "hin"

    def _use(self, b: Behavior) -> None:
        b.engine = self.engine
        self.inner = b

    def on_start(self, st) -> None:
        self._use(GoTo(self.ziel[0], self.ziel[1], speed=0.15, label=self.ziel_name))

    def tick(self, st, dt):
        if self.inner is None:
            return None
        cmd = self.inner._step(st, dt)
        if not self.inner.done:
            return cmd
        if self.phase == "hin":
            if getattr(self.inner, "failed", False):
                self.failed = True
                return self.finish(f"komme nicht bis zum {self.ziel_name} ({self.inner.result}) – bitte den Akku "
                                   "hier wechseln")
            be = getattr(self.engine, "backend", None)
            skills = be.skills() if be is not None and callable(getattr(be, "skills", None)) else []
            if "sit_toggle" in skills and not st.sitting:
                self.phase = "setzen"
                self.needs_legs = False            # ab hier darf sie sitzen (sonst wartet `_step` auf die Beine)
                self._use(SkillRun("sit_toggle", voice=None))
                return Command()
        return self.finish(f"am {self.ziel_name} – bitte den Akku wechseln")

    def target(self):
        return self.ziel

    def describe(self) -> str:
        return f"zum {self.ziel_name}"


class Rundgang(Behavior):
    """Eine Runde über die Wegpunkte, an jedem umschauen; kommt sie an einen nicht heran, geht es zum nächsten."""

    name = "Rundgang"
    channels = ("base", "head")
    UMSCHAUEN_S = 4.0

    def __init__(self, punkte: list[tuple[float, float, str]]) -> None:
        super().__init__()
        self.punkte = list(punkte)
        self.timeout = 70.0 * max(1, len(self.punkte)) + 10.0
        self.nr = -1
        self.phase = "hin"
        self.inner: Behavior | None = None
        self.besucht: list[str] = []
        self.verpasst: list[str] = []

    def _use(self, b: Behavior) -> None:
        b.engine = self.engine
        self.inner = b

    def _weiter(self) -> Command | None:
        self.nr += 1
        if self.nr >= len(self.punkte):
            text = f"Rundgang fertig: {len(self.besucht)} von {len(self.punkte)} Stellen"
            if self.verpasst:
                text += f" (nicht erreicht: {', '.join(self.verpasst)})"
            if not self.besucht:
                self.failed = True
            return self.finish(text)
        x, y, name = self.punkte[self.nr]
        self.phase = "hin"
        if self.engine:
            self.engine.note({"type": "haushalt", "message": f"Rundgang: {name} ({self.nr + 1}/{len(self.punkte)})"})
        self._use(GoTo(x, y, speed=0.18, label=name))
        return Command()

    def on_start(self, st) -> None:
        if not self.punkte:
            self.failed = True
            self.finish("Kein Weg für den Rundgang – merk dir erst Orte oder Räume")
            return
        self._weiter()

    def tick(self, st, dt):
        if self.inner is None:
            return None
        cmd = self.inner._step(st, dt)
        if not self.inner.done:
            return cmd
        name = self.punkte[self.nr][2]
        if self.phase == "hin":
            if getattr(self.inner, "failed", False):
                self.verpasst.append(name)
                return self._weiter()
            self.phase = "schauen"
            self._use(LookAround(self.UMSCHAUEN_S, seed=self.nr))
            return Command()
        self.besucht.append(name)
        return self._weiter()

    def target(self):
        return self.punkte[self.nr][:2] if 0 <= self.nr < len(self.punkte) else None

    def describe(self) -> str:
        return f"Rundgang ({max(0, self.nr) + 1}/{len(self.punkte)})"
