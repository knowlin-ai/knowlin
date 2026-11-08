"""Tanzen zu Musik und Choreomodus (0.36): Tanzplan, Choreobuch, Routen, Werkzeug, Tanz im Takt, Posen."""

import asyncio
import json
import math
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duckpilot import choreo as C
from duckpilot.api import IntentResult
from duckpilot.brain.tools import ToolRunner
from duckpilot.config import load
from duckpilot.motion import behaviors as B  # noqa: F401
from duckpilot.motion import tanz as T
from duckpilot.server.app import Runtime, create_app
from tests.helpers import make, run_for

ANALYSE = {"bpm": 120, "start": 0.4, "energie": [0.1] * 8 + [0.5] * 8 + [0.9, 0.95, 1.0, 0.85] + [0.6] * 4 + [0.2] * 8}


def _lueckenlos(c):
    tl = C.takt_s(c["bpm"])
    for a, b in zip(c["schritte"], c["schritte"][1:]):
        assert abs(a["t"] + a["takte"] * tl - b["t"]) < 0.01, (a, b)


def test_plan_is_deterministic_beat_aligned_and_follows_energy():
    c = C.plane(ANALYSE)
    assert c == C.plane(ANALYSE)
    assert c["bpm"] == 120 and c["start"] == 0.4
    assert abs(c["dauer"] - (0.4 + 32 * 2.0)) < 0.01
    tl = C.takt_s(120)
    for s in c["schritte"]:
        assert s["art"] in C.SCHRITTE
        assert abs(((s["t"] - 0.4) / tl) - round((s["t"] - 0.4) / tl)) < 1e-6   # immer auf einem Taktanfang
    _lueckenlos(c)
    arten = [s["art"] for s in c["schritte"]]
    assert arten[0] in ("nicken", "wippen", "wiegen")                 # leiser Anfang: ruhig
    assert "drehen" in arten or "schritt" in arten                    # lauter Teil: mehr Bewegung
    assert any(s["art"] == "gefuehl" for s in c["schritte"])          # ohne Posen: Gefühl am Höhepunkt


def test_plan_puts_saved_poses_on_peaks_and_survives_garbage():
    c = C.plane(ANALYSE, ["Storch"])
    posen = [s for s in c["schritte"] if s["art"] == "pose"]
    assert posen and posen[0]["name"] == "Storch" and posen[0]["takte"] == 1
    assert 16 * 2.0 <= posen[0]["t"] - 0.4 < 20 * 2.0                  # im lauten Teil
    _lueckenlos(c)
    leer = C.plane({"bpm": None, "energie": []})
    assert leer["schritte"] and leer["bpm"] == 110
    assert C.plane({"bpm": 999, "energie": [2, -1]})["bpm"] == 220


def test_parts_of_a_song_and_same_dance_for_every_chorus():
    energie = [0.1] * 8 + [0.5] * 8 + [0.9] * 8 + [0.5] * 8 + [0.9] * 8 + [0.1] * 4 + [0.95] * 8 + [0.2] * 4
    namen = [t["name"] for t in C.teile(energie)]
    assert namen == ["Intro", "Strophe", "Refrain", "Strophe", "Refrain", "Breakdown", "Drop", "Outro"]
    c = C.plane({"bpm": 128, "start": 0.0, "energie": energie})
    tl = C.takt_s(128)

    def tanz_ab(takt, n):
        return [(round((s["t"] / tl) - takt), s["takte"], s["art"]) for s in c["schritte"] if takt <= s["t"] / tl + 1e-6 < takt + n]
    erster = [(a, n) for _, n, a in tanz_ab(16, 8)]
    zweiter = [(a, n) for _, n, a in tanz_ab(32, 8)]
    assert erster == zweiter                                          # jeder Refrain gleich getanzt
    assert tanz_ab(44, 8)[0][2] == "gefuehl"                          # Drop beginnt mit einem Höhepunkt
    assert c["schritte"][-1]["art"] == "gefuehl"                     # Schlussgeste im letzten Takt
    assert [a["name"] for a in c["abschnitte"]] == namen
    assert C.pruefe(c)["abschnitte"] == c["abschnitte"]              # Teile bleiben beim Speichern erhalten
    assert C.teile([]) == [] and C.teile([0.5] * 3)[0]["name"] == "Refrain"


def test_pruefe_drops_unknown_steps_and_clamps():
    c = C.pruefe({"bpm": 100, "schritte": [
        {"t": 4, "takte": 2, "art": "wippen"}, {"t": 0, "takte": 999, "art": "nicken"},
        {"t": 1, "art": "rm -rf"}, {"t": 2, "art": "pose"}, {"t": "x", "art": "drehen"},
        {"t": 3, "art": "pose", "name": "Storch / ../x"}]})
    assert [s["art"] for s in c["schritte"]] == ["nicken", "pose", "wippen"]
    assert c["schritte"][0]["takte"] == 64
    assert "/" not in c["schritte"][1]["name"]


def test_book_saves_lists_and_keeps_music_safe(tmp_path):
    buch = C.ChoreoBuch(tmp_path)
    with pytest.raises(ValueError):
        buch.musik_ablegen("virus.exe", b"x")
    with pytest.raises(ValueError):
        buch.musik_ablegen("leer.mp3", b"")
    datei = buch.musik_ablegen("../../Mein Lied!.mp3", b"ID3data")
    assert datei == "Mein_Lied.mp3" and (tmp_path / "musik" / datei).read_bytes() == b"ID3data"
    assert buch.musik_pfad("../settings.json") is None and buch.musik_pfad(datei)
    gespeichert = buch.speichere("Ententanz", C.plane(ANALYSE), datei)
    assert gespeichert["musik"] == datei
    assert buch.speichere("Ohne", C.plane(ANALYSE), "gibtsnicht.mp3")["musik"] == ""
    assert [t["name"] for t in buch.liste()] == ["Ententanz", "Ohne"]
    assert buch.hole("Ententanz")["schritte"]
    with pytest.raises(ValueError):
        buch.speichere("", C.plane(ANALYSE))
    with pytest.raises(ValueError):
        buch.speichere("Leer", {"schritte": []})
    assert buch.loesche("Ohne") and not buch.loesche("Ohne")
    assert json.loads((tmp_path / "choreos.json").read_text(encoding="utf-8")).keys() == {"Ententanz"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        yield c, rt


def test_routes_upload_plan_save_and_dance(client):
    c, rt = client
    assert c.get("/api/choreo").json()["taenze"] == []
    assert c.post("/api/musik?name=a.txt", content=b"x").status_code == 400
    datei = c.post("/api/musik?name=Lied.mp3", content=b"ID3").json()["datei"]
    assert c.get(f"/api/musik/{datei}").content == b"ID3"
    assert c.get("/api/musik/..%2Fsettings.json").status_code == 404
    plan = c.post("/api/choreo/plan", json={"analyse": ANALYSE}).json()
    assert plan["ok"] and plan["choreo"]["schritte"]
    r = c.post("/api/choreo/speichern", json={"name": "Probe1", "choreo": plan["choreo"], "musik": datei}).json()
    assert r["ok"] and r["choreo"]["musik"] == datei
    liste = c.get("/api/choreo").json()
    assert liste["taenze"][0]["name"] == "Probe1" and liste["musik"] == [datei]
    assert c.get("/api/choreo/Probe1").json()["ok"] and c.get("/api/choreo/Nix").status_code == 404
    assert c.post("/api/choreo/tanzen", json={"choreo": {"schritte": [{"art": "quatsch"}]}}).status_code == 400
    assert c.request("DELETE", "/api/choreo", json={"name": "Probe1"}).json()["ok"]
    assert "freude" in liste["gesten"] and "tot_stellen" not in liste["gesten"]   # Gesten aus Tricks, ohne Hinlegen


def test_ai_choreography_goes_through_the_normal_chat(client, monkeypatch):
    c, rt = client
    plan = c.post("/api/choreo/plan", json={"analyse": ANALYSE}).json()["choreo"]
    if not rt.agent.online:
        assert c.post("/api/choreo/ki", json={"name": "X", "choreo": plan}).status_code == 400
    gesagt = []

    async def chat(text, via="text"):
        gesagt.append((text, via))

    monkeypatch.setattr(type(rt.agent), "online", property(lambda self: True))
    monkeypatch.setattr(rt, "chat", chat)
    assert c.post("/api/choreo/ki", json={"name": "Mein Lied", "musik": "fehlt.mp3", "choreo": plan}).json()["ok"]
    for _ in range(50):
        if gesagt:
            break
        c.get("/api/choreo")
    text, via = gesagt[0]
    assert via == "tanz" and "Mein Lied" in text and "Refrain ab" in text and "begeistert" in text
    assert "fehlt.mp3" not in text                                   # nur Musik, die es wirklich gibt


def test_tool_dances_saved_choreo_and_starts_music(tmp_path):
    async def go():
        sim, eng = await make(zufall=3)
        r = ToolRunner(eng)
        assert (await r.run("choreo", {"aktion": "liste"}))["ok"] is False   # ohne Buch kein Choreomodus
        r.choreos = C.ChoreoBuch(tmp_path)
        datei = r.choreos.musik_ablegen("x.mp3", b"ID3")
        r.choreos.speichere("Kurz", {"bpm": 120, "schritte": [{"t": 0, "takte": 1, "art": "nicken"},
                                                              {"t": 2, "takte": 1, "art": "drehen"}]}, datei)
        gespielt, neu = [], []
        r.on_musik = lambda datei, ab=0.0: gespielt.append((datei, ab))
        r.on_choreo = neu.append
        assert (await r.run("choreo", {"aktion": "liste"}))["taenze"][0]["name"] == "Kurz"
        nein = await r.run("choreo", {"aktion": "tanzen", "name": "Gibtsnicht"})
        assert not nein["ok"] and nein["taenze"] == ["Kurz"]
        ja = await r.run("choreo", {"aktion": "tanzen", "name": "Kurz", "ab": 2.0})
        assert ja["ok"] and gespielt == [(datei, 2.0)] and eng.current.ab == 2.0   # ab der Startmarke
        # Die KI legt Tänze mit dem Werkzeug an – die Oberfläche öffnet sie danach
        k = await r.run("choreo", {"aktion": "speichern", "name": "Von Claude", "musik": datei, "bpm": 100, "start": 0.2,
                                    "schritte": [{"t": 0.2, "takte": 2, "art": "wippen"},
                                                 {"t": 5.0, "takte": 1, "art": "gefuehl", "name": "freude"},
                                                 {"t": 7.4, "takte": 1, "art": "laserschwert"}]})
        assert k["ok"] and k["schritte"] == 2 and neu == ["Von Claude"]
        assert r.choreos.hole("Von Claude")["musik"] == datei
        assert not (await r.run("choreo", {"aktion": "speichern", "name": "Leer", "schritte": []}))["ok"]
        assert await run_for(sim, eng, 8, until=lambda: eng.current is None or eng.current.name != "choreo")
        assert not sim.state().fallen
    asyncio.run(go())


def test_dance_moves_on_beat_and_hints_rejected_poses():
    async def go():
        sim, eng = await make(zufall=5)
        gerufen = []

        async def haltung(gelenke, sekunden):        # einfacher Simulator: Beine posieren geht nicht
            gerufen.append((gelenke, sekunden))
            return IntentResult(False, "nur Physik")

        sim.haltung = haltung
        c = {"bpm": 120, "start": 0.0, "dauer": 6.0, "schritte": [
            {"t": 0.0, "takte": 1, "art": "wackeln"}, {"t": 2.0, "takte": 1, "art": "pose", "name": "Storch"},
            {"t": 4.0, "takte": 1, "art": "gefuehl", "name": "freude"}]}
        tanz = T.MusikTanz(c, {"Storch": {"left_knee": 0.5}}, "Test")
        eng.run(tanz)
        await run_for(sim, eng, 1.0)
        assert tanz._schritt(tanz.elapsed)[1]["art"] == "wackeln"
        await run_for(sim, eng, 1.6)
        assert gerufen and gerufen[0][0] == {"left_knee": 0.5} and tanz._angedeutet   # abgelehnt → angedeutet
        await run_for(sim, eng, 4.0)
        assert eng.current is None or eng.current is not tanz
        assert not sim.state().fallen
    asyncio.run(go())


def test_simple_backend_rejects_leg_poses():
    async def go():
        sim, _ = await make()
        r = await sim.haltung({"left_knee": 0.3}, 1.0)
        assert not r.accepted and "Physik" in r.reason
    asyncio.run(go())


def test_physics_pose_ramps_holds_and_returns():
    np = pytest.importorskip("numpy")
    pytest.importorskip("mujoco")
    from duckpilot.physics import core as P

    core = P.PhysicsCore(None)
    ziele = (lambda: core.bam_ctrl.q_target) if core.bam is not None else (lambda: core.data.ctrl)
    ziel = P.DEFAULT_POSE.astype(np.float32).copy()
    ziel[7] += 0.3
    core.start_pose(0.2, ziel=ziel, halten=0.2)
    n = round(0.2 / P.CONTROL_DT)
    for _ in range(n + 2):
        core.control_step(P.Command())
    assert abs(ziele()[7] - ziel[7]) < 1e-5 and core.posing                # angekommen und hält
    for _ in range(n + 2 * n + 2):
        core.control_step(P.Command())
    assert not core.posing                                                  # zurück in der Grundstellung
    assert abs(ziele()[7] - P.DEFAULT_POSE[7]) < 0.05


# ── 0.36.1: Tanzgesten aus den Tricks, nach Gehör, Klangsignatur ──────────────────────────────────────────────────

def test_dance_gestures_fit_the_beat_and_come_from_tricks():
    from duckpilot.motion.behaviors import EMOTIONS

    for liste in C.TANZGESTEN.values():
        for name in liste:
            assert name in EMOTIONS and not any("skill" in kf for kf in EMOTIONS[name])   # nie hinsetzen im Tanz
    for laenge, bpm, takte in [(1.6, 120, 2), (2.9, 174, 2), (0.9, 72, 1), (4.0, 60, 1)]:
        schlaege, tempo = C.geste_im_takt(laenge, bpm, takte)
        assert (takte * 4) % schlaege == 0                       # Wiederholungen füllen den Schritt glatt
        assert 0.5 <= tempo <= 2.0 or schlaege in (1, takte * 4)
    c = C.plane(ANALYSE)
    tricks = [s for s in c["schritte"] if s["art"] == "trick"]
    assert tricks and all(s["name"] in sum(C.TANZGESTEN.values(), ()) for s in tricks)
    assert C.pruefe({"bpm": 100, "schritte": [{"t": 0, "takte": 2, "art": "trick", "name": "jep"}]})["schritte"][0]["name"] == "jep"


def test_trick_step_plays_the_gesture_in_time():
    async def go():
        sim, eng = await make(zufall=7)
        tanz = T.MusikTanz({"bpm": 120, "start": 0.0, "dauer": 4.5, "schritte": [
            {"t": 0.0, "takte": 2, "art": "trick", "name": "begeistert"}]}, {}, "Test")
        eng.run(tanz)
        await run_for(sim, eng, 1.0)
        assert tanz._geste is not None and tanz._geste.title == "begeistert"
        assert tanz._geste.loops * C.geste_im_takt(tanz._geste.length, 120, 2)[0] == 8
        await run_for(sim, eng, 4.5)
        assert eng.current is not tanz and not sim.state().fallen
    asyncio.run(go())


def test_dancing_by_ear_follows_tempo_and_stops_in_silence():
    async def go():
        sim, eng = await make(zufall=9)
        r = ToolRunner(eng)
        r.choreos = C.ChoreoBuch(Path(tempfile.mkdtemp()))
        assert (await r.run("choreo", {"aktion": "gehoer"}))["ok"]
        tanz = r.gehoer
        assert eng.current is tanz or tanz.started is False
        await run_for(sim, eng, 0.5)
        tanz.hoeren(128, 0.1, 0.9)                          # laut → wackeln, drehen, Tanzgesten
        await run_for(sim, eng, 2.0)
        assert tanz.bpm == 128 and tanz.stufe() == 2 and not tanz.done
        for _ in range(12):                                   # Stille: nach 8 s hört sie auf
            tanz.hoeren(128, 0.2, 0.0)
            await run_for(sim, eng, 1.0)
        assert tanz.done and "Musik" in tanz.result
        assert not sim.state().fallen
    asyncio.run(go())


def test_dancing_by_ear_moves_on_through_steps_turns_and_gestures():
    """Regression (Hinweis aus dem Test 1.11.): Mit Messungen alle 1,5 s blieb sie im ersten Abschnitt hängen und wackelte
    nur. Der Schlagzähler läuft jetzt weiter – Seitschritte, Drehung und Tanzgesten wechseln sich ab."""
    async def go():
        sim, eng = await make(zufall=9)
        tanz = T.GehoerTanz()
        eng.run(tanz)
        await run_for(sim, eng, 0.3)
        bpm, arten, yaw0, gedreht = 120.0, set(), sim.yaw, 0.0
        for i in range(30):                                   # 45 s Musik, Messung alle 1,5 s wie die Oberfläche
            tanz.hoeren(bpm, (i * 1.5) % 0.5, 0.2)             # leise Musik (Stufe 0)
            for _ in range(3):
                await run_for(sim, eng, 0.5)
                arten.add(tanz._art)
                gedreht = max(gedreht, abs(sim.yaw - yaw0))
        assert tanz._segment >= 5, tanz._segment
        assert {"schritt", "drehen", "trick"} <= arten, arten
        assert gedreht > 1.0 and not tanz.done and not sim.state().fallen
        b0 = tanz.takt()[1]
        tanz.hoeren(bpm, 0.25, 0.2)                           # neue Messung: kein Sprung im Schlagzähler
        assert abs(tanz.takt()[1] - b0) < 0.01
    asyncio.run(go())


def test_dancing_by_ear_ends_without_measurements(client):
    c, rt = client
    assert c.post("/api/gehoer", json={"aktion": "messung", "bpm": 120}).json()["laeuft"] is False
    assert c.post("/api/gehoer", json={"aktion": "quatsch"}).status_code == 400
    t = T.GehoerTanz()
    t.elapsed = 10.0
    t._gemeldet = 0.0
    assert t.tick(None, 0.05) is None and t.done and "Keine Musik" in t.result


def test_sound_signature_setting_is_checked():
    from duckpilot import settings as S

    ok = S.validate({"klang_hoehe": 2.5, "klang_farbe": -0.4})
    assert ok["klang_hoehe"] == 2.5 and ok["klang_farbe"] == -0.4
    for falsch in ({"klang_hoehe": 9}, {"klang_farbe": 2}, {"klang_hoehe": True}):
        with pytest.raises(ValueError):
            S.validate(falsch)


# ── 0.36.2: am Platz bleiben, Bein zu Bein, Drehungen ────────────────────────────────────────────────────────────

def test_dance_stays_on_its_spot():
    """Hinweis aus dem Test: „die Ente geht beim Tanzen immer weiter rückwärts“ – Abdrift wird zurückgeholt."""
    from types import SimpleNamespace as NS

    from duckpilot.api import Twist
    from duckpilot.motion.engine import Command

    tanz = T.MusikTanz({"bpm": 120, "schritte": [{"t": 0, "takte": 2, "art": "schritt"}]}, {}, "x")
    tanz.on_start(NS(x=1.0, y=2.0, yaw=0.0))
    weg = tanz._am_platz(NS(x=0.8, y=2.0, yaw=0.0), Command(twist=Twist()))          # 20 cm zurückgerutscht
    assert 0.05 <= weg.twist.vx <= 0.06 and abs(weg.twist.vy) < 1e-9
    seitlich = tanz._am_platz(NS(x=0.8, y=2.0, yaw=math.pi / 2), Command(twist=Twist()))   # gedreht: Korrektur seitlich
    assert abs(seitlich.twist.vx) < 1e-9 and seitlich.twist.vy < -0.05
    nah = tanz._am_platz(NS(x=1.01, y=2.0, yaw=0.0), Command(twist=Twist(0.0, 0.05, 0.0)))   # innerhalb 3 cm: nichts
    assert nah.twist.vx == 0.0 and nah.twist.vy == 0.05


def test_leg_to_leg_and_full_turns():
    tanz = T.MusikTanz({"bpm": 120, "schritte": []}, {}, "x")
    vy = [tanz._bewegung("schritt", b / 20, 0.0).twist.vy for b in range(40)]        # zwei Schläge
    assert max(vy) > 0.05 and min(vy) < -0.05 and abs(sum(vy)) < 0.05                 # links, rechts – kein Wandern
    rolle = [tanz._bewegung("wiegen", b / 10, 0.0).pose.roll for b in range(40)]
    assert max(rolle) > 0.15 and min(rolle) < -0.15
    links = tanz._bewegung("drehen", 0.3, 0.0, richtung=1.0, takte=4).twist.vyaw
    rechts = tanz._bewegung("drehen", 0.3, 0.0, richtung=-1.0, takte=4).twist.vyaw
    assert links > 0.7 and rechts == -links                                            # 4 Takte bei 120 BPM: eine Drehung
    c = C.plane(ANALYSE)
    arten = {s["art"] for s in c["schritte"]}
    assert {"schritt", "drehen", "wiegen"} <= arten


# ── 0.36.2: Fehlerbericht „Das lief schief“ ────────────────────────────────────────────────────────────────────────

def test_report_keeps_only_allowed_fields_and_no_private_data():
    from duckpilot.server.fehlerbericht import Blackbox, issue_link

    box = Blackbox()
    box.zustand({"x": 1.23456, "y": 0.0, "yaw": 0.1, "fallen": True, "twist": {"vx": 0.1}, "perception": {"personen": ["Anna"]},
                 "physik": {"policy": "walk", "geheim": 1}}, {"aktuell": "choreo (Quacki-Tanz, 120 bpm, 60s)", "gefuehl": "x"})
    box.ereignis({"type": "fall", "message": r"gefallen C:\Users\Namenlos\AppData\x", "bild": "data:..."})
    box.ereignis({"type": "chat", "message": "Ich heiße Anna"})
    box.ereignis({"type": "person", "message": "Anna erkannt"})
    b = box.bericht(version="0.36.2", einstellungen={"backend": "sim", "api_key": "sk-ant-geheim", "duck_name": "Quacki",
                                                    "gehirn": "claude"}, ente="Quacki", beschreibung="Quacki fiel um")
    text = json.dumps(b, ensure_ascii=False)
    for verboten in ("Anna", "sk-ant", "Namenlos", "Quacki", "perception", "data:", "api_key", "geheim"):
        assert verboten not in text, verboten
    assert b["zustand"][0]["x"] == 1.235 and b["zustand"][0]["policy"] == "walk"
    assert [e["type"] for e in b["ereignisse"]] == ["fall"]
    assert b["einstellungen"] == {"backend": "sim", "gehirn": "claude"}
    assert "die Ente fiel um" in b["beschreibung"]
    assert issue_link(b, "bericht-1.json").startswith("https://github.com/knowlin-ai/knowlin/issues/new?")


def test_report_route_saves_and_serves_the_file(client):
    c, rt = client
    rt.blackbox.zustand({"x": 0.0, "y": 0.0, "fallen": False}, {"aktuell": None})
    r = c.post("/api/fehlerbericht", json={"beschreibung": "Test"}).json()
    assert r["ok"] and r["datei"].startswith("bericht-") and r["bericht"]["version"]
    assert c.get(f"/api/fehlerbericht/{r['datei']}").json()["art"] == "duckpilot-fehlerbericht"
    assert c.get("/api/fehlerbericht/..%2Fsettings.json").status_code == 404


def test_music_stops_with_the_dance_and_extra_ducks_show_their_state():
    """0.37.1 (Hinweis aus dem Teste „wie kann ich Musik im Tanzmodus stoppen?“, „die anderen Enten werden nicht angezeigt“):
    Musik endet mit dem Tanz (Not-Aus, Esc, Stopp, anderer Befehl), eine Leiste mit Stopp-Knopf solange sie spielt; die
    Auswahl „Weitere Enten“ zeigt beim Start die echte Anzahl und ist ohne einfachen Simulator ausgegraut."""
    static = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"
    html = (static / "index.html").read_text("utf-8")
    tanz = (static / "tanz.js").read_text("utf-8")
    app = (static / "app.js").read_text("utf-8")
    enten = (static / "enten.js").read_text("utf-8")
    assert 'id="tanz-spielt"' in html and 'id="tanz-spielt-stopp"' in html
    assert "function pruefen(engine)" in tanz and "startsWith('choreo')" in tanz and "audio.pause()" in tanz
    assert "tanz?.pruefen(lastEngine);" in app
    assert "sel.disabled = !d.verfuegbar" in enten and "\n  laden();" in enten
    assert "data-enten-hinweis" in html


def test_body_can_be_switched_from_the_top_and_extra_ducks_have_contact_shadows():
    """0.37.2: Körper-Chip oben als Menü (einfach / Physik / Roboter, am Handy nur Anzeige); Kontaktschatten unter
    weiteren Enten (Hinweis aus dem Test „die Enten schweben“)."""
    static = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"
    html = (static / "index.html").read_text("utf-8")
    wahl = (static / "koerperwahl.js").read_text("utf-8")
    app = (static / "app.js").read_text("utf-8")
    d3 = (static / "duck3d.js").read_text("utf-8")
    for k in ("sim", "physik", "robotd"):
        assert f'data-koerper="{k}"' in html
    assert 'id="koerper-btn"' in html and 'aria-controls="koerper-pop"' in html
    assert "modul: modul === 'open_duck_mini' ? modul : 'duckpilot', backend: 'sim', sim_physik: k === 'physik' }" in wahl and "btn.disabled = fern" in wahl
    assert "koerperwahl.update(config);" in app
    assert "_kontaktSchatten()" in d3 and "e._schatten.position.set" in d3


def test_stopp_beim_tanzen_ist_kein_not_aus(tmp_path):
    """Gemeldet nach 0.38.33: „Stopp“ unter Tanzen löste den Not-Aus aus – danach 2 Minuten Sperre, „Probe tanzen“
    wurde abgelehnt. Jetzt endet nur der Tanz."""
    async def go():
        sim, eng = await make(zufall=3)
        r = ToolRunner(eng)
        r.choreos = C.ChoreoBuch(tmp_path)
        r.choreos.speichere("Kurz", {"bpm": 120, "schritte": [{"t": 0, "takte": 4, "art": "wippen"}]}, "")
        assert (await r.run("choreo", {"aktion": "tanzen", "name": "Kurz"}))["ok"]
        await run_for(sim, eng, 1.0)
        aus = await r.run("choreo", {"aktion": "stopp"})
        assert aus["ok"] and aus["gestoppt"] and eng.current is None
        assert not eng.notaus_gesperrt()                       # keine Sperre wie nach dem Not-Aus
        assert (await r.run("choreo", {"aktion": "tanzen", "name": "Kurz"}))["ok"]   # gleich wieder tanzen
    asyncio.run(go())
