"""Selbst lernen am PC: ONNX ↔ PyTorch, Übungswelt, PPO-Lauf mit Rechenprozessen, Export."""

import importlib.util
import json
import time

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("onnxruntime")
pytest.importorskip("onnx")

from onnx_fixtures import linear_policy  # noqa: E402
from test_physics import make_store  # noqa: E402

from duckpilot.physics import course as K  # noqa: E402
from duckpilot.physics import lernen as L  # noqa: E402
from duckpilot.physics.core import Policy  # noqa: E402

needs_torch = pytest.mark.skipif(importlib.util.find_spec("torch") is None, reason="PyTorch fehlt")


def mlp_policy(path, seed=0, hidden=(32, 16), normalize=True, gemm=True):
    """Ein MLP wie rsl_rl es exportiert: (obs − mean) / std → Gemm/Elu → … → actions."""
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    rng = np.random.default_rng(seed)
    inits, nodes = [], []
    x = "obs"
    if normalize:
        inits += [numpy_helper.from_array(rng.normal(0, 0.1, 61).astype(np.float32), "mean"),
                  numpy_helper.from_array(rng.uniform(0.5, 2, 61).astype(np.float32), "std")]
        nodes += [helper.make_node("Sub", ["obs", "mean"], ["centered"]),
                  helper.make_node("Div", ["centered", "std"], ["normed"])]
        x = "normed"
    sizes = [61, *hidden, 14]
    for i, (a, b) in enumerate(zip(sizes, sizes[1:])):
        w = (rng.normal(0, 1, (a, b)) / np.sqrt(a) * 0.3).astype(np.float32)
        bias = rng.normal(0, 0.05, b).astype(np.float32)
        out = "actions" if i == len(sizes) - 2 else f"h{i}"
        lin = out if out == "actions" else f"lin{i}"
        if gemm:          # torch.onnx.export: Gemm mit transB
            inits += [numpy_helper.from_array(w.T.copy(), f"W{i}"), numpy_helper.from_array(bias, f"b{i}")]
            nodes.append(helper.make_node("Gemm", [x, f"W{i}", f"b{i}"], [lin], transB=1))
        else:
            inits += [numpy_helper.from_array(w, f"W{i}"), numpy_helper.from_array(bias, f"b{i}")]
            nodes += [helper.make_node("MatMul", [x, f"W{i}"], [f"mm{i}"]), helper.make_node("Add", [f"mm{i}", f"b{i}"], [lin])]
        if out != "actions":
            nodes.append(helper.make_node("Elu", [lin], [out], alpha=1.0))
        x = out
    graph = helper.make_graph(nodes, "policy", [helper.make_tensor_value_info("obs", TensorProto.FLOAT, [1, 61])],
                              [helper.make_tensor_value_info("actions", TensorProto.FLOAT, [1, 14])], inits)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.save(model, str(path))
    return path


def test_available_names_missing_torch(monkeypatch):
    monkeypatch.setattr(L, "_find_spec", lambda name: None if name == "torch" else object())
    ok, why = L.available()
    assert not ok and why.startswith("PyTorch fehlt")
    monkeypatch.setattr(L, "_find_spec", lambda name: object())
    assert L.available() == (True, "bereit")


def test_netz_reads_mlp_and_rejects_unsupported(tmp_path):
    net = L.lade_netz(mlp_policy(tmp_path / "mlp.onnx"))
    assert net.lernbar == ["W0", "b0", "W1", "b1", "W2", "b2"]          # Normierung bleibt fest
    assert net.obs_form == [1, 61] and net.out_form == [1, 14]
    obs = np.random.default_rng(1).normal(size=(5, 61)).astype(np.float32)
    pol = Policy(net.pfad)
    want = np.stack([pol.act(o) for o in obs])
    assert np.allclose(L.netz_numpy(net, obs), want, atol=1e-5)
    # MatMul + Add wie im Test-Fixture
    assert L.lade_netz(linear_policy(tmp_path / "lin.onnx")).lernbar == ["W", "B"]
    with pytest.raises(L.LernFehler, match="LSTM"):
        L.lade_netz(linear_policy(tmp_path / "rec.onnx", recurrent=True))
    import onnx
    from onnx import helper

    m = onnx.load(str(tmp_path / "lin.onnx"))
    m.graph.node.append(helper.make_node("Sin", ["actions"], ["sin"]))
    onnx.save(m, str(tmp_path / "sin.onnx"))
    with pytest.raises(L.LernFehler, match="Baustein „Sin“"):
        L.lade_netz(tmp_path / "sin.onnx")


@needs_torch
def test_onnx_to_torch_matches_onnxruntime_and_exports_back(tmp_path):
    import torch

    for gemm in (True, False):
        path = mlp_policy(tmp_path / f"mlp{gemm}.onnx", seed=3, gemm=gemm)
        net = L.lade_netz(path)
        model = L.onnx_nach_torch(net)
        assert sum(p.numel() for p in model.parameters()) == sum(net.tensoren[n].size for n in net.lernbar)
        obs = np.random.default_rng(2).normal(size=(7, 61)).astype(np.float32)
        pol = Policy(path)
        want = np.stack([pol.act(o) for o in obs])
        got = model(torch.tensor(obs)).detach().numpy()
        assert np.abs(got - want).max() < 1e-5
        # Gewichte ändern, exportieren: onnxruntime rechnet dasselbe wie torch, Ein-/Ausgänge bleiben gleich
        with torch.no_grad():
            for p in model.parameters():
                p.add_(0.01 * torch.randn_like(p))
        out = L.torch_nach_onnx(net, model.gewichte(), tmp_path / "neu.onnx")
        again = L.lade_netz(out)
        assert again.obs_form == net.obs_form and again.out_form == net.out_form
        pol2 = Policy(out)
        want2 = np.stack([pol2.act(o) for o in obs])
        assert np.abs(model(torch.tensor(obs)).detach().numpy() - want2).max() < 1e-5
        assert np.abs(want2 - want).max() > 1e-4                       # wirklich andere Gewichte


def test_practice_world_steps_rewards_and_ends(tmp_path):
    spec = {"name": "Mini", "elemente": [{"art": "schwelle", "hoehe_cm": 1}, {"art": "rampe", "hoehe_cm": 2}]}
    env = L._Umgebung(spec, 1.0, np.random.default_rng(0), None)
    assert env.obs.shape == (61,) and env.mitten          # Starts vor dem zweiten Element möglich
    ends, rewards = [], []
    for _ in range(400):                                   # Nullaktion: die Ente sackt zusammen
        r, term, trunc, last, ber = env.step(np.zeros(14, np.float32))
        rewards.append(r)
        if ber:
            ends.append(ber)
            assert term and not trunc and last is None
    assert ends and ends[0]["ende"] == "sturz" and all(np.isfinite(rewards))
    flat = L._Umgebung(None, 1.0, np.random.default_rng(1), None)
    assert flat.goal == (L.EBEN_LAENGE, 0.0) and flat.limit == L.EBEN_ZEIT_S


def test_sources_and_resolve(tmp_path):
    make_store(tmp_path)
    assert L.quellen(tmp_path)[0]["id"] == "standard"
    path, scale, _ = L.aufloesen(tmp_path, "standard")
    assert path.name == "velstand.onnx" and scale == 1.0
    for bad in ("lokal:../x", "lokal:lokal-gibtsnicht", "lauf:x", "irgendwas"):
        with pytest.raises(L.LernFehler):
            L.aufloesen(tmp_path, bad)


@needs_torch
def test_local_training_smoke_runs_stops_and_exports(tmp_path):
    store = make_store(tmp_path)
    mlp_policy(store.official / "velstand.onnx", seed=5, hidden=(16,))
    spec = {"name": "Mini", "elemente": [{"art": "schwelle", "hoehe_cm": 1}]}
    trainer = L.LocalTrainer(tmp_path)
    with pytest.raises(L.LernFehler):
        trainer.start(spec, "standard", 0.0, "x")
    with pytest.raises(ValueError):
        trainer.start({"elemente": [{"art": "trampolin"}]}, "standard", 1, "x")
    t0 = time.monotonic()
    st = trainer.start(spec, "standard", minuten=0.75, name="Schwelle üben", workers=2, umgebungen=2, geraet="cpu")
    assert st["laeuft"] and st["prozesse"] == 2 and st["umgebungen"] == 4
    with pytest.raises(L.LernFehler, match="schon"):
        trainer.start(spec, "standard", 1, "noch einer")
    while time.monotonic() - t0 < 40:
        st = trainer.status()
        if st["iteration"] >= L.KRITIKER_AUFWAERMEN + 3 or not st["laeuft"]:
            break
        time.sleep(0.3)
    assert st["laeuft"], st["fehler"]
    assert st["geraet"].startswith("Prozessor") and st["phase"] in ("lernt", "wärmt den Kritiker auf")
    end = trainer.stop()
    assert time.monotonic() - t0 < 60
    assert not end["laeuft"] and end["fehler"] is None and end["phase"].startswith("beendet")
    for k in ("iteration", "schritte", "minuten", "geraet", "kurve", "faehigkeit", "im_ziel", "bester", "ergebnis"):
        assert k in end
    assert end["iteration"] >= L.KRITIKER_AUFWAERMEN + 1 and end["schritte"] == end["iteration"] * 4 * L.ROLLOUT_STEPS
    pts = end["kurve"]
    assert len(pts) == end["iteration"] and pts[-1]["iteration"] == end["iteration"]
    assert set(pts[0]) >= {"iteration", "belohnung", "faehigkeit", "im_ziel_anteil"}
    assert end["faehigkeit"] is None or 0 <= end["faehigkeit"] <= 100
    # Export: läuft im Policy-Satz und auf dem Parcours, gleiche Ein-/Ausgänge wie die Start-Policy
    assert end["ergebnis"].startswith("lokal:lokal-schwelle-ueben-")
    path, _, label = L.aufloesen(tmp_path, end["ergebnis"])
    assert path.parent == tmp_path / "policies" / "lokal" and label.startswith("Selbst gelernt")
    start, neu = L.lade_netz(store.official / "velstand.onnx"), L.lade_netz(path)
    assert (start.obs_form, start.out_form, start.obs_name, start.out_name) == \
           (neu.obs_form, neu.out_form, neu.obs_name, neu.out_name)
    meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["job"] == end["id"] and meta["parcours"]["name"] == "Mini"
    res = K.evaluate(K.build(spec), str(path), attempts=1, max_seconds=2)
    assert res["versuche"] == 1
    assert any(q["id"] == end["ergebnis"] for q in L.quellen(tmp_path))
    # nach einem Neustart: Kurve und Verlauf sind noch da
    again = L.LocalTrainer(tmp_path)
    st2 = again.status()
    assert st2["id"] == end["id"] and len(st2["kurve"]) == len(pts) and st2["ergebnis"] == end["ergebnis"]
    hist = again.history()
    assert hist[0]["id"] == end["id"] and hist[0]["punkte"] == len(pts) and "kurve" not in hist[0]
    assert not (tmp_path / "lernen" / end["id"]).exists()          # Zwischenstand aufgeräumt
