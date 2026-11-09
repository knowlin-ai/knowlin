"""Knowlin Link (Reachy-Mini-App, seit 0.38.35): erfüllt die Regeln von Pollens `reachy-mini-app-assistant check`.

Nachgebaut aus reachy_mini 1.14 (apps/assistant.py): index.html und style.css im Wurzelordner, Paket mit main.py, Klasse
<Paket in CamelCase>(ReachyMiniApp), Entry Point `reachy_mini_apps`, README mit title und den Tags `reachy_mini` und
`reachy_mini_python_app`. Die App bewegt den Roboter nicht.
"""

import ast
import tomllib
from pathlib import Path

import yaml

APP = Path(__file__).resolve().parents[1] / "apps" / "knowlin-link-reachy"


def test_struktur_wie_pollens_pruefung():
    pp = tomllib.loads((APP / "pyproject.toml").read_text(encoding="utf-8"))
    name = pp["project"]["name"]
    ep = pp["project"]["entry-points"]["reachy_mini_apps"]
    paket = ep[name].split(":")[0].split(".")[0]
    klasse = "".join(w.capitalize() for w in paket.split("_"))
    assert ep[name] == f"{paket}.main:{klasse}"
    for datei in ("index.html", "style.css", "README.md", f"{paket}/__init__.py", f"{paket}/main.py",
                  f"{paket}/static/index.html"):
        assert (APP / datei).is_file(), datei
    assert f"class {klasse}(ReachyMiniApp)" in (APP / paket / "main.py").read_text(encoding="utf-8")
    kopf = (APP / "README.md").read_text(encoding="utf-8").split("---")[1]
    meta = yaml.safe_load(kopf)
    assert meta["title"] and {"reachy_mini", "reachy_mini_python_app"} <= set(meta["tags"])


def test_app_bewegt_den_roboter_nicht():
    """Knowlin steuert Reachy über Pollens Daemon – die App darf nicht um die Motoren konkurrieren."""
    quelltext = (APP / "knowlin_link" / "main.py").read_text(encoding="utf-8")
    aufrufe = {n.func.attr for n in ast.walk(ast.parse(quelltext)) if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Attribute)}
    assert not aufrufe & {"set_target", "goto_target", "enable_motors", "play_move", "set_mode"}


def test_kein_klarname_und_keine_pollen_marke_als_eigene():
    text = " ".join(p.read_text(encoding="utf-8") for p in APP.rglob("*") if p.is_file())
    assert "not affiliated with Pollen Robotics" in text
