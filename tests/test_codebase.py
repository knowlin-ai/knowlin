"""Architektur-Leitplanken: Stil sauber, Module überschaubar, Server aus Bereichen zusammengesetzt.

Diese Tests halten fest, was beim Aufräumen (0.21) vereinbart wurde – damit es so bleibt.
"""

import importlib
import shutil
import subprocess
from pathlib import Path

import pytest

from duckpilot.server.oberflaeche import seite

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "duckpilot"
MAX_PY_LINES = 1400            # größer = in Bereiche aufteilen (so wie server/app.py → runtime, security, routes/*)
MAX_JS_KB = 64                 # seit 0.38.17 (vorher 100) – größer = in Module aufteilen
APP_JS_KB = 72                 # app.js setzt nur noch zusammen; Neues kommt in eigene Module (0.38.17: 98 → 67 KB)


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff nicht installiert")
def test_ruff_is_clean():
    r = subprocess.run(["ruff", "check", "duckpilot", "tests", "tools"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:]


def test_python_modules_stay_small():
    big = {str(p.relative_to(ROOT)): n for p in PKG.rglob("*.py")
           if (n := len(p.read_text(encoding="utf-8").splitlines())) > MAX_PY_LINES}
    assert not big, f"zu groß, bitte aufteilen: {big}"


def test_frontend_modules_stay_small():
    static = PKG / "server" / "static"
    big = {p.name: p.stat().st_size // 1024 for p in static.glob("*.js")
           if p.stat().st_size > (APP_JS_KB if p.name == "app.js" else MAX_JS_KB) * 1024}
    assert not big, f"zu groß, bitte in Module aufteilen: {big}"


def test_every_frontend_module_is_used():
    """Jedes Modul unter static/ wird von einem anderen importiert oder von index.html geladen – keine Waisen."""
    static = PKG / "server" / "static"
    texte = {p.name: p.read_text(encoding="utf-8") for p in static.glob("*.js")}
    html = seite() + "".join(
        p.read_text(encoding="utf-8") for p in static.glob("*.html") if p.name != "index.html")
    waisen = [n for n in texte if not n.endswith(".min.js") and f"./{n}" not in "".join(texte.values()) and n not in html]
    assert not waisen, f"nirgends geladen: {waisen}"


def test_server_is_assembled_from_route_modules():
    from duckpilot.server import routes

    app_src = (PKG / "server" / "app.py").read_text(encoding="utf-8")
    assert "@app." in app_src and app_src.count("@app.") <= 3          # nur Startseite und Manifest
    for name in routes.MODULES:
        mod = importlib.import_module(f"duckpilot.server.routes.{name}")
        assert callable(mod.register), name


def test_no_unreferenced_background_tasks():
    offenders = [str(p.relative_to(ROOT)) for p in PKG.rglob("*.py")
                 if p.name != "aio.py" and "asyncio.ensure_future(" in p.read_text(encoding="utf-8")]
    assert not offenders, f"spawn() aus duckpilot.aio benutzen: {offenders}"


def test_icons_get_a_fresh_address_when_they_change(tmp_path, monkeypatch):
    """Browser und Edge-App-Fenster merken sich Symbole nach Adresse – neue Icons brauchen eine neue Adresse."""
    from fastapi.testclient import TestClient

    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app, icon_stamp

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        page = c.get("/").text
        stamp = icon_stamp()
        assert f'/static/icon-192.png?v={stamp}"' in page and f'/manifest.webmanifest?v={stamp}"' in page
        assert all(i["src"].endswith(f"?v={stamp}") for i in c.get("/manifest.webmanifest").json()["icons"])
        assert c.get("/static/icon-192.png").headers["cache-control"] == "no-cache"


def test_changelog_has_the_current_version():
    """Jede Version steht im CHANGELOG (für die Release-Notes auf GitHub), und pyproject passt zur Paketversion."""
    from duckpilot import __version__

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"\n## {__version__} " in changelog, f"CHANGELOG.md: Abschnitt „## {__version__}“ fehlt"
    assert f'version = "{__version__}"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for name in ("LICENSE", "NOTICE"):
        assert (ROOT / name).exists(), f"{name} fehlt"
