"""Farbe und Linie im Kamerabild (seit 0.55) – für „Farbe folgen“ und „Linie folgen“ am echten Roboter.

Wie Hiwonders Studio für die WonderDuck („Object tracking“ mit gewählter Farbe, „Line following“): Im Bild der
Kopfkamera wird die gewählte Farbe bzw. ein dunkles Klebeband gesucht und mit Kopfneigung und Kamerahöhe auf den Boden
umgerechnet (`laser.to_floor`). So liefert der echte Roboter dieselben Dinge wie der Simulator, und dieselben
Verhalten (`motion/aufgaben.py`) laufen hier wie dort.

Gerechnet wird auf diesem PC, nur solange eines der beiden Verhalten läuft; kein Bild wird gespeichert. Die Schwellen
sind Schätzungen und am echten Roboter nachzustellen (nicht geprüft).
"""

from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING, Any

from .laser import to_floor

if TYPE_CHECKING:  # pragma: no cover
    from .server.app import Runtime

# Farben zum Folgen: Name → (Farbton von, bis in Grad, Anzeige). Rot liegt um 0°, deshalb zwei Bereiche.
FARBZIELE: dict[str, tuple[tuple[tuple[float, float], ...], str]] = {
    "rot": (((345.0, 360.0), (0.0, 15.0)), "#d93a32"),
    "gelb": (((40.0, 65.0),), "#f2c230"),
    "gruen": (((80.0, 160.0),), "#3c9a4b"),
    "blau": (((195.0, 250.0),), "#3a78d0"),
}
FARBNAME = {"rot": "Rot", "gelb": "Gelb", "gruen": "Grün", "blau": "Blau"}
MIN_SAETTIGUNG, MIN_HELL = 0.45, 0.25
MIN_FLAECHE = 0.002          # kleiner als 0,2 % des Bildes: Rauschen
LINIE_DUNKEL = 0.25          # Helligkeit, unter der ein Bildpunkt zum Klebeband zählt
LINIE_BAENDER = (0.62, 0.78, 0.94)   # Höhen im Bild (Anteil), in denen nach der Linie gesucht wird


def farbname(hexfarbe: str) -> str | None:
    """Welche der Zielfarben ist das (für die Dinge im Simulator)? `None`, wenn keine passt (Weiß, Schwarz, Grau)."""
    try:
        r, g, b = (int(hexfarbe.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, AttributeError):
        return None
    hoch, tief = max(r, g, b), min(r, g, b)
    if hoch < MIN_HELL or hoch == 0 or (hoch - tief) / hoch < MIN_SAETTIGUNG:
        return None
    if hoch == r:
        h = (60 * ((g - b) / (hoch - tief))) % 360
    elif hoch == g:
        h = 60 * ((b - r) / (hoch - tief)) + 120
    else:
        h = 60 * ((r - g) / (hoch - tief)) + 240
    return next((n for n, (bereiche, _) in FARBZIELE.items() if any(a <= h <= z for a, z in bereiche)), None)


def _hsv(rgb):
    import numpy as np

    f = rgb.astype(np.float32) / 255.0
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    hoch, tief = f.max(axis=-1), f.min(axis=-1)
    d = np.where(hoch - tief < 1e-6, 1e-6, hoch - tief)
    h = np.where(hoch == r, (60 * (g - b) / d) % 360, np.where(hoch == g, 60 * (b - r) / d + 120, 60 * (r - g) / d + 240))
    s = np.where(hoch > 0, (hoch - tief) / np.maximum(hoch, 1e-6), 0)
    return h, s, hoch


def detect_farbe(rgb, farbe: str) -> dict[str, Any] | None:
    """Größter Fleck der Farbe im Bild → {"x", "y" (Pixel, Mitte unten), "flaeche"} oder None."""
    import numpy as np

    if farbe not in FARBZIELE:
        return None
    h, s, v = _hsv(rgb)
    maske = (s >= MIN_SAETTIGUNG) & (v >= MIN_HELL)
    ton = np.zeros_like(maske)
    for a, z in FARBZIELE[farbe][0]:
        ton |= (h >= a) & (h <= z)
    maske &= ton
    anteil = float(maske.mean())
    if anteil < MIN_FLAECHE:
        return None
    ys, xs = np.nonzero(maske)
    return {"x": float(np.median(xs)), "y": float(np.percentile(ys, 90)), "flaeche": round(anteil, 4)}


def detect_linie(rgb) -> list[dict[str, float]]:
    """Dunkles Klebeband in den unteren Bildbändern → je Band die Mitte {"x", "y"} (Pixel), von unten nach oben."""
    import numpy as np

    hgt, wid, _ = rgb.shape
    _, s, v = _hsv(rgb)
    dunkel = (v < LINIE_DUNKEL) & (s < 0.5)
    out = []
    for anteil in sorted(LINIE_BAENDER, reverse=True):
        y = min(hgt - 1, int(anteil * hgt))
        zeile = dunkel[max(0, y - 2):y + 3].any(axis=0)
        xs = np.nonzero(zeile)[0]
        if 0 < len(xs) < 0.5 * wid:                 # mehr als die halbe Breite dunkel: Schatten, kein Band
            out.append({"x": float(xs.mean()), "y": float(y)})
    return out


def linie_auf_boden(mitten: list[dict[str, float]], wid: int, hgt: int, tilt: float, head_yaw: float
                    ) -> dict[str, Any] | None:
    """Mitten der Linie im Bild → Ding „Linie“ wie im Simulator (Versatz voraus, Winkel)."""
    if len(mitten) < 2:
        return None
    boden = []
    for m in mitten:
        p = to_floor(m, wid, hgt, tilt, head_yaw)
        a = math.radians(p["richtung_grad"])
        boden.append((p["entfernung_m"] * math.cos(a), p["entfernung_m"] * math.sin(a)))
    (x0, y0), (x1, y1) = boden[0], boden[-1]
    if math.hypot(x1 - x0, y1 - y0) < 0.02:
        return None
    winkel = math.atan2(y1 - y0, x1 - x0)
    mx, my = boden[len(boden) // 2]
    return {"name": "Linie", "art": "linie", "versatz_m": round(my, 3), "winkel_grad": round(math.degrees(winkel)),
            "entfernung_m": round(mx, 2), "richtung_grad": round(math.degrees(math.atan2(my, max(mx, 0.01)))),
            "quelle": "kamera"}


class AufgabenSicht:
    """Schaut am echten Roboter ein paar Mal pro Sekunde nach Farbe oder Linie – nur solange eines davon läuft."""

    PERIOD = 0.2

    def __init__(self) -> None:
        self.error: str | None = None

    @staticmethod
    def was(rt: "Runtime") -> tuple[str, str | None] | None:
        from .motion.aufgaben import FarbeFolgen, LinieFolgen

        cur = rt.engine.current
        if isinstance(cur, LinieFolgen):
            return ("linie", None)
        if isinstance(cur, FarbeFolgen):
            return ("farbe", cur.farbe)
        return None

    async def run(self, rt: "Runtime") -> None:
        while True:
            await asyncio.sleep(self.PERIOD)
            try:
                await self.once(rt)
            except asyncio.CancelledError:
                raise
            except Exception as exc:              # Kamera mal weg: weiter versuchen
                self.error = f"{type(exc).__name__}: {exc}"

    async def once(self, rt: "Runtime") -> None:
        backend = rt.backend
        see = getattr(backend, "see_objects", None)
        was = self.was(rt)
        if see is None or was is None:
            return
        addr = rt.camera_address()
        if not addr:
            return
        rt.camera.address = addr
        await rt.camera.picture()
        rgb = rt.camera.last_rgb
        if rgb is None:
            return
        wid, hgt = int(rgb.shape[1]), int(rgb.shape[0])
        tilt, head_yaw = backend.gaze()
        if was[0] == "linie":
            mitten = await asyncio.to_thread(detect_linie, rgb)
            ding = linie_auf_boden(mitten, wid, hgt, tilt, head_yaw)
        else:
            fleck = await asyncio.to_thread(detect_farbe, rgb, was[1] or "")
            ding = None if fleck is None else {**to_floor(fleck, wid, hgt, tilt, head_yaw), "name": FARBNAME[was[1]],
                                               "art": "farbziel", "farbe": was[1]}
        see([ding] if ding else [])
        self.error = None
