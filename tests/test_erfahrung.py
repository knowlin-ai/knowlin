"""Erfahrungsnetz: Hebb'sches Lernen, Vergessen, Erinnern, Prägung – und Datenschutz."""

import time

from duckpilot import remote as R
from duckpilot.brain.erfahrung import PRAEGUNG_MAX, Erfahrungsnetz, key


def test_together_wires_together_and_recall_follows(tmp_path):
    n = Erfahrungsnetz(tmp_path / "e.json")
    n.set_rahmen({key("zeit", "abends"): "abends"})
    for _ in range(5):
        n.erleben({key("person", "Anna"): "Anna", key("ding", "Ball"): "Ball", key("gefuehl", "freude"): "Freude"}, 1.2, "Ball gespielt")
        n.tick(30)                                    # Aktivierung klingt zwischen den Erlebnissen ab
    w = n.kanten["ding:ball|person:anna"]["w"]
    assert w > 0.25
    assert n.kanten["ding:ball|zeit:abends"]["w"] > 0       # der Rahmen lernt leise mit
    assert n.warum("person:anna", "ding:ball") == ["Ball gespielt"]
    einfall = [e["id"] for e in n.recall({"person:anna": 1.0})]
    assert "ding:ball" in einfall and "gefuehl:freude" in einfall
    assert "person:anna" not in [e["id"] for e in n.recall({"ding:ball": 1.0}, ohne=("person",))]


def test_strong_moments_imprint_deeper_and_unused_fades(tmp_path):
    n = Erfahrungsnetz(tmp_path / "e.json")
    n.erleben({"sinn:sturz": "gestürzt", "ort:treppe": "Treppe"}, 1.6)
    n.akt.clear()
    n.erleben({"ding:socke": "Socke", "ort:flur": "Flur"}, 0.8)
    assert n.kanten["ort:treppe|sinn:sturz"]["w"] > n.kanten["ding:socke|ort:flur"]["w"]
    n.gelernt_bis = time.time() - 120 * 86400        # vier Monate ohne Auffrischung
    res = n.consolidate()
    assert res["verbindungen_vergessen"] >= 1 and not n.kanten


def test_praegung_is_bounded(tmp_path):
    n = Erfahrungsnetz(tmp_path / "e.json")
    assert n.praegung()["energie"] == 0.0             # zu wenig erlebt
    for _ in range(40):
        n.erleben({"rueckmeldung:lob": "Lob", "gefuehl:freude": "Freude"})
    p = n.praegung()["energie"]
    assert 0 < p <= PRAEGUNG_MAX
    for _ in range(400):
        n.erleben({"sinn:sturz": "gestürzt", "gefuehl:schreck": "Schreck"})
    assert -PRAEGUNG_MAX <= n.praegung()["energie"] < 0


def test_persistence_and_message_hides_people_for_phones(tmp_path):
    n = Erfahrungsnetz(tmp_path / "e.json")
    n.erleben({"person:anna": "Anna", "ding:ball": "Ball"})
    n.save()
    m = Erfahrungsnetz(tmp_path / "e.json")
    assert "person:anna" in m.knoten
    msg = m.message(ohne_personen=True)
    assert all(not k["id"].startswith("person:") for k in msg["knoten"])
    assert all("person:" not in e["a"] + e["b"] for e in msg["kanten"])


def test_runtime_learns_from_events_and_feeds_claude(tmp_path, monkeypatch):
    import asyncio

    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.server.app import Runtime

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "s.json"))
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "m.json")))
    svc = rt.erfahrung
    assert svc.on
    for _ in range(4):
        svc.on_event({"type": "kick", "message": "Ball getroffen"})
        svc.hear("super gemacht!", "text")
        svc.person("Anna")
    assert svc.netz.kanten
    svc.netz.tick(60)                                 # später: das Erlebte ist nicht mehr „gerade jetzt“
    ctx = svc.context("Wo ist der Ball?")
    assert ctx and any("Freude" in x or "spielen" in x for x in ctx["faellt_ihr_ein"])
    tok = R.REMOTE_TURN.set(True)
    try:
        far = svc.context("Wo ist der Ball?") or {"faellt_ihr_ein": []}
        assert not any("Anna" in x for x in far["faellt_ihr_ein"])     # nie Personen ans Handy
    finally:
        R.REMOTE_TURN.reset(tok)
    # „Alles vergessen“ leert auch das Netz
    asyncio.run(rt.handle_client_message({"type": "memory_clear"}))
    assert not svc.netz.kanten
