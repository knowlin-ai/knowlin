"""WonderDuck von Hiwonder (seit 0.53): Profil, Simulator, Sicherheitsprüfung, Modell aus dem GLB, Laden und Routen.

Das Modell selbst liegt nicht im Repo (CC BY-NC-SA) – die Tests backen ein kleines GLB mit demselben Aufbau.
"""

import asyncio
import json
import struct

import numpy as np
import pytest
from fastapi.testclient import TestClient
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot import koerper, remote
from duckpilot.modell import wonderduck as W


# ── Ein kleines GLB wie Hiwonders: origin → joint → body → visual, plus Füße, Kamera, ToF ──────────────────────────
def _glb() -> bytes:
    nodes = [{"name": "world_y_up", "children": [1], "rotation": [-0.7071, 0, 0, 0.7071]},
             {"name": "origin_trunk_base", "children": [2]},
             {"name": "body_trunk_base", "children": [3]},
             {"name": "visual_p_trunk_base_01", "mesh": 0}]
    meshes = [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}]

    def kette(eltern: int, gelenke: list[str], lage: list[float], extra: dict[str, list[float]]) -> None:
        for g in gelenke:
            i = len(nodes)
            dreh = {"left_hip_pitch": [0, -0.192, 0, 0.981]}.get(g, [0, 0, 0, 1])
            nodes.extend([{"name": f"origin_{g}", "children": [i + 1], "translation": lage},
                          {"name": f"joint_{g}", "children": [i + 2], "rotation": dreh},
                          {"name": f"body_{g}", "children": [i + 3]},
                          {"name": f"visual_p_{g}_01", "mesh": 0}])
            nodes[eltern].setdefault("children", []).append(i)
            eltern = i + 2
        for name, pos in extra.items():
            j = len(nodes)
            nodes.extend([{"name": name, "children": [j + 1], "translation": pos}, {"name": name.replace("origin", "body")}])
            nodes[eltern]["children"].append(j)

    kette(2, ["left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle"], [0, 0.02, -0.02],
          {"origin_left_foot": [0, 0, -0.024]})
    kette(2, ["right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle"], [0, -0.02, -0.02],
          {"origin_right_foot": [0, 0, -0.024]})
    kette(2, ["neck_pitch", "head_pitch", "head_yaw", "head_roll", "mouth"], [0.02, 0, 0.04],
          {"origin_camera": [0.06, 0, 0.012]})
    pos = np.array([[0, 0, 0], [0.01, 0, 0], [0, 0.01, 0], [0, 0, 0.01]], dtype="<f4")
    idx = np.array([0, 2, 1, 0, 1, 3, 0, 3, 2, 1, 2, 3], dtype="<u2")
    binaer = pos.tobytes() + idx.tobytes()
    kopf = {"asset": {"version": "2.0"}, "nodes": nodes, "meshes": meshes,
            "materials": [{"name": "body_yellow", "pbrMetallicRoughness": {"baseColorFactor": [1, 0.82, 0, 1]}}],
            "buffers": [{"byteLength": len(binaer)}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 48}, {"buffer": 0, "byteOffset": 48, "byteLength": 24}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "type": "VEC3", "count": 4},
                          {"bufferView": 1, "componentType": 5123, "type": "SCALAR", "count": 12}]}
    js = json.dumps(kopf).encode()
    js += b" " * (-len(js) % 4)
    binaer += b"\0" * (-len(binaer) % 4)
    body = struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(binaer), b"BIN\0") + binaer
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def _kopf(dpm: bytes) -> dict:
    n = struct.unpack("<I", dpm[4:8])[0]
    return json.loads(dpm[8:8 + n])


def test_profil_und_sicherheitspruefung():
    from duckpilot.figuren import figur, ist_ente
    from duckpilot.koerper_pruefung import bestanden, pruefen

    p = koerper.holen("wonderduck")
    assert p.fehler() == [] and p.familie == "ente" and {"beine", "kopf", "schnabel", "tiefensensor"} <= p.faehigkeiten
    assert p.lizenz == "Apache-2.0" and p.quelle == "https://github.com/Hiwonder/wonderduck" and "ungeprüft" in p.echt
    assert figur("wonderduck")["name"] == "Wondi" and ist_ente("wonderduck")
    assert bestanden(asyncio.run(pruefen(p.bauen(type("C", (), {"backend": "sim", "sim_physik": False})()), p)))


def test_simulator_nur_was_sie_kann():
    from duckpilot.backends.wonderduck import WonderduckSim

    async def go():
        sim = WonderduckSim(realtime=False)
        await sim.connect()
        await sim.init()
        return sim, await sim.do("roulade"), await sim.do("kick_left")

    sim, purzel, schuss = asyncio.run(go())
    assert sim.state().koerper == "wonderduck" and sim.skills() == ["sit_toggle", "ground_pick"]
    assert not purzel.accepted and not schuss.accepted and "WonderDuck" in purzel.reason


def test_physik_gibt_es_noch_nicht_und_echt_ueber_robotd():
    from duckpilot.backends import baue_wonderduck
    from duckpilot.backends.robotd import RobotdBackend

    sim = baue_wonderduck(type("C", (), {"backend": "sim", "sim_physik": True})())
    assert "Physik" in sim.limited_by[0]
    cfg = type("C", (), {"backend": "robotd", "robot": "tcp:127.0.0.1:1", "tof": None, "head_signs": None, "updater": None})()
    echt = baue_wonderduck(cfg)
    assert isinstance(echt, RobotdBackend) and echt.koerper_art == "wonderduck" and echt.state().koerper == "wonderduck"


def test_modell_aus_dem_glb_mit_gelenken_stand_und_fuessen(tmp_path):
    glb = tmp_path / "w.glb"
    glb.write_bytes(_glb())
    out = W.bake(glb, tmp_path / "w.dpm")
    h = _kopf((tmp_path / "w.dpm").read_bytes())
    assert out["teile"] == 16 and h["art"] == "wonderduck" and "CC BY-NC-SA" in h["licence"]
    gelenke = {b["joint"]: b for b in h["bodies"] if "joint" in b}
    assert set(gelenke) == set(W.JOINT_NAMES) and gelenke["left_knee"]["axis"] == [0, -1, 0]
    assert h["poses"]["stand"]["left_hip_pitch"] == pytest.approx(-0.3865, abs=1e-3)      # Ruhelage aus dem Modell
    um = h["von_microduck"]
    assert um["vorzeichen"] == [1] * 15 and um["stand"] == W.STAND_MICRODUCK
    sites = {k for b in h["bodies"] for k in b.get("sites", {})}
    assert {"left_foot", "right_foot", "head_camera"} <= sites
    assert h["bodies"][0]["parent"] == -1 and h["bodies"][0]["pos"] == [0.0, 0.0, 0.0]   # ohne world_y_up


def test_fehlt_ein_gelenk_bricht_das_backen_ab(tmp_path):
    kaputt = _glb().replace(b"joint_mouth", b"joint_xxxxx")
    (tmp_path / "w.glb").write_bytes(kaputt)
    with pytest.raises(KeyError):
        W.bake(tmp_path / "w.glb", tmp_path / "w.dpm")


def test_laden_nur_mit_passender_pruefsumme_und_nie_offline(tmp_path, monkeypatch):
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    store = W.WonderduckModellStore(tmp_path, fetch=lambda url: b"fremd")
    with pytest.raises(ValueError, match="Prüfsumme"):
        store.ensure()
    assert store.view_path() is None and not (store.dir / "quelle.glb").exists()
    monkeypatch.setenv("DUCKPILOT_OFFLINE", "1")
    assert not store.missing()
    with pytest.raises(RuntimeError, match="Offline"):
        store.ensure()
    assert W.RAW.startswith("https://raw.githubusercontent.com/Hiwonder/wonderduck_studio/531d4f86")


def test_laden_backt_und_raeumt_die_quelle_weg(tmp_path, monkeypatch):
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    daten = _glb()
    monkeypatch.setitem(W.QUELLE, "sha256", __import__("hashlib").sha256(daten).hexdigest())
    store = W.WonderduckModellStore(tmp_path, fetch=lambda url: daten)
    schritte = []
    out = store.ensure(schritte.append)
    assert out["teile"] == 16 and store.view_path() is not None and not (store.dir / "quelle.glb").exists()
    assert store.ensure() == {} and len(schritte) == 2 and store.status()["ansicht"] == "geladen"


def test_routen_und_handy_sperre(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "daten"))
    monkeypatch.setenv("DUCKPILOT_OFFLINE", "1")
    rt = Runtime(load(memory_path=str(tmp_path / "m.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        s = c.get("/api/wonderduck").json()
        assert s["ok"] and not s["aktiv"] and s["ansicht"] is None and "Hiwonder" in s["repo"]
        assert c.get("/api/modell/wonderduck.dpm").status_code == 404
    assert remote.pc_only("POST", "/api/wonderduck/laden") and not remote.pc_only("GET", "/api/modell/wonderduck.dpm")



def test_verbindungstest_prueft_sie_wie_die_microduck(monkeypatch):
    from duckpilot import verbindungstest as V

    gerufen = []

    async def microduck(adresse):
        gerufen.append(adresse)
        return {"ok": True}

    monkeypatch.setattr(V, "pruefe_microduck", microduck)
    assert "wonderduck" in V.KOERPER and asyncio.run(V.pruefen("wonderduck", "tcp:1.2.3.4:7900"))["ok"]
    assert gerufen == ["tcp:1.2.3.4:7900"]
    assert V.fehlende_funktionen(62) == ["Fotos der Ente ansehen und löschen", "Lautstärke einstellen",
                                        "sehen, welches Spiel der Ente gerade läuft", "ein Foto machen lassen"]
