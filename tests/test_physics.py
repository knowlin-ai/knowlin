"""Echte Physik: Pollens MuJoCo-Modell, Policy-Schleife, Policy-Satz, Üben."""

import asyncio
import json

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")
pytest.importorskip("onnxruntime")
pytest.importorskip("onnx")

from onnx_fixtures import linear_policy  # noqa: E402

from duckpilot.backends.world import World  # noqa: E402
from duckpilot.physics import core as C  # noqa: E402
from duckpilot.physics.policies import PolicyStore, role_of  # noqa: E402

MANIFEST = {"schema_version": 2, "policies": [
    {"file": "velstand.onnx", "name": "velstand", "kind": "perpetual", "slot": "walk"},
    {"file": "alpha_sitstand.onnx", "kind": "scripted", "command": {"encoding": "posture_flag"}, "unwind_s": 2.0},
    {"file": "ball_kick_left.onnx", "name": "kick_left", "kind": "episodic", "duration_s": 3.0},
    {"file": "roulade.onnx", "kind": "episodic", "duration_s": 2.0},
    {"file": "alpha_ground_pick.onnx", "command": {"encoding": "phase", "period_s": 4.0, "end_phase": 0.7}},
    {"file": "roller_pick.onnx", "mode": "roller", "command": {"encoding": "phase"}},
    {"file": "../evil.onnx", "name": "walk"},
]}


def make_store(tmp_path, roles=("velstand", "alpha_sitstand", "ball_kick_left", "roulade", "alpha_ground_pick")):
    off = tmp_path / "policies" / "pollen"
    off.mkdir(parents=True)
    (off / "manifest.json").write_text(json.dumps(MANIFEST))
    for f in roles:
        linear_policy(off / f"{f}.onnx")
    return PolicyStore(tmp_path)


def test_baked_model_matches_pollens_robot():
    m = mujoco.MjModel.from_xml_path(str(C.model_xml()))
    assert m.nu == 14 and m.nq == 21
    assert [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, i) for i in range(m.nu)] == list(C.ACTUATORS)
    assert abs(m.body_subtreemass[1] - 0.737) < 0.01
    for s in ("imu_ang_vel", "imu_accel"):
        assert mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SENSOR, s) >= 0
    for site in ("imu", "head_camera", "tof", "left_foot", "right_foot"):
        assert mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, site) >= 0
    assert C.model_xml().stat().st_size < 1_500_000   # ohne Darstellungsteile


def test_policy_wrapper_feedforward_recurrent_and_rejects(tmp_path):
    ff = C.Policy(linear_policy(tmp_path / "a.onnx", bias=np.full(14, 0.1)))
    assert np.allclose(ff.act(np.zeros(61, np.float32)), 0.1)
    rec = C.Policy(linear_policy(tmp_path / "r.onnx", recurrent=True))
    assert rec.recurrent and rec.h.sum() == 0         # nach dem Laden zurückgesetzt
    rec.act(np.zeros(61, np.float32))
    rec.act(np.zeros(61, np.float32))
    assert rec.h.ravel()[0] == 2.0
    rec.reset()
    assert rec.h.sum() == 0
    with pytest.raises(C.PolicyError):
        C.Policy(linear_policy(tmp_path / "w.onnx", obs_len=51))
    with pytest.raises(C.PolicyError):
        C.Policy(linear_policy(tmp_path / "x.onnx", act_len=12))


def test_observation_layout_and_action_mapping(tmp_path):
    core = C.PhysicsCore(None)
    cmd = C.Command()
    cmd.twist[:] = [0.2, 0.0, 0.5]
    cmd.head[:] = [0.1, 0.2, 0.3, 0.05]
    obs = core.observation(cmd)
    assert obs.shape == (61,)
    assert np.allclose(obs[3:6], [0, 0, -1], atol=1e-3)              # aufrecht: Schwerkraft nach unten
    assert np.allclose(obs[6:20], 0, atol=1e-5)                       # Grundstellung
    assert np.allclose(obs[48:51], [0.2, 0, 0.5]) and np.allclose(obs[51:55], [0.1, 0.2, 0.3, 0.05])
    # Aktion = Abweichung von der Grundstellung; die letzte Aktion steht in der nächsten Beobachtung
    w = np.zeros((61, 14), np.float32)
    w[48, 7] = 1.0                                                   # Fahrbefehl vx → head_yaw
    core.set_policy(C.Policy(linear_policy(tmp_path / "p.onnx", weight=w, bias=np.full(14, 0.01))))
    core.control_step(cmd)
    assert abs(core.data.ctrl[7] - (C.DEFAULT_POSE[7] + 0.21)) < 1e-5
    assert abs(core.last_action[7] - 0.21) < 1e-5
    assert abs(core.observation(cmd)[34 + 7] - 0.21) < 1e-5
    assert core.steps == 1


def test_world_furniture_is_solid_and_limp_collapses():
    world = World.living_room()
    core = C.PhysicsCore(world)
    names = {mujoco.mj_id2name(core.model, mujoco.mjtObj.mjOBJ_GEOM, i) for i in range(core.model.ngeom)}
    assert {"boden", "m:Sofa", "m:Pflanze", "wand_n"} <= names
    core.reset(-0.6, -0.2, 0.0)
    core.set_limp(True)
    for _ in range(100):
        core.control_step(C.Command())
    assert core.trunk()["z"] < 0.1                                    # stromlos sackt sie zusammen
    core.set_limp(False)
    assert np.allclose(core.model.actuator_gainprm[:, 0], core.kp0)


def test_manifest_roles_and_safe_files(tmp_path):
    store = make_store(tmp_path)
    roles = store.roles()
    assert sorted(roles) == ["ground_pick", "kick_left", "roulade", "sitstand", "walk"]
    assert roles["walk"]["pfad"].name == "velstand.onnx"
    assert role_of({"file": "roller_pick.onnx", "mode": "roller", "command": {"encoding": "phase"}}) is None
    st = store.status()
    assert st["bereit"] and st["rollen"]["kick_right"] is False


def test_official_download_uses_only_listed_safe_files(tmp_path):
    files = {"manifest.json": json.dumps(MANIFEST).encode()}
    src = tmp_path / "src"
    src.mkdir()
    for f in ("velstand", "alpha_sitstand", "ball_kick_left", "roulade", "alpha_ground_pick"):
        files[f"{f}.onnx"] = linear_policy(src / f"{f}.onnx").read_bytes()
    asked = []

    def fetch(url):
        asked.append(url)
        name = url.rsplit("/", 1)[-1]
        if name not in files:
            raise OSError(f"404 {url}")
        return files[name]

    store = PolicyStore(tmp_path / "data", fetch=fetch)
    res = store.download_official()
    assert store.ready() and "roller_pick.onnx" not in res["dateien"]
    assert not any("evil" in u for u in asked)
    assert all(u.startswith("https://huggingface.co/pollen-robotics/microduck-policies/resolve/main/") for u in asked)


def test_physics_backend_falls_for_real_and_offers_policy_skills(tmp_path):
    from duckpilot.backends.physics import PhysicsBackend

    async def go():
        b = PhysicsBackend(make_store(tmp_path), realtime=False)
        b._task = object()
        events = []
        b.on_event(lambda e: events.append(e["type"]))
        assert set(b.skills()) == {"sit_toggle", "ground_pick", "kick_left", "roulade"}
        assert (await b.do("kick_right")).accepted is False
        assert b.core.policy is None or b.core.policy.name in ("walk", "velstand")
        for _ in range(200):                       # eine Null-Policy hält die Ente nicht: sie fällt wirklich
            b.step(0.02)
        st = b.state()
        assert st.fallen and "fall" in events
        assert len(st.body) == 3 and st.physik["policy"] == "walk"
        assert len(st.display_joints) == 15
        assert "steht gleich" in (await b.init()).reason
        b.reset_body()
        assert not b.state().fallen
        r = await b.do("roulade")
        assert r.accepted
        b.step(0.02)
        assert b.core.policy is b.policies["roulade"]
    asyncio.run(go())


def test_hub_trick_and_gait_run_in_physics(tmp_path):
    from duckpilot.backends.physics import PhysicsBackend

    src = tmp_path / "trick.onnx"
    linear_policy(src)
    man = {"name": "polite-bow", "kind": "episodic", "duration_s": 2.5, "obs_len": 61, "action_len": 14,
           "command": {"encoding": "constant", "idle": [0, 0, 0]}}
    gait_man = {"name": "sprint", "kind": "perpetual", "slot": "walk"}

    def fetch(url):
        if url.endswith("manifest.json"):
            return json.dumps(gait_man if "sprint" in url else man).encode()
        return src.read_bytes()

    async def go():
        store = make_store(tmp_path)
        store.fetch = fetch
        b = PhysicsBackend(store, realtime=False)
        b._task = object()
        res = await b.add_trick("someone/microduck-polite-bow")
        assert res.accepted and "polite-bow" in b.skills()
        b.reset_body()
        assert (await b.do("polite-bow")).accepted
        b.step(0.02)
        assert b.core.policy is b.tricks["polite-bow"]
        assert abs(b._skill_len("polite-bow") - 2.5) < 1e-6
        assert (await b.load_gait("arena/microduck-sprint")).accepted
        assert b.gait_policy is not None
        assert (await b.reset_gait()).accepted and b.gait_policy is None
        bad = await b.add_trick("../../etc")
        assert not bad.accepted
    asyncio.run(go())


def test_hub_trick_runs_like_robotd_window_zero_then_unwind_idle(tmp_path):
    """Hinweis aus dem Test 1.11. („Tricks vom Hub setzt er nicht korrekt um“), abgeglichen mit Pollens robotd
    (control.rs, SkillDef): im Fenster Befehl 0 – nicht `idle` –, danach `unwind_s` lang `command.idle`; mit
    Befehl ≈ 0 und Stand-Policy „standing tuned“ (Faktor 1,0 ohne eigenen action_scale, Stärke 0,8)."""
    import numpy as np

    from duckpilot.backends.physics import STANDING_GAIN_RATIO, PhysicsBackend

    src = tmp_path / "trick.onnx"
    linear_policy(src)
    man = {"name": "Flamingo Hold", "kind": "perpetual", "duration_s": 1.0, "unwind_s": 0.5, "obs_len": 61,
           "action_len": 14, "command": {"encoding": "constant", "idle": [0, 1, 0]}}

    async def go():
        store = make_store(tmp_path)
        store.fetch = lambda url: json.dumps(man).encode() if url.endswith("manifest.json") else src.read_bytes()
        b = PhysicsBackend(store, realtime=False)
        b._task = object()
        res = await b.add_trick("someone/microduck-flamingo-hold")
        assert res.accepted and "flamingo-hold" in b.skills()          # derselbe Name wie in der Hub-Liste
        assert abs(b._skill_len("flamingo-hold") - 1.5) < 1e-6        # Fenster + Rückweg
        b.reset_body()
        assert (await b.do("flamingo-hold")).accepted
        b.step(0.02)
        pol, cmd = b._command()
        assert pol is b.tricks["flamingo-hold"] and not np.any(cmd.twist) and not np.any(cmd.head)
        standing = "stand" in b.policies
        assert pol.action_scale == (1.0 if standing else 0.9)
        assert b.core.gain_ratio == (STANDING_GAIN_RATIO if standing else 1.0)
        b.skill_t = 1.2                                                # im Rückweg: idle
        pol, cmd = b._command()
        assert list(cmd.twist) == [0.0, 1.0, 0.0] and b.core.gain_ratio == 1.0
        for _ in range(40):
            b.step(0.02)
        assert b.skill is None and b.core.gain_ratio == 1.0           # danach wieder volle Stärke
    asyncio.run(go())


def test_practice_rehearses_without_moving_the_live_duck(tmp_path):
    from duckpilot.physics.practice import rehearse

    store = make_store(tmp_path)
    res = rehearse(store, [{"t": 0, "kopf": {"neigen": 10}}, {"t": 1.0, "kopf": {}}])
    assert res["urteil"] == "fällt um"          # die Null-Policy balanciert nicht
    assert res["umgefallen_bei_s"] is not None and res["hinweise"]
    with pytest.raises(ValueError):
        rehearse(store, [{"t": 0}, {"t": 31}])


def test_build_backend_falls_back_to_the_simple_simulator(tmp_path, monkeypatch):
    from duckpilot.backends import build_backend
    from duckpilot.backends.physics import PhysicsBackend
    from duckpilot.backends.sim import SimBackend
    from duckpilot.config import Config

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "s.json"))
    b = build_backend(Config(sim_physik=True))
    assert type(b) is SimBackend and "Policies" in b.physics_problem
    make_store(tmp_path)
    assert isinstance(build_backend(Config(sim_physik=True)), PhysicsBackend)
    assert type(build_backend(Config(sim_physik=False))) is SimBackend


def test_server_runs_the_physics_body_and_offers_practice(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    make_store(tmp_path)
    S.save_user_settings({"sim_physik": True})
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        st = c.get("/api/physik").json()
        assert st["aktiv"] and st["ueben"] and st["policies"]["bereit"]
        assert c.get("/api/skills").json()["koerper"] == "physik"
        assert any(t["name"] == "bewegung_ueben" for t in rt.runner.tools())
        assert rt.init_message()["config"]["physik"] is True
        r = c.post("/api/physik/ueben", json={"keyframes": [{"t": 0, "kopf": {"drehen": 20}}, {"t": 0.8, "kopf": {}}]})
        assert r.json()["urteil"] in ("sicher", "wackelig", "fällt um")
        assert c.get("/api/physik").json()["geuebt"]
        assert c.post("/api/physik/zuruecksetzen").json()["ok"]
        # Körper wechseln: ohne Physik wieder der einfache Simulator
        assert c.post("/api/settings", json={"sim_physik": False}).json()["ok"]
        assert c.get("/api/physik").json()["aktiv"] is False
        assert c.post("/api/physik/zuruecksetzen").status_code == 400


def test_small_commands_jump_the_policy_deadband():
    """Pollens VelStand steht bei kleinen Befehlen still (gemessen: vx 0,1 → 0,003 m/s) – kleine Wünsche anheben."""
    from duckpilot.backends.physics import shape_twist

    assert shape_twist(0, 0, 0) == (0.0, 0.0, 0.0)
    vx, _, _ = shape_twist(0.06, 0, 0)
    assert vx >= 0.2                                          # langsames Annähern wird zu echten Schritten
    assert shape_twist(-0.05, 0, 0)[0] <= -0.2
    assert shape_twist(0.5, 0, 0)[0] == pytest.approx(0.3)    # Obergrenze der Policy
    assert abs(shape_twist(0, 0, 0.2)[2]) >= 0.8              # Drehen aus dem Stand
    assert shape_twist(0.1, 0, 0.1)[2] == pytest.approx(0.15) # beim Gehen fein lenken


def test_somersault_upside_down_is_not_a_fall(tmp_path):
    """Purzelbaum: kopfüber mitten in der Rolle darf die Rolle nicht als Sturz abbrechen."""
    from duckpilot.backends.physics import ACRO_LANDING_S, PhysicsBackend

    b = PhysicsBackend(make_store(tmp_path), realtime=False)
    upside = {"up": -0.9, "roll": 0.1, "z": 0.05}
    standing = {"up": 0.98, "roll": 0.0, "z": 0.2}
    b.skill, b.t = "roulade", 10.0
    for i in range(30):                                   # 0,6 s kopfüber während der Rolle
        b.t += 0.02
        b._watch_fall(upside)
    assert not b.fallen and b.skill == "roulade"
    b.skill = None                                        # Rolle zu Ende, sie landet
    b.t += ACRO_LANDING_S / 2
    b._watch_fall(standing)
    assert not b.fallen
    # bleibt sie nach der Landezeit liegen, zählt es als Sturz
    b.t += ACRO_LANDING_S
    for _ in range(20):
        b.t += 0.02
        b._watch_fall(upside)
    assert b.fallen


def test_robotd_smoothing_matches_pollen():
    """Wie robotd: Gelenkziele geglättet (Kopf 0,5, Beine 0,7), Befehle per EMA 0,2 – sonst zappeln Rolle und Stürze."""
    import numpy as np

    from duckpilot.physics import core as C
    from duckpilot.physics.params import CMD_ALPHA, HEAD_ALPHA, HEAD_LOWPASS, LEGS_LOWPASS

    assert (HEAD_LOWPASS, LEGS_LOWPASS, CMD_ALPHA, HEAD_ALPHA) == (0.5, 0.7, 0.2, 0.2)
    assert np.allclose(C.LOWPASS[C.HEAD_IDX], 0.5)
    legs = [i for i in range(14) if i not in list(C.HEAD_IDX)]
    assert np.allclose(C.LOWPASS[legs], 0.7)
    assert C.TWIST_MAX[2] == pytest.approx(1.0)               # Drehen wie trainiert, nicht 1,5


def test_physics_commands_ramp_like_robotd(tmp_path):
    from duckpilot.backends.physics import PhysicsBackend
    from duckpilot.physics.core import Command

    b = PhysicsBackend(make_store(tmp_path), realtime=False)
    target = Command()
    target.twist[:] = [0.3, 0.0, 0.0]
    target.head[:] = [0.0, 1.0, 0.0, 0.0]
    first = b._smoothed(target)
    assert first.twist[0] == pytest.approx(0.06)               # 0,2 × 0,3 – ein Sprung wird zur Rampe
    for _ in range(30):
        b._smoothed(target)
    assert b._cmd_ema.twist[0] == pytest.approx(0.3, abs=1e-3)  # nach ≈ 0,6 s angekommen
    assert b._cmd_ema.head[1] == pytest.approx(1.0, abs=1e-2)
