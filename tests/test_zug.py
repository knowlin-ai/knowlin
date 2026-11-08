"""Kollisionsmodus: die Ente an einem Punkt anfassen und ziehen (wie MuJoCo simulate / Gazebo Mouse Drag)."""

import asyncio
from types import SimpleNamespace

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")
pytest.importorskip("onnxruntime")
pytest.importorskip("onnx")

from test_kollision import physics, steps  # noqa: E402

from duckpilot.physics import kollision as KO  # noqa: E402


def an(tmp_path):
    b = physics(tmp_path)
    b.kollision_an(True)
    return b, b.kollision


def punkt(b, teil="rumpf"):
    return b.core.data.xipos[b.kollision.ziele[teil]].copy()


def test_grab_point_on_the_surface_is_kept_in_the_body(tmp_path):
    b, k = an(tmp_path)
    p = punkt(b, "kopf")
    info = k.zug_start(*p)
    assert info["aktiv"] and info["teil"] == "kopf" and info["kraft_n"] == 0.0
    assert np.allclose(info["anker"], p, atol=1e-4) and np.allclose(info["ziel"], p, atol=1e-4)   # kein Ruck
    steps(b, 5)
    zi = k.zug_info()
    assert zi["kraft_n"] < 1.0                                                # Ziel = Anfasspunkt: kaum Kraft
    assert np.linalg.norm(np.array(zi["anker"]) - p) < 0.03                    # der Anker wandert mit dem Körper
    assert k.zug_ende() == {"zug": None} and k.zug_info() is None
    assert not np.any(b.core.data.xfrc_applied[: b.core.model.nbody])          # Kraft sofort weg


def test_named_body_and_nearest_shape(tmp_path):
    b, k = an(tmp_path)
    p = punkt(b, "bein_links")
    assert k.zug_start(*p, koerper="leg")["koerper"] == "leg"
    k.zug_ende()
    assert k.zug_start(*p, koerper="gibtsnicht")["teil"] == "bein_links"       # unbekannt: nächste Form zählt
    k.zug_ende()


def test_grab_off_the_duck_is_refused(tmp_path):
    b, k = an(tmp_path)
    p = punkt(b) + np.array([0.0, 0.0, 0.3])                                  # 30 cm über ihr: Luft
    with pytest.raises(KO.KollisionsFehler, match="nicht"):
        k.zug_start(*p)
    with pytest.raises(KO.KollisionsFehler):
        k.zug_ziel(0, 0, 0.1)                                                 # nichts angefasst
    with pytest.raises(KO.KollisionsFehler):
        k.zug_start("x", 0, 0.1)


def test_pull_moves_her_towards_the_target_with_a_capped_force(tmp_path):
    b, k = an(tmp_path)
    p = punkt(b)
    y0 = b.core.trunk()["y"]
    k.zug_start(*p)
    k.zug_ziel(p[0], p[1] + 1.0, p[2])                                        # 1 m zur Seite: Feder wäre 60 N
    kraefte = []
    for _ in range(15):
        b.step(0.02)
        kraefte.append(k.zug_info()["kraft_n"])
    assert max(kraefte) <= KO.ZUG_N_MAX + 1e-6 and max(kraefte) > 0.9 * KO.ZUG_N_MAX
    assert b.core.trunk()["y"] - y0 > 0.01                                     # gezogen, in Zugrichtung
    k.zug_ende()


def test_pull_is_an_episode_and_counts_as_play(tmp_path):
    b, k = an(tmp_path)
    eps = []
    b.on_episode = eps.append
    p = punkt(b, "kopf")
    res = b.kollision_reiz("zug", k.zug_start, x=p[0], y=p[1], z=p[2])
    assert b.episode is not None and b.episode.art == "zug" and b.episode.reiz["teil"] == "kopf"
    assert res["anker"] == b.episode.reiz["anker"]
    t0 = b._last_reiz
    steps(b, 10)
    assert b._last_reiz > t0 and b.t - b._last_reiz < 0.05                    # solange gezogen wird: Spiel
    events = []
    b.on_event(events.append)
    b.emit("fall", message="Gleichgewicht verloren")
    assert events[-1]["kollision"] and "Spiel" in events[-1]["message"]       # Stimmung/Erfahrung lassen es aus
    k.zug_ende()
    b.kollision_an(False)
    assert len(eps) == 1 and eps[0]["art"] == "zug"


def test_pulls_and_pushes_add_up_and_reset_clears_them(tmp_path):
    b, k = an(tmp_path)
    p = punkt(b)
    k.zug_start(*p)
    k.zug_ziel(p[0] + 0.05, p[1], p[2])
    k.stoss("rumpf", 0.5)
    k.pre_step()
    body = k.zug["body"]
    assert b.core.data.xfrc_applied[body, 0] > KO.ZUG_K * 0.05 * 0.9          # Stoß obendrauf, nicht überschrieben
    b.reset_body()
    assert k.zug is None and not np.any(b.core.data.xfrc_applied)


def test_zug_over_the_websocket_and_in_the_stream(tmp_path):
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

    def ws(kind, **msg):
        asyncio.run(rt.ws_extra[kind]({"type": kind, **msg}))

    p = punkt(b, "kopf")
    ws("kollision_zug", x=0, y=0, z=0.1)                                       # vor dem Anfassen: Fehler
    assert sent[-1]["event"]["type"] == "kollision"
    ws("kollision_zug_start", x=float(p[0]), y=float(p[1]), z=float(p[2]) + 0.5)
    assert "nicht" in sent[-1]["event"]["message"] and k.zug is None
    ws("kollision_zug_start", x=float(p[0]), y=float(p[1]), z=float(p[2]), koerper="yaw_roll_motion")
    assert sent[-1]["type"] == "kollision_objekte" and sent[-1]["zug"]["teil"] == "kopf"
    ws("kollision_zug", x=float(p[0]), y=float(p[1]) + 0.2, z=float(p[2]))
    steps(b, 3)
    z = svc.objekte_message()["zug"]
    assert z["aktiv"] and z["kraft_n"] > 1.0 and len(z["anker"]) == 3 and len(z["ziel"]) == 3
    ws("kollision_zug", x="weit", y=0, z=0)
    assert sent[-1]["event"]["type"] == "kollision"
    assert svc.status()["zug"]["aktiv"]
    ws("kollision_zug_ende")
    assert k.zug is None and sent[-1]["type"] == "kollision_objekte" and sent[-1]["zug"] is None
    g = KO.grenzen()["zug"]
    assert g["kraft_n_max"] == KO.ZUG_N_MAX and g["reichweite_m"] == 0.03 and g["steifigkeit_n_m"] == KO.ZUG_K
