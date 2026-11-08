"""Kamera und Enten-Erkenner am echten Roboter.

* **Kamera:** `mediad` gibt auf seinem lokalen Socket ein einzelnes Bild heraus (`media.frame`:
  eine JSON-Zeile mit Größe, Format und Drehung, danach die Rohdaten im Format UYVY). Über den
  SSH-Tunnel (`-L 7903:/run/mediad/media.sock`) holt duckpilot so ein paar Bilder pro Sekunde und
  zeigt sie im Entenblick.
* **Enten-Erkenner:** Pollens YOLO-Modell (`pollen-robotics/microduck-duck-detector`,
  `duck_detect.onnx`, eine Klasse, 320 × 320) läuft hier auf dem PC – vorbereitet wie in
  Pollens `duck-detect`: aufrecht gedreht, RGB, auf ein Quadrat eingepasst mit Grau 114,
  Werte 0…1; Ausgabe [1, 5, N] (cx, cy, w, h, Wert) mit Überlappungsfilter.

Farbumrechnung BT.601 (begrenzter Bereich) wie Pollens `uyvy`-Crate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DETECTOR_REPO = "pollen-robotics/microduck-duck-detector"
DETECTOR_FILE = "duck_detect.onnx"
PAD = 114
MAX_FRAME = 16 * 1024 * 1024
HFOV_DEG = 70.0          # grob: Blickwinkel der Kopfkamera für die Richtung einer erkannten Ente


def _np():
    import numpy as np

    return np


def uyvy_to_rgb(data: bytes, width: int, height: int, rotate: int = 0, max_side: int = 640):
    """UYVY → aufrechtes RGB (H, W, 3), dabei auf höchstens `max_side` verkleinert (jeder n-te Punkt)."""
    np = _np()
    if width % 2 or len(data) < width * height * 2:
        raise ValueError("kaputtes UYVY-Bild")
    raw = np.frombuffer(data[: width * height * 2], np.uint8).reshape(height, width // 2, 4).astype(np.int32)
    step = max(1, int(np.ceil(max(width, height) / max_side)))
    if step % 2:
        step = step + 1 if step > 1 else 1
    u, y0, v, y1 = raw[..., 0] - 128, raw[..., 1] - 16, raw[..., 2] - 128, raw[..., 3] - 16
    y = np.stack([y0, y1], axis=-1).reshape(height, width)
    u = np.repeat(u, 2, axis=1)
    v = np.repeat(v, 2, axis=1)
    if step > 1:
        y, u, v = y[::step, ::step], u[::step, ::step], v[::step, ::step]
    r = (298 * y + 409 * v + 128) >> 8
    g = (298 * y - 100 * u - 208 * v + 128) >> 8
    b = (298 * y + 516 * u + 128) >> 8
    rgb = np.clip(np.stack([r, g, b], axis=-1), 0, 255).astype(np.uint8)
    turns = {0: 0, 90: 3, 180: 2, 270: 1}.get(int(rotate) % 360, 0)   # im Uhrzeigersinn drehen
    return np.ascontiguousarray(np.rot90(rgb, turns)) if turns else rgb


def to_bmp(rgb) -> bytes:
    """RGB-Bild als 24-Bit-BMP – kann jeder Browser, braucht keine Bildbibliothek."""
    np = _np()
    h, w, _ = rgb.shape
    row = (w * 3 + 3) & ~3
    body = np.zeros((h, row), np.uint8)
    body[:, : w * 3] = rgb[::-1, :, ::-1].reshape(h, w * 3)
    size = 54 + body.size
    head = b"BM" + struct.pack("<IHHI", size, 0, 0, 54) + struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, body.size,
                                                                      2835, 2835, 0, 0)
    return head + body.tobytes()


async def fetch_frame(address: str, timeout: float = 3.0) -> tuple[dict[str, Any], bytes]:
    """Ein Bild von mediad (eine Verbindung pro Bild, so will es mediad)."""
    from .backends.robotd import open_line_stream

    reader, writer = await asyncio.wait_for(open_line_stream(address), timeout)
    try:
        writer.write(b'{"jsonrpc":"2.0","id":1,"method":"media.frame","params":{}}\n')
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout)
        msg = json.loads(line)
        if msg.get("error"):
            raise RuntimeError(msg["error"].get("message", "mediad lehnt ab"))
        head = msg.get("result") or {}
        n = int(head.get("bytes") or 0)
        if head.get("format") != "UYVY" or not 0 < n <= MAX_FRAME:
            raise RuntimeError(f"unerwartetes Bild: {head.get('format')} {n} Bytes")
        data = await asyncio.wait_for(reader.readexactly(n), timeout)
        return head, data
    finally:
        writer.close()


class DuckDetector:
    def __init__(self, path: str | Path, threshold: float = 0.5, iou: float = 0.45) -> None:
        import onnxruntime as ort

        self.session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        inp = self.session.get_inputs()[0]
        shape = inp.shape
        if len(shape) != 4 or shape[1] != 3:
            raise ValueError(f"erwartet [1, 3, H, W], bekommen {shape}")
        self.size = int(shape[2]) if isinstance(shape[2], int) else 320
        self.input = inp.name
        self.threshold = threshold
        self.iou = iou

    def letterbox(self, rgb):
        np = _np()
        h, w, _ = rgb.shape
        s = self.size
        scale = min(s / w, s / h)
        fw, fh = max(1, min(s, round(w * scale))), max(1, min(s, round(h * scale)))
        px, py = (s - fw) // 2, (s - fh) // 2
        ys = (np.arange(fh) * h) // fh
        xs = (np.arange(fw) * w) // fw
        out = np.full((s, s, 3), PAD, np.uint8)
        out[py:py + fh, px:px + fw] = rgb[ys][:, xs]
        return out, scale, px, py

    def detect(self, rgb) -> list[dict[str, Any]]:
        np = _np()
        box, scale, px, py = self.letterbox(rgb)
        x = (box.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        raw = np.asarray(self.session.run(None, {self.input: x})[0], np.float32).reshape(5, -1)
        keep = raw[4] >= self.threshold
        cand = raw[:, keep]
        found = []
        for cx, cy, bw, bh, score in cand.T:
            found.append((float(score), [(cx - bw / 2 - px) / scale, (cy - bh / 2 - py) / scale,
                                         (cx + bw / 2 - px) / scale, (cy + bh / 2 - py) / scale]))
        found.sort(key=lambda f: -f[0])
        kept: list[tuple[float, list[float]]] = []
        for score, b in found:
            if all(_iou(b, k[1]) < self.iou for k in kept):
                kept.append((score, b))
        w = rgb.shape[1]
        return [{"wert": round(s, 3), "box": [round(v, 1) for v in b],
                 "richtung_grad": round(-((b[0] + b[2]) / 2 / w * 2 - 1) * HFOV_DEG / 2),
                 "groesse": round((b[3] - b[1]) / rgb.shape[0], 3)} for s, b in kept]


def _iou(a: list[float], b: list[float]) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    area = lambda r: max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])
    union = area(a) + area(b) - inter
    return inter / union if union > 0 else 0.0


class Camera:
    """Holt Bilder von mediad (höchstens ~5/s), merkt sich das letzte und die Erkennungen."""

    def __init__(self, address: str | None, root: Path) -> None:
        self.address = address
        self.root = root / "erkenner"
        self.detector: DuckDetector | None = None
        self.detect_on = False
        self.last: tuple[float, bytes, dict[str, Any]] | None = None
        self.error: str | None = None
        self.last_rgb = None
        self._lock = asyncio.Lock()

    def model_path(self) -> Path:
        return self.root / DETECTOR_FILE

    def ensure_detector(self) -> DuckDetector:
        if self.detector is None:
            path = self.model_path()
            if not path.exists():
                from . import hub

                path.parent.mkdir(parents=True, exist_ok=True)
                data = hub._get(f"{hub.HUB}/{DETECTOR_REPO}/resolve/main/{DETECTOR_FILE}", timeout=120)
                path.write_bytes(data)
            self.detector = DuckDetector(path)
        return self.detector

    async def picture(self) -> tuple[bytes, dict[str, Any]]:
        if not self.address:
            raise RuntimeError("Keine Kamera-Adresse – Einstellungen → Körper (Tunnel -L 7903:/run/mediad/media.sock)")
        async with self._lock:
            if self.last and time.monotonic() - self.last[0] < 0.18:
                return self.last[1], self.last[2]
            try:
                head, data = await fetch_frame(self.address)
            except Exception as exc:
                self.error = f"{type(exc).__name__}: {exc}"
                raise
            rgb = await asyncio.to_thread(uyvy_to_rgb, data, int(head["width"]), int(head["height"]),
                                          int(head.get("rotate") or 0))
            info: dict[str, Any] = {"breite": int(rgb.shape[1]), "hoehe": int(rgb.shape[0]), "enten": None}
            if self.detect_on:
                try:
                    det = await asyncio.to_thread(self.ensure_detector)
                    info["enten"] = await asyncio.to_thread(det.detect, rgb)
                except Exception as exc:
                    info["fehler_erkenner"] = f"{type(exc).__name__}: {exc}"
            bmp = await asyncio.to_thread(to_bmp, rgb)
            self.last_rgb = rgb                      # für „ansehen“ (Claude) und das Wiedererkennen
            self.error = None
            self.last = (time.monotonic(), bmp, info)
            return bmp, info
