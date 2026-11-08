"""Knowlins Mind-Form auf der Startseite als dreidimensionales neuronales Netz (Hinweis aus dem Test vom 5.11.:
„es soll ein neuronales Netz sein, mit 3D-Look, das die Synapsen und Datenverläufe zeigt und bei Aktivität wabert“)."""
import json
import re
import shutil
import subprocess

import pytest

from duckpilot.server.app import STATIC

MIND = STATIC / "mind.js"


def test_mind_sparsam_und_ruhig_bei_reduzierter_bewegung():
    js = MIND.read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in js and "standbild" in js          # still: ein Bild je Zustand
    assert "IntersectionObserver" in js and "document.hidden" in js      # nur zeichnen, solange sichtbar
    assert "const SCHRITT = 1000 / 30" in js                             # höchstens 30 Bilder je Sekunde
    assert "Math.min(2, window.devicePixelRatio" in js
    for z in ("ruhe", "hoert", "denkt", "spricht"):
        assert re.search(rf"\b{z}: {{ energie:", js), z
    # Farben nur aus den Tokens, keine festen Farbwerte; nichts aus dem Netz, keine Bibliothek
    assert "getComputedStyle" in js and "--accent" in js and "--ink-3" in js
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", js)
    assert "import " not in js and "fetch(" not in js and "three" not in js.lower()
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    regel = css[css.index(".mind {"):]
    assert "pointer-events: none" in regel[:regel.index("}")]           # schmückend, fängt keine Klicks
    # seit 0.38.23 auf einem flachen Halo (Wunsch: „nur auf einer Art Halo oder Bezugsfläche“), keine Blase
    assert "function halo(" in js and "function blase(" not in js
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '<canvas class="mind" id="mind" aria-hidden="true">' in html


def test_mind_netz_dreidimensional_und_zusammenhaengend():
    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    code = ("import { bauNetz, projiziere, ZUSTAENDE } from '" + MIND.as_uri() + "';"
            "const a = bauNetz(); const b = bauNetz();"
            "const { neuronen, synapsen, nachbarn } = a;"
            "const paare = new Set(synapsen.map(s => Math.min(s.a, s.b) + '|' + Math.max(s.a, s.b)));"
            "const teil = new Set([0]); const stapel = [0];"
            "while (stapel.length) { const v = stapel.pop(); for (const k of nachbarn[v]) { const s = synapsen[k];"
            "  const w = s.a === v ? s.b : s.a; if (!teil.has(w)) { teil.add(w); stapel.push(w); } } }"
            "const zs = neuronen.map(n => n.z);"
            "const vorn = projiziere({ x: 0.5, y: 0, z: -0.8 }, 0, 0), hinten = projiziere({ x: 0.5, y: 0, z: 0.8 }, 0, 0);"
            "const gedreht = projiziere({ x: 1, y: 0, z: 0 }, Math.PI / 2, 0);"
            "console.log(JSON.stringify({ n: neuronen.length, s: synapsen.length, einzig: paare.size,"
            "  zusammen: teil.size, zspanne: Math.max(...zs) - Math.min(...zs),"
            "  gleich: JSON.stringify(a.neuronen) === JSON.stringify(b.neuronen),"
            "  ohneSich: synapsen.every(s => s.a !== s.b),"
            "  gerade: synapsen.every(s => Math.abs(s.c.x - (neuronen[s.a].x + neuronen[s.b].x) / 2) < 1e-9),"
            "  innen: neuronen.filter(n => Math.hypot(n.x, n.y, n.z) < 0.5).length,"
            "  vorn: vorn.s, hinten: hinten.s, vornX: vorn.x, hintenX: hinten.x, gedrehtZ: gedreht.z,"
            "  zustaende: Object.keys(ZUSTAENDE), rate: Object.fromEntries(Object.entries(ZUSTAENDE).map(([k, v]) => [k, v.rate])),"
            "  welle: Object.fromEntries(Object.entries(ZUSTAENDE).map(([k, v]) => [k, v.welle])) }));")
    out = json.loads(subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True,
                                    check=True).stdout)
    # seit 0.38.21 ein Plexus (Hinweis „verbogen … hohl wie ein Obstnetz“): viele Neuronen, gerade Synapsen,
    # der Raum ist gefüllt – auch innen liegen Neuronen
    assert 160 <= out["n"] <= 320
    assert out["s"] == out["einzig"] and out["ohneSich"] and out["gerade"]  # jede Synapse einmal, gerade
    assert out["innen"] >= out["n"] * 0.12
    assert out["s"] >= out["n"]                                          # ein Netz, keine Kette
    assert out["zusammen"] == out["n"]                                   # alles hängt zusammen
    assert out["zspanne"] > 1.2                                          # echte Tiefe, kein flaches Bild
    assert out["gleich"]                                                 # fester Zufall: immer dasselbe Netz
    assert out["vorn"] > 1 > out["hinten"] and out["vornX"] > out["hintenX"]  # Perspektive: hinten kleiner
    assert out["gedrehtZ"] < -0.99                                       # Drehen um die Hochachse
    assert out["zustaende"] == ["ruhe", "hoert", "denkt", "spricht"]
    r = out["rate"]
    assert r["denkt"] > r["spricht"] > r["ruhe"] and r["hoert"] > r["ruhe"]  # Nachdenken: die meisten Impulse
    assert out["welle"] == {"ruhe": "", "hoert": "innen", "denkt": "", "spricht": "aussen"}
