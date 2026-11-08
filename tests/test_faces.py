"""Gesichtserkennung (duckpilot/faces.py): Mathematik, Einverständnis, Speicher, echte Gesichter.

Die Modelle (≈ 39 MB) und Testbilder werden einmal nach ~/.cache/duckpilot-test/faces geladen
(anders: DUCKPILOT_TEST_CACHE). Geht das nicht, werden die betroffenen Tests übersprungen.

Die Tests mit echten Gesichtern laufen nur mit eigenen Fotos (Einverständnis der Abgebildeten!) in einem
Ordner, den DUCKPILOT_FACE_SAMPLES angibt: person_a1.jpg und person_a2.jpg = zwei Fotos derselben Person,
person_b.jpg = eine andere Person, two_people.jpg = zwei Personen auf einem Bild. Sonst werden sie übersprungen.
"""

import hashlib
import io
import json
import math
import os
import time
import urllib.request
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from duckpilot import faces as F  # noqa: E402

CACHE = Path(os.environ.get("DUCKPILOT_TEST_CACHE") or Path.home() / ".cache" / "duckpilot-test") / "faces"
SAMPLES = os.environ.get("DUCKPILOT_FACE_SAMPLES")
BILDER = ("person_a1.jpg", "person_a2.jpg", "person_b.jpg", "two_people.jpg")
T = np.array(F.VORLAGE, np.float64)


def _rot(deg):
    a = math.radians(deg)
    return np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])


# ── Mathematik ───────────────────────────────────────────────────────────────
def test_umeyama_template_maps_to_itself():
    m = F.umeyama(T, T)
    assert np.allclose(m, [[1, 0, 0], [0, 1, 0]], atol=1e-9)


def test_umeyama_recovers_known_similarity():
    r, s, t = _rot(30), 2.5, np.array([120.0, -40.0])
    src = (s * (r @ T.T)).T + t                          # Vorlage gedreht, skaliert, verschoben
    m = F.umeyama(src, T)
    assert np.allclose(m[:, :2], r.T / s, atol=1e-9)     # die Umkehrung: zurückdrehen, verkleinern
    back = (m[:, :2] @ src.T).T + m[:, 2]
    assert np.allclose(back, T, atol=1e-9)
    # mit etwas Rauschen bleibt es die beste Näherung, und es gibt nie eine Spiegelung
    noisy = src + np.random.default_rng(1).normal(0, 0.5, src.shape)
    m2 = F.umeyama(noisy, T)
    assert np.linalg.det(m2[:, :2]) > 0
    assert np.allclose(m2[:, :2], r.T / s, atol=0.02)


def test_umeyama_rejects_degenerate_points():
    with pytest.raises(F.FacesError):
        F.umeyama(np.ones((5, 2)), T)


def test_warp_affine_identity_shift_and_rotation():
    img = np.arange(6 * 6 * 3, dtype=np.float32).reshape(6, 6, 3)
    ident = np.array([[1.0, 0, 0], [0, 1.0, 0]])
    assert np.allclose(F.warp_affine(img, ident, (6, 6)), img)
    shift = np.array([[1.0, 0, 2], [0, 1.0, 1]])          # Inhalt 2 nach rechts, 1 nach unten
    out = F.warp_affine(img, shift, (6, 6))
    assert np.allclose(out[1:, 2:], img[:-1, :-2])
    assert np.all(out[0] == 0) and np.all(out[:, :2] == 0)    # Rand schwarz wie cv2.BORDER_CONSTANT
    n = 6
    inv = np.array([[0.0, -1, n - 1], [1, 0, 0]])         # out(x, y) = img(n-1-y, x) ⇔ np.rot90
    out = F.warp_affine(img, F.invert_affine(inv), (n, n))
    assert np.allclose(out, np.rot90(img))
    half = np.array([[1.0, 0, 0.5], [0, 1.0, 0]])         # halbe Pixel: bilinear gemittelt
    out = F.warp_affine(img, half, (6, 6))
    assert np.allclose(out[:, 1:], (img[:, :-1] + img[:, 1:]) / 2)


def test_align_face_on_template_is_identity_crop():
    rng = np.random.default_rng(3)
    img = rng.integers(0, 255, (112, 112, 3)).astype(np.uint8)
    assert np.allclose(F.align_face(img, T), img, atol=1e-3)
    big = np.zeros((300, 300, 3), np.uint8)               # doppelt so groß, gedreht
    r = _rot(-20)
    pts = (2 * (r @ (T - 56).T)).T + 150
    m = F.umeyama(T, pts)                                 # Vorlage → großes Bild
    big = F.warp_affine(img, m, (300, 300)).round().astype(np.uint8)
    back = F.align_face(big, pts)
    inner = slice(20, 92)                                 # der Rand ist durch Drehen abgeschnitten
    assert np.abs(back[inner, inner] - img[inner, inner].astype(np.float32)).mean() < 40


def test_nms():
    boxes = [[0, 0, 10, 10], [1, 1, 10, 10], [50, 50, 10, 10], [0, 0, 10, 10]]
    scores = [0.8, 0.95, 0.7, 0.1]
    assert F.nms(boxes, scores, iou=0.3) == [1, 2]
    assert F.nms(boxes, scores, iou=0.99) == [1, 0, 2]      # nur die exakte Kopie fällt weg
    assert F.nms([], []) == []
    assert F.nms([[0, 0, 10, 10], [10, 0, 10, 10]], [0.5, 0.6]) == [1, 0]   # berühren sich nur


def test_decode_yunet_one_anchor():
    outs = {}
    for s in F.STRIDES:
        n = (F.DET_SIZE // s) ** 2
        outs[f"cls_{s}"] = np.zeros((1, n, 1), np.float32)
        outs[f"obj_{s}"] = np.zeros((1, n, 1), np.float32)
        outs[f"bbox_{s}"] = np.zeros((1, n, 4), np.float32)
        outs[f"kps_{s}"] = np.zeros((1, n, 10), np.float32)
    s, r, c = 16, 3, 5
    idx = r * (F.DET_SIZE // s) + c
    outs["cls_16"][0, idx, 0], outs["obj_16"][0, idx, 0] = 0.9, 1.2       # obj wird auf 1 begrenzt
    outs["bbox_16"][0, idx] = [0.5, 0.25, math.log(4), math.log(2)]
    outs["kps_16"][0, idx] = [0.1, 0.2] * 5
    boxes, kps, scores = F.decode_yunet(outs, F.DET_SIZE, 0.5)
    assert len(scores) == 1 and scores[0] == pytest.approx(math.sqrt(0.9))
    cx, cy, w, h = (c + 0.5) * s, (r + 0.25) * s, 4 * s, 2 * s
    assert boxes[0] == pytest.approx([cx - w / 2, cy - h / 2, w, h])
    assert kps[0, 0] == pytest.approx([(c + 0.1) * s, (r + 0.2) * s])
    assert len(F.decode_yunet(outs, F.DET_SIZE, 0.99)[2]) == 0


def test_match_needs_threshold_and_margin(tmp_path):
    f = F.Faces(tmp_path)
    e = np.zeros(128)
    e[0] = 1.0
    near = np.zeros(128)
    near[0], near[1] = 0.9, math.sqrt(1 - 0.81)
    far = np.zeros(128)
    far[2] = 1.0
    assert f._match(e, [{"name": "Anna", "embeddings": [e.tolist()]}]) == ("Anna", pytest.approx(1.0))
    assert f._match(far, [{"name": "Anna", "embeddings": [e.tolist()]}])[0] == F.UNBEKANNT
    # zwei Personen fast gleich ähnlich → lieber „unbekannt“ als ein falscher Name
    two = [{"name": "Anna", "embeddings": [e.tolist()]}, {"name": "Ben", "embeddings": [near.tolist()]}]
    q = (e + near) / np.linalg.norm(e + near)
    assert f._match(q, two)[0] == F.UNBEKANNT
    assert f._match(e, two)[0] == "Anna"
    assert f._match(e, [])[0] == F.UNBEKANNT


# ── Einverständnis und Speicher (ohne Modelle) ──────────────────────────────
def test_consent_required(tmp_path):
    f = F.Faces(tmp_path)
    for flag in (False, None, "ja", 1):
        res = f.enroll("Anna", [b"x", b"y", b"z"], einverstanden=flag)
        assert res["ok"] is False and "Einverständnis" in res["fehler"]
    assert not (tmp_path / "personen.json").exists()
    assert f.enroll("  ", [b"x"] * 3, einverstanden=True)["ok"] is False


def test_persons_delete_and_delete_all(tmp_path):
    f = F.Faces(tmp_path)
    emb = [[0.1] * 128]
    f._save([{"name": "Anna", "angelegt": "2026-10-28", "proben": 1, "einverstanden": True,
              "einverstanden_am": "2026-10-28T10:00:00", "embeddings": emb},
             {"name": "Ben", "angelegt": "2026-10-28", "proben": 1, "einverstanden": True,
              "einverstanden_am": "2026-10-28T10:00:00", "embeddings": emb}])
    people = f.persons()
    assert [p["name"] for p in people] == ["Anna", "Ben"]
    assert all("embeddings" not in p for p in people)
    assert f.delete("anna") is True                       # Groß-/Kleinschreibung egal
    assert f.delete("Anna") is False
    assert [p["name"] for p in f.persons()] == ["Ben"]
    assert "Anna" not in (tmp_path / "personen.json").read_text(encoding="utf-8")
    assert f.delete_all() == 1
    assert not (tmp_path / "personen.json").exists()
    assert f.persons() == []


# ── Echte Gesichter (Modelle + Bilder nötig) ────────────────────────────────
def _fetch(url: str, dest: Path, sha: str) -> Path:
    if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() == sha:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "duckpilot-test"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    if hashlib.sha256(data).hexdigest() != sha:
        raise RuntimeError("Prüfsumme stimmt nicht")
    dest.write_bytes(data)
    return dest


@pytest.fixture(scope="module")
def assets():
    pytest.importorskip("onnxruntime")
    pytest.importorskip("PIL")
    try:
        F.Faces(CACHE).ensure_models()
        if not SAMPLES:
            pytest.skip("eigene Testfotos fehlen (DUCKPILOT_FACE_SAMPLES)")
        imgs = {n: (Path(SAMPLES) / n).read_bytes() for n in BILDER}
    except Exception as e:  # kein Netz o. Ä.
        pytest.skip(f"Gesichtsmodelle/Testbilder nicht verfügbar: {e}")
    return imgs


@pytest.fixture
def faces(tmp_path, assets):
    f = F.Faces(tmp_path)
    f.models_dir = CACHE / "modelle"                       # Modelle aus dem Cache, Personen im tmp-Ordner
    return f


def _augment(data: bytes) -> list[bytes]:
    from PIL import Image, ImageEnhance, ImageOps

    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    variants = [
        ImageOps.mirror(img),
        ImageEnhance.Brightness(img).enhance(0.6),
        ImageEnhance.Brightness(img).enhance(1.4),
        img.crop((w // 10, h // 12, w - w // 10, h - h // 12)).resize((w // 2, h // 2)),
        img.rotate(8, resample=Image.BILINEAR),
    ]
    out = []
    for v in variants:
        b = io.BytesIO()
        v.save(b, "JPEG", quality=85)
        out.append(b.getvalue())
    return out


def test_detect_real_faces(faces, assets):
    one = faces.detect(assets["person_a1.jpg"])
    assert len(one) == 1
    x, y, w, h = one[0]["box"]
    assert one[0]["score"] >= F.SCORE_KLAR and 150 < w < 350 and 200 < h < 450
    (rx, ry), (lx, ly) = one[0]["landmarks"][:2]
    assert x < rx < lx < x + w and y < ry < y + h       # Augen im Rahmen, rechtes Auge der Person links im Bild
    assert len(faces.detect(assets["two_people.jpg"])) == 2


def test_enroll_recognize_unknown_and_delete(faces, assets, tmp_path):
    res = faces.enroll("Person A", _augment(assets["person_a1.jpg"]), einverstanden=True)
    assert res["ok"], res
    assert res["proben"] == 5

    # gespeichert: nur Merkmale, keine Bilder
    raw = (tmp_path / "personen.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    p = data["personen"][0]
    assert set(p) == {"name", "angelegt", "geaendert", "proben", "einverstanden", "einverstanden_am", "embeddings"}
    assert p["einverstanden"] is True and p["einverstanden_am"]
    assert len(p["embeddings"]) == 5 and all(len(e) == 128 for e in p["embeddings"])
    assert all(isinstance(v, float) for e in p["embeddings"] for v in e)
    assert len(raw) < 64 * 1024 and "base64" not in raw and "/9j/" not in raw   # kein eingebettetes JPEG
    assert sorted(os.listdir(tmp_path)) == ["personen.json"]

    # ein anderes Foto derselben Person wird erkannt
    hit = faces.who(assets["person_a2.jpg"])
    assert len(hit) == 1 and hit[0]["name"] == "Person A"
    assert hit[0]["aehnlichkeit"] >= F.SCHWELLE
    # eine andere Person bleibt unbekannt – und wird nirgends gespeichert
    miss = faces.who(assets["person_b.jpg"])
    assert len(miss) == 1 and miss[0]["name"] == F.UNBEKANNT
    assert miss[0]["aehnlichkeit"] < F.SCHWELLE
    assert raw == (tmp_path / "personen.json").read_text(encoding="utf-8")

    # nachlernen: höchstens 10 Proben
    res = faces.enroll("Person A", _augment(assets["person_a1.jpg"]) + _augment(assets["person_a2.jpg"]), True)
    assert res["ok"] and res["proben"] == F.MAX_PROBEN
    assert faces.persons()[0]["proben"] == F.MAX_PROBEN

    assert faces.delete("Person A") is True
    assert faces.who(assets["person_a2.jpg"])[0]["name"] == F.UNBEKANNT
    assert not (tmp_path / "personen.json").exists()


def test_enroll_reports_problems(faces, assets):
    from PIL import Image

    blank = io.BytesIO()
    Image.new("RGB", (320, 240), (200, 200, 200)).save(blank, "PNG")
    imgs = [blank.getvalue(), assets["two_people.jpg"], b"kein bild"] + _augment(assets["person_a1.jpg"])[:2]
    res = faces.enroll("Person A", imgs, einverstanden=True)
    assert res["ok"] is False
    text = " ".join(res["hinweise"])
    assert "Bild 1: kein Gesicht" in text
    assert "Bild 2: mehrere Gesichter" in text
    assert "Bild 3:" in text
    assert faces.persons() == []

    # eine fremde Person zwischen den Bildern fällt auf
    mixed = _augment(assets["person_a1.jpg"])[:3] + [assets["person_b.jpg"]]
    res = faces.enroll("Person A", mixed, einverstanden=True)
    assert res["ok"] and res["proben"] == 3
    assert any("Bild 4: passt nicht" in h for h in res["hinweise"])
    assert faces.delete_all() == 1


def test_speed(faces, assets):
    from PIL import Image

    faces.enroll("Person A", _augment(assets["person_a1.jpg"]), einverstanden=True)
    b = io.BytesIO()
    Image.open(io.BytesIO(assets["person_a2.jpg"])).convert("RGB").resize((480, 920)).save(b, "JPEG")
    frame = b.getvalue()
    faces.who(frame)                                      # Modelle laden
    t = time.perf_counter()
    for _ in range(5):
        faces.who(frame)
    ms = (time.perf_counter() - t) / 5 * 1000
    print(f"who(): {ms:.0f} ms je Bild")
    assert ms < 500                                       # ≥ 2 Bilder pro Sekunde auf der CPU
