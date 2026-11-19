"""Ins Wort fallen (0.40): das Echo der eigenen Stimme unterbricht nicht, eine Stimme dazwischen schon."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from duckpilot.server.oberflaeche import seite

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"


def _node(code: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    mod = (STATIC / "ins_wort.js").as_uri()
    r = subprocess.run([node, "--input-type=module", "-e", f"const I = await import('{mod}');\n{code}"],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def test_echo_unterbricht_nicht_stimme_dazwischen_schon():
    out = _node("""
      function lauf(werte) {          // je 50 ms ein Pegel → Zeitpunkt der Unterbrechung oder null
        const p = new I.Pegel();
        for (let i = 0; i < werte.length; i++) if (p.schritt(werte[i], i * 50)) return i * 50;
        return null;
      }
      const echo = Array.from({ length: 100 }, (_, i) => 0.05 + 0.02 * Math.sin(i));            // eigene Stimme, gedämpft
      const dazwischen = [...echo.slice(0, 30), ...Array(20).fill(0.3)];                          // ab 1,5 s spricht jemand
      const knall = [...echo.slice(0, 30), 0.5, ...echo.slice(31, 60)];                           // kurzer Knall
      const stille = Array(40).fill(0.002).concat(Array(10).fill(0.04));                          // leiser Raum, dann Stimme
      console.log(JSON.stringify({ echo: lauf(echo), dazwischen: lauf(dazwischen), knall: lauf(knall), stille: lauf(stille),
        rms: Math.round(I.rms(new Uint8Array([128, 128, 255, 1])) * 100) / 100 }));""")
    assert out["echo"] is None and out["knall"] is None
    assert 1500 + 250 <= out["dazwischen"] <= 1500 + 400
    assert out["stille"] is not None and out["rms"] == 0.7


def test_verdrahtet_und_abschaltbar():
    html = seite()
    assert 'data-set="ins_wort_fallen"' in html
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "unterbrecher.start(" in app and "lastUserSpoke && !fern.remote" in app and "unterbrecher.stop()" in app
    from duckpilot import settings as S

    assert S.validate({"ins_wort_fallen": False}) == {"ins_wort_fallen": False}
