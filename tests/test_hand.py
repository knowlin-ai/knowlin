"""Kollisionsmodus: die Hand (Maus/Finger), Greifen und Werfen, mehr Objekte, Hand-Reize und der WebSocket-Weg."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")
pytest.importorskip("onnxruntime")
pytest.importorskip("onnx")

from test_kollision import physics, steps  # noqa: E402

from duckpilot.physics import kollision as KO  # noqa: E402

FREI_Y = -0.3          # dort steht kein Möbel der Standardwohnung


def an(tmp_path):
    b = physics(tmp_path)
    b.kollision_an(True)
    return b, b.kollision


def rumpf(b):
    return b.core.data.xipos[b.kollision.ziele["rumpf"]].copy()


def eindringen(b, geoms):
    """Wie tief steckt eines der Geoms in der Ente (m, geometrisch – unabhängig davon, ob MuJoCo Kontakte meldet)."""
    m, d = b.core.model, b.core.data
    ft = np.zeros(6)
    worst = 0.0
    for g in geoms:
        for r in b.core.robot_geoms:
            if m.geom_contype[r] or m.geom_conaffinity[r]:
                worst = min(worst, mujoco.mj_geomDistance(m, d, g, r, 0.05, ft))
    return -worst


def test_hand_follows_with_at_most_2_5_m_s_and_stops_without_overshoot(tmp_path):
    b, k = an(tmp_path)
    k.hand(0.0, FREI_Y, 0.3)
    assert k.hand_aktiv and np.allclose(k.hand_pos, [0.0, FREI_Y, 0.3])      # erscheint, wo der Zeiger ist
    k.hand(1.0, FREI_Y, 0.3)
    wege = []
    for _ in range(25):
        before = k.hand_pos
        b.step(0.02)
        wege.append(float(np.linalg.norm(k.hand_pos - before)))
    assert max(wege) <= KO.HAND_MAX_MS * 0.02 * 1.08                        # Ziel ≤ 2,5 m/s, die Hand kaum mehr
    assert wege[2] > 0.95 * KO.HAND_MAX_MS * 0.02                           # nach 40 ms auf vollem Tempo
    assert abs(k.hand_pos[0] - 1.0) < 0.002 and k.hand_pos[1] == pytest.approx(FREI_Y, abs=0.002)
    assert k.hand_pos[2] == pytest.approx(0.3, abs=0.002)                   # schwebt: Schwerkraft ausgeglichen
    info = k.hand_aus()
    assert not info["aktiv"] and info["pos"][0] == KO.HAND_PARK[0]          # weit weg geparkt


def test_hand_glides_between_pointer_messages(tmp_path):
    """Der Zeiger kommt mit 30 Hz – dazwischen gleitet das Ziel, statt stehen zu bleiben (kein Ruckeln)."""
    import mujoco as mj

    b, k = an(tmp_path)
    k.hand(0.0, FREI_Y, 0.3)
    m, d = b.core.model, b.core.data
    tempi = []
    for i in range(1, 16):                                                   # 1 m/s, eine Nachricht je 1/30 s
        k.hand(i / 30.0, FREI_Y, 0.3)
        for _ in range(7):                                                   # ≈ 1/30 s in 5-ms-Teilschritten
            k.pre_step()
            mj.mj_step(m, d)
            if i > 3:
                tempi.append(float(d.qvel[k.hand_dof]))
    assert min(tempi) > 0.6 and max(tempi) < 1.4                            # gleichmäßig, kein Stop-and-go


def test_hand_does_not_pass_through_the_duck(tmp_path):
    """Die Hand stößt an der Ente an – an Rumpf, Hüfte und Beinen –, statt durch sie hindurchzugehen."""
    for n_lauf, (hoehe, tempo) in enumerate(((0.0, 2.5), (-0.05, 1.0), (0.04, 2.5))):
        b, k = an(tmp_path / str(n_lauf))
        steps(b, 20)
        c = rumpf(b)
        c[2] += hoehe
        k.hand(c[0], c[1] + 0.3, c[2])
        steps(b, 3)
        n = int(0.6 / (tempo * 0.02))
        tief = 0.0
        for i in range(1, n + 1):
            k.hand(c[0], c[1] + 0.3 - 0.6 * i / n, c[2])
            b.step(0.02)
            tief = max(tief, eindringen(b, [k.hand_geom]))
        assert tief < 0.01, (hoehe, tempo, tief)                             # höchstens wenige mm, nie hindurch
    m = b.core.model
    for i in b.core.robot_geoms:                                             # auch der Körper-Vorfilter von MuJoCo
        if m.geom_contype[i] or m.geom_conaffinity[i]:
            assert m.body_conaffinity[m.geom_bodyid[i]] & KO.HAND_BIT


def test_hand_pushes_with_capped_force(tmp_path):
    b, k = an(tmp_path)
    steps(b, 20)
    c = rumpf(b)
    k.hand(c[0] + 0.2, c[1], c[2])
    steps(b, 3)
    k.hand(c[0] - 0.4, c[1], c[2])                                           # Ziel weit hinter der Ente
    kraefte = []
    for _ in range(15):
        b.step(0.02)
        if k._an_ente:
            kraefte.append(float(np.linalg.norm(k.kraft)))
    assert kraefte and max(kraefte) <= KO.HAND_KRAFT_N + 1e-6
    assert KO.grenzen()["hand"]["kraft_n_max"] == KO.HAND_KRAFT_N


def test_hand_pushes_the_duck_and_counts_as_play(tmp_path):
    b, k = an(tmp_path)
    steps(b, 50)
    c = rumpf(b)
    k.hand(c[0] - 0.3, c[1], c[2])
    steps(b, 3)
    v0 = b.core.trunk()["vx"]
    k.hand(c[0] + 0.3, c[1], c[2])
    dv, touched = 0.0, False
    for _ in range(25):
        b.step(0.02)
        dv = max(dv, b.core.trunk()["vx"] - v0)
        touched = touched or k.beruehrt
    assert touched and dv > 0.05                                             # die Hand schubst sie wirklich
    assert b.episode is not None and b.episode.art == "hand"
    reiz = b.episode.reiz
    assert reiz["koerperteil"] in KO.ZIELE and len(reiz["punkt"]) == 3 and reiz["tempo"] > 0
    assert b.t - b._last_reiz < 1.0                                          # Spiel: kein Ärger, keine Stimmung
    seen = []
    b._listeners.append(seen.append)
    b.emit("fall", message="Umgefallen")
    assert seen and seen[-1].get("kollision") is True


def test_hand_passes_through_objects(tmp_path):
    b, k = an(tmp_path)
    k.setzen("klotz", [0.6, FREI_Y])
    steps(b, 20)
    vor = np.array(k.objekt("klotz")["pos"])
    k.hand(0.2, FREI_Y, 0.025)
    k.hand(1.0, FREI_Y, 0.025)
    steps(b, 25)                                                             # mitten durch den Klotz
    assert k.hand_pos[0] > 0.9
    assert np.allclose(k.objekt("klotz")["pos"], vor, atol=0.002)


def test_grab_carries_and_release_throws_with_the_hand_speed(tmp_path):
    b, k = an(tmp_path)
    k.setzen("ball", [0.2, FREI_Y])
    steps(b, 10)
    k.hand(0.2, FREI_Y, 0.3)
    steps(b, 3)
    with pytest.raises(KO.KollisionsFehler, match="0.08"):
        k.greifen("ball")                                                    # 0,23 m über dem Ball: zu weit
    with pytest.raises(KO.KollisionsFehler, match="Reichweite"):
        k.greifen()
    k.hand(0.2, FREI_Y, 0.09)
    steps(b, 15)
    res = k.greifen()                                                        # ohne Namen: das nächste
    assert res["id"] == "ball" and res["in_der_hand"] and k.hand_gehalten == "ball"
    off = np.array(res["pos"]) - k.hand_pos
    k.hand(0.2, FREI_Y, 0.4)
    steps(b, 20)
    assert np.allclose(np.array(k.objekt("ball")["pos"]) - k.hand_pos, off, atol=3e-3)   # hängt fest an der Hand
    k.hand(1.4, FREI_Y, 0.4)
    steps(b, 6)
    out = k.hand_loslassen()
    v = np.array(out["geschwindigkeit"])
    assert v[0] > 2.0 and np.linalg.norm(v) <= KO.MAX_WURF_MS                # fliegt mit dem Tempo der Hand
    assert k.hand_gehalten is None
    m, d = b.core.model, b.core.data
    o = k.obj["ball"]
    assert not d.eq_active[o["eq"]] and m.body_gravcomp[o["body"]] == 0.0  # los: Weld aus, Schwerkraft wieder an
    b.step(0.02)
    assert k.objekt("ball")["tempo"] > 1.5
    with pytest.raises(KO.KollisionsFehler):
        k.hand_loslassen()


def test_a_thing_right_next_to_the_duck_can_be_grabbed(tmp_path):
    """Regression (das Bild): Ein Würfel direkt neben der Ente ließ sich nicht greifen – die Hand erschien
    pauschal 0,3 m höher, sobald das Ziel unter 0,2 m vom Rumpf lag („Würfel ist 0.28 m von der Hand weg“)."""
    b, k = an(tmp_path)
    r = rumpf(b)
    k.setzen("wuerfel", [float(r[0]), float(r[1]) - 0.11])                # 11 cm neben dem Rumpf
    steps(b, 15)
    c = np.array(k.objekt("wuerfel")["pos"])
    assert np.linalg.norm(c[:2] - r[:2]) < 0.2
    k.hand(*c)
    assert np.linalg.norm(k.hand_pos - c) < 0.01                             # erscheint im Würfel, nicht darüber
    assert k.greifen("wuerfel")["in_der_hand"]
    k.hand_aus()
    k.hand(float(r[0]), float(r[1]), float(r[2]))                            # mitten in der Ente: frei darüber
    assert k.hand_pos[2] > r[2] + 0.02
    assert min(dist for dist, _g in k._abstaende(k.hand_pos)) >= KO.HAND_R


def test_released_with_fest_it_stays_in_the_air_until_grabbed_again(tmp_path):
    """Anna: „Ich kann die Höhe ändern, aber es fällt direkt runter – was bringt mir das?“ → in der Luft abstellen."""
    b, k = an(tmp_path)
    k.setzen("ball", [0.4, FREI_Y])
    steps(b, 10)
    c = np.array(k.objekt("ball")["pos"])
    k.hand(*c)
    k.greifen("ball")
    k.hand(0.4, FREI_Y, 0.3)
    steps(b, 25)
    oben = np.array(k.objekt("ball")["pos"])
    assert oben[2] > 0.25
    info = k.hand_loslassen(fest=True)
    assert info["fest"] and info["geschwindigkeit"] == [0.0, 0.0, 0.0]
    k.hand_aus()
    steps(b, 50)                                                             # 1 s: fällt nicht
    assert np.allclose(k.objekt("ball")["pos"], oben, atol=1e-3) and k.objekt("ball")["fest"]
    assert not k.bewegt()                                                    # kein Dauer-Strom wegen eines stehenden Dings
    k.hand(*oben)
    k.greifen("ball")                                                        # wieder anfassen löst es
    assert not k.objekt("ball")["fest"]
    k.hand_loslassen()
    k.hand_aus()
    steps(b, 40)
    assert k.objekt("ball")["pos"][2] < 0.06                                 # jetzt fällt es
    k.hand(*k.objekt("ball")["pos"]); k.greifen("ball"); k.hand_loslassen(fest=True); k.hand_aus()
    k.parken("ball")
    assert not k.objekt("ball")["fest"]                                      # wegräumen löst es auch


def test_floating_things_can_be_dropped_one_or_all(tmp_path):
    """Anna (30.10.): „Wenn ich Dinge in der Luft platziere, muss per Doppelklick oder Schalter wieder ‚Schwerkraft‘
    angehen, sonst ist es schwierig, Dinge fallen zu lassen.“ → `fallen_lassen` (eines oder alle, 0.33)."""
    b, k = an(tmp_path)
    for name, x in (("ball", 0.4), ("wuerfel", 0.6)):
        k.setzen(name, [x, FREI_Y])
        steps(b, 10)
        k.hand(*k.objekt(name)["pos"])
        k.greifen(name)
        k.hand(x, FREI_Y, 0.3)
        steps(b, 25)
        k.hand_loslassen(fest=True)
        k.hand_aus()
    steps(b, 20)
    assert k.objekt("ball")["fest"] and k.objekt("wuerfel")["fest"]
    assert k.fallen_lassen("ball") == ["ball"]
    steps(b, 40)
    assert k.objekt("ball")["pos"][2] < 0.06 and not k.objekt("ball")["fest"]         # der eine fällt
    assert k.objekt("wuerfel")["pos"][2] > 0.25 and k.objekt("wuerfel")["fest"]       # der andere bleibt
    assert k.fallen_lassen("alle") == ["wuerfel"]
    steps(b, 40)
    assert k.objekt("wuerfel")["pos"][2] < 0.06
    assert k.fallen_lassen() == []                                                    # nichts mehr in der Luft


def test_release_with_a_given_velocity_flies_exactly_that(tmp_path):
    b, k = an(tmp_path)
    k.setzen("wuerfel", [0.4, FREI_Y])
    steps(b, 10)
    k.hand(0.4, FREI_Y, 0.03)
    steps(b, 3)
    k.greifen("wuerfel")
    k.hand(0.4, FREI_Y, 0.4)
    steps(b, 25)
    out = k.hand_loslassen(v=[1.0, 0.5, 2.0])
    assert out["geschwindigkeit"] == [1.0, 0.5, 2.0]
    d = b.core.data
    o = k.obj["wuerfel"]
    for _ in range(5):
        b.step(0.02)
    vel = d.qvel[o["v"]:o["v"] + 3]
    assert vel[0] == pytest.approx(1.0, abs=1e-3) and vel[1] == pytest.approx(0.5, abs=1e-3)
    assert vel[2] == pytest.approx(2.0 - 9.81 * 0.1, abs=0.02)              # reiner Wurf: nur Schwerkraft
    def nochmal():
        k.hand_aus()
        k.setzen("wuerfel", [0.4, FREI_Y])
        k.hand(0.4, FREI_Y, 0.03)
        steps(b, 3)
        k.greifen("wuerfel")

    nochmal()
    out = k.hand_loslassen(v=[30.0, 0.0, 0.0])
    assert np.linalg.norm(out["geschwindigkeit"]) == pytest.approx(KO.MAX_WURF_MS, abs=1e-3)   # geklemmt
    nochmal()
    for bad in ([1, 2], ["a", 0, 0], [float("nan"), 0, 0], "schnell"):
        with pytest.raises(KO.KollisionsFehler):
            k.hand_loslassen(v=bad)
    assert k.hand_gehalten == "wuerfel"                                      # Fehler: hält es weiter


def test_held_things_do_not_pass_through_the_duck_and_the_klotz_hangs_still(tmp_path):
    b, k = an(tmp_path)
    steps(b, 20)
    c = rumpf(b)
    k.setzen("ball", [c[0], c[1] + 0.35])
    steps(b, 10)
    k.hand(*k.objekt("ball")["pos"])
    steps(b, 2)
    k.greifen("ball")
    k.hand(c[0], c[1] + 0.35, c[2])
    steps(b, 10)
    tief = 0.0
    for i in range(1, 31):
        k.hand(c[0], c[1] + 0.35 - 0.05 * i, c[2])                           # 2,5 m/s quer durch den Rumpf
        b.step(0.02)
        tief = max(tief, eindringen(b, [k.obj["ball"]["geom"]]))
    assert tief < 0.01
    k.hand_aus()
    # Klotz (0,6 kg): hängt ruhig an der Hand, ohne zu sinken oder zu pendeln
    k.setzen("klotz", [0.4, FREI_Y])
    steps(b, 10)
    k.hand(*k.objekt("klotz")["pos"])
    steps(b, 2)
    k.greifen("klotz")
    k.hand(0.4, FREI_Y, 0.3)
    steps(b, 40)
    p1 = np.array(k.objekt("klotz")["pos"])
    steps(b, 25)
    p2 = np.array(k.objekt("klotz")["pos"])
    assert float(np.linalg.norm(p2 - p1)) < 0.002 and abs(k.hand_pos[2] - 0.3) < 0.003
    info = k.hand_info()
    assert info["ziel"] == [0.4, FREI_Y, 0.3] and info["gehalten"] == "klotz"


def test_new_objects_rest_on_the_floor_and_report_their_size(tmp_path):
    b, k = an(tmp_path)
    assert {o["form"] for o in KO.OBJEKTE.values()} == set(KO.FORMEN)
    assert len({o["farbe"] for o in KO.OBJEKTE.values()}) == len(KO.OBJEKTE) == 6
    for i, key in enumerate(KO.OBJEKTE):
        r = k.setzen(key, [0.0 + 0.3 * i, FREI_Y])
        assert r["pos"][2] == pytest.approx(KO.halbachsen(key)[2])
    steps(b, 100)
    for o in k.objekte():
        assert o["im_raum"]
        assert o["pos"][2] == pytest.approx(o["halbachsen"][2], abs=0.006), o["id"]   # liegt, kippt nicht
        assert o["tempo"] < 0.02
    kegel = k.objekt("kegel")
    assert kegel["form"] == "zylinder" and kegel["groesse"] == [0.025, 0.08]
    assert kegel["abmessungen"] == {"durchmesser": 0.05, "hoehe": 0.16}
    assert k.objekt("klotz")["masse"] > 0.5 and k.objekt("kissen")["weich"]
    g = KO.grenzen()
    assert g["hand"]["tempo_ms_max"] == 2.5 and g["objekte"]["kissen"]["halbachsen"] == [0.08, 0.06, 0.025]


def test_ws_hook_in_the_runtime_sync_and_async():
    from duckpilot.server.runtime import Runtime

    rt = Runtime.__new__(Runtime)
    rt.ws_extra = {}
    got = []

    async def later(msg):
        got.append(("async", msg["x"]))

    rt.ws_extra["eins"] = lambda msg: got.append(("sync", msg["x"]))
    rt.ws_extra["zwei"] = later
    asyncio.run(rt.handle_client_message({"type": "eins", "x": 1}))
    asyncio.run(rt.handle_client_message({"type": "zwei", "x": 2}))
    asyncio.run(rt.handle_client_message({"type": "gibtsnicht"}))           # unbekannt: still ignoriert
    assert got == [("sync", 1), ("async", 2)]


def test_kollision_service_hand_over_the_websocket(tmp_path):
    from duckpilot.kollision_service import KollisionService

    b, k = an(tmp_path)
    sent = []

    async def broadcast(m):
        sent.append(m)

    rt = SimpleNamespace(ws_extra={}, backend=b, broadcast=broadcast, config=SimpleNamespace(backend="sim"),
                         engine=SimpleNamespace(config=SimpleNamespace(auto_recover=True, recover_delay=3.0)))
    svc = KollisionService(rt)
    svc._start = lambda: None
    svc._save = lambda ep: None
    assert set(rt.ws_extra) == {"kollision_hand", "kollision_greifen", "kollision_loslassen", "kollision_zug_start",
                                "kollision_zug", "kollision_zug_ende"}

    def ws(kind, **msg):
        asyncio.run(rt.ws_extra[kind]({"type": kind, **msg}))

    k.setzen("wuerfel", [0.2, FREI_Y])
    ws("kollision_hand", x=0.2, y=FREI_Y, z=0.08)
    assert k.hand_aktiv
    ws("kollision_greifen", name="ball")                                     # liegt nicht im Raum
    assert sent[-1] == {"type": "event", "event": {"type": "kollision", "message": "Ball liegt nicht im Raum"}}
    ws("kollision_greifen")
    assert k.hand_gehalten == "wuerfel"
    msg = svc.objekte_message()
    assert msg["hand"]["gehalten"] == "wuerfel" and msg["hand"]["aktiv"] and len(msg["hand"]["pos"]) == 3
    assert "beruehrt" in msg["hand"]
    ws("kollision_hand", x=1.2, y=FREI_Y, z=0.3)
    steps(b, 8)
    ws("kollision_loslassen", v=[1.0, "x", 0])                               # ungültig: Fehler, hält es weiter
    assert sent[-1]["event"]["type"] == "kollision" and k.hand_gehalten == "wuerfel"
    ws("kollision_loslassen", v=[0.0, 2.0, 1.5])
    assert k.hand_gehalten is None and b.episode is not None and b.episode.art == "wurf"
    assert b.episode.reiz["geschwindigkeit"] == [0.0, 2.0, 1.5]
    n = len(sent)
    ws("kollision_loslassen")                                                # hält nichts: kein Fehler
    assert len(sent) == n
    ws("kollision_hand", x="viel", y=0, z=0)
    assert sent[-1]["event"]["type"] == "kollision"
    ws("kollision_hand", aus=True)
    assert not k.hand_aktiv and sent[-1]["type"] == "kollision_objekte"
    b.kollision_an(False)
    ws("kollision_hand", x=0, y=0, z=0.3)
    assert not k.hand_aktiv and "aus" in sent[-1]["event"]["message"]


def test_runtime_stays_small():
    from duckpilot.server import runtime

    assert len(Path(runtime.__file__).read_text(encoding="utf-8").splitlines()) <= 1400
    from duckpilot.server.app import _plans_from as a
    from duckpilot.server.runtime import _plans_from as b

    assert a is b
