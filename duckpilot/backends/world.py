"""Eine kleine 2D-Welt für den Simulator: Wände, Möbel, ein Ball, eine Socke.

Alles in Metern, Ursprung in der Raummitte, x nach vorn (Start-Blickrichtung
der Ente), y nach links. Die Höhe spielt nur für die Darstellung eine Rolle.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Box:
    name: str
    x: float          # Mitte
    y: float
    sx: float         # volle Breite in x
    sy: float         # volle Breite in y
    h: float = 0.4
    color: str = "#b9a58c"

    def segments(self) -> list[tuple[float, float, float, float]]:
        x0, x1 = self.x - self.sx / 2, self.x + self.sx / 2
        y0, y1 = self.y - self.sy / 2, self.y + self.sy / 2
        return [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]

    def push_out(self, px: float, py: float, r: float) -> tuple[float, float] | None:
        """Kollidiert ein Kreis (px, py, r)? Dann der Vektor, der ihn herausschiebt."""
        cx = min(max(px, self.x - self.sx / 2), self.x + self.sx / 2)
        cy = min(max(py, self.y - self.sy / 2), self.y + self.sy / 2)
        dx, dy = px - cx, py - cy
        d = math.hypot(dx, dy)
        if d >= r:
            return None
        if d < 1e-9:  # Mittelpunkt innen: nach oben schieben
            return (0.0, r)
        return (dx / d * (r - d), dy / d * (r - d))


@dataclass
class Cylinder:
    name: str
    x: float
    y: float
    r: float
    h: float = 0.35
    color: str = "#6f8f5a"

    def push_out(self, px: float, py: float, r: float) -> tuple[float, float] | None:
        dx, dy = px - self.x, py - self.y
        d = math.hypot(dx, dy)
        if d >= r + self.r:
            return None
        if d < 1e-9:
            return (r + self.r, 0.0)
        k = (r + self.r - d) / d
        return (dx * k, dy * k)


AUFHEBBAR = ("sock", "block", "baustein", "figur")   # passt in den Schnabel (seit 0.37 auch Klemmbaustein, Schachfigur)


@dataclass
class Item:
    """Bewegliches Ding: Ball (rollt, kickbar) oder etwas zum Aufheben (Socke, Klötzchen, Klemmbaustein, Schachfigur)."""

    name: str
    kind: str          # "ball" | "sock" | "block" | "baustein" | "figur"
    x: float
    y: float
    r: float = 0.04
    vx: float = 0.0
    vy: float = 0.0
    held: bool = False
    color: str = "#e0533d"
    traeger: str = ""          # wer es im Schnabel hat: „haupt“ oder die Kennung einer weiteren Ente (seit 0.37.4)

    @property
    def pickable(self) -> bool:
        return self.kind in AUFHEBBAR


@dataclass
class World:
    width: float = 4.0     # x-Ausdehnung
    depth: float = 3.0     # y-Ausdehnung
    boxes: list[Box] = field(default_factory=list)
    cylinders: list[Cylinder] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    # Laserpunkt vom Menschen (Maus oder Finger in der 3D-Ansicht): (x, y, zuletzt gesetzt), nur Licht, kein Ding
    laser: tuple[float, float, float] | None = None       # (x, y, gesetzt um)
    laser_z: float = 0.0                                   # Höhe des Punkts (0 = Boden, sonst auf einem Möbel)
    LASER_TTL = 3.0                     # ohne Lebenszeichen der Oberfläche ist der Pointer „aus“
    # Mensch zum Hinterherlaufen (Follow-me im Simulator): die Maus führt ihn über den Boden
    person: tuple[float, float, float] | None = None      # (x, y, gesetzt um)
    PERSON_TTL = 3.0

    def set_laser(self, x: float | None, y: float | None, z: float = 0.0) -> None:
        if x is None or y is None:
            self.laser = None
            return
        self.laser_z = max(0.0, min(2.0, z))
        w, d = self.width / 2, self.depth / 2
        self.laser = (max(-w, min(w, x)), max(-d, min(d, y)), time.monotonic())

    def set_person(self, x: float | None, y: float | None) -> None:
        if x is None or y is None:
            self.person = None
            return
        w, d = self.width / 2, self.depth / 2
        self.person = (max(-w, min(w, x)), max(-d, min(d, y)), time.monotonic())

    def person_point(self) -> tuple[float, float] | None:
        if self.person is None or time.monotonic() - self.person[2] > self.PERSON_TTL:
            return None
        return self.person[0], self.person[1]

    def laser_point(self) -> tuple[float, float] | None:
        if self.laser is None or time.monotonic() - self.laser[2] > self.LASER_TTL:
            return None
        return self.laser[0], self.laser[1]

    @classmethod
    def living_room(cls) -> "World":
        return cls(
            boxes=[
                Box("Sofa", 0.0, 1.22, 1.6, 0.55, 0.45, "#7a8fb3"),
                Box("Regal", 1.82, -0.6, 0.35, 1.0, 0.9, "#b9926f"),
                Box("Kiste", -1.1, -0.75, 0.4, 0.4, 0.3, "#dcbf92"),
                Box("Couchtisch", 0.55, 0.25, 0.25, 0.25, 0.4, "#a88565"),
            ],
            cylinders=[
                Cylinder("Pflanze", -1.65, 1.1, 0.16, 0.6, "#5f8a4e"),
                Cylinder("Hocker", 1.0, -1.05, 0.14, 0.4, "#8f8f8f"),
            ],
            items=[
                Item("Ball", "ball", 0.75, -0.35, 0.045, color="#e8553e"),
                Item("Socke", "sock", -0.55, 0.55, 0.035, color="#e9e2cf"),
                Item("Klötzchen", "block", -0.8, -0.2, 0.025, color="#4a90d9"),
                Item("Klemmbaustein", "baustein", 0.25, -0.85, 0.02, color="#d23c32"),
                Item("Schachfigur", "figur", 0.3, 0.72, 0.018, color="#2f2f33"),
            ],
        )

    # ── Geometrie ────────────────────────────────────────────────────────
    def wall_segments(self) -> list[tuple[float, float, float, float]]:
        w, d = self.width / 2, self.depth / 2
        return [(-w, -d, w, -d), (w, -d, w, d), (w, d, -w, d), (-w, d, -w, -d)]

    def all_segments(self) -> list[tuple[float, float, float, float]]:
        segs = self.wall_segments()
        for b in self.boxes:
            segs.extend(b.segments())
        return segs

    def collide(self, px: float, py: float, r: float) -> tuple[float, float, str] | None:
        """Erste Kollision eines Kreises: (push_x, push_y, mit_was)."""
        w, d = self.width / 2, self.depth / 2
        if px - r < -w:
            return (-w - (px - r), 0.0, "Wand")
        if px + r > w:
            return (w - (px + r), 0.0, "Wand")
        if py - r < -d:
            return (0.0, -d - (py - r), "Wand")
        if py + r > d:
            return (0.0, d - (py + r), "Wand")
        for obstacle in [*self.boxes, *self.cylinders]:
            push = obstacle.push_out(px, py, r)
            if push:
                return (push[0], push[1], obstacle.name)
        return None

    def raycast(self, ox: float, oy: float, angle: float, max_dist: float = 2.5,
                include_items: bool = True) -> tuple[float, str] | None:
        """Abstand entlang eines Strahls bis zum ersten Treffer."""
        dx, dy = math.cos(angle), math.sin(angle)
        best: tuple[float, str] | None = None

        def consider(t: float, what: str) -> None:
            nonlocal best
            if 0.0 < t <= max_dist and (best is None or t < best[0]):
                best = (t, what)

        for (x1, y1, x2, y2), name in self._named_segments():
            ex, ey = x2 - x1, y2 - y1
            denom = dx * ey - dy * ex
            if abs(denom) < 1e-12:
                continue
            t = ((x1 - ox) * ey - (y1 - oy) * ex) / denom
            u = ((x1 - ox) * dy - (y1 - oy) * dx) / denom
            if 0.0 <= u <= 1.0:
                consider(t, name)
        circles = [(c.x, c.y, c.r, c.name) for c in self.cylinders]
        if include_items:
            circles += [(i.x, i.y, i.r, i.name) for i in self.items if not i.held]
        for cx, cy, cr, name in circles:
            fx, fy = ox - cx, oy - cy
            b = fx * dx + fy * dy
            c = fx * fx + fy * fy - cr * cr
            disc = b * b - c
            if disc >= 0:
                consider(-b - math.sqrt(disc), name)
        return best

    def _named_segments(self):
        for seg in self.wall_segments():
            yield seg, "Wand"
        for b in self.boxes:
            for seg in b.segments():
                yield seg, b.name

    def line_of_sight(self, ox: float, oy: float, tx: float, ty: float) -> bool:
        dist = math.hypot(tx - ox, ty - oy)
        hit = self.raycast(ox, oy, math.atan2(ty - oy, tx - ox), dist, include_items=False)
        return hit is None or hit[0] >= dist - 0.02

    def step_items(self, dt: float) -> None:
        for item in self.items:
            if item.held:
                continue
            speed = math.hypot(item.vx, item.vy)
            if speed < 1e-3:
                item.vx = item.vy = 0.0
                continue
            item.x += item.vx * dt
            item.y += item.vy * dt
            # Mehrere Kollisionen nacheinander auflösen (seit 0.37.14): In einer Ecke stieß der Ball an zwei Wände, nur
            # eine wurde berücksichtigt – er blieb halb in der Wand stecken (das Bildschirmfoto)
            for _ in range(4):
                hit = self.collide(item.x, item.y, item.r)
                if not hit:
                    break
                px, py, _ = hit
                item.x += px
                item.y += py
                n = math.hypot(px, py) or 1.0
                nx, ny = px / n, py / n
                dot = item.vx * nx + item.vy * ny
                if dot < 0:
                    item.vx = (item.vx - 2 * dot * nx) * 0.6
                    item.vy = (item.vy - 2 * dot * ny) * 0.6
            self.im_zimmer(item)
            friction = 0.55 if item.kind == "ball" else 4.0
            factor = max(0.0, 1.0 - friction * dt)
            item.vx *= factor
            item.vy *= factor

    def im_zimmer(self, item: Any) -> None:
        """Ding sicher im Zimmer halten: zuletzt immer innerhalb der Wände (seit 0.37.14)."""
        w, d = self.width / 2 - item.r, self.depth / 2 - item.r
        if abs(item.x) > w:
            item.x = math.copysign(w, item.x)
            item.vx = -item.vx * 0.6 if item.x * item.vx > 0 else item.vx
        if abs(item.y) > d:
            item.y = math.copysign(d, item.y)
            item.vy = -item.vy * 0.6 if item.y * item.vy > 0 else item.vy

    def loesen(self, item: Any) -> None:
        """Ding aus Wänden und Möbeln herausschieben (nach dem Schubsen durch die Ente)."""
        for _ in range(4):
            hit = self.collide(item.x, item.y, item.r)
            if not hit:
                break
            item.x += hit[0]
            item.y += hit[1]
        self.im_zimmer(item)

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "depth": self.depth,
            "boxes": [vars(b) for b in self.boxes],
            "cylinders": [vars(c) for c in self.cylinders],
        }

    def items_dict(self) -> list[dict[str, Any]]:
        return [
            {"name": i.name, "kind": i.kind, "x": i.x, "y": i.y, "r": i.r, "held": i.held, "color": i.color,
             "traeger": i.traeger}
            for i in self.items
        ]
