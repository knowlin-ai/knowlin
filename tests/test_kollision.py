"""Kollisionsmodus in der Physik: Stöße, Ball und Würfel, Episoden und Stoß-Profil fürs Training."""

import asyncio
import json

import pytest

mujoco = pytest.importorskip("mujoco")
pytest.importorskip("onnxruntime")
pytest.importorskip("onnx")

from test_physics import make_store  # noqa: E402

from duckpilot.physics import kollision as KO  # noqa: E402


def physics(tmp_path):
    from duckpilot.backends.physics import PhysicsBackend

    b = PhysicsBackend(make_store(tmp_path), realtime=False)
    b._task = object()
    return b


def steps(b, n):
    for _ in range(n):
        b.step(0.02)


def test_objects_are_free_bodies_but_not_part_of_the_duck(tmp_path):
    b = physics(tmp_path)
    m = b.core.model
    names = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, i) for i in b.core.robot_geoms}
    assert not any(n and n.startswith("o:") for n in names)          # Ball/Würfel zählen nicht als Ente
    assert m.nq == 21 + 7 * (len(KO.OBJEKTE) + 1)                       # die Objekte und die Hand
    assert all(not o["im_raum"] for o in b.kollision.objekte())       # geparkt, bis man sie holt
    with pytest.raises(KO.KollisionsFehler):                          # aus: keine Reize
        b.kollision_reiz("stoss", b.kollision.stoss, staerke=1.0)


def test_push_moves_her_and_becomes_an_episode(tmp_path):
    b = physics(tmp_path)
    eps = []
    b.on_episode = eps.append
    b.kollision_an(True)
    x0 = b.core.trunk()["x"]
    res = b.kollision_reiz("stoss", b.kollision.stoss, ziel="rumpf", staerke=5.0, richtung_grad=0)
    assert res["impuls_ns"] == KO.MAX_STOSS_NS                        # Stärke auf 0…1 begrenzt
    steps(b, 10)
    assert b.core.trunk()["x"] - x0 > 0.02                             # nach vorn geschoben
    for _ in range(int(KO.EPISODE_MAX_S / 0.02) + 20):
        b.step(0.02)
        if b.episode is None:
            break
    assert len(eps) == 1
    ep = eps[0]
    assert ep["art"] == "stoss" and ep["ausgang"] in KO.AUSGAENGE
    assert ep["dv_rumpf"][0] > 0.1 and abs(ep["dv_rumpf"][1]) < 0.1   # Stoß nach vorn, im Blick der Ente gemessen
    assert len(ep["reihe"]) >= 20 and len(ep["reihe"][0]) == len(ep["reihe_spalten"])
    json.dumps(ep)                                                    # schreibbar
    with pytest.raises(KO.KollisionsFehler):
        b.kollision.stoss(ziel="fluegel")


def test_thrown_ball_hits_her_and_the_bump_is_marked_as_play(tmp_path):
    b = physics(tmp_path)
    events = []
    b.on_event(events.append)
    b.kollision_an(True)
    res = b.kollision_reiz("wurf", b.kollision.werfen, name="ball", ziel="ente", staerke=0.6)
    assert 0 < res["tempo"] <= KO.MAX_WURF_MS
    steps(b, 60)
    bumps = [e for e in events if e["type"] == "bump" and e.get("what") == "Ball"]
    assert bumps and all(e.get("kollision") for e in bumps)
    assert "Spiel" in bumps[0]["message"]
    # die Episode weiß, wo und wie fest der Ball sie getroffen hat (fürs Training)
    hit = b.episode.treffer if b.episode is not None else None
    assert hit is not None and hit["koerperteil"] in KO.ZIEL_NAMEN and hit["tempo_ms"] > 0.3
    assert hit["impuls_ns"] == pytest.approx(KO.OBJEKTE["ball"]["masse"] * hit["tempo_ms"], rel=1e-3)
    # Greifen, Halten, Loslassen mit Schwung (= werfen), Rollen, Parken
    held = b.kollision_reiz("objekt", b.kollision.halten, name="Würfel", pos=[0.0, 0.0, 0.3])
    assert held["gehalten"]
    steps(b, 10)
    assert abs(b.kollision.objekt("wuerfel")["pos"][2] - 0.3) < 1e-3          # fällt nicht, solange gehalten
    b.kollision_reiz("wurf", b.kollision.loslassen, name="wuerfel", geschwindigkeit=[50, 0, 0])
    assert b.kollision.objekt("wuerfel")["tempo"] <= KO.MAX_WURF_MS + 1e-6
    r = b.kollision_reiz("rollen", b.kollision.rollen, name="ball", tempo=1.0)
    assert r["pos"][2] == pytest.approx(KO.OBJEKTE["ball"]["groesse"])
    b.kollision_an(False)
    assert all(not o["im_raum"] for o in b.kollision.objekte())


def test_fallen_duck_lies_still_until_the_reflex_allows_standing_up(tmp_path):
    b = physics(tmp_path)
    steps(b, 200)                                                      # Null-Policy: sie fällt wirklich
    assert b.fallen
    b.step(0.02)
    assert b.core.limp                                                 # liegt schlaff – VelStand richtet nicht auf
    res = asyncio.run(b.init())
    assert res.accepted and "steht gleich" in res.reason
    b.step(0.02)
    assert not b.core.limp                                             # jetzt darf die Policy sie aufrichten


def test_episode_log_and_push_profile(tmp_path):
    log = KO.EpisodenLog(tmp_path)
    for dv, aus in (([0.3, 0.0], "steht"), ([0.0, -2.0], "faellt"), ([0.001, 0.0], "wackelt"), (None, "steht")):
        log.schreiben({"art": "stoss", "ausgang": aus, "dv_rumpf": dv})
    st = log.stats()
    assert st["anzahl"] == 4 and st["ausgaenge"]["faellt"] == 1
    assert KO.EpisodenLog(tmp_path).stats()["anzahl"] == 4             # liest die Datei wieder
    proben = KO.stossproben(tmp_path)
    assert proben == [[0.3, 0.0], [0.0, -0.8]]                         # winzige weg, große begrenzt


def test_local_training_uses_the_measured_pushes(monkeypatch):
    import numpy as np

    from duckpilot.physics import lernen as L

    monkeypatch.setattr(L, "SCHUBS_ECHT_ANTEIL", 1.0)
    env = L._Umgebung(None, 1.0, np.random.default_rng(0), None, schubs=[[0.8, 0.0]])
    env.next_push = 0.0
    env.step(np.zeros(14, np.float32))
    assert env.core.trunk()["vx"] > 0.2                               # der echte Stoß (gedämpft) schiebt nach vorn
    plain = L._Umgebung(None, 1.0, np.random.default_rng(0), None)
    assert plain.schubs is None


def test_buttons_work_without_a_pointer(tmp_path):
    """Tasten statt Maus: Seite (von wo) und Stufe (leicht/mittel/kräftig)."""
    b = physics(tmp_path)
    b.kollision_an(True)
    res = b.kollision.stoss(seite="links", stufe="kräftig")
    assert res["staerke"] == KO.STUFEN["kraeftig"] and res["richtung"][1] < -0.9   # von links → schiebt nach rechts
    steps(b, 5)
    r = b.kollision.rollen("ball", seite="hinten", stufe="leicht")
    assert r["tempo"] == pytest.approx(KO.ROLL_TEMPO["leicht"], abs=0.01) and r["pos"][0] < b.core.trunk()["x"]
    w = b.kollision.werfen("wuerfel", seite="vorn", stufe="mittel")
    assert w["geschwindigkeit"][0] < 0                                               # von vorn auf sie zu
    with pytest.raises(KO.KollisionsFehler):
        b.kollision.stoss(seite="oben")
    with pytest.raises(KO.KollisionsFehler):
        b.kollision.rollen("ball", stufe="brutal")


def test_a_hit_from_outside_becomes_a_ruck_for_vibrating(tmp_path):
    """Controller und Gamepad vibrieren bei Stößen und Treffern: state.ruck zählt Erschütterungen von außen hoch
    (Kontaktkraft von Dingen, Hand, Möbeln; Stöße direkt). Stehen und Boden zählen nicht."""
    b = physics(tmp_path)
    steps(b, 60)
    assert b.state().ruck is None                                     # nur Boden: nichts
    b.kollision_an(True)
    b.kollision_reiz("stoss", b.kollision.stoss, ziel="rumpf", staerke=0.5, richtung_grad=90)
    r = b.state().ruck
    assert r["n"] == 1 and r["quelle"] == "Stoß" and 0.4 < r["staerke"] < 0.8
    steps(b, 150)
    n = b.state().ruck["n"]
    b.kollision_reiz("wurf", b.kollision.werfen, name="ball", seite="links", stufe="kraeftig")
    hit = None
    for _ in range(100):
        b.step(0.02)
        r = b.state().ruck
        if r["n"] > n:
            hit = r
            break
    assert hit is not None and hit["quelle"] == "Ball" and hit["staerke"] > 0.3
    assert b.state().to_dict()["ruck"]["n"] == hit["n"]               # geht so an die Oberfläche
