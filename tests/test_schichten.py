"""Schnitt Kern / Motorik / Lab / Körper (0.33): jedes Modul hat eine Schicht, und die Import-Regeln halten."""

import ast
from pathlib import Path

from duckpilot.schichten import REGELN, SCHICHTEN, schicht_von

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "duckpilot"


def _module(p: Path) -> str:
    parts = list(p.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports(p: Path) -> set[str]:
    """Alle duckpilot-Module, die eine Datei importiert – auch Importe in Funktionen (die gibt es hier oft)."""
    mod = _module(p)
    pkg = mod.split(".") if p.name == "__init__.py" else mod.split(".")[:-1]
    found: set[str] = set()
    for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg[: len(pkg) - (node.level - 1)]
                full = ".".join(base + ([node.module] if node.module else []))
            else:
                full = node.module or ""
            if full.startswith("duckpilot"):
                found.add(full)
                found.update(f"{full}.{a.name}" for a in node.names)   # „from ..skills import alltag“
        elif isinstance(node, ast.Import):
            found.update(a.name for a in node.names if a.name.startswith("duckpilot"))
    return found


def _files():
    return [p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts and p != PKG / "__init__.py"]


def test_every_module_has_a_layer():
    missing = [_module(p) for p in _files() if schicht_von(_module(p)) is None]
    assert not missing, f"in duckpilot/schichten.py eintragen: {missing}"


def test_layers_respect_the_import_rules():
    known = {_module(p) for p in _files()}
    broken = []
    for p in _files():
        own = schicht_von(_module(p))
        for imp in _imports(p):
            while imp not in known and "." in imp:      # „duckpilot.api.Twist“ → „duckpilot.api“
                imp = imp.rsplit(".", 1)[0]
            other = schicht_von(imp)
            if other in REGELN.get(own, ()):
                broken.append(f"{_module(p)} ({own}) → {imp} ({other})")
    assert not broken, "Schicht-Regel verletzt:\n" + "\n".join(sorted(broken))


def test_layer_lookup():
    assert schicht_von("duckpilot.brain.agent") == "kern"
    assert schicht_von("duckpilot.motion.engine") == "motorik"
    assert schicht_von("duckpilot.physics.lernen") == "lab"
    assert schicht_von("duckpilot.backends.physics") == "koerper"
    assert schicht_von("duckpilot.skills.gaits") == "koerper"          # längster Eintrag gewinnt
    assert schicht_von("duckpilot.server.runtime") == "verbindung"
    assert schicht_von("duckpilot.skills.alltag") == "kern"
    assert set(SCHICHTEN) >= {"kern", "motorik", "lab", "koerper"}
