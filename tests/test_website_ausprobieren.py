"""T4 (0.38.29): „Odi ausprobieren“ auf knowlin.de – läuft ganz im Browser, nur mit offenen Modellen."""

import base64
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import website  # noqa: E402
from duckpilot.api import Head, Twist  # noqa: E402
from duckpilot.backends.sim import display_joints  # noqa: E402
from website import DEMO_DATEIEN, MODELL_QUELLE, MODELL_ZIEL, bauen  # noqa: E402

NODE = shutil.which("node")


def test_vorerst_aus_keine_seite_keine_demo_keine_links(tmp_path):
    # 8.11.: „Im Browser ausprobieren enttäuscht ggf. die Erwartungen – die App kann ja viel mehr“
    assert website.MIT_AUSPROBIEREN is False
    ziel = bauen(tmp_path / "seite")
    assert not (ziel / "ausprobieren.html").exists() and not (ziel / "demo").exists()
    assert "ausprobieren.html" not in (ziel / "index.html").read_text(encoding="utf-8")


def test_seite_gebaut_mit_offenem_modell(tmp_path, monkeypatch):
    monkeypatch.setattr(website, "MIT_AUSPROBIEREN", True)                    # bleibt baubar für später
    ziel = bauen(tmp_path / "seite")
    seite = (ziel / "ausprobieren.html").read_text(encoding="utf-8")
    assert '<script type="module" src="demo/odi.js"></script>' in seite and 'id="odi-start"' in seite
    assert '<meta name="robots" content="noindex">' not in seite                  # soll gefunden werden
    for rel in DEMO_DATEIEN + ("odi.js", "gang.js", MODELL_ZIEL):
        assert (ziel / "demo" / rel).exists(), rel
    daten = json.loads((ziel / "demo" / MODELL_ZIEL).read_text(encoding="utf-8"))
    assert base64.b64decode(daten["daten"]) == (ROOT / "duckpilot/server/static" / MODELL_QUELLE).read_bytes()
    assert "Apache" in daten["lizenz"]
    namen = [p.name.lower() for p in (ziel / "demo").rglob("*")]
    assert not [n for n in namen if "microduck" in n or "reachy" in n]           # Pollens Modelle nie auf der Website
    assert "Apache" in (ziel / "demo" / "model" / "LIZENZ-open-duck-mini.md").read_text(encoding="utf-8")
    # lädt nichts von fremden Servern: keine absoluten Adressen in den Skripten der Seite
    for js in ("odi.js", "gang.js"):
        assert "http" not in (ziel / "demo" / js).read_text(encoding="utf-8").split("\n", 8)[-1]


def _node(code: str):
    r = subprocess.run([NODE, "--input-type=module", "-e", code], capture_output=True, text=True, timeout=30, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.skipif(NODE is None, reason="node fehlt")
def test_gangformel_wie_im_simulator():
    faelle = [dict(fold=0, vx=0, vyaw=0, phase=0), dict(fold=0, vx=0.16, vyaw=0, phase=1.1),
              dict(fold=0, vx=-0.08, vyaw=0.4, phase=4.0), dict(fold=0, vx=0, vyaw=-0.9, phase=2.5),
              dict(fold=1, vx=0, vyaw=0, phase=0), dict(fold=0.3, vx=0.1, vyaw=0, phase=0.7,
                                                         kopf=dict(neck=0.1, pitch=-0.2, yaw=0.3, roll=0.05))]
    js = _node("import { gelenke } from './website/demo/gang.js'; console.log(JSON.stringify("
               + json.dumps(faelle) + ".map((f) => gelenke(f))));")
    for f, got in zip(faelle, js):
        k = f.get("kopf", dict(neck=0, pitch=0, yaw=0, roll=0))
        # sitzt (fold > 0,5) ↔ sitting im Simulator; dazwischen rechnet der Simulator mit dem Fortschritt des Hinsetzens
        py = display_joints(sitting=False, skill="_rest" if 0 < f["fold"] else None, progress=f["fold"], powered=True,
                            fallen=False, twist=Twist(f["vx"], 0.0, f["vyaw"]), phase=f["phase"],
                            head=Head(neck_pitch=k["neck"], head_pitch=k["pitch"], head_yaw=k["yaw"], head_roll=k["roll"]),
                            mouth=0.0)
        assert len(got) == len(py) == 15
        assert all(math.isclose(a, b, abs_tol=1e-9) for a, b in zip(got, py)), (f, got, py)


@pytest.mark.skipif(NODE is None, reason="node fehlt")
def test_odi_versteht_ein_paar_woerter():
    saetze = {"geh zum Ball": "ball", "Tanz für mich": "tanzen", "setz dich": "sitzen", "steh auf": "aufstehen",
              "schüttel den Kopf": "schuetteln", "dreh dich nach rechts": "rechts", "geh rückwärts": "zurueck",
              "stopp": "halt", "Hallo Odi": "hallo", "go to the ball": "ball", "dance": "tanzen", "turn left": "links",
              "walk": "vor", "look around": "umschauen", "nod": "nicken", "irgendwas": None}
    js = _node("import { verstehen } from './website/demo/gang.js'; console.log(JSON.stringify("
               + json.dumps(list(saetze)) + ".map(verstehen)));")
    assert dict(zip(saetze, js)) == saetze
