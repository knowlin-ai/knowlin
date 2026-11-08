import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Pollens Robotermodell: in der öffentlichen Fassung nicht im Paket, sondern einmal per
# `python -m duckpilot.modell` in den Datenordner geladen – den sollen die Tests finden (nur lesen)
if "DUCKPILOT_MODELL" not in os.environ:
    from duckpilot.settings import data_dir

    os.environ["DUCKPILOT_MODELL"] = str(data_dir() / "pollen-modell")

# Tests nie gegen die echten Einstellungen des Nutzers laufen lassen
os.environ["DUCKPILOT_SETTINGS"] = str(Path(tempfile.mkdtemp(prefix="duckpilot-test-")) / "settings.json")
os.environ.pop("ANTHROPIC_API_KEY", None)
# Tests laden nie etwas aus dem Netz nach (Pollens Robotermodell, siehe duckpilot/modell)
os.environ["DUCKPILOT_OFFLINE"] = "1"


# Ohne Pollens Modell (öffentliche Fassung, noch nicht geladen): Physik-Tests überspringen statt scheitern
BRAUCHT_PHYSIK = {"test_physics.py", "test_acrobatics.py", "test_parcours.py", "test_kollision.py"}
BRAUCHT_PHYSIK_TESTS = {"test_signs_match_pollens_model", "test_walking_head_is_much_steadier",
                        "test_rehearse_trick_reports_a_verdict", "test_physics_report",
                        "test_practice_world_steps_rewards_and_ends", "test_local_training_smoke_runs_stops_and_exports"}
BRAUCHT_ANSICHT_TESTS = {"test_baked_model_is_complete"}


def pytest_collection_modifyitems(config, items):
    import pytest

    from duckpilot.modell import ModellStore

    st = ModellStore(Path(os.environ["DUCKPILOT_SETTINGS"]).parent)
    hint = "Pollens Robotermodell fehlt – einmal `python -m duckpilot.modell` ausführen"
    for item in items:
        name = item.path.name
        if st.physics_path() is None and (name in BRAUCHT_PHYSIK or item.originalname in BRAUCHT_PHYSIK_TESTS):
            item.add_marker(pytest.mark.skip(reason=hint))
        if st.view_path() is None and item.originalname in BRAUCHT_ANSICHT_TESTS:
            item.add_marker(pytest.mark.skip(reason=hint))
