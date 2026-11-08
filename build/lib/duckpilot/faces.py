"""Gesichter wiedererkennen – nur angelernte Personen, nur auf diesem PC.

Damit die Ente Menschen mit Namen begrüßen kann, die der Nutzer **ausdrücklich angelernt** hat.
Gesichtsmerkmale sind biometrische Daten (DSGVO Art. 9), deshalb gilt hier:

* **Alles bleibt auf dem PC.** Bilder und Merkmale verlassen nie den Rechner; aus dem Netz kommen
  nur die beiden Modelldateien (einmalig, mit Prüfsumme, sie werden nur als ONNX gelesen, nie ausgeführt).
* **Nur mit Einverständnis.** `enroll()` verlangt `einverstanden=True` und merkt sich das Datum.
* **Keine Bilder.** Gespeichert werden je Person nur Merkmalsvektoren (128 Zahlen je Bild, höchstens 10).
* **Unbekannte bleiben unbekannt.** Für fremde Gesichter gibt es nur das Ergebnis „unbekannt“ –
  nichts davon wird gespeichert oder geloggt.
* **Löschen jederzeit.** `delete(name)` entfernt eine Person, `delete_all()` die ganze Datei.

Gespeichert wird in `<Datenordner>/personen.json`, die Modelle liegen in `<Datenordner>/modelle`.

Modelle aus dem OpenCV Zoo (laufen mit onnxruntime + numpy, ohne OpenCV):

* **YuNet** (`face_detection_yunet_2023mar.onnx`, MIT-Lizenz, Shiqi Yu): findet Gesichter mit
  Rahmen und 5 Punkten (Augen, Nase, Mundwinkel). Feste Eingabe 640 × 640, BGR, Werte 0…255;
  Ausgabe je Raster 8/16/32: Klassen- und Objektwert, Rahmen (Versatz + log. Größe), 5 Punkte.
* **SFace** (`face_recognition_sface_2021dec.onnx`, Apache-2.0, Yaoyao Zhong): macht aus einem
  ausgerichteten 112 × 112-Gesicht (RGB, Werte 0…255) 128 Merkmale. Ausgerichtet wird wie bei
  OpenCVs `FaceRecognizerSF.alignCrop`: Ähnlichkeitstransformation (Umeyama) der 5 Punkte auf die
  ArcFace-Vorlage, dann bilinear umgerechnet.

Vergleich per Kosinus-Ähnlichkeit. OpenCV empfiehlt für SFace die Schwelle 0,363 (siehe `sface.py`
im Zoo: `_threshold_cosine = 0.363`); zusätzlich muss die beste Person um `ABSTAND` vor der
zweitbesten liegen, sonst heißt es lieber „unbekannt“ als einen falschen Namen zu sagen.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import threading
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

# ── Modelle ──────────────────────────────────────────────────────────────────
ZOO_COMMIT = "48b10fa505aeb51fbd127fc60a5c660040e823b7"   # opencv/opencv_zoo, Stand Oktober 2026
_MEDIA = "https://media.githubusercontent.com/media/opencv/opencv_zoo"

MODELLE: dict[str, dict[str, Any]] = {
    "detektor": {
        "datei": "face_detection_yunet_2023mar.onnx",
        "urls": [
            f"{_MEDIA}/{ZOO_COMMIT}/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
            f"{_MEDIA}/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        ],
        "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "bytes": 232_589,
        "lizenz": "MIT (Shiqi Yu, libfacedetection)",
    },
    "erkenner": {
        "datei": "face_recognition_sface_2021dec.onnx",
        "urls": [
            f"{_MEDIA}/{ZOO_COMMIT}/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
            f"{_MEDIA}/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        ],
        "sha256": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
        "bytes": 38_696_353,
        "lizenz": "Apache-2.0 (Yaoyao Zhong, SFace)",
    },
}
MAX_DOWNLOAD = 64 * 1024 * 1024

# ── Erkennung ────────────────────────────────────────────────────────────────
DET_SIZE = 640                 # YuNet 2023mar hat eine feste Eingabe 640 × 640
STRIDES = (8, 16, 32)
SCORE_MIN = 0.8                # ab hier zählt etwas als Gesicht
SCORE_KLAR = 0.9               # „deutlich erkannt“ – so viel braucht ein Bild zum Anlernen
NMS_IOU = 0.3
TOP_K = 5000

SCHWELLE = 0.363               # OpenCVs Kosinus-Schwelle für SFace
ABSTAND = 0.05                 # so weit muss die beste Person vor der zweitbesten liegen
UNBEKANNT = "unbekannt"

MIN_BILDER = 3
MAX_PROBEN = 10
MIN_GESICHT_PX = 48            # kleinere Gesichter taugen nicht zum Anlernen
MAX_NAME = 40

# ArcFace-Vorlage der 5 Punkte im 112 × 112-Bild (wie OpenCVs alignCrop)
VORLAGE = (
    (38.2946, 51.6963),        # rechtes Auge der Person (im Bild links)
    (73.5318, 51.5014),        # linkes Auge
    (56.0252, 71.7366),        # Nasenspitze
    (41.5493, 92.3655),        # rechter Mundwinkel
    (70.7299, 92.2041),        # linker Mundwinkel
)
ALIGN_SIZE = 112


class FacesError(RuntimeError):
    pass


def _np():
    import numpy as np

    return np


def _missing_modules() -> list[str]:
    fehlt = []
    for mod, label in (("numpy", "numpy"), ("onnxruntime", "onnxruntime"), ("PIL", "Pillow")):
        try:
            __import__(mod)
        except Exception:
            fehlt.append(label)
    return fehlt


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Bildmathematik (reines numpy, ohne OpenCV) ───────────────────────────────
def nms(boxes, scores, iou: float = NMS_IOU, top_k: int = TOP_K) -> list[int]:
    """Gierige Überlappungsunterdrückung. boxes: (N, 4) als x, y, w, h. Gibt die behaltenen Indizes zurück."""
    np = _np()
    boxes = np.asarray(boxes, np.float64).reshape(-1, 4)
    scores = np.asarray(scores, np.float64).reshape(-1)
    if not len(boxes):
        return []
    order = np.argsort(-scores, kind="stable")[:top_k]
    x1, y1 = boxes[:, 0], boxes[:, 1]
    x2, y2 = x1 + boxes[:, 2], y1 + boxes[:, 3]
    area = np.maximum(boxes[:, 2], 0) * np.maximum(boxes[:, 3], 0)
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        rest = order[1:]
        w = np.maximum(0.0, np.minimum(x2[i], x2[rest]) - np.maximum(x1[i], x1[rest]))
        h = np.maximum(0.0, np.minimum(y2[i], y2[rest]) - np.maximum(y1[i], y1[rest]))
        inter = w * h
        union = area[i] + area[rest] - inter
        overlap = np.where(union > 0, inter / np.maximum(union, 1e-12), 0.0)
        order = rest[overlap <= iou]
    return keep


def umeyama(src, dst):
    """Ähnlichkeitstransformation (Drehung, gleichmäßige Skalierung, Verschiebung), die `src` bestmöglich
    auf `dst` abbildet (Umeyama 1991, ohne Spiegelung). Gibt eine 2 × 3-Matrix zurück."""
    np = _np()
    src = np.asarray(src, np.float64)
    dst = np.asarray(dst, np.float64)
    n, m = src.shape
    mu_s, mu_d = src.mean(axis=0), dst.mean(axis=0)
    s0, d0 = src - mu_s, dst - mu_d
    var_s = (s0 ** 2).sum() / n
    if var_s < 1e-12:
        raise FacesError("Die Gesichtspunkte liegen aufeinander")
    cov = d0.T @ s0 / n
    u, s, vt = np.linalg.svd(cov)
    d = np.ones(m)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        d[-1] = -1.0
    rot = u @ np.diag(d) @ vt
    scale = float((s * d).sum() / var_s)
    t = mu_d - scale * rot @ mu_s
    return np.hstack([scale * rot, t[:, None]])


def invert_affine(mat):
    np = _np()
    mat = np.asarray(mat, np.float64)
    a_inv = np.linalg.inv(mat[:, :2])
    return np.hstack([a_inv, (-a_inv @ mat[:, 2])[:, None]])


def warp_affine(img, mat, size: tuple[int, int]):
    """Wie cv2.warpAffine (bilinear, Rand schwarz): out(x, y) = img(M⁻¹ · (x, y, 1)). img: (H, W, C)."""
    np = _np()
    out_w, out_h = size
    h, w = img.shape[:2]
    inv = invert_affine(mat)
    ys, xs = np.mgrid[0:out_h, 0:out_w].astype(np.float64)
    sx = inv[0, 0] * xs + inv[0, 1] * ys + inv[0, 2]
    sy = inv[1, 0] * xs + inv[1, 1] * ys + inv[1, 2]
    x0, y0 = np.floor(sx).astype(np.int64), np.floor(sy).astype(np.int64)
    fx, fy = (sx - x0)[..., None], (sy - y0)[..., None]
    src = img.astype(np.float32).reshape(h, w, -1)
    out = np.zeros((out_h, out_w, src.shape[2]), np.float64)
    for dy, dx, wgt in ((0, 0, (1 - fx) * (1 - fy)), (0, 1, fx * (1 - fy)), (1, 0, (1 - fx) * fy), (1, 1, fx * fy)):
        yy, xx = y0 + dy, x0 + dx
        ok = ((yy >= 0) & (yy < h) & (xx >= 0) & (xx < w))[..., None]
        px = src[np.clip(yy, 0, h - 1), np.clip(xx, 0, w - 1)]
        out += np.where(ok, px, 0.0) * wgt
    return out.astype(np.float32).reshape((out_h, out_w) + img.shape[2:])


def align_face(rgb, landmarks):
    """Gesicht anhand der 5 Punkte auf 112 × 112 ausrichten (wie OpenCVs alignCrop)."""
    np = _np()
    mat = umeyama(np.asarray(landmarks, np.float64).reshape(5, 2), np.asarray(VORLAGE, np.float64))
    return warp_affine(rgb, mat, (ALIGN_SIZE, ALIGN_SIZE))


def decode_yunet(outputs: dict[str, Any], size: int = DET_SIZE, score_min: float = SCORE_MIN):
    """Rohausgabe von YuNet 2023mar → (boxes x,y,w,h; landmarks (N,5,2); scores) im Netzbild, vor NMS."""
    np = _np()
    boxes, kps, scores = [], [], []
    for s in STRIDES:
        cols = size // s
        cls = np.clip(np.asarray(outputs[f"cls_{s}"], np.float32).reshape(-1), 0, 1)
        obj = np.clip(np.asarray(outputs[f"obj_{s}"], np.float32).reshape(-1), 0, 1)
        score = np.sqrt(cls * obj)
        sel = np.nonzero(score >= score_min)[0]
        if not sel.size:
            continue
        bb = np.asarray(outputs[f"bbox_{s}"], np.float32).reshape(-1, 4)[sel]
        kp = np.asarray(outputs[f"kps_{s}"], np.float32).reshape(-1, 5, 2)[sel]
        c, r = (sel % cols).astype(np.float32), (sel // cols).astype(np.float32)
        cx, cy = (c + bb[:, 0]) * s, (r + bb[:, 1]) * s
        bw, bh = np.exp(bb[:, 2]) * s, np.exp(bb[:, 3]) * s
        boxes.append(np.stack([cx - bw / 2, cy - bh / 2, bw, bh], axis=1))
        kps.append(np.stack([(kp[..., 0] + c[:, None]) * s, (kp[..., 1] + r[:, None]) * s], axis=-1))
        scores.append(score[sel])
    if not boxes:
        return np.zeros((0, 4), np.float32), np.zeros((0, 5, 2), np.float32), np.zeros(0, np.float32)
    return np.concatenate(boxes), np.concatenate(kps), np.concatenate(scores)


def cosine(a, b) -> float:
    np = _np()
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    return float(a @ b / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-12))


def _to_rgb(image):
    """bytes (JPEG/PNG/BMP …), PIL-Bild oder numpy-Array (H, W, 3, RGB) → uint8-Array (H, W, 3)."""
    np = _np()
    if isinstance(image, np.ndarray):
        arr = image
        if arr.ndim == 2:
            arr = np.repeat(arr[..., None], 3, axis=2)
        if arr.ndim != 3 or arr.shape[2] < 3:
            raise FacesError("Bild hat kein RGB-Format")
        return np.ascontiguousarray(arr[..., :3].astype(np.uint8, copy=False))
    from PIL import Image, ImageOps

    if isinstance(image, (bytes, bytearray, memoryview)):
        try:
            img = Image.open(io.BytesIO(bytes(image)))
            img.load()
        except Exception as e:
            raise FacesError("Bild lässt sich nicht lesen") from e
    elif isinstance(image, Image.Image):
        img = image
    else:
        raise FacesError("Unbekanntes Bildformat")
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    return np.asarray(img.convert("RGB"), np.uint8)


def _resize(rgb, width: int, height: int):
    np = _np()
    from PIL import Image

    if rgb.shape[1] == width and rgb.shape[0] == height:
        return rgb
    return np.asarray(Image.fromarray(rgb).resize((width, height), Image.BILINEAR), np.uint8)


# ── Speicher ─────────────────────────────────────────────────────────────────
def _clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not name:
        raise FacesError("Bitte einen Namen angeben.")
    if len(name) > MAX_NAME:
        raise FacesError(f"Der Name ist zu lang (höchstens {MAX_NAME} Zeichen).")
    if any(ord(ch) < 32 for ch in name):
        raise FacesError("Der Name enthält ungültige Zeichen.")
    return name


class Faces:
    """Lokale Gesichtserkennung für angelernte Personen. Thread-sicher, Modelle werden erst bei Bedarf geladen."""

    def __init__(self, root: Path, schwelle: float = SCHWELLE, abstand: float = ABSTAND, threads: int = 1) -> None:
        self.root = Path(root)
        self.models_dir = self.root / "modelle"
        self.path = self.root / "personen.json"
        self.schwelle = float(schwelle)
        self.abstand = float(abstand)
        self.threads = max(1, int(threads))
        self._model_lock = threading.Lock()
        self._store_lock = threading.RLock()
        self._det = None
        self._rec = None
        self._cache: list[dict[str, Any]] | None = None
        self._cache_stamp: tuple[int, int] | None = None

    # ── Modelle ──
    def model_path(self, key: str) -> Path:
        return self.models_dir / MODELLE[key]["datei"]

    def models_present(self) -> bool:
        return all(self.model_path(k).is_file() and self.model_path(k).stat().st_size == m["bytes"]
                   for k, m in MODELLE.items())

    def available(self) -> tuple[bool, str]:
        fehlt = _missing_modules()
        if fehlt:
            return False, f"Für die Gesichtserkennung fehlt noch: {', '.join(fehlt)}."
        if not self.models_present():
            mb = sum(m["bytes"] for m in MODELLE.values()) / 1e6
            return False, f"Die Gesichtsmodelle sind noch nicht geladen (einmalig ca. {mb:.0f} MB aus dem OpenCV Zoo)."
        return True, "Gesichtserkennung bereit – läuft nur auf diesem PC."

    def ensure_models(self, progress_cb: Callable[[float], None] | None = None) -> list[Path]:
        """Fehlende Modelle laden und per SHA-256 prüfen. progress_cb bekommt den Anteil 0…1 über beide Dateien."""
        self.models_dir.mkdir(parents=True, exist_ok=True)
        total = sum(m["bytes"] for m in MODELLE.values())
        done = 0
        paths = []
        for key, m in MODELLE.items():
            dest = self.model_path(key)
            if not (dest.is_file() and dest.stat().st_size == m["bytes"] and _sha256(dest) == m["sha256"]):
                base = done
                self._download(m, dest, (lambda n, b=base: progress_cb((b + n) / total)) if progress_cb else None)
            done += m["bytes"]
            if progress_cb:
                progress_cb(done / total)
            paths.append(dest)
        return paths

    def _download(self, m: dict[str, Any], dest: Path, progress: Callable[[int], None] | None) -> None:
        tmp = dest.with_suffix(dest.suffix + ".teil")
        fehler = ""
        for url in m["urls"]:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "duckpilot"})
                h = hashlib.sha256()
                n = 0
                with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(1 << 16)
                        if not chunk:
                            break
                        n += len(chunk)
                        if n > MAX_DOWNLOAD:
                            raise FacesError("Download ist größer als erwartet")
                        h.update(chunk)
                        f.write(chunk)
                        if progress:
                            progress(n)
                if h.hexdigest() != m["sha256"]:
                    raise FacesError("Prüfsumme stimmt nicht")
                tmp.replace(dest)
                log.info("Gesichtsmodell geladen: %s", m["datei"])
                return
            except Exception as e:
                fehler = str(e)
                log.warning("Gesichtsmodell %s von %s: %s", m["datei"], url, e)
            finally:
                tmp.unlink(missing_ok=True)
        raise FacesError(f"{m['datei']} ließ sich nicht laden ({fehler}).")

    def _sessions(self):
        if self._det is not None and self._rec is not None:
            return self._det, self._rec
        with self._model_lock:
            if self._det is None or self._rec is None:
                ok, grund = self.available()
                if not ok:
                    raise FacesError(grund)
                import onnxruntime as ort

                for key, m in MODELLE.items():
                    if _sha256(self.model_path(key)) != m["sha256"]:
                        raise FacesError(f"{m['datei']} ist beschädigt – bitte die Gesichtsmodelle neu laden.")
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = self.threads
                opts.inter_op_num_threads = 1
                opts.log_severity_level = 3          # SFace meldet sonst seitenweise harmlose Warnungen
                prov = ["CPUExecutionProvider"]
                det = ort.InferenceSession(str(self.model_path("detektor")), sess_options=opts, providers=prov)
                rec = ort.InferenceSession(str(self.model_path("erkenner")), sess_options=opts, providers=prov)
                self._det_in = det.get_inputs()[0].name
                self._det_out = [o.name for o in det.get_outputs()]
                self._rec_in = rec.get_inputs()[0].name
                self._det, self._rec = det, rec
        return self._det, self._rec

    # ── Erkennen ──
    def _detect_rgb(self, rgb, score_min: float = SCORE_MIN) -> list[dict[str, Any]]:
        np = _np()
        det, _ = self._sessions()
        h, w = rgb.shape[:2]
        base = min(DET_SIZE / w, DET_SIZE / h, 1.0)
        # YuNet kennt Gesichter von etwa 10 bis 300 Pixeln. Findet es nichts, noch einmal kleiner versuchen
        # (für Nahaufnahmen, in denen das Gesicht fast das ganze Bild füllt).
        for scale in (base, base / 2):
            sw, sh = max(1, round(w * scale)), max(1, round(h * scale))
            if min(sw, sh) < 32 and scale != base:
                break
            canvas = np.zeros((DET_SIZE, DET_SIZE, 3), np.float32)
            canvas[:sh, :sw] = _resize(rgb, sw, sh)[..., ::-1]            # RGB → BGR wie OpenCV
            blob = canvas.transpose(2, 0, 1)[None]
            outs = dict(zip(self._det_out, det.run(self._det_out, {self._det_in: blob})))
            boxes, kps, scores = decode_yunet(outs, DET_SIZE, score_min)
            if not len(scores):
                continue
            fx, fy = w / sw, h / sh
            faces = []
            for i in nms(boxes, scores):
                b = boxes[i] * np.array([fx, fy, fx, fy], np.float32)
                k = kps[i] * np.array([fx, fy], np.float32)
                faces.append({
                    "box": [int(round(v)) for v in b],
                    "landmarks": [[round(float(x), 1), round(float(y), 1)] for x, y in k],
                    "score": round(float(scores[i]), 3),
                })
            return faces
        return []

    def detect(self, image) -> list[dict[str, Any]]:
        """Gesichter finden. Je Gesicht: box [x, y, w, h], landmarks (5 Punkte: rechtes/linkes Auge, Nase,
        rechter/linker Mundwinkel aus Sicht der Person), score 0…1. Koordinaten im Originalbild."""
        return self._detect_rgb(_to_rgb(image))

    def _embed(self, rgb, landmarks):
        np = _np()
        _, rec = self._sessions()
        face = align_face(rgb, landmarks)                                   # RGB, 0…255
        blob = np.ascontiguousarray(face.transpose(2, 0, 1)[None], np.float32)
        feat = rec.run(None, {self._rec_in: blob})[0].reshape(-1).astype(np.float64)
        return feat / max(float(np.linalg.norm(feat)), 1e-12)

    def embed(self, image, face: dict[str, Any] | None = None):
        """Merkmalsvektor (128, L2-normiert) für ein Gesicht; ohne `face` für das deutlichste im Bild."""
        rgb = _to_rgb(image)
        if face is None:
            faces = self._detect_rgb(rgb)
            if not faces:
                raise FacesError("kein Gesicht")
            face = max(faces, key=lambda f: f["score"])
        return self._embed(rgb, face["landmarks"])

    def _match(self, emb, people: list[dict[str, Any]]) -> tuple[str, float]:
        np = _np()
        scores = []
        for p in people:
            embs = np.asarray(p.get("embeddings") or [], np.float64)
            if not embs.size:
                continue
            embs = embs / np.maximum(np.linalg.norm(embs, axis=1, keepdims=True), 1e-12)
            scores.append((float((embs @ emb).max()), p["name"]))
        if not scores:
            return UNBEKANNT, 0.0
        scores.sort(reverse=True)
        best, name = scores[0]
        second = scores[1][0] if len(scores) > 1 else -1.0
        if best >= self.schwelle and best - second >= self.abstand:
            return name, best
        return UNBEKANNT, best

    def who(self, image) -> list[dict[str, Any]]:
        """Wer ist im Bild? Je Gesicht: box, name (oder „unbekannt“), aehnlichkeit (Kosinus, −1…1), score.
        Fremde Gesichter werden weder gespeichert noch geloggt."""
        rgb = _to_rgb(image)
        faces = self._detect_rgb(rgb)
        people = self._load()
        out = []
        for f in faces:
            if people:
                name, sim = self._match(self._embed(rgb, f["landmarks"]), people)
            else:
                name, sim = UNBEKANNT, 0.0
            out.append({"box": f["box"], "name": name, "aehnlichkeit": round(sim, 3), "score": f["score"]})
        return out

    # ── Anlernen ──
    def enroll(self, name: str, images: list, einverstanden: bool) -> dict[str, Any]:
        """Person anlernen. Verlangt ausdrückliches Einverständnis und mindestens 3 Bilder mit je genau einem
        deutlich erkennbaren Gesicht. Gespeichert werden nur Merkmale (höchstens 10), keine Bilder."""
        if einverstanden is not True:
            return {"ok": False, "fehler": "Ohne ausdrückliches Einverständnis der Person wird niemand angelernt.",
                    "hinweise": []}
        try:
            name = _clean_name(name)
        except FacesError as e:
            return {"ok": False, "fehler": str(e), "hinweise": []}
        ok, grund = self.available()
        if not ok:
            return {"ok": False, "fehler": grund, "hinweise": []}
        images = list(images or [])
        if len(images) < MIN_BILDER:
            return {"ok": False, "fehler": f"Bitte mindestens {MIN_BILDER} Bilder aufnehmen.", "hinweise": []}

        np = _np()
        hinweise: list[str] = []
        embs: list[tuple[int, Any]] = []
        for i, image in enumerate(images, 1):
            try:
                rgb = _to_rgb(image)
                faces = self._detect_rgb(rgb, score_min=0.6)
            except FacesError as e:
                hinweise.append(f"Bild {i}: {e}.")
                continue
            if not faces:
                hinweise.append(f"Bild {i}: kein Gesicht gefunden.")
                continue
            if len(faces) > 1:
                hinweise.append(f"Bild {i}: mehrere Gesichter – bitte nur die Person allein im Bild.")
                continue
            f = faces[0]
            if f["score"] < SCORE_KLAR:
                hinweise.append(f"Bild {i}: Gesicht nicht deutlich genug (mehr Licht, gerade in die Kamera schauen).")
                continue
            if min(f["box"][2], f["box"][3]) < MIN_GESICHT_PX:
                hinweise.append(f"Bild {i}: Gesicht zu klein – bitte näher an die Kamera.")
                continue
            embs.append((i, self._embed(rgb, f["landmarks"])))
        del images

        # Passen die Bilder zueinander? (Schutz davor, versehentlich zwei Personen zu mischen)
        if len(embs) >= MIN_BILDER:
            good = []
            for k, (i, e) in enumerate(embs):
                others = np.sum([x for j, (_, x) in enumerate(embs) if j != k], axis=0)
                if cosine(e, others) >= self.schwelle:
                    good.append((i, e))
                else:
                    hinweise.append(f"Bild {i}: passt nicht zu den anderen Bildern (andere Person?).")
            embs = good
        if len(embs) < MIN_BILDER:
            return {"ok": False, "hinweise": hinweise,
                    "fehler": f"Nur {len(embs)} brauchbare Bilder – es braucht mindestens {MIN_BILDER}."}

        with self._store_lock:
            people = self._load()
            mean = np.mean([e for _, e in embs], axis=0)
            mean /= max(float(np.linalg.norm(mean)), 1e-12)
            andere = [p for p in people if p["name"].casefold() != name.casefold()]
            aehnlich, sim = self._match(mean, andere)
            if aehnlich != UNBEKANNT:
                hinweise.append(f"Achtung: sieht {aehnlich} ähnlich (Ähnlichkeit {sim:.2f}).")
            now = datetime.now().isoformat(timespec="seconds")
            person = next((p for p in people if p["name"].casefold() == name.casefold()), None)
            neu = [[round(float(v), 6) for v in e] for _, e in embs]
            if person is None:
                person = {"name": name, "angelegt": date.today().isoformat()}
                people.append(person)
                alt = []
            else:
                alt = list(person.get("embeddings") or [])
                person["name"] = name
            person["geaendert"] = now
            person["einverstanden"] = True
            person["einverstanden_am"] = now
            person["embeddings"] = (alt + neu)[-MAX_PROBEN:]
            person["proben"] = len(person["embeddings"])
            self._save(people)
        log.info("Gesicht angelernt: %d Proben", person["proben"])      # bewusst ohne Namen
        return {"ok": True, "name": name, "proben": person["proben"], "hinweise": hinweise,
                "meldung": f"{name} ist angelernt ({len(neu)} Bilder verwendet)."}

    # ── Personen verwalten ──
    def persons(self) -> list[dict[str, Any]]:
        """Angelernte Personen – ohne Merkmale."""
        return [{k: p.get(k) for k in ("name", "angelegt", "geaendert", "proben", "einverstanden",
                                       "einverstanden_am")} for p in self._load()]

    def delete(self, name: str) -> bool:
        with self._store_lock:
            people = self._load()
            key = str(name or "").strip().casefold()
            rest = [p for p in people if p["name"].casefold() != key]
            if len(rest) == len(people):
                return False
            if rest:
                self._save(rest)
            else:
                self.delete_all()
            return True

    def delete_all(self) -> int:
        with self._store_lock:
            n = len(self._load())
            for p in (self.path, self.path.with_suffix(".json.teil")):
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass
            self._cache, self._cache_stamp = [], None
            return n

    def _load(self) -> list[dict[str, Any]]:
        with self._store_lock:
            try:
                st = self.path.stat()
            except FileNotFoundError:
                self._cache, self._cache_stamp = [], None
                return []
            stamp = (st.st_mtime_ns, st.st_size)
            if self._cache is None or stamp != self._cache_stamp:
                try:
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                    people = [p for p in data.get("personen", []) if isinstance(p, dict) and p.get("name")]
                except Exception as e:
                    log.warning("personen.json lässt sich nicht lesen: %s", e)
                    people = []
                self._cache, self._cache_stamp = people, stamp
            return [dict(p) for p in self._cache]

    def _save(self, people: list[dict[str, Any]]) -> None:
        with self._store_lock:
            self.root.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 1,
                "hinweis": "Nur Gesichtsmerkmale (keine Bilder) von Personen, die eingewilligt haben. "
                           "Bleibt auf diesem PC. Löschen jederzeit in duckpilot.",
                "modell": MODELLE["erkenner"]["datei"],
                "personen": people,
            }
            tmp = self.path.with_suffix(".json.teil")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            tmp.replace(self.path)
            self._cache, self._cache_stamp = None, None

