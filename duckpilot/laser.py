"""Laserpunkt: im Kamerabild des echten Roboters finden und als Ding auf dem Boden melden.

Wie Pollens eigene Funktion („follow a laser dot“, Pointer liegt dem Zubehör-Pack bei): Ein roter
Laserpunkt ist klein, sehr hell und deutlich röter als seine Umgebung. Der Erkenner sucht den
röteste-hellsten Fleck und verwirft große rote Flächen (der rote Ball, ein Kissen).

Aus der Bildposition wird mit der Kopfneigung und der Kamerahöhe ein Punkt auf dem Boden – so
liefert der echte Roboter dieselbe Art Ding (`art = "laser"`, Entfernung, Richtung zum Rumpf) wie
der Simulator, und dasselbe Verhalten `FollowLaser` läuft hier wie dort.

Die Schwellen sind Schätzungen und am echten Roboter mit dem echten Pointer nachzustellen.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .server.app import Runtime

log = logging.getLogger(__name__)

HFOV_DEG = 70.0          # Blickwinkel der Kopfkamera (grob, wie beim Enten-Erkenner)
CAM_HEIGHT = 0.21        # m über dem Boden im Stand
MIN_RED = 200            # so hell muss der Rotanteil mindestens sein
MIN_REDNESS = 45         # Rot minus stärkste andere Farbe
MAX_AREA = 0.004         # größer als 0,4 % des Bildes: eher ein rotes Ding als ein Laserpunkt
FAR_M = 1.5              # Punkt über dem Horizont (Wand, Möbel): Entfernung unbekannt, „weit weg“
LASER_NAME = "Laserpunkt"


def detect_laser(rgb) -> dict[str, Any] | None:
    """Laserpunkt im RGB-Bild (H, W, 3, uint8) → {"x", "y" (Pixel), "flaeche" (Anteil), "wert"} oder None."""
    import numpy as np

    h, w, _ = rgb.shape
    px = rgb.astype(np.int16)
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    redness = r - np.maximum(g, b)
    hot = (r >= MIN_RED) & (redness >= MIN_REDNESS)
    if not hot.any():
        return None
    score = np.where(hot, redness + 2 * (r - MIN_RED), -1)
    cy, cx = np.unravel_index(int(np.argmax(score)), score.shape)
    ri = max(5, int(0.025 * w))                 # so groß darf ein Laserfleck samt Schein sein
    ro = 3 * ri

    def box(rad):
        return max(0, cy - rad), min(h, cy + rad + 1), max(0, cx - rad), min(w, cx + rad + 1)

    y0, y1, x0, x1 = box(ri)
    win = hot[y0:y1, x0:x1]
    n_in = int(win.sum())
    oy0, oy1, ox0, ox1 = box(ro)
    n_out = int(hot[oy0:oy1, ox0:ox1].sum())
    if n_out - n_in > 0.5 * n_in + 3 or n_out / float(h * w) > MAX_AREA:
        return None                              # Fläche geht weiter: Ball, Kissen, Pulli – kein Laser
    area = n_in / float(h * w)
    ys, xs = np.nonzero(win)
    return {"x": float(xs.mean() + x0), "y": float(ys.mean() + y0), "flaeche": round(area, 5),
            "wert": int(score[cy, cx])}


def to_floor(spot: dict[str, Any], width: int, height: int, tilt: float, head_yaw: float,
             cam_h: float = CAM_HEIGHT, hfov_deg: float = HFOV_DEG) -> dict[str, Any]:
    """Bildpunkt → Ding auf dem Boden: Entfernung (m) und Richtung zum Rumpf (Grad, + = links).

    `tilt` ist die Blickneigung (+ = nach unten), `head_yaw` die Kopfdrehung (+ = links), beide in rad.
    """
    th = math.tan(math.radians(hfov_deg) / 2)
    tv = th * height / max(1, width)
    ax = math.atan((1 - 2 * spot["x"] / width) * th)        # + = links im Bild
    ay = math.atan((1 - 2 * spot["y"] / height) * tv)       # + = oben im Bild
    elev = ay - tilt
    dist = cam_h / math.tan(-elev) if elev < -0.03 else FAR_M
    dist = max(0.05, min(FAR_M, dist))
    return {"name": LASER_NAME, "art": "laser", "entfernung_m": round(dist, 2),
            "richtung_grad": round(math.degrees(head_yaw + ax)), "quelle": "kamera"}


class LaserWatch:
    """Schaut am echten Roboter ein paar Mal pro Sekunde nach dem Laserpunkt – nur solange sie ihm folgt."""

    PERIOD = 0.2

    def __init__(self) -> None:
        self.last_spot: dict[str, Any] | None = None
        self.error: str | None = None

    @staticmethod
    def wanted(rt: "Runtime") -> bool:
        from .motion.behaviors import FollowLaser

        return isinstance(rt.engine.current, FollowLaser)

    async def run(self, rt: "Runtime") -> None:
        while True:
            await asyncio.sleep(self.PERIOD)
            try:
                await self.once(rt)
            except asyncio.CancelledError:
                raise
            except Exception as exc:              # Kamera mal weg: weiter versuchen, nicht abstürzen
                self.error = f"{type(exc).__name__}: {exc}"

    async def once(self, rt: "Runtime") -> None:
        backend = rt.backend
        see = getattr(backend, "see_objects", None)
        if see is None or not self.wanted(rt):
            return
        addr = rt.camera_address()
        if not addr:
            return
        rt.camera.address = addr
        await rt.camera.picture()
        rgb = rt.camera.last_rgb
        if rgb is None:
            return
        spot = await asyncio.to_thread(detect_laser, rgb)
        self.last_spot = spot
        if spot is None:
            see([])
            return
        tilt, head_yaw = backend.gaze()
        see([to_floor(spot, int(rgb.shape[1]), int(rgb.shape[0]), tilt, head_yaw)])
        self.error = None


def fresh(objects: list[dict[str, Any]], at: float, max_age: float = 0.8) -> list[dict[str, Any]]:
    return list(objects) if objects and time.monotonic() - at < max_age else []
