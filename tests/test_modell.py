"""Pollens Robotermodell: von der Originalquelle geladen (Prüfsummen), auf dem PC gebaut, nie mitverteilt."""

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duckpilot import modell as M
from duckpilot import remote as R
from duckpilot import settings as S
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app

REF = Path("/root/ref/microduck_rl/src/mjlab_microduck/robot/microduck")


def _ref_da() -> bool:
    """Pollens Quellen lokal? Auf fremden Rechnern (z. B. GitHub-Prüfung ohne root) darf schon das Nachsehen scheitern."""
    try:
        return REF.exists()
    except OSError:
        return False


def fake_fetch(files: dict[str, bytes], calls: list | None = None):
    def fetch(url: str) -> bytes:
        assert url.startswith(M.RAW + "/"), url               # nur der feste Stand bei Pollen
        name = url[len(M.RAW) + 1:]
        if calls is not None:
            calls.append(name)
        return files[name]
    return fetch


def test_sources_are_pinned_and_checked():
    assert M.REPO == "pollen-robotics/microduck_rl" and len(M.COMMIT) == 40
    assert "/" + M.COMMIT + "/" in M.RAW
    names = list(M.QUELLEN["dateien"])
    assert {"robot_walk.xml", "robot_groundcontact.xml", "scene.xml"} <= set(names)
    assert all(M.SAFE.fullmatch(n) for n in names)
    assert all(len(v["sha256"]) == 64 for v in M.QUELLEN["dateien"].values())


def test_wrong_checksum_aborts_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    files = {n: b"falsch" for n in M.QUELLEN["dateien"]}
    st = M.ModellStore(tmp_path, fetch=fake_fetch(files), packaged=False)
    with pytest.raises(ValueError, match="Prüfsumme"):
        st.download()
    assert not any(st.src.rglob("*.stl")) and not any(st.src.rglob("*.xml"))


def test_download_skips_files_already_there(tmp_path, monkeypatch):
    names = list(M.QUELLEN["dateien"])[:2]
    data = {n: f"inhalt {n}".encode() for n in names}
    monkeypatch.setattr(M, "QUELLEN", {**M.QUELLEN, "dateien": {
        n: {"sha256": hashlib.sha256(d).hexdigest(), "bytes": len(d)} for n, d in data.items()}})
    calls: list = []
    st = M.ModellStore(tmp_path, fetch=fake_fetch(data, calls), packaged=False)
    assert st.download() == 2 and sorted(calls) == sorted(names)
    assert st.download() == 0 and len(calls) == 2
    assert st.sources_ok()


def test_offline_and_packaged_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("DUCKPILOT_MODELL", raising=False)
    st = M.ModellStore(tmp_path, fetch=lambda u: pytest.fail("kein Netz"), packaged=False)
    assert st.view_path() is None and st.physics_path() is None
    assert not st.missing()                                   # offline (conftest): nichts nachladen
    with pytest.raises(RuntimeError, match="Offline"):
        st.ensure(physics=False)
    monkeypatch.delenv("DUCKPILOT_OFFLINE")
    assert st.missing()
    # eigener Bau im Datenordner geht vor das Paket
    own = M.ModellStore(tmp_path)
    (own.dir).mkdir(parents=True)
    (own.dir / "ansicht.dpm").write_bytes(b"DPM2")
    assert own.view_path() == own.dir / "ansicht.dpm"
    assert own.status()["ansicht"] == "geladen" and own.status()["repo"] == M.REPO


@pytest.mark.skipif(not _ref_da(), reason="Pollens Quellen liegen nicht lokal vor")
def test_build_from_pollens_files_matches_private_build(tmp_path, monkeypatch):
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    files = {n: (REF / n).read_bytes() for n in M.QUELLEN["dateien"]}
    st = M.ModellStore(tmp_path, fetch=fake_fetch(files), packaged=False)
    res = st.ensure()
    assert res["geladen"] == len(files)
    if M.PACKAGED_VIEW.exists():
        assert (st.dir / "ansicht.dpm").read_bytes() == M.PACKAGED_VIEW.read_bytes()
    if "physik" in res:
        mujoco = pytest.importorskip("mujoco")
        assert res["physik"]["nu"] == 14 and abs(res["physik"]["masse"] - 0.737) < 0.01
        m = mujoco.MjModel.from_xml_path(str(st.physics_path()))
        assert m.ngeom == 11 and "quelle/assets" in st.physics_path().read_text(encoding="utf-8")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "s.json"))
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "m.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        yield c, rt


def test_routes_serve_model_and_status(client, tmp_path, monkeypatch):
    c, rt = client
    monkeypatch.delenv("DUCKPILOT_MODELL", raising=False)
    st = c.get("/api/modell").json()
    assert st["type"] == "modell" and st["repo"] == M.REPO and "lizenz" in st
    monkeypatch.setattr(M, "PACKAGED_VIEW", tmp_path / "fehlt.dpm")
    assert c.get("/api/modell/ansicht.dpm").status_code == 404
    rt.modell.dir.mkdir(parents=True, exist_ok=True)
    (rt.modell.dir / "ansicht.dpm").write_bytes(b"DPM2test")
    r = c.get("/api/modell/ansicht.dpm")
    assert r.status_code == 200 and r.content == b"DPM2test"
    assert R.pc_only("POST", "/api/modell/laden") and not R.pc_only("GET", "/api/modell/ansicht.dpm")
    init = json.loads(json.dumps(rt.init_message(), default=str))
    assert init["config"]["modell"]["repo"] == M.REPO


def test_shared_model_folder_is_found_but_never_written(tmp_path, monkeypatch):
    shared = tmp_path / "geteilt"
    shared.mkdir()
    (shared / "physik.xml").write_text("<mujoco/>")
    monkeypatch.setenv("DUCKPILOT_MODELL", str(shared))
    st = M.ModellStore(tmp_path / "daten")
    assert st.physics_path() == shared / "physik.xml"
    assert st.dir == tmp_path / "daten" / "pollen-modell"            # gebaut wird nur im eigenen Datenordner
    assert M.ModellStore(tmp_path / "daten", packaged=False).physics_path() is None
