"""Karten zoomen und verschieben (seit 0.38.66, Wunsch: „das sollte man zoomen können – bei größeren Maps sieht man
sonst keine Details mehr“)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"

ATTRAPPE = """
const knoten = () => ({ classList: { contains: () => false, add() {} }, style: {}, append() {}, replaceWith() {},
  setAttribute() {}, getAttribute: () => '', hasAttribute: () => false, addEventListener() {}, textContent: '',
  disabled: false });
globalThis.document = { createElement: knoten };
const canvas = { ...knoten(), parentElement: knoten(), getBoundingClientRect: () => ({ left: 0, top: 0 }) };
"""


def _node(code: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    mod = (STATIC / "kartenzoom.js").as_uri()
    i18n = (STATIC / "i18n.js").as_uri()
    skript = (f"{ATTRAPPE} const {{ KartenZoom }} = await import('{mod}'); await import('{i18n}');\n{code}")
    r = subprocess.run([node, "--input-type=module", "-e", skript], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def test_zoom_haelt_den_punkt_unter_dem_zeiger_fest_und_einpassen_setzt_zurueck():
    out = _node("""
      let n = 0;
      const z = new KartenZoom(canvas, () => { n += 1; });
      const welt = (v, x, y) => [v.cx + (x - v.w / 2) / v.s, v.cy - (y - v.h / 2) / v.s];
      let v = z.ansicht(0, 0, 100, 400, 400);
      const vorher = welt(v, 300, 120);
      z.zoomen(2, 300, 120);
      v = z.ansicht(0, 0, 100, 400, 400);
      const nachher = welt(v, 300, 120);
      z.verschieben(50, 0);
      const verschoben = z.ansicht(0, 0, 100, 400, 400).cx;
      z.zoomen(100);                                   // nicht über das Höchstmaß
      const max = z.zoom;
      z.einpassen();
      const zurueck = z.ansicht(0, 0, 100, 400, 400);
      console.log(JSON.stringify({ vorher, nachher, s: v.s, verschoben, cx: v.cx, max, zurueck, n }));""")
    assert out["s"] == 200
    assert abs(out["vorher"][0] - out["nachher"][0]) < 1e-9 and abs(out["vorher"][1] - out["nachher"][1]) < 1e-9
    assert out["verschoben"] < out["cx"]                 # nach rechts ziehen zeigt, was links liegt
    assert out["max"] == 12
    assert out["zurueck"]["cx"] == 0 and out["zurueck"]["s"] == 100 and out["n"] >= 4


def test_beide_karten_nutzen_den_zoom():
    for datei in ("raum.js", "dashboard.js"):
        text = (STATIC / datei).read_text(encoding="utf-8")
        assert "KartenZoom" in text and "zeichneZellen" in text, datei
    assert 'href="/static/bereiche/karten.css"' in (STATIC / "index.html").read_text(encoding="utf-8")
