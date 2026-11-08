"""Die Augen der Ente: ein Bild holen – vom echten Roboter oder, im Simulator, aus dem Programmfenster.

* **Echter Roboter:** die Kopfkamera über mediad (siehe vision.py).
* **Simulator:** Das Programmfenster am PC liefert das Bild – wahlweise von der **PC-Webcam** (die Ente „sieht“
  dann dich und dein Zimmer) oder das gerenderte Bild ihrer Kopfkamera im Simulator.

Bilder bleiben im Arbeitsspeicher (höchstens das letzte, wenige Sekunden lang) und werden nie gespeichert.
Was an Claude geht, entscheidet allein das Werkzeug „ansehen“ – und nur, wenn „Sehen“ im Alltag an ist.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import struct
import time
import zlib
from typing import Any

log = logging.getLogger(__name__)

FRESH_S = 3.0              # so alt darf ein Bild aus dem Fenster höchstens sein
MAX_BYTES = 4 * 1024 * 1024


def png_from_rgb(rgb) -> bytes:
    """Kleiner PNG-Schreiber (ohne Pillow) für numpy-Bilder H × W × 3, uint8."""
    import numpy as np

    a = np.ascontiguousarray(rgb, dtype=np.uint8)
    h, w = a.shape[:2]
    raw = np.empty((h, 1 + w * 3), np.uint8)
    raw[:, 0] = 0
    raw[:, 1:] = a.reshape(h, w * 3)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw.tobytes(), 6)) + chunk(b"IEND", b""))


def sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class Eyes:
    def __init__(self, rt) -> None:
        self.rt = rt
        self.last: tuple[float, bytes, str, str] | None = None     # Zeit, Daten, Typ, Quelle
        self._waiters: list[asyncio.Future] = []

    # Bild aus dem Programmfenster (Webcam oder Simulator-Kopfkamera)
    def receive(self, data: bytes, quelle: str) -> None:
        if len(data) > MAX_BYTES:
            raise ValueError("Bild zu groß")
        kind = sniff(data)
        if kind not in ("image/jpeg", "image/png"):
            raise ValueError("Nur JPEG oder PNG")
        self.last = (time.monotonic(), data, kind, "webcam" if quelle == "webcam" else "simulator")
        for f in self._waiters:
            if not f.done():
                f.set_result(True)
        self._waiters.clear()

    def fresh(self) -> tuple[bytes, str, str] | None:
        if self.last and time.monotonic() - self.last[0] < FRESH_S:
            return self.last[1], self.last[2], self.last[3]
        return None

    async def image(self, timeout: float = 4.0) -> tuple[bytes, str, str]:
        """(Daten, MIME-Typ, Quelle) – Roboterkamera, sonst ein frisches Bild aus dem Programmfenster."""
        rt = self.rt
        addr = rt.camera_address() if hasattr(rt, "camera_address") else None
        if rt.config.backend == "robotd" and addr:
            rt.camera.address = addr
            await rt.camera.picture()
            rgb = rt.camera.last_rgb if getattr(rt.camera, "last_rgb", None) is not None else None
            if rgb is None:
                raise RuntimeError("Kamera liefert kein Bild")
            return await asyncio.to_thread(png_from_rgb, rgb), "image/png", "roboter"
        got = self.fresh()
        if got:
            return got
        if not any(getattr(ws, "fern_geraet", None) is None for ws in rt.clients):
            raise RuntimeError("Im Simulator liefert das Programmfenster am PC das Bild – es ist gerade nicht offen.")
        fut = asyncio.get_running_loop().create_future()
        self._waiters.append(fut)
        await rt.broadcast_local({"type": "augen_bitte", "quelle": rt.alltag.planner.data.get("augen", "simulator")})
        try:
            await asyncio.wait_for(fut, timeout)
        except TimeoutError:
            raise RuntimeError("Kein Bild bekommen – ist die Webcam freigegeben?") from None
        got = self.fresh()
        if not got:
            raise RuntimeError("Kein Bild bekommen")
        return got

    @staticmethod
    def for_claude(data: bytes, kind: str) -> dict[str, Any]:
        return {"media_type": kind, "data": base64.b64encode(data).decode("ascii")}
