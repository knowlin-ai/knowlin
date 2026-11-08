"""Policies aus Isaac Lab übernehmen (0.38.27, Entscheidung „3. fänd ich sehr wichtig“)."""

import json

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("onnxruntime")
pytest.importorskip("onnx")

from fastapi.testclient import TestClient  # noqa: E402
from onnx_fixtures import linear_policy  # noqa: E402

from duckpilot.physics import isaaclab as IL  # noqa: E402
from duckpilot.physics.core import ACTUATORS, DEFAULT_POSE, Command  # noqa: E402


def test_vertrag_wie_pollen_und_isaac_lab():
    """Isaac Labs „61-wide deploy contract“: Gelenkreihenfolge und Grundstellung wie Pollens Policies."""
    assert ACTUATORS[:5] == ("left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle")
    assert ACTUATORS[5:9] == ("neck_pitch", "head_pitch", "head_yaw", "head_roll")
    assert np.allclose(DEFAULT_POSE[:5], [0.0, -0.0873, -0.4579, -0.0049, 0.4530])
    assert IL.GRENZEN["kopf"] == [1.1, 1.1, 1.4, 0.31] and IL.GRENZEN["fahren"] == [0.4, 0.3, 1.0]


def test_falsche_datei_wird_abgelehnt(tmp_path):
    with pytest.raises(IL.ImportFehler, match="Beobachtungswerte"):
        IL.pruefe_datei(linear_policy(tmp_path / "x.onnx", obs_len=48))
    (tmp_path / "kaputt.onnx").write_bytes(b"kein onnx")
    with pytest.raises(IL.ImportFehler, match="keine lesbare ONNX-Datei"):
        IL.pruefe_datei(tmp_path / "kaputt.onnx")


def test_pruefstand_ist_ehrlich_eine_nichtstuende_policy_faellt_durch(tmp_path):
    r = IL.pruefstand(linear_policy(tmp_path / "null.onnx"))
    assert r["bestanden"] is False and r["roboter_frei"] is False
    assert set(r["pruefungen"]) == {"wie_trainiert", "wie_am_roboter"}
    assert [p["art"] for p in r["pruefungen"]["wie_am_roboter"]] == ["stehen", "vor", "seite", "drehen", "schubs"]
    assert all(p["grund"] for p in r["pruefungen"]["wie_trainiert"])


def test_importieren_legt_manifest_und_gangart_an(tmp_path):
    e = IL.importieren(tmp_path, linear_policy(tmp_path / "rough_v1.onnx"), "Mein Lauf", mit_pruefstand=False)
    assert e["name"] == "isaac_mein_lauf" and e["roboter_frei"] is False
    m = json.loads((tmp_path / "policies/import/isaac_mein_lauf/manifest.json").read_text(encoding="utf-8"))
    assert m["quelle"] == "isaaclab" and m["action_scale"] == 1.0 and m["obs_len"] == 61
    eigene = json.loads((tmp_path / "policies/eigene.json").read_text(encoding="utf-8"))
    assert eigene[-1]["art"] == "gangart" and eigene[-1]["name"] == "isaac_mein_lauf"
    assert [x["name"] for x in IL.liste(tmp_path)] == ["isaac_mein_lauf"]


def test_befehle_bleiben_im_trainierten_bereich(tmp_path):
    IL.importieren(tmp_path, linear_policy(tmp_path / "a.onnx"), "a", mit_pruefstand=False)
    g = IL.lade_grenzen(tmp_path / "policies/import/isaac_a/policy.onnx")
    assert g and g["action_scale"] == 1.0
    c = Command()
    c.twist[:] = [0.9, -0.9, 2.0]
    c.head[:] = [2.0, -2.0, 2.0, 1.0]
    c.body[:] = [0.02, 0.0, -0.03, 0.4, -0.4, 0.0]
    b = IL.begrenzen(c, g["grenzen"])
    assert np.allclose(b.twist, [0.4, -0.3, 1.0]) and np.allclose(b.head, [1.1, -1.1, 1.4, 0.31])
    assert np.allclose(b.body, [0.005, 0.0, -0.005, 0.05, -0.05, 0.0])
    assert c.twist[0] == pytest.approx(0.9)                       # Original bleibt (Kopf ruhig nutzt ihn weiter)


def test_route_nimmt_nur_am_pc_an_und_meldet_fehler_klar(tmp_path, monkeypatch):
    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.remote import pc_only
    from duckpilot.server.app import Runtime, create_app

    assert pc_only("POST", "/api/isaaclab") and pc_only("POST", "/api/isaaclab/isaac_x/nutzen")
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    monkeypatch.setattr(IL, "pruefstand", lambda *a, **k: {"bestanden": False, "roboter_frei": False, "pruefungen": {}})
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        h = {"origin": "http://127.0.0.1:8765"}
        r = c.post("/api/isaaclab?name=test", content=b"kein onnx", headers=h)
        assert r.status_code == 400 and "keine lesbare ONNX-Datei" in r.json()["fehler"] and "`" not in r.json()["fehler"] and "_eingang" not in r.json()["fehler"]
        daten = linear_policy(tmp_path / "gut.onnx").read_bytes()
        r = c.post("/api/isaaclab?name=gut", content=daten, headers=h)
        assert r.status_code == 200 and r.json()["neu"]["name"] == "isaac_gut"
        assert c.get("/api/isaaclab").json()["liste"][0]["name"] == "isaac_gut"
        r = c.post("/api/isaaclab/isaac_gut/nutzen", headers=h)
        assert r.status_code == 400 and "Physik-Simulator" in r.json()["fehler"]


def test_physik_setzt_die_gangart_mit_ihren_grenzen_ein(tmp_path, monkeypatch):
    import asyncio

    from test_physics import make_store

    from duckpilot.backends.physics import PhysicsBackend

    store = make_store(tmp_path)
    IL.importieren(tmp_path, linear_policy(tmp_path / "lauf.onnx"), "lauf", mit_pruefstand=False)
    gesehen = []
    echt = IL.begrenzen
    monkeypatch.setattr(IL, "begrenzen", lambda c, g: gesehen.append(1) or echt(c, g))

    async def go():
        b = PhysicsBackend(store, realtime=False)
        b._task = object()
        assert b.gait_policy is not None and b.gait_policy.name == "isaac_lauf"   # aus eigene.json, wie trainiert
        assert b.gait_policy.action_scale == 1.0 and b.gait_policy.grenzen is not None
        b.reset_body()
        for _ in range(10):
            b.step(0.02)
        assert gesehen                                                           # Befehle gingen durch die Grenzen
    asyncio.run(go())
