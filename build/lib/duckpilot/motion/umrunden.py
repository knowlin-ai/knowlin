"""Um ein Ding oder Möbel herumlaufen (seit 0.38.21, Fund: „um den Tisch läuft er nicht – er läuft einfach ein
bisschen nach vorn“).

Ablauf: das Ziel suchen (auf der Stelle drehen, wie beim Annähern), seine Mitte im Raum festhalten, dann einmal ringsum
laufen – mit Abstand wie ein abgerundetes Rechteck um einen Kasten (Sofa, Tisch, Kiste), sonst im Kreis. Die Größe
kommt aus der Wahrnehmung (`ausdehnung_m` bzw. `radius_m`, im Simulator bekannt); fehlt sie, nimmt sie einen
vorsichtigen Kreis. Der Kopf schaut dabei zum Ziel. Ist ein Stück nicht frei, lässt sie den Punkt aus; geht es dreimal
hintereinander nicht weiter (z. B. das Sofa steht an der Wand), kehrt sie um und läuft die freien Seiten von der anderen
Richtung ab – und sagt ehrlich, dass sie nicht ganz herum kam.
"""

from __future__ import annotations

import math

from ..api import Head, Twist, wrap_angle
from .behaviors import GoTo
from .engine import Behavior, Command
from .hilfen import DEG

ABSTAND_M = 0.2                 # Luft zwischen Ding und Laufweg (Rumpf + Sicherheitsabstand)
ERSATZ_RADIUS_M = 0.3           # Ziel ohne bekannte Größe
PUNKTE_JE_ECKE = 3


def rundweg(mx: float, my: float, ausdehnung: tuple[float, float] | None, radius: float | None,
            abstand: float = ABSTAND_M) -> list[tuple[float, float]]:
    """Wegpunkte gegen den Uhrzeigersinn um die Mitte: Kasten (volle Breiten) als abgerundetes Rechteck, sonst Kreis."""
    if ausdehnung:
        a, b = ausdehnung[0] / 2, ausdehnung[1] / 2
        punkte = []
        for i, (ex, ey) in enumerate(((a, b), (-a, b), (-a, -b), (a, -b))):
            for k in range(PUNKTE_JE_ECKE):
                w = (i + k / (PUNKTE_JE_ECKE - 1)) * math.pi / 2
                punkte.append((mx + ex + abstand * math.cos(w), my + ey + abstand * math.sin(w)))
        return punkte
    r = (radius if radius else ERSATZ_RADIUS_M - abstand) + abstand
    return [(mx + r * math.cos(w), my + r * math.sin(w)) for w in (i * math.pi / 6 for i in range(12))]


class Umrunden(Behavior):
    name = "umrunden"
    channels = ("base", "head")
    timeout = 150.0

    def __init__(self, target: str, richtung: str = "links") -> None:
        super().__init__()
        self.target_name = target.lower()
        self.rechts = richtung == "rechts"
        self.mitte: tuple[float, float] | None = None
        self.weg: list[tuple[float, float]] = []
        self.inner: GoTo | None = None
        self.such_t = 0.0
        self.fehlt = 0
        self.geschafft = 0
        self.besucht: list[tuple[float, float]] = []
        self.umgekehrt = False
        self.ziel_name = target

    def _find(self, st) -> dict | None:
        for obj in st.perception.objects:
            if self.target_name in obj["name"].lower() or self.target_name == obj.get("art", ""):
                return obj
        return None

    def _planen(self, st, obj) -> None:
        b = math.radians(obj["richtung_grad"])
        r = obj["entfernung_m"] + 0.03
        mx, my = st.x + r * math.cos(st.yaw + b), st.y + r * math.sin(st.yaw + b)
        self.mitte = (mx, my)
        self.ziel_name = obj["name"]
        aus = obj.get("ausdehnung_m")
        punkte = rundweg(mx, my, tuple(aus) if aus else None, obj.get("radius_m"))
        if self.rechts:
            punkte.reverse()
        # beim nächsten Punkt einsteigen und einmal ganz herum bis wieder dorthin
        start = min(range(len(punkte)), key=lambda i: math.hypot(punkte[i][0] - st.x, punkte[i][1] - st.y))
        self.weg = punkte[start:] + punkte[:start] + [punkte[start]]

    def _naechster(self) -> None:
        x, y = self.weg.pop(0)
        self.inner = GoTo(x, y, speed=0.16, label=f"um {self.ziel_name}")
        self.inner.engine = self.engine

    def tick(self, st, dt):
        if self.mitte is None:
            obj = self._find(st)
            if obj is None:
                self.such_t += dt
                if self.such_t > 12.0:
                    self.failed = True
                    return self.finish(f"'{self.target_name}' nicht gefunden")
                return Command(twist=Twist(0.0, 0.0, 0.6), head=Head(0.0, 0.2, 0.4, 0.0), guard=False)
            self._planen(st, obj)
            self._naechster()
        cmd = self.inner._step(st, dt)
        if self.inner.done:
            if getattr(self.inner, "failed", False):
                self.fehlt += 1
                if self.fehlt >= 3:
                    if self.umgekehrt or not self.besucht:
                        return self.finish(f"um {self.ziel_name}, soweit Platz ist – ganz herum ging es nicht (Wand oder Möbel)")
                    # umkehren: zurück über die schon gelaufenen Punkte, dann die freien Seiten auf der anderen Seite
                    self.umgekehrt, self.fehlt = True, 0
                    zurueck = list(reversed(self.besucht[:-1]))
                    rest = list(reversed(self.weg))
                    self.weg = zurueck + rest
            else:
                self.fehlt = 0
                self.geschafft += 1
                self.besucht.append((self.inner.tx, self.inner.ty))
            if not self.weg:
                if self.umgekehrt:
                    return self.finish(f"um {self.ziel_name}, soweit Platz ist – ganz herum ging es nicht (Wand oder Möbel)")
                return self.finish(f"einmal um {self.ziel_name} herum")
            self._naechster()
            cmd = Command()
        # Kopf zum Ziel
        gx, gy = self.mitte
        blick = wrap_angle(math.atan2(gy - st.y, gx - st.x) - st.yaw)
        head = Head(0.0, 0.2, max(-60 * DEG, min(60 * DEG, blick)), 0.0)
        twist = cmd.twist if cmd is not None and cmd.twist is not None else Twist()
        return Command(twist=twist, head=head)

    def on_stop(self):
        if not self.result.startswith(("einmal um", "um ")):
            self.failed = True

    def target(self):
        return self.inner.target() if self.inner is not None else self.mitte

    def wegpunkte(self) -> list[tuple[float, float]]:
        return list(self.weg)

    def describe(self):
        return f"um {self.ziel_name} herum"
