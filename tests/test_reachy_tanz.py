"""Reachys eigener Tanz, Mitwippen und Begrüßung (seit 0.38.13, Hinweis aus dem Test 5.11.: „der tanzmodus ist nicht auf
reachy angepasst“): nur Reachy-Bewegungen, keine Laute, Kinematik eingehalten, Takt-Dehnung, Begrüßung nur beim
Wecken, Einstellungen, Not-Aus stoppt Tanz und Mitwippen. Dazu: Open Duck schlägt die Antennen im Takt."""

import asyncio
import json
import math
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from helpers import make, run_for

from duckpilot import choreo as C
from duckpilot import settings as S
from duckpilot.backends.open_duck import OpenDuckSim
from duckpilot.backends.reachy import ReachyMiniSim, kopf_ziel
from duckpilot.backends.reachy_kinematik import ersatz_erreichbar
from duckpilot.brain.tools import ToolRunner
from duckpilot.config import load
from duckpilot.motion import reachy_tanz as RT
from duckpilot.motion.engine import MotionEngine
from duckpilot.motion.reachy_gesten import GESTEN
from duckpilot.motion.tanz import TANZGESTEN, MusikTanz
from duckpilot.server.app import Runtime, create_app

ANALYSE = {"bpm": 120, "start": 0.4, "energie": [0.1] * 8 + [0.5] * 8 + [0.9, 0.95, 1.0, 0.85] + [0.6] * 4 + [0.2] * 8}
WS = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
STATIC = Path(__file__).resolve().parent.parent / "duckpilot" / "server" / "static"


def run(coro):
    return asyncio.run(coro)


async def make_reachy():
    sim = ReachyMiniSim(realtime=False, seed=1)
    sim._task = object()
    eng = MotionEngine(sim)
    await eng.stand_up()
    await run_for(sim, eng, 2.5)
    return sim, eng


def _nur_reachy(c):
    for s in c["schritte"]:
        assert s["art"] in ("trick", "gefuehl", "pause"), s
        if s["art"] == "trick":
            assert s["name"] in RT.REACHY_TANZ, s
        if s["art"] == "gefuehl":
            assert s["name"] in GESTEN, s


# ── Vokabular ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_plan_fuer_reachy_nur_reachy_bewegungen_ohne_posen():
    c = C.plane(ANALYSE, ["Storch"], reachy=True)
    assert c == C.plane(ANALYSE, ["Storch"], reachy=True) and c["koerper"] == "reachy_mini"
    _nur_reachy(c)
    tl = C.takt_s(120)
    for a, b in zip(c["schritte"], c["schritte"][1:]):           # lückenlos auf Taktanfängen
        assert abs(a["t"] + a["takte"] * tl - b["t"]) < 0.01
    namen = {s["name"] for s in c["schritte"] if s["art"] == "trick"}
    assert "koerper_drehen" in namen                               # im lauten Teil dreht sich der Körper
    assert not namen & (set(TANZGESTEN[0] + TANZGESTEN[1] + TANZGESTEN[2]) - set(RT.REACHY_TANZ))   # keine Entengesten
    gespeichert = C.pruefe(c)
    assert gespeichert["koerper"] == "reachy_mini"
    assert "koerper" not in C.pruefe(C.plane(ANALYSE))            # der Entenplan bleibt, wie er war
    assert {s["art"] for s in C.plane(ANALYSE)["schritte"]} & {"schritt", "wiegen"}


def test_stufen_und_namen_vollstaendig():
    alle = {n for liste in RT.REACHY_STUFEN.values() for n in liste}
    assert alle <= set(RT.REACHY_TANZ) and set(RT.REACHY_TANZ) == set(RT.REACHY_TANZ_TEXT)
    assert set(RT.AUS_ENTE.values()) <= set(RT.REACHY_TANZ) and set(RT.REACHY_GEFUEHLE) <= set(GESTEN)
    for name in ("schritt", "drehen", "traellern", "quatsch"):
        assert RT.aufloesen(name) in RT.REACHY_TANZ


def test_ki_bekommt_nur_reachy_bewegungen():
    auftrag = C.ki_auftrag_reachy("Lied", "", C.plane(ANALYSE, reachy=True))
    assert all(n in auftrag for n in RT.REACHY_TANZ) and "Posen" not in auftrag
    assert "traellern" not in auftrag and "Bein zu Bein" not in auftrag

    async def go():
        sim, eng = await make_reachy()
        werkzeug = next(t for t in ToolRunner(eng).tools() if t["name"] == "choreo")
        schritt = werkzeug["input_schema"]["properties"]["schritte"]["items"]["properties"]
        assert schritt["art"]["enum"] == ["trick", "gefuehl", "pause"]
        assert set(schritt["name"]["enum"]) == set(RT.REACHY_TANZ) | set(C.reachy_gesten())
        _, ente = await make()
        werkzeug = next(t for t in ToolRunner(ente).tools() if t["name"] == "choreo")
        assert "schritt" in werkzeug["input_schema"]["properties"]["schritte"]["items"]["properties"]["art"]["enum"]
    run(go())


# ── Keine Laute, Kinematik, Takt ──────────────────────────────────────────────────────────────────────────────────
def test_keine_laute_in_den_bewegungen():
    for name, kfs in [*RT.REACHY_TANZ.items(), ("begruessung", RT.BEGRUESSUNG)]:
        for kf in kfs:
            assert not {"ton", "sound", "klang", "skill", "fahren", "move", "schnabel"} & set(kf), (name, kf)


@pytest.mark.parametrize("name", sorted(RT.REACHY_TANZ))
def test_bewegungen_bleiben_in_reachys_kinematik(name):
    """Auch ohne Pollens Modell (vorsichtige Ersatzprüfung) erreichbar – bei jeder Skala und jedem Tempo; jede
    Wiederholung endet, wo sie begann; die Körperdrehung bleibt in ±30°."""
    kfs = RT.REACHY_TANZ[name]
    assert kfs[0]["t"] == 0 and {k: kfs[0].get(k) for k in ("kopf",)} == {k: kfs[-1].get(k) for k in ("kopf",)}
    assert (kfs[0].get("koerper") or {}).get("hoehe_mm", 0) == (kfs[-1].get("koerper") or {}).get("hoehe_mm", 0)
    for skala in (0.68, 1.0, 1.1):
        for bpm in (70, 120, 180):
            ch = RT.bewegung(name, bpm, 8, skala)
            for i in range(int(ch.length * ch.loops / 0.02)):
                ch.elapsed = i * 0.02
                cmd = ch.tick(None, 0.02)
                if cmd is None:
                    break
                lage = kopf_ziel(cmd.head, cmd.pose)
                assert ersatz_erreichbar(lage), (name, skala, bpm, lage)
    for b in range(0, 81):
        w = RT.koerper_winkel(name, b / 10)
        assert w is None or abs(w) <= RT.KOERPER_MAX_GRAD


def test_begruessung_bleibt_in_der_kinematik():
    ch = RT.begruessung()
    assert not ch.needs_legs                     # nur Kopf und Antennen – geht gleich nach dem Aufwachen
    for i in range(int(ch.length / 0.02)):
        ch.elapsed = i * 0.02
        cmd = ch.tick(None, 0.02)
        assert cmd is None or ersatz_erreichbar(kopf_ziel(cmd.head, cmd.pose))


def test_bewegung_wird_im_takt_gestreckt():
    langsam, schnell = RT.bewegung("kopfnicken", 60, 8), RT.bewegung("kopfnicken", 120, 8)
    assert langsam.length == pytest.approx(1.0) and schnell.length == pytest.approx(0.5)
    assert langsam.loops == 8 and schnell.loops == 8                     # ein Nicken je Schlag
    dreh = RT.bewegung("koerper_drehen", 120, 16)
    assert dreh.length == pytest.approx(4.0) and dreh.loops == 2          # zwei Takte je Wiederholung
    assert RT.bewegung("wiegen", 100, 3).loops >= 1
    assert RT.koerper_winkel("koerper_drehen", 2.0) == pytest.approx(25.0)
    assert RT.koerper_winkel("koerper_drehen", 10.0) == pytest.approx(25.0)   # wiederholt sich
    assert RT.koerper_winkel("kopfnicken", 1.0) is None


def test_reachy_tanzt_im_simulator_mit_kopf_antennen_und_drehung():
    async def go():
        sim, eng = await make_reachy()
        toene = []
        orig = sim.sound

        async def sound(tag):
            toene.append(tag)
            return await orig(tag)
        sim.sound = sound
        notizen = []
        eng.listeners.append(notizen.append)
        r = ToolRunner(eng)
        r.choreos = C.ChoreoBuch(Path(__import__("tempfile").mkdtemp()))
        r.choreos.speichere("Reachy", C.plane(ANALYSE, reachy=True))
        assert (await r.run("choreo", {"aktion": "tanzen", "name": "Reachy"}))["ok"]
        assert isinstance(eng.current, RT.ReachyMusikTanz)
        x0, y0 = sim.x, sim.y
        antennen, koerper, kipp = set(), [], []
        for _ in range(50 * 4):
            await run_for(sim, eng, 0.25)
            st = sim.state()
            antennen.add(tuple(round(a, 1) for a in st.antennen))
            koerper.append(math.degrees(st.kopf_lage["koerper"]))
            kipp.append(abs(st.kopf_lage["pitch"]) + abs(st.kopf_lage["roll"]))
        assert toene == [] and not any(n.get("type") == "sound" for n in notizen)   # nie Entenlaute
        assert len(antennen) > 10 and max(kipp) > 0.05                                # Antennen und Kopf tanzen
        assert max(koerper) > 15 and min(koerper) < -15 and max(map(abs, koerper)) < 35   # Körper dreht hin und her
        assert (sim.x, sim.y) == (x0, y0) and not sim.limited_by                      # steht fest, kein „ohne Beine“
    run(go())


def test_alte_entenschritte_werden_fuer_reachy_uebersetzt():
    async def go():
        sim, eng = await make_reachy()
        c = {"bpm": 120, "schritte": [{"t": 0, "takte": 1, "art": "schritt"}, {"t": 2, "takte": 1, "art": "drehen"},
                                      {"t": 4, "takte": 1, "art": "pose", "name": "Storch"},
                                      {"t": 6, "takte": 1, "art": "trick", "name": "traellern"}]}
        tanz = RT.ReachyMusikTanz(C.pruefe(c), "alt")
        eng.run(tanz)
        gesehen = set()
        for _ in range(40):
            await run_for(sim, eng, 0.25)
            if tanz._bew is not None:
                gesehen.add(tanz._bew_name)
            if tanz._geste is not None:
                gesehen.add(tanz._geste.title)
        assert gesehen and gesehen <= set(RT.REACHY_TANZ) | set(GESTEN)
        assert "antennen_takt" in gesehen and "koerper_drehen" in gesehen and "stolz" in gesehen
    run(go())


def test_dance_werkzeug_tanzt_bei_reachy_den_eigenen_tanz():
    async def go():
        sim, eng = await make_reachy()
        assert (await ToolRunner(eng).run("dance", {"style": "party", "seconds": 8}))["ok"]
        assert isinstance(eng.current, RT.ReachyMusikTanz)
        _nur_reachy({"schritte": eng.current.schritte})
    run(go())


# ── Mitwippen und Not-Aus ────────────────────────────────────────────────────────────────────────────────────────
def test_mitwippen_ruhig_und_ohne_koerperdrehung():
    async def go():
        sim, eng = await make_reachy()
        tanz = RT.ReachyGehoerTanz(ruhig=True)
        eng.run(tanz)
        koerper = []
        for _ in range(16):
            tanz.hoeren(128, 0.1, 0.95)                 # auch laute Musik: nur ruhige Bewegungen
            await run_for(sim, eng, 1.5)
            koerper.append(abs(sim.state().kopf_lage["koerper"]))
            assert tanz._bew_name in RT.REACHY_STUFEN[0]
        assert not tanz.done and tanz.describe().startswith("mitwippen")
        assert max(koerper) < math.radians(3)
        laut = RT.ReachyGehoerTanz()
        laut.energie = 0.95
        assert laut.stufe() == 2 and tanz.stufe() == 0
    run(go())


@pytest.fixture()
def reachy_client(tmp_path, monkeypatch):
    einst = tmp_path / "settings.json"
    einst.write_text(json.dumps({"backend": "sim", "modul": "reachy_mini"}), encoding="utf-8")
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(einst))
    monkeypatch.setenv("DUCKPILOT_OFFLINE", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    gesendet = []
    orig = rt.broadcast

    async def spy(msg):
        gesendet.append(msg)
        await orig(msg)
    rt.broadcast = spy
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        yield c, rt, gesendet


def _warte(pred, sekunden=6.0):
    ende = time.time() + sekunden
    while time.time() < ende:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


def _gruesse(gesendet):
    return [m for m in gesendet if m.get("type") == "chat" and m.get("source") == "system" and "Ich bin" in m.get("text", "")]


def test_routen_fuer_reachy_und_not_aus_stoppt_mitwippen(reachy_client):
    c, rt, gesendet = reachy_client
    assert isinstance(rt.backend, ReachyMiniSim)
    d = c.get("/api/choreo").json()
    assert d["reachy"] and d["gesten"] == list(RT.REACHY_TANZ) and d["posen"] == [] and set(d["namen"]) == set(RT.REACHY_TANZ)
    assert set(d["gefuehle"]) <= set(GESTEN) and "traurig" not in d["gefuehle"]
    plan = c.post("/api/choreo/plan", json={"analyse": ANALYSE}).json()
    assert plan["ok"]
    _nur_reachy(plan["choreo"])
    with c.websocket_connect("/ws", headers=WS) as ws:
        ws.send_json({"type": "koerper"})                       # Reachy wecken
        assert _warte(lambda: rt.im_koerper and rt.backend.state().powered and not rt.backend.state().sitting)
        r = c.post("/api/gehoer", json={"aktion": "start", "ruhig": True}).json()
        assert r["ok"] and isinstance(rt.runner.gehoer, RT.ReachyGehoerTanz) and rt.runner.gehoer.ruhig
        assert c.post("/api/gehoer", json={"aktion": "messung", "bpm": 100, "schlag_vor_s": 0.1, "energie": 0.4}).json()["laeuft"]
        ws.send_json({"type": "stop"})                          # Not-Aus
        assert _warte(lambda: rt.engine.current is None)
        assert c.post("/api/gehoer", json={"aktion": "messung", "bpm": 100, "schlag_vor_s": 0.1, "energie": 0.4}).json()["laeuft"] is False
        assert time.monotonic() - rt.engine.estop_at < 120       # die Sperre bleibt gesetzt


# ── Begrüßung beim Aufwecken ────────────────────────────────────────────────────────────────────────────────────
def test_begruessung_text_mit_tageszeit_und_namen():
    assert RT.begruessung_text("Reachy", "Anna", 8) == "Guten Morgen, Anna! Ich bin Reachy."
    assert RT.begruessung_text("Robbi", "", 20) == "Guten Abend! Ich bin Robbi."
    assert RT.begruessung_text("", "  ", 13).startswith("Guten Tag!")
    assert RT.begruessung_text("Reachy", "", 2).startswith("Hallo!")
    from duckpilot import i18n
    assert RT.begruessung_text("Reachy", "Anna", 8, lambda k, **w: i18n.t(k, sprache="en", **w)) == \
        "Good morning, Anna! I'm Reachy."


def test_begruessung_nur_beim_wecken(reachy_client):
    c, rt, gesendet = reachy_client
    rt.config.nutzer_name = "Anna"
    with c.websocket_connect("/ws", headers=WS) as ws:
        ws.send_json({"type": "koerper"})
        assert _warte(lambda: len(_gruesse(gesendet)) == 1)
        gruss = _gruesse(gesendet)[0]["text"]
        assert "Anna" in gruss and rt.config.duck_name in gruss and "quak" not in gruss.lower()
        assert _warte(lambda: rt.engine.current is not None and "begruessung" in rt.engine.current.describe(), 3)
        ws.send_json({"type": "koerper"})                       # Seitenwechsel, erneut ins Cockpit: kein zweiter Gruß
        c.post("/api/settings", json={"idle_life": False})
        time.sleep(0.5)
        assert len(_gruesse(gesendet)) == 1


def test_begruessung_abschaltbar(reachy_client):
    c, rt, gesendet = reachy_client
    assert c.post("/api/settings", json={"reachy_begruessung": False}).json()["ok"]
    assert c.get("/api/settings").json()["werte"]["reachy_begruessung"] is False
    with c.websocket_connect("/ws", headers=WS) as ws:
        ws.send_json({"type": "koerper"})
        assert _warte(lambda: rt.im_koerper)
        time.sleep(0.5)
    assert _gruesse(gesendet) == [] and not any("Ich bin wach" in (m.get("text") or "") for m in gesendet)


# ── Einstellungen ────────────────────────────────────────────────────────────────────────────────────────────────
def test_einstellungen_begruessung_und_radioliste():
    assert S.validate({"reachy_begruessung": False}) == {"reachy_begruessung": False}
    with pytest.raises(ValueError):
        S.validate({"reachy_begruessung": "ja"})
    urls = [f"https://radio{i}.example/stream" for i in range(7)]
    assert S.validate({"radio_adressen": [urls[0], urls[0], *urls[1:]]})["radio_adressen"] == urls[:5]
    assert S.validate({"radio_adressen": ["http://192.168.1.5:8000/live.mp3"]})["radio_adressen"] == ["http://192.168.1.5:8000/live.mp3"]
    for schlecht in ("ftp://x.example/a", "javascript:alert(1)", "https://nutzer:geheim@x.example/a", "x.example", "https://"):
        with pytest.raises(ValueError):
            S.validate({"radio_adressen": [schlecht]})
    from duckpilot.config import Config
    cfg = Config()
    assert cfg.reachy_begruessung is True and cfg.radio_adressen == []
    assert {"reachy_begruessung", "radio_adressen"} <= set(cfg.public())


# ── Open Duck: Antennen im Takt ─────────────────────────────────────────────────────────────────────────────────
def test_open_duck_schlaegt_die_antennen_im_takt():
    async def go():
        sim = OpenDuckSim(realtime=False, seed=1)
        sim._task = object()
        eng = MotionEngine(sim)
        await eng.stand_up()
        await run_for(sim, eng, 2.5)
        gesetzt = []
        orig = sim.antennen_setzen

        async def setzen(r, l, s=1.5):
            gesetzt.append((r, l))
            return await orig(r, l, s)
        sim.antennen_setzen = setzen
        eng.run(MusikTanz({"bpm": 120, "schritte": [{"t": 0, "takte": 2, "art": "schritt"}, {"t": 4, "takte": 1, "art": "pause"}]}))
        await run_for(sim, eng, 4.0)
        assert len(gesetzt) >= 6                                   # je Schlag
        assert gesetzt[0] != gesetzt[1]                            # im Wechsel
        n = len(gesetzt)
        await run_for(sim, eng, 1.5)                               # Pause: Antennen ruhen
        assert len(gesetzt) == n
        # Microduck hat keine Antennen: nichts passiert, nichts bricht
        _, ente = await make()
        ente.run(MusikTanz({"bpm": 120, "schritte": [{"t": 0, "takte": 1, "art": "schritt"}]}))
        await run_for(ente.backend, ente, 1.0)
    run(go())


# ── Oberfläche ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_oberflaeche_tanz_je_koerper():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    zeile = lambda text: next(z for z in html.splitlines() if text in z)          # noqa: E731
    assert "nur-microduck" in zeile("Posen aus Lernen → Akrobatik")
    assert "nur-reachy" in zeile('id="mitwippen"') and "nur-reachy" in zeile('data-set="reachy_begruessung"')
    assert "nur-reachy" in zeile("Reachy tanzt mit Kopf, Antennen und Drehung")
    teil = html[html.index('<div data-part="tanz"'):html.index('<div data-part="team"')]
    weitere = teil.index("Weitere Enten")
    assert '<div class="nur-ente stapel">' in teil[weitere - 200:weitere]   # „Weitere Enten“ nur bei Enten
    js = (STATIC / "mitwippen.js").read_text(encoding="utf-8")
    assert "fetch(" not in js and "WebSocket" not in js              # lädt nichts nach, nur über api() zum eigenen PC and "localStorage" not in js and "MediaRecorder" not in js
    assert "import { initMitwippen } from './mitwippen.js'" in (STATIC / "tanz.js").read_text(encoding="utf-8")
    assert (STATIC / "app.js").stat().st_size < 100_000
