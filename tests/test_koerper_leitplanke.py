"""Leitplanke der Körperschnittstelle (seit 0.38.35): Körper werden über ihr Profil und ihre Fähigkeiten angesprochen,
nicht über ihren Namen. Diese Liste hält fest, wo Namen heute noch stehen (meist Inhalte je Körper: Stimmen, Figuren,
Texte). Sie darf nur kleiner werden – eine neue Stelle mit `== "reachy_mini"` & Co. schlägt fehl.

Statt `koerper_art == "reachy_mini"`: `"pollen_bewegungen" in backend.eigenschaften()`, `koerper.zu_zustand(...)`
oder ein Feld im Profil (`duckpilot/koerper.py`).
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMEN = {"reachy_mini", "open_duck_mini", "microduck", "lerobot"}
AUSGENOMMEN = ("duckpilot/koerper.py", "duckpilot/koerper_pruefung.py")
AUS_ORDNER = ("duckpilot/backends/", "duckpilot/modell/", "duckpilot/i18n/")   # die Körper selbst und ihre Modelle

ERLAUBT = {
    "duckpilot/api.py": 1,
    "duckpilot/brain/agent.py": 4,
    "duckpilot/brain/kopf.py": 1,
    "duckpilot/brain/tools.py": 3,
    "duckpilot/choreo.py": 3,
    "duckpilot/desktop.py": 1,
    "duckpilot/figuren.py": 7,
    "duckpilot/hub.py": 3,
    "duckpilot/knowlets.py": 4,
    "duckpilot/motion/eigenstaendig.py": 4,
    "duckpilot/motion/reachy_gesten.py": 1,
    "duckpilot/motion/tanz.py": 1,
    "duckpilot/physics/isaaclab.py": 1,
    "duckpilot/physics/isaaclab_hf.py": 1,
    "duckpilot/physics/policies.py": 1,
    "duckpilot/server/routes/basis.py": 1,
    "duckpilot/server/routes/choreo.py": 5,
    "duckpilot/server/routes/start.py": 1,
    "duckpilot/server/routes/stimme.py": 2,
    "duckpilot/server/routes/verbindung.py": 1,
    "duckpilot/server/runtime.py": 2,
    "duckpilot/server/runtime_eigenstaendig.py": 1,
    "duckpilot/server/runtime_reachy.py": 1,
    "duckpilot/suite.py": 2,
    "duckpilot/verbindungstest.py": 6,
    "duckpilot/voice/describe.py": 6,
    "duckpilot/voice/tts.py": 6,
}


def _zaehlen(pfad: Path) -> int:
    n = 0
    for node in ast.walk(ast.parse(pfad.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in NAMEN:
            n += 1
        if isinstance(node, ast.Compare):
            n += sum(1 for c in (node.left, *node.comparators) if isinstance(c, ast.Constant) and c.value == "duckpilot")
    return n


def test_koerpernamen_nur_wo_erlaubt():
    zuviel = []
    for p in sorted((ROOT / "duckpilot").rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        if rel in AUSGENOMMEN or rel.startswith(AUS_ORDNER):
            continue
        n = _zaehlen(p)
        if n > ERLAUBT.get(rel, 0):
            zuviel.append(f"{rel}: {n} statt höchstens {ERLAUBT.get(rel, 0)}")
    assert not zuviel, "Körper über Profil/Fähigkeiten ansprechen, nicht über den Namen: " + "; ".join(zuviel)


def test_liste_wird_kleiner_gehalten():
    """Wer eine Stelle entfernt, senkt auch die Zahl hier – sonst wächst sie unbemerkt wieder."""
    zu_hoch = [f"{rel}: erlaubt {n}, gefunden {_zaehlen(ROOT / rel)}" for rel, n in ERLAUBT.items()
               if (ROOT / rel).exists() and _zaehlen(ROOT / rel) < n]
    assert not zu_hoch, "; ".join(zu_hoch)
