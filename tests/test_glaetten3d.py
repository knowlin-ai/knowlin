"""Ruhiges Bild trotz holprigem Zustand (seit 0.38.52, Maintainer: „Der Controller-Modus ruckelt stark bei Bewegung bzw.
zappelt“): Die Lage der Figur gleitet statt zu springen, große Sprünge gelten sofort; der Entenblick ist stabilisiert
und hält den Horizont gerade."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"
MODUL = STATIC / "glaetten3d.js"


def _node(code: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    r = subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def test_lage_glaettet_holprigen_zustand():
    code = ("import { Lage } from '" + MODUL.as_uri() + "';"
            "const l = new Lage(); const xs = [];"
            # Ente läuft gleichmäßig 0,2 m/s, Zustand kommt aber holprig: mal zwei Schritte auf einmal, mal keiner
            "let t = 0, x = 0, letzt = 0; const pakete = [1,0,2,1,0,0,3,1,1,0,2,1];"
            "for (let i = 0; i < 240; i++) { t += 1/60; if (i % 3 === 0) { x = letzt += 0.01 * pakete[(i/3) % 12]; }"
            "  xs.push(l.glaetten({ x, y: 0, yaw: Math.PI - 0.001 + (i % 2) * 0.002 }, 1/60).x); }"
            "const roh = []; letzt = 0; for (let i = 0; i < 240; i++) { if (i % 3 === 0) letzt += 0.01 * pakete[(i/3) % 12]; roh.push(letzt); }"
            "const ruck = (a) => Math.max(...a.slice(1).map((v, i) => Math.abs(v - a[i])));"
            "const sprung = l.glaetten({ x: 5, y: 1, yaw: 0 }, 1/60);"
            "const w = new Lage(); w.glaetten({ x: 0, y: 0, yaw: 3.1 }, 0.016); const ueber = w.glaetten({ x: 0, y: 0, yaw: -3.1 }, 0.016).yaw;"
            "const orig = { x: 1, y: 2, yaw: 0, name: 'q' }; const kopie = new Lage().glaetten(orig, 0.016);"
            "console.log(JSON.stringify({ rohRuck: ruck(roh), glattRuck: ruck(xs), ende: xs.at(-1), rohEnde: roh.at(-1),"
            "  sprung: [sprung.x, sprung.y], ueber, unveraendert: orig.x === 1 && kopie !== orig && kopie.name === 'q' }));")
    out = _node(code)
    assert out["glattRuck"] < out["rohRuck"] / 2                  # keine Sprünge mehr
    assert abs(out["ende"] - out["rohEnde"]) < 0.05                # bleibt dicht dran
    assert out["sprung"] == [5, 1]                                 # Zurücksetzen: sofort dort
    assert abs(out["ueber"]) > 3.0                                 # über ±π gleitet der Winkel den kurzen Weg
    assert out["unveraendert"]


def test_entenblick_stabilisiert_und_horizont_gerade():
    code = ("import * as THREE from '" + (STATIC / "vendor" / "three.module.min.js").as_uri() + "';"
            "import { Stabilisator } from '" + MODUL.as_uri() + "';"
            "const s = new Stabilisator(); const cam = new THREE.PerspectiveCamera(); const ys = []; const rolls = [];"
            "for (let i = 0; i < 120; i++) { const wackel = Math.sin(i * 1.7) * 0.01;"
            "  s.fuehren(cam, new THREE.Vector3(i * 0.002, 0.2 + wackel, 0), new THREE.Vector3(1, wackel, Math.sin(i) * 0.05), 1/60);"
            "  ys.push(cam.position.y); const up = new THREE.Vector3(0, 1, 0).applyQuaternion(cam.quaternion);"
            "  const vorn = new THREE.Vector3(0, 0, -1).applyQuaternion(cam.quaternion); const rechts = vorn.clone().cross(new THREE.Vector3(0, 1, 0));"
            "  rolls.push(Math.abs(up.dot(rechts.normalize()))); }"
            "const spanne = (a) => Math.max(...a.slice(20)) - Math.min(...a.slice(20));"
            "console.log(JSON.stringify({ ySpanne: spanne(ys), roll: Math.max(...rolls) }));")
    out = _node(code)
    assert out["ySpanne"] < 0.02 * 0.5                             # Wackeln mindestens halbiert
    assert out["roll"] < 1e-6                                      # Horizont gerade


def test_szene_nutzt_glaettung():
    js = (STATIC / "duck3d.js").read_text(encoding="utf-8")
    assert "this.duck.update(this.lage.glaetten(st, dt), dt)" in js
    assert "this._placePovCam(size.x / Math.max(1, size.y), dt)" in js
