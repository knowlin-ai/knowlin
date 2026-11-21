"""Choreografie zum Ziehen (seit 0.51): Einfügestelle, Verschieben, Treffer in der Zeitleiste."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

MODUL = (Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static" / "tanz_ziehen.js").as_uri()


def _node(code: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    r = subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def test_ziehen_reiht_um_und_trifft_bloecke():
    out = _node(f"""
      import {{ zielIndex, verschieben, einfuegen, treffer }} from '{MODUL}';
      const T = 2;   // Takt 2 s
      const s = [{{t: 0, takte: 1, art: 'nicken'}}, {{t: 2, takte: 2, art: 'drehen'}}, {{t: 6, takte: 1, art: 'pose', name: 'P'}}];
      const x = (t) => t * 10;   // 10 px je s
      console.log(JSON.stringify({{
        ziel: [zielIndex(s, 0.5, T), zielIndex(s, 1.5, T), zielIndex(s, 4.5, T), zielIndex(s, 99, T)],
        nachHinten: verschieben(s, 0, 3).map((x) => x.art),
        nachVorn: verschieben(s, 2, 0).map((x) => x.art),
        rein: einfuegen(s, {{art: 'pause'}}, 1).map((x) => x.art),
        oben: treffer(s, 25, 90, x, T), rand: treffer(s, 58, 90, x, T), unten: treffer(s, 65, 120, x, T),
        nichts: treffer(s, 25, 120, x, T),
      }}));
    """)
    assert out["ziel"] == [0, 1, 2, 3]
    assert out["nachHinten"] == ["drehen", "pose", "nicken"]
    assert out["nachVorn"] == ["pose", "nicken", "drehen"]
    assert out["rein"] == ["nicken", "pause", "drehen", "pose"]
    assert out["oben"] == {"i": 1, "rand": False} and out["rand"] == {"i": 1, "rand": True}
    assert out["unten"]["i"] == 2 and out["nichts"] is None


def test_tanzseite_hat_palette_und_loeschen():
    html = (Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static" / "teile" / "tanz.html").read_text("utf-8")
    js = (Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static" / "tanz.js").read_text("utf-8")
    assert 'id="tanz-palette"' in html and "initZiehen(" in js and "entfernen" in js
