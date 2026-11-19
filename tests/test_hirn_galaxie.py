"""Hirnaktivität als Galaxie (seit 0.38.67, Wunsch: „Die Optik fand ich ja ganz cool – vielleicht kann man das noch etwas
interaktiver gestalten“)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from duckpilot.brain.erfahrung import Erfahrungsnetz

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"


def _node(code: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    mod = (STATIC / "hirn_galaxie.js").as_uri()
    r = subprocess.run([node, "--input-type=module", "-e", f"const G = await import('{mod}');\n{code}"],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def test_nebel_liegen_fest_und_der_staub_ist_bei_jedem_bild_gleich():
    out = _node("""
      const z1 = G.zentren(['ding', 'person', 'gefuehl'], 800, 400), z2 = G.zentren(['gefuehl', 'ding', 'person'], 800, 400);
      const s1 = G.staub('ding', 50), s2 = G.staub('ding', 50), s3 = G.staub('ort', 50);
      const innen = s1.every((p) => Math.hypot(p.x, p.y) <= 1.0001);
      console.log(JSON.stringify({ gleich: JSON.stringify(z1) === JSON.stringify(z2), arten: Object.keys(z1),
        staubGleich: JSON.stringify(s1) === JSON.stringify(s2), anders: JSON.stringify(s1) !== JSON.stringify(s3), innen,
        allein: G.zentren(['zeit'], 800, 400).zeit }));""")
    assert out["gleich"] and out["arten"] == ["person", "ding", "gefuehl"]
    assert out["staubGleich"] and out["anders"] and out["innen"]
    assert out["allein"] == {"x": 400, "y": 200}


def test_suche_und_wachsen():
    out = _node("""
      const zeig = (n) => n;
      const k = { name: 'Küche', art: 'ort' };
      const reihe = G.wachsReihe([{ id: 'b', erst: 20 }, { id: 'a', erst: 10 }, { id: 'c', erst: 20, n: 5 }]);
      console.log(JSON.stringify({ umlaut: G.trifft(k, 'kuche', zeig), art: G.trifft(k, 'orte', zeig),
        nein: G.trifft(k, 'ball', zeig), leer: G.trifft(k, '', zeig), reihe,
        farbe: G.artFarbe('ding', '#199e70')(0.5) }));""")
    assert out["umlaut"] and out["art"] and not out["nein"] and out["leer"]
    assert out["reihe"] == ["a", "c", "b"]
    assert out["farbe"].startswith("hsla(") and out["farbe"].endswith(", 0.5)")


def test_knoten_wissen_wann_sie_zuerst_erlebt_wurden(tmp_path):
    netz = Erfahrungsnetz(tmp_path / "netz.json")
    netz.erleben({"ding:ball": "Ball", "ort:sofa": "Sofa"})
    msg = netz.message()
    assert all(k["erst"] > 0 for k in msg["knoten"])


def test_werkzeugleiste_mit_tasten_und_suche():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for aktion in ("umformen", "wachsen", "klar", "aufnahme"):
        assert f'data-brain-aktion="{aktion}"' in html
    assert 'id="brain-suche"' in html and 'href="/static/bereiche/hirn.css"' in html
    js = (STATIC / "hirn.js").read_text(encoding="utf-8")
    assert "k.art === 'person' ? zeigName('Person')" in js          # Aufnahme ohne Namen von Personen
