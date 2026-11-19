"""Haushalt und Smart Home (seit 0.45): Home Assistant und Hue Bridge lokal, nie Schlösser, Alarm oder Heizung;
aufräumen vor dem Saugroboter und Heimkehr zum Ladeplatz im Simulator."""

import asyncio
import json
import math
import time

import pytest
from fastapi.testclient import TestClient
from helpers import make, run_for

from duckpilot import haus as H
from duckpilot import settings as S
from duckpilot.brain.tools import ToolRunner
from duckpilot.config import load
from duckpilot.motion.haushalt import GEBRACHT_M, Heimkehr, VorDemSauger
from duckpilot.remote import pc_only
from duckpilot.server.app import Runtime, create_app
from duckpilot.server.oberflaeche import seite

O = {"Origin": "http://127.0.0.1:8765"}

HA_STATES = [
    {"entity_id": "light.wohnzimmer", "state": "off", "attributes": {"friendly_name": "Deckenlicht"}},
    {"entity_id": "light.kueche", "state": "on", "attributes": {"friendly_name": "Küchenlampe"}},
    {"entity_id": "vacuum.dreame", "state": "docked", "attributes": {"friendly_name": "Dreame"}},
    {"entity_id": "scene.abend", "state": "unknown", "attributes": {"friendly_name": "Abend",
                                                                    "entity_id": ["light.wohnzimmer", "light.kueche"]}},
    {"entity_id": "scene.gute_nacht", "state": "unknown", "attributes": {"friendly_name": "Gute Nacht",
                                                                         "entity_id": ["light.kueche", "lock.haustuer"]}},
    {"entity_id": "scene.ohne_liste", "state": "unknown", "attributes": {"friendly_name": "Unklar"}},
    {"entity_id": "lock.haustuer", "state": "locked", "attributes": {"friendly_name": "Haustür"}},
    {"entity_id": "alarm_control_panel.haus", "state": "disarmed", "attributes": {"friendly_name": "Alarm"}},
    {"entity_id": "climate.wohnzimmer", "state": "heat", "attributes": {"friendly_name": "Heizung"}},
    {"entity_id": "switch.steckdose", "state": "on", "attributes": {"friendly_name": "Steckdose"}},
    {"entity_id": "cover.garage", "state": "closed", "attributes": {"friendly_name": "Garagentor"}},
]
RAEUME = {"light.wohnzimmer": "Wohnzimmer", "light.kueche": "Küche", "vacuum.dreame": "Flur"}


class FalschesNetz:
    """Home Assistant und Hue Bridge zum Nachspielen – merkt sich jede Anfrage."""

    def __init__(self, knopf=True):
        self.anfragen = []
        self.knopf = knopf

    def __call__(self, methode, url, daten, kopf):
        self.anfragen.append((methode, url, daten, dict(kopf)))
        if ":8123" in url:
            if kopf.get("Authorization") != "Bearer " + "t" * 40:
                raise PermissionError("401 Unauthorized")
            if url.endswith("/api/"):
                return {"message": "API running."}
            if url.endswith("/api/states"):
                return HA_STATES
            if url.endswith("/api/template"):
                ids = json.loads(daten["template"].split(" in ", 1)[1].split(" %}", 1)[0])
                return "".join(f"{e}|{RAEUME.get(e, '')}\n" for e in ids)
            if "/api/services/" in url:
                return []
        if url.endswith("/api") and methode == "POST":
            return [{"success": {"username": "k" * 20}}] if self.knopf else \
                [{"error": {"type": 101, "description": "link button not pressed"}}]
        if url.endswith("/lights"):
            return {"1": {"name": "Stehlampe", "state": {"on": True}}, "2": {"name": "Leselicht", "state": {"on": False}}}
        if url.endswith("/groups"):
            return {"5": {"name": "Wohnzimmer", "type": "Room", "lights": ["1", "2"]},
                    "6": {"name": "Alle", "type": "LightGroup", "lights": ["1"]}}
        if url.endswith("/scenes"):
            return {"abc": {"name": "Gemütlich", "type": "GroupScene", "group": "5"},
                    "xyz": {"name": "Alt", "type": "LightScene"}}
        if methode == "PUT":
            return [{"success": {}}]
        raise AssertionError(f"unerwartet: {methode} {url}")


class Tresor(dict):
    def lesen(self, wer):
        return self.get(wer)

    def schreiben(self, wer, wert):
        if wert is None:
            self.pop(wer, None)
        else:
            self[wer] = wert


def _haus(tmp_path, netz=None, mit_ha=True, mit_hue=False):
    netz = netz or FalschesNetz()
    t = Tresor()
    h = H.Haus(tmp_path, t.lesen, t.schreiben, netz)
    if mit_ha:
        h.ha_verbinden("homeassistant.local", "t" * 40, "mobile_app_handy")
    if mit_hue:
        assert h.hue_koppeln("192.168.178.20")
    return h, t, netz


# ── Adressen nur im eigenen Netz ─────────────────────────────────────────
def test_nur_lokale_adressen():
    assert H.lokale_adresse("homeassistant.local", 8123) == "http://homeassistant.local:8123"
    assert H.lokale_adresse("https://192.168.1.5:8123/") == "https://192.168.1.5:8123"
    assert H.lokale_adresse("10.0.0.2") == "http://10.0.0.2"
    assert H.lokale_adresse("pc.tail1234.ts.net:8123").startswith("http://pc.tail1234.ts.net")
    assert H.lokale_adresse("100.101.102.103") == "http://100.101.102.103"
    assert H.lokale_adresse("hassio:8123") == "http://hassio:8123"
    for falsch in ("https://abcd.ui.nabu.casa", "8.8.8.8", "http://example.com", "http://user:pw@homeassistant.local",
                   "http://homeassistant.local/api/states", "ftp://192.168.1.5", "", "http://a b.local"):
        with pytest.raises(ValueError):
            H.lokale_adresse(falsch)
    with pytest.raises(ValueError):
        H.lokale_adresse("https://192.168.178.20", nur_http=True)


# ── Home Assistant ───────────────────────────────────────────────────────
def test_ha_zeigt_nur_licht_sauger_und_reine_lichtszenen(tmp_path):
    h, tresor, _ = _haus(tmp_path)
    geraete, fehler = h.geraete()
    assert fehler == []
    ids = {g.id for g in geraete}
    assert ids == {"ha:light.wohnzimmer", "ha:light.kueche", "ha:vacuum.dreame", "ha:scene.abend"}
    for nie in H.NIE:
        assert not any(i.startswith(f"ha:{nie}.") for i in ids), nie
    licht = next(g for g in geraete if g.id == "ha:light.wohnzimmer")
    assert licht.raum == "Wohnzimmer" and licht.an is False
    # Token nur im Tresor, nie in der Datei
    datei = (tmp_path / H.DATEI).read_text(encoding="utf-8")
    assert "t" * 40 not in datei and tresor[H.TRESOR_HA] == "t" * 40
    assert json.loads(datei)["ha_adresse"] == "http://homeassistant.local:8123"


def test_ha_schaltet_nur_freigegebenes(tmp_path):
    h, _, netz = _haus(tmp_path)
    h.schalten("ha:light.wohnzimmer", "an")
    m, url, daten, _ = netz.anfragen[-1]
    assert (m, url, daten) == ("POST", "http://homeassistant.local:8123/api/services/light/turn_on",
                               {"entity_id": "light.wohnzimmer"})
    h.schalten("ha:vacuum.dreame", "heim")
    assert netz.anfragen[-1][1].endswith("/api/services/vacuum/return_to_base")
    vorher = len(netz.anfragen)
    for gid, aktion in (("ha:lock.haustuer", "an"), ("ha:climate.wohnzimmer", "an"), ("ha:scene.gute_nacht", "an"),
                        ("ha:alarm_control_panel.haus", "aus"), ("ha:switch.steckdose", "aus"),
                        ("ha:light.wohnzimmer", "unlock"), ("ha:vacuum.dreame", "an")):
        with pytest.raises(ValueError):
            h.schalten(gid, aktion)
    assert not any("/api/services/" in a[1] for a in netz.anfragen[vorher:])       # nichts davon ging raus
    with pytest.raises(ValueError):
        h.ha().schalten("lock.haustuer", "licht", "an")                           # auch eine Ebene tiefer nicht


def test_ha_falsches_token_und_meldung(tmp_path):
    t = Tresor()
    h = H.Haus(tmp_path, t.lesen, t.schreiben, FalschesNetz())
    with pytest.raises(PermissionError):
        h.ha_verbinden("homeassistant.local", "f" * 40)
    assert H.TRESOR_HA not in t and not (tmp_path / H.DATEI).exists()
    with pytest.raises(ValueError):
        h.ha_verbinden("homeassistant.local", "kurz")
    h, _, netz = _haus(tmp_path)
    assert h.melden("Fertig   aufgeräumt " + "x" * 300)
    _, url, daten, _ = netz.anfragen[-1]
    assert url.endswith("/api/services/notify/mobile_app_handy") and len(daten["message"]) == H.MELDUNG_MAX
    h.trennen("ha")
    assert h.ha() is None and not h.melden("x")


# ── Hue Bridge ───────────────────────────────────────────────────────────
def test_hue_koppeln_mit_knopf(tmp_path):
    t = Tresor()
    netz = FalschesNetz(knopf=False)
    h = H.Haus(tmp_path, t.lesen, t.schreiben, netz)
    assert h.hue_koppeln("192.168.178.20") is False                     # Knopf nicht gedrückt
    assert H.TRESOR_HUE not in t and h.stand()["hue"]["adresse"] == "http://192.168.178.20"
    netz.knopf = True
    assert h.hue_koppeln("192.168.178.20")
    assert t[H.TRESOR_HUE] == "k" * 20 and "k" * 20 not in (tmp_path / H.DATEI).read_text(encoding="utf-8")
    geraete, _ = h.geraete()
    assert {(g.id, g.raum) for g in geraete} == {("hue:licht:1", "Wohnzimmer"), ("hue:licht:2", "Wohnzimmer"),
                                                 ("hue:szene:5:abc", "Wohnzimmer")}
    h.schalten("hue:licht:2", "an")
    assert netz.anfragen[-1][:3] == ("PUT", f"http://192.168.178.20/api/{'k' * 20}/lights/2/state", {"on": True})
    h.schalten("hue:szene:5:abc", "an")
    assert netz.anfragen[-1][1].endswith("/groups/5/action") and netz.anfragen[-1][2] == {"scene": "abc"}
    with pytest.raises(ValueError):
        h.schalten("hue:licht:2", "start")


def test_beide_wege_und_ein_ausfall(tmp_path):
    h, _, netz = _haus(tmp_path, mit_hue=True)
    geraete, fehler = h.geraete(neu=True)
    assert {g.quelle for g in geraete} == {"ha", "hue"} and not fehler
    h.trennen("hue")
    h.schreiben(H.TRESOR_HA, "f" * 40)                                  # Token ungültig geworden
    geraete, fehler = h.geraete(neu=True)
    assert geraete == [] and fehler and "Home Assistant" in fehler[0]


# ── Ohne Sprachmodell ────────────────────────────────────────────────────
@pytest.mark.parametrize("text,erwartet", [
    ("Licht im Wohnzimmer an", ("licht", "an")), ("Mach das Licht aus", ("licht", "aus")),
    ("Turn on the lights", ("licht", "an")), ("Starte den Saugroboter", ("sauger", "start")),
    ("Schick den Staubsauger zur Ladestation", ("sauger", "heim")), ("Sauger stopp", ("sauger", "stopp")),
    ("Szene Abend aktivieren", ("szene", "an")),
])
def test_befehle(text, erwartet):
    b = H.befehl(text)
    assert (b["art"], b["aktion"]) == erwartet


@pytest.mark.parametrize("text", ["Schließ die Haustür ab", "Mach die Heizung an", "Alarmanlage ausschalten",
                                  "unlock the door", "Öffne das Garagentor", "Mach die Steckdose aus"])
def test_nie_schloss_alarm_heizung(text):
    assert H.befehl(text) == {"nie": True}


def test_kein_befehl():
    for text in ("Wie spät ist es?", "Ist das Fenster geschlossen?", "Erzähl mir was über Lampen"):
        assert H.befehl(text) is None


# ── Werkzeug ─────────────────────────────────────────────────────────────
def test_werkzeug_fragt_nach_und_schaltet_den_raum(tmp_path):
    async def go():
        sim, eng = await make()
        r = ToolRunner(eng)
        h, _, netz = _haus(tmp_path)
        r.haus = h
        assert any(t["name"] == "haus" for t in r.tools())
        out = await r.run("haus", {"aktion": "schalten", "art": "licht", "befehl": "an", "geraet": "Licht an"})
        assert not out["ok"] and out.get("nachfrage") and "Wohnzimmer" in out["fehler"]
        vorher = len(netz.anfragen)
        out = await r._haus_befehl("Licht im Wohnzimmer an")
        assert out["ok"] and out["geschaltet"] == ["Deckenlicht (Wohnzimmer)"]
        assert sum("/api/services/light/turn_on" in a[1] for a in netz.anfragen[vorher:]) == 1
        out = await r._haus_befehl("Schließ die Haustür ab")
        assert not out["ok"] and "nie" in out["text"]
        liste = await r.run("haus", {"aktion": "liste"})
        assert not any("lock" in g["id"] or "climate" in g["id"] for g in liste["geraete"])
        r.haus_sperre = lambda: True                                     # gerade Not-Aus
        out = await r.run("haus", {"aktion": "schalten", "art": "sauger", "befehl": "start", "geraet": "Dreame"})
        assert not out["ok"] and "Not-Aus" in out["fehler"]
        assert not any("vacuum/start" in a[1] for a in netz.anfragen)
    asyncio.run(go())


def test_werkzeug_ohne_verbindung(tmp_path):
    async def go():
        sim, eng = await make()
        r = ToolRunner(eng)
        assert not any(t["name"] == "haus" for t in r.tools())
        t = Tresor()
        r.haus = H.Haus(tmp_path, t.lesen, t.schreiben, FalschesNetz())
        out = await r.run("haus", {"aktion": "liste"})
        assert not out["ok"] and "einrichten" in out["fehler"]
    asyncio.run(go())


# ── Haushalt im Simulator ────────────────────────────────────────────────
def test_vor_dem_sauger_aufraeumen():
    async def go():
        sim, eng = await make()
        welt = sim.world_model
        ziel = (-0.2, 0.0)
        dinge = [{"name": i.name, "x": i.x, "y": i.y} for i in welt.items if i.name in ("Socke", "Klötzchen")]
        b = VorDemSauger(dinge, ziel, "Korb")
        eng.run(b)
        await run_for(sim, eng, 400, until=lambda: b.done)
        assert b.done and b.ergebnis_art == "erfolg", b.result
        assert set(b.gebracht) == {"Socke", "Klötzchen"} and "2 von 2" in b.result
        for name in ("Socke", "Klötzchen"):
            i = next(x for x in welt.items if x.name == name)
            assert math.hypot(i.x - ziel[0], i.y - ziel[1]) < GEBRACHT_M, (name, i.x, i.y)
        leer = VorDemSauger([], ziel, "Korb")
        eng.run(leer)
        await run_for(sim, eng, 1, until=lambda: leer.done)
        assert leer.ergebnis_art == "erfolg" and "nichts" in leer.result
    asyncio.run(go())


def test_heimkehr_geht_hin_und_setzt_sich():
    async def go():
        sim, eng = await make()
        b = Heimkehr((0.2, 0.3), "Ladeplatz")
        eng.run(b)
        await run_for(sim, eng, 60, until=lambda: b.done)
        assert b.done and not getattr(b, "failed", False), b.result
        assert math.hypot(sim.x - 0.2, sim.y - 0.3) < 0.12 and "Akku wechseln" in b.result
        await run_for(sim, eng, 3)
        assert sim.state().sitting
    asyncio.run(go())


def test_simulierter_akku_bleibt_knapp():
    async def go():
        sim, eng = await make()
        sim.battery = 0.12
        sim.applied.vx = 0.1
        sim.step(0.05)
        assert sim.battery <= 0.12                                       # springt nicht auf 25 % zurück
    asyncio.run(go())


# ── Mit dem Server ───────────────────────────────────────────────────────
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "daten"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        c.runtime = rt
        yield c


def test_einrichten_nur_am_pc_schalten_auch_vom_handy():
    for m, p in (("POST", "/api/haus/ha"), ("POST", "/api/haus/hue"), ("DELETE", "/api/haus/ha"),
                 ("DELETE", "/api/haus/hue"), ("POST", "/api/haus/einstellungen"), ("POST", "/api/haus/akku_knapp")):
        assert pc_only(m, p), p
    for m, p in (("GET", "/api/haus"), ("GET", "/api/haus/geraete"), ("POST", "/api/haus/schalten"),
                 ("POST", "/api/haus/aufraeumen"), ("POST", "/api/haus/ort")):
        assert not pc_only(m, p), p


def test_server_ohne_tresor_und_ohne_verbindung(client):
    s = client.get("/api/haus").json()
    assert not s["ha"]["verbunden"] and not s["hue"]["verbunden"] and "nie" in s["nie"].lower()
    r = client.post("/api/haus/ha", json={"adresse": "https://abcd.ui.nabu.casa", "token": "t" * 40}, headers=O)
    assert r.status_code == 400 and "eigenen Netz" in r.json()["fehler"]
    assert client.post("/api/haus/schalten", json={"id": "ha:lock.haustuer", "aktion": "an"}, headers=O).status_code == 400


def test_server_haushalt_im_simulator(client, monkeypatch):
    rt = client.runtime
    netz = FalschesNetz()
    t = Tresor()
    rt.haus.lesen, rt.haus.schreiben, rt.haus.anfrage = t.lesen, t.schreiben, netz
    rt.haus.ha_verbinden("homeassistant.local", "t" * 40)
    r = client.post("/api/haus/einstellungen", json={"sauger_danach": "ha:light.kueche"}, headers=O)
    assert r.status_code == 400                                          # kein Saugroboter
    assert client.post("/api/haus/einstellungen", json={"sauger_danach": "ha:vacuum.dreame"}, headers=O).json()["ok"]
    r = client.post("/api/haus/aufraeumen", json={}, headers=O)
    assert r.status_code == 400 and ("Korb" in r.json()["fehler"] or "aufwecken" in r.json()["fehler"])
    # Not-Aus: in der Sperre kein Aufräumen, kein Saugroboter
    rt.engine.estop_at = time.monotonic()
    r = client.post("/api/haus/schalten", json={"id": "ha:vacuum.dreame", "aktion": "start"}, headers=O)
    assert r.status_code == 400 and "Not-Aus" in r.json()["fehler"]
    assert not any("vacuum/start" in a[1] for a in netz.anfragen)
    r = client.post("/api/haus/akku_knapp", headers=O).json()
    assert r["ok"] and r["akku"] < 0.15 and not r["ladeplatz"]
    assert rt.haus_dienst._heimkehr_noetig() is None                    # Sperre, kein Ladeplatz, liegt


def test_heimkehr_regeln(client):
    rt = client.runtime
    d = rt.haus_dienst
    rt.memory.remember_place("Ladeplatz", d.koerper(), 0.3, 0.2, 0.0)
    rt.backend.powered = True                                            # steht (ohne eigene Ereignisschleife)
    rt.backend.battery = 0.5
    assert d._heimkehr_noetig() is None
    rt.backend.battery = 0.1
    ziel = d._heimkehr_noetig()
    assert ziel is not None and ziel[2] == "Ladeplatz"
    d.heimkehr_bereit = False                                           # schon einmal losgegangen
    assert d._heimkehr_noetig() is None
    rt.backend.battery = 0.3
    assert d._heimkehr_noetig() is None and d.heimkehr_bereit            # erst nach dem Laden wieder bereit
    rt.backend.battery = 0.1
    rt.engine.estop_at = time.monotonic()
    assert d._heimkehr_noetig() is None                                 # nie in der Sperre


def test_oberflaeche_hat_die_karte():
    html = seite()
    for i in ("al-haus", "haus-ha-form", "haus-hue-form", "haus-aufraeumen", "haus-ladeplatz", "haus-akku-knapp"):
        assert f'id="{i}"' in html, i
    assert 'type="password"' in html.split('id="haus-ha-token"')[0][-200:] + html.split('id="haus-ha-token"')[1][:60]
    assert "pc-only" in html.split('id="haus-einrichten"')[0][-80:]
