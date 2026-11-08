"""Kamera, Enten-Erkenner, Roboter-Pflege und Training (alles gegen Test-Gegenstellen)."""

import asyncio
import io
import tarfile

import numpy as np
import pytest

from duckpilot import training as T
from duckpilot.care import RobotCare, guess
from duckpilot.vision import fetch_frame, to_bmp, uyvy_to_rgb


def test_uyvy_conversion_and_rotation():
    w, h = 8, 4
    frame = bytes([128, 126, 128, 126]) * (w // 2 * h)            # mittelgrau, keine Farbe
    rgb = uyvy_to_rgb(frame, w, h)
    assert rgb.shape == (4, 8, 3) and np.all(np.abs(rgb.astype(int) - 128) <= 2)
    assert uyvy_to_rgb(frame, w, h, rotate=90).shape == (8, 4, 3)
    big = bytes([128, 200, 128, 200]) * (1280 // 2 * 720)
    assert max(uyvy_to_rgb(big, 1280, 720, max_side=640).shape[:2]) <= 640
    with pytest.raises(ValueError):
        uyvy_to_rgb(b"\0" * 10, 8, 4)
    bmp = to_bmp(rgb)
    assert bmp[:2] == b"BM" and int.from_bytes(bmp[18:22], "little") == 8


def test_duck_detector_decodes_and_suppresses(tmp_path):
    onnx = pytest.importorskip("onnx")
    from onnx import TensorProto, helper, numpy_helper

    # Kopf [1, 5, 4]: zwei fast gleiche Kästen (einer fällt weg), ein schwacher, einer links
    head = np.array([[[160, 162, 100, 60], [160, 160, 100, 160], [40, 40, 30, 40], [80, 80, 30, 80],
                      [0.9, 0.8, 0.2, 0.7]]], np.float32)
    nodes = [helper.make_node("ReduceMean", ["images"], ["m"], keepdims=0),
             helper.make_node("Mul", ["m", "zero"], ["z"]),
             helper.make_node("Add", ["head", "z"], ["output0"])]
    graph = helper.make_graph(nodes, "det", [helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, 320, 320])],
                              [helper.make_tensor_value_info("output0", TensorProto.FLOAT, [1, 5, 4])],
                              [numpy_helper.from_array(head, "head"), numpy_helper.from_array(np.zeros((), np.float32), "zero")])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.save(model, tmp_path / "d.onnx")
    from duckpilot.vision import DuckDetector

    det = DuckDetector(tmp_path / "d.onnx")
    rgb = np.zeros((320, 640, 3), np.uint8)                       # breiter als hoch: oben/unten aufgefüllt
    found = det.detect(rgb)
    assert len(found) == 2
    assert found[0]["wert"] == 0.9 and found[0]["richtung_grad"] == 0     # Mitte
    assert found[1]["richtung_grad"] > 0                                  # links im Bild = links
    assert found[0]["box"][1] < found[0]["box"][3]


def test_camera_and_care_against_the_test_robot(tmp_path):
    from duckpilot.backends.fake_robotd import start_server

    async def go():
        server, fake = await start_server("tcp:127.0.0.1:7987")
        try:
            head, data = await fetch_frame("tcp:127.0.0.1:7987")
            assert head["format"] == "UYVY" and len(data) == head["bytes"]

            class Cfg:
                robot = "tcp:127.0.0.1:7987"
                updater = "tcp:127.0.0.1:7987"
                configd = "tcp:127.0.0.1:7987"

            care = RobotCare(Cfg())
            ov = await care.overview()
            assert ov["pflegeheft"]["ok"] and ov["pflegeheft"]["daten"]["zuerst_ansehen"] == ["Rechtes Knie"]
            assert ov["gesundheit"]["ok"] and ov["system"]["daten"]["name"] == "duck-test"
            assert ov["netz"]["daten"]["ssid"] == "Heimnetz" and ov["updates"]["ok"]
            assert (await care.check())["state"] == "available"
            job = await care.apply(dry_run=True)
            assert job["ergebnis"]["outcome"] == "dry_run_passed"
            job = await care.apply(dry_run=False)
            assert "sudo robotctl update apply daemon" in job["fehler"]
            logs = await care.logs("mediad", 20)
            assert logs["unit"] == "mediad" and len(logs["lines"]) == 20
            with pytest.raises(ValueError):
                await care.logs("rm -rf", 5)
        finally:
            server.close()
            await fake.sim.close()
    asyncio.run(go())
    assert guess("tcp:127.0.0.1:7900", 4) == "tcp:127.0.0.1:7904" and guess("unix:/run/x", 3) is None


def test_training_plan_rules():
    plan = T.check_plan("Mjlab-Spin-Flat-MicroDuck", None, {"env.rewards.upright.weight": 2, "agent.learning_rate": "3e-4"})
    assert plan["iterationen"] == 2000 and plan["anpassungen"]["env.rewards.upright.weight"] == "2"
    args = T.train_args(plan, wandb=False)
    assert args[:1] == ["Mjlab-Spin-Flat-MicroDuck"] and "--agent.logger" in args and "tensorboard" in args
    for bad in ({"env.rewards.x.weight": "1; rm -rf /"}, {"--agent.resume": "true"}, {"env.scene.num_envs": "9"},
                {"$(whoami)": "1"}):
        with pytest.raises(ValueError):
            T.check_plan("Mjlab-Spin-Flat-MicroDuck", 500, bad)
    with pytest.raises(ValueError):
        T.check_plan("Mjlab-Evil", 500)
    with pytest.raises(ValueError):
        T.check_plan("Mjlab-Spin-Flat-MicroDuck", 50)


def _github_tarball() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in (("microduck_rl-main/pyproject.toml", b"[project]"), ("microduck_rl-main/scripts/export.py", b"x"),
                           ("microduck_rl-main/../evil", b"!")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_repack_and_submit_with_a_fake_hub(tmp_path, monkeypatch):
    pytest.importorskip("huggingface_hub")
    packed = T.repack_tarball(_github_tarball())
    names = tarfile.open(fileobj=io.BytesIO(packed), mode="r:gz").getnames()
    assert sorted(names) == ["pyproject.toml", "scripts/export.py"]

    calls = []

    class Job:
        id = "job123"
        url = "https://huggingface.co/jobs/alex/job123"

    class Status:
        stage = "RUNNING"
        message = None

    class FakeApi:
        def whoami(self):
            return {"name": "alex", "orgs": [{"name": "entenclub"}]}

        def create_repo(self, *a, **k):
            calls.append(("repo", a, k))

        def upload_file(self, **k):
            calls.append(("upload", k["path_in_repo"], k["repo_id"]))

        def run_job(self, **k):
            calls.append(("job", k))
            return Job()

        def inspect_job(self, job_id, namespace):
            return type("J", (), {"status": Status()})()

    tr = T.Trainer(tmp_path, api_factory=lambda token: FakeApi(), fetch=lambda url: _github_tarball())
    plan = T.check_plan("Mjlab-Roulade-Flat-MicroDuck", 1000, {"env.rewards.upright.weight": "1.5"})
    run = tr.submit(plan, "hf_" + "x" * 30, None)
    assert run["job"] == "job123" and run["ckpt_repo"].startswith("alex/mjlab-roulade-flat-microduck-")
    job = next(c[1] for c in calls if c[0] == "job")
    assert job["flavor"] == "l4x1" and job["env"]["TRAIN_ARGS"].startswith("Mjlab-Roulade-Flat-MicroDuck")
    assert "--env.rewards.upright.weight 1.5" in job["env"]["TRAIN_ARGS"]
    assert job["secrets"]["HF_TOKEN"].startswith("hf_") and "WANDB_API_KEY" not in job["secrets"]
    assert job["volumes"][0].source == "alex/mjlab-microduck-src"
    with pytest.raises(T.TrainingError):
        tr.submit(plan, "hf_" + "x" * 30, "fremdes-konto")
    runs = tr.refresh("hf_" + "x" * 30)
    assert runs[0]["status"] == "trainiert"

    # huggingface_hub < 1.0 (wie es Qwen3-TTS braucht): kein Volume, kein follow/tail – der Job lädt selbst
    import sys
    import types

    monkeypatch.setitem(sys.modules, "huggingface_hub", types.ModuleType("huggingface_hub"))
    calls.clear()
    run2 = tr.submit(plan, "hf_" + "x" * 30, None)
    job2 = next(c[1] for c in calls if c[0] == "job")
    assert "volumes" not in job2 and job2["env"]["SRC_REPO"] == "alex/mjlab-microduck-src"
    assert 'SRC_FILE="/src/$SRC_TARBALL"' in T.BOOTSTRAP and "$SRC_REPO/resolve/main" in T.BOOTSTRAP
    with pytest.raises(ValueError):
        T.Trainer._logs_http("t", "../x", "job", 5)
    FakeApi.fetch_job_logs = lambda self, job_id, namespace: iter(["nie"])
    monkeypatch.setattr(T.Trainer, "_logs_http", staticmethod(lambda token, ns, job, lines: ["a", "b"]))
    assert tr.logs("hf_" + "x" * 30, run2["id"]) == ["a", "b"]


def test_server_guards_for_robot_only_and_training(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        assert c.get("/api/pflege").status_code == 400
        assert c.get("/api/kamera/bild").status_code == 404
        st = c.get("/api/training").json()
        assert "Mjlab-Spin-Flat-MicroDuck" in st["aufgaben"] and st["token"] is None
        r = c.post("/api/training/start", json={"aufgabe": "Mjlab-Spin-Flat-MicroDuck"})
        assert r.status_code == 400 and "Token" in r.json()["fehler"]
        assert c.post("/api/training/start", json={"aufgabe": "x"}).status_code == 400
        assert c.post("/api/training/token", json={"token": "nope"}).status_code == 400
        assert any(t["name"] == "training_vorschlagen" for t in rt.runner.tools())

        async def propose():
            return await rt.runner.run("training_vorschlagen", {"aufgabe": "Mjlab-Spin-Flat-MicroDuck",
                                                                "begruendung": "Pirouette für die Show"})
        out = asyncio.run(propose())
        assert out["ok"] and c.get("/api/training").json()["vorschlag"]["aufgabe"] == "Mjlab-Spin-Flat-MicroDuck"
        assert c.post("/api/training/vorschlag/verwerfen").json()["ok"]
        detector = next(p for p in c.get("/api/skills").json()["pakete"] if p["id"] == "duck_detector")
        assert detector["verfuegbar"] and detector["werkzeug"] == "andere_enten"


def test_camera_picture_can_be_made_small_for_the_phone_controller(tmp_path, monkeypatch):
    """Controller am Handy: das Live-Bild kommt verkleinert (jedes n-te Pixel), damit es durchs WLAN passt."""
    import struct

    from fastapi.testclient import TestClient

    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    rgb = np.zeros((480, 640, 3), np.uint8)

    async def picture():
        rt.camera.last_rgb = rgb
        return to_bmp(rgb), {"breite": 640, "hoehe": 480, "enten": None}

    monkeypatch.setattr(rt, "camera_address", lambda: "tcp:127.0.0.1:1")
    monkeypatch.setattr(rt.camera, "picture", picture)
    size = lambda b: struct.unpack("<ii", b[18:26])
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        assert size(c.get("/api/kamera/bild").content) == (640, 480)
        small = c.get("/api/kamera/bild?breite=320")
        assert small.headers["content-type"] == "image/bmp" and size(small.content) == (320, 240)
        assert size(c.get("/api/kamera/bild?breite=5000").content) == (640, 480)     # nie größer als das Original
        assert size(c.get("/api/kamera/bild?breite=1").content) == (80, 60)          # nie winziger als 80 px
