"""Pollens Protokoll 64–68 (daemon 0.22–0.23.1): Fotos, Lautstärke, Spiele der Ente, Pollens NFC-Karten.

Alles gegen den Test-Roboter (`fake_robotd`), der robotd, configd, updaterd und nfcd auf einem Anschluss beantwortet.
"""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from duckpilot import settings as S
from duckpilot.backends.robotd import (
    API_VERSION,
    RobotdBackend,
    fehlende_funktionen,
    kann,
    pollen_schalter,
)
from duckpilot.care import RobotCare, foto_name
from duckpilot.config import load
from duckpilot.nfc import POLLEN_TAGS, TagStore, pollen_tag
from duckpilot.server.app import Runtime, create_app

H = {"Origin": "http://127.0.0.1:8765"}


def test_knowlin_spricht_protokoll_68_und_nennt_was_einer_alten_ente_fehlt():
    assert API_VERSION == 68
    assert fehlende_funktionen(68) == [] and fehlende_funktionen(None) == []
    alt = fehlende_funktionen(50)                         # Stand von Knowlin bis 0.51
    assert "Fotos der Ente ansehen und löschen" in alt and "Lautstärke einstellen" in alt and len(alt) == 4
    assert fehlende_funktionen(66) == ["sehen, welches Spiel der Ente gerade läuft", "ein Foto machen lassen"]
    assert kann(64, "fotos") and not kann(63, "fotos") and kann(None, "lautstaerke") and not kann(67, "foto_machen")


def test_pollens_spiele_im_robot_state():
    assert pollen_schalter({"autonomous": True, "soccer": {"autonomous": False}, "laser": None}) == ["Ente allein", "Fußball"]
    assert pollen_schalter({"autonomous": False}) == [] and pollen_schalter(None) == []


def test_laeuft_pollens_spiel_faengt_knowlin_nichts_eigenes_an():
    be = RobotdBackend("tcp:127.0.0.1:1")
    gemeldet = []
    be.emit = lambda kind, **kw: gemeldet.append((kind, kw))
    assert be.pollen_steuert() is None
    be._on_state("robot.state", {"policy": "walk", "laser": {"seen": False}})
    assert be.pollen_steuert() == "Pollens Laser verfolgen läuft"
    assert gemeldet[-1][0] == "pollen_modus" and gemeldet[-1][1]["an"] == ["Laser verfolgen"]
    be._on_state("robot.state", {"policy": "walk", "laser": {"seen": True}})     # gleicher Stand: kein neues Ereignis
    assert len([g for g in gemeldet if g[0] == "pollen_modus"]) == 1
    be._on_state("robot.state", {"policy": "stand"})
    assert be.pollen_steuert() is None and gemeldet[-1][1]["an"] == []


def test_sperre_der_eigenen_beschaeftigung_bei_pollens_spiel():
    from helpers import make

    from duckpilot.motion.eigenstaendig import sperre

    async def go():
        sim, eng = await make()
        frei = sperre(eng, haeufigkeit="ab_und_zu")
        sim.pollen_steuert = lambda: "Pollens Ente allein läuft"
        return frei, sperre(eng, haeufigkeit="ab_und_zu")

    frei, gesperrt = asyncio.run(go())
    assert frei is None and gesperrt == "Pollens Ente allein läuft"


def test_lautstaerke_fotos_und_spiele_gegen_den_test_roboter():
    from duckpilot.backends.fake_robotd import start_server

    async def go():
        server, fake = await start_server("tcp:127.0.0.1:7988")
        try:
            class Cfg:
                robot = updater = configd = nfcd = "tcp:127.0.0.1:7988"

            care = RobotCare(Cfg())
            fake.schalter["soccer"] = {"autonomous": False}
            ov = await care.overview()
            assert ov["lautstaerke"]["daten"]["volume"] == 70
            assert ov["modus"]["daten"]["spiele"] == ["Fußball"] and ov["gesundheit"]["daten"]["goal_pwm"] == 760
            assert (await care.set_volume(140))["volume"] == 100 and fake.volume == 100    # begrenzt, nie abgelehnt
            assert (await care.set_volume("35"))["volume"] == 35
            fotos = await care.photos()
            assert [f["name"] for f in fotos] == ["2026-11-20_18-04-11"]
            bild = await care.photo("2026-11-20_18-04-11")
            assert bild[:2] == b"\xff\xd8" and bild == fake.fotos["2026-11-20_18-04-11"]
            assert (await care.take_photo())["accepted"] and len(await care.photos()) == 2
            assert await care.delete_photo("2026-11-20_18-04-11") and not await care.delete_photo("2026-11-20_18-04-11")
            for boese in ("../etc/passwd", "a", "/var/lib/robot/photos/x", "2026-11-20_18-04-11.jpg"):
                with pytest.raises(ValueError):
                    await care.photo(boese)
        finally:
            server.close()
            await fake.sim.close()
    asyncio.run(go())


def test_grosses_foto_kommt_in_stuecken():
    from duckpilot.backends.fake_robotd import start_server

    async def go():
        server, fake = await start_server("tcp:127.0.0.1:7989")
        try:
            gross = b"\xff\xd8" + bytes(range(256)) * 200 + b"\xff\xd9"         # ≈ 51 KB → vier Stücke
            fake.fotos = {"2026-11-21_09-00-00-2": gross}

            class Cfg:
                robot = updater = configd = nfcd = "tcp:127.0.0.1:7989"

            return gross, await RobotCare(Cfg()).photo("2026-11-21_09-00-00-2")
        finally:
            server.close()
            await fake.sim.close()

    gross, geholt = asyncio.run(go())
    assert geholt == gross


def test_fotoname_nur_wie_bei_pollen():
    assert foto_name(" 2026-11-11_14-03-27 ") == "2026-11-11_14-03-27" and foto_name("2026-11-11_14-03-27-3")
    for boese in ("..", "x", "2026/11", "", None, "2026-11-11_14-03-27;rm"):
        with pytest.raises(ValueError):
            foto_name(boese)


# ── Pollens NFC-Karten ─────────────────────────────────────────────────────
def test_pollens_tagtexte_wie_pollen_sie_liest():
    assert pollen_tag("  Soccer_Mode ") == "soccer_mode" and pollen_tag("walk_mode") == "walk_mode"
    assert pollen_tag("walk_mode please") is None and pollen_tag("") is None and pollen_tag(None) is None
    assert set(POLLEN_TAGS) == {"walk_mode", "roller_skating_mode", "laser_mode", "soccer_mode", "autonomous_mode",
                                "take_photo", "microduck_gamepad_pairing"}


@pytest.mark.parametrize("text,erwartet", [
    ("walk_mode", ("zubehoer", "rollen_ab")), ("roller_skating_mode", ("zubehoer", "rollen_an")),
    ("laser_mode", ("laser_folgen", None)), ("soccer_mode", ("team", None)), ("autonomous_mode", ("explore", None)),
])
def test_jeder_vorgeschlagene_satz_versteht_knowlin_ohne_sprachmodell(text, erwartet):
    from duckpilot.brain.fallback import parse
    from duckpilot.brain.tools_zubehoer import befehl

    satz = POLLEN_TAGS[text][1]
    werkzeug, aktion = erwartet
    if werkzeug == "zubehoer":
        assert befehl(satz) == aktion
    else:
        cmds = parse(satz)
        assert cmds and cmds[0][0] == werkzeug, (satz, cmds)


def test_neuer_pollen_tag_bekommt_namen_und_satz_bekannter_bleibt(tmp_path):
    st = TagStore(tmp_path / "t.json")
    r = st.touched("04:A1:B2:9F:12:34:80", "soccer_mode")
    assert r["neu"] and r["pollen"] == "soccer_mode" and r["tag"]["name"] == "Pollen: Fußball"
    assert r["satz"] == "spiel Ball mit mir"
    st.put("04A1B29F123480", None, "tanz")                      # selbst geändert – bleibt so
    assert st.touched("04A1B29F123480", "soccer_mode")["satz"] == "tanz"
    foto = st.touched("04FFEE01", "take_photo")
    assert foto["satz"] == "" and "Foto" in foto["hinweis"]
    assert "Gamepad" in st.touched("04FFEE02", "microduck_gamepad_pairing")["hinweis"]
    fremd = st.touched("04FFEE03", "hallo welt")
    assert fremd["neu"] and "pollen" not in fremd and fremd["satz"] == ""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "s.json"))
    monkeypatch.setattr(S, "_keyring", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "m.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        c.rt = rt
        yield c


def test_pollen_karte_vom_handy_fuehrt_den_satz_aus(client):
    r = client.post("/api/nfc/beruehrt", json={"uid": "04:AA:BB:CC", "text": "laser_mode"}, headers=H).json()
    assert r["ok"] and r["pollen"] == "laser_mode" and r["satz"] == "folge dem Laser"
    for _ in range(50):
        if client.rt.engine.current is not None or any("Laser" in str(e) for e in client.rt.engine.events):
            break
        time.sleep(0.05)
    tags = client.get("/api/nfc").json()["tags"]
    assert tags[0]["name"] == "Pollen: Laser"


def test_fotos_und_lautstaerke_nur_am_echten_roboter(client):
    for methode, pfad in (("GET", "/api/pflege/fotos"), ("POST", "/api/pflege/fotos"),
                          ("GET", "/api/pflege/foto/2026-11-20_18-04-11"), ("POST", "/api/pflege/lautstaerke")):
        r = client.request(methode, pfad, json={}, headers=H)
        assert r.status_code == 400 and "echten Roboter" in r.json()["fehler"]


def test_fotos_sind_vom_handy_gesperrt():
    from duckpilot import remote

    def gesperrt(methode, pfad):
        return any((m in ("*", methode)) and p.search(pfad) for m, p in remote.PC_ONLY)

    assert gesperrt("GET", "/api/pflege/fotos") and gesperrt("GET", "/api/pflege/foto/2026-11-20_18-04-11")
    assert gesperrt("DELETE", "/api/pflege/foto/2026-11-20_18-04-11") and gesperrt("POST", "/api/pflege/fotos")
    assert not gesperrt("POST", "/api/pflege/lautstaerke")
    assert "nfcd" in remote.PC_ONLY_SETTINGS


def test_verbindungstest_nennt_was_einer_alten_ente_fehlt():
    from duckpilot import verbindungstest as V
    from duckpilot.backends.fake_robotd import start_server

    async def go():
        server, fake = await start_server("tcp:127.0.0.1:7953")
        original = fake.dispatch

        async def alt(method, p):
            res = await original(method, p)
            return {**res, "api_version": 50, "daemon_version": "0.20.0"} if method == "hello" else res

        fake.dispatch = alt
        try:
            return await V.pruefe_microduck("tcp:127.0.0.1:7953")
        finally:
            server.close()
            await server.wait_closed()

    erg = asyncio.run(go())
    version = next(s for s in erg["schritte"] if s["was"] == "Version")
    assert erg["ok"] and version["stand"] == "hinweis"
    assert "Fotos der Ente" in version["text"] and "Lautstärke" in version["text"] and "OS-Update" in version["text"]
