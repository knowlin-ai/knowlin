"""Nur zeigen, was der Körper kann (seit 0.38.64; Maintainer: „schau in jedem Fall, dass nur Funktionen gezeigt
werden, die die Roboter auch abbilden können“) – geprüft gegen die Körperschnittstelle (`eigenschaften()`)."""

import re
from pathlib import Path

from fastapi.testclient import TestClient
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot.config import load
from duckpilot.server.app import create_app
from duckpilot.server.runtime import Runtime

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"


def _klassen(html: str, id_: str) -> set[str]:
    m = re.search(rf'<[^>]*class="([^"]*)"[^>]*id="{id_}"', html)
    assert m, id_
    return set(m.group(1).split())


def test_blick_laser_und_folgen_brauchen_eine_kamera():
    """Bello (Bittle X) und Ari (SO-101) haben ab Werk keine Kamera: kein „Blick durch ihre Augen“, kein Laserpointer
    und kein „Folg mir“ – am echten Körper sähen sie weder Punkt noch Mensch."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert "braucht-kamera" in _klassen(html, "laser-btn") and "braucht-kamera" in _klassen(html, "follow-btn")
    assert re.search(r'class="stage-mode braucht-kamera"', html)
    assert "body:not(.im-kopf).ohne-kamera .braucht-kamera" in css
    assert "mode === 'entenblick' && kamera" in (STATIC / "app.js").read_text(encoding="utf-8")
    # dieselbe Regel für die KI: ohne Kamera kein Laser und kein Folgen
    from duckpilot.backends.bittle import BittleSim
    from duckpilot.brain.tools import ToolRunner
    from duckpilot.motion.engine import MotionEngine

    namen = {t["name"] for t in ToolRunner(MotionEngine(BittleSim(realtime=False))).tools()}
    assert not {"laser_folgen", "mir_folgen"} & namen and "skill" in namen


def test_leerlauf_ohne_schnabel_putzt_kein_gefieder(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        namen = {e["name"] for e in c.get("/api/emotions").json()}
        assert "gefieder_putzen" in namen                                   # die Microduck hat einen Schnabel
        for modul in ("open_duck_mini", "bittle", "stackchan"):
            assert c.post("/api/settings", json={"modul": modul, "backend": "sim", "sim_physik": False}).json()["ok"]
            namen = {e["name"] for e in c.get("/api/emotions").json()}
            assert "gefieder_putzen" not in namen and "boden_picken" not in namen, modul
