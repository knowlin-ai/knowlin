"""Körperschnittstelle 1.0 (seit 0.38.35): Profile, Erweiterungen per Entry Point, Konformitätsprüfung, LeRobot."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from duckpilot import koerper as K
from duckpilot import koerper_pruefung as KP
from duckpilot import settings as S
from duckpilot.api import Twist
from duckpilot.backends import build_backend
from duckpilot.backends.lerobot import LeRobotKoerper, NichtVerfuegbar, baue_lerobot, faehigkeiten_aus
from duckpilot.brain.kopf import kann
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app


@pytest.fixture(autouse=True)
def _frisch():
    K._zuruecksetzen_fuer_tests()
    yield
    K._zuruecksetzen_fuer_tests()


def _cfg(**kw):
    base = dict(backend="sim", modul="duckpilot", sim_physik=False, koerper_optionen={},
                reachy_adresse="http://localhost:8000", robot="tcp:127.0.0.1:7900", tof=None, head_signs=None, updater=None)
    return SimpleNamespace(**{**base, **kw})


# ── Profile ──────────────────────────────────────────────────────────────────
def test_eingebaute_profile_sind_gueltig_und_vollstaendig():
    assert set(K.ids()) >= {"duckpilot", "reachy_mini", "open_duck_mini", "lerobot"}
    for k in K.EINGEBAUT:
        assert k.fehler() == [], k.id
        assert k.eingebaut
    assert K.holen("duckpilot").koerper_zustand == "microduck"
    with pytest.raises(KeyError):
        K.holen("gibt_es_nicht")


def test_wortschatz_trennt_koerper_und_betrieb():
    w = K.wortschatz()
    assert w["schnittstelle"] == K.SCHNITTSTELLE and w["entry_point"] == "knowlin.koerper"
    assert not set(K.FAEHIGKEITEN) & set(K.BETRIEB)
    assert K.wort_gueltig("x-hoverboard") and not K.wort_gueltig("laser-augen")


def test_ungueltiges_profil_wird_erklaert():
    k = K.Koerper("X", "", "", "raumschiff", frozenset({"flügel"}), "kein_doppelpunkt", quelle="http://a.b")
    f = " ".join(k.fehler())
    for teil in ("id", "name fehlt", "familie", "flügel", "fabrik", "https"):
        assert teil in f


# ── Erweiterungen per Entry Point ────────────────────────────────────────────
class _EP:
    def __init__(self, name, obj):
        self.name, self._obj = name, obj

    def load(self):
        if isinstance(self._obj, Exception):
            raise self._obj
        return self._obj


def _rollbot():
    from duckpilot.backends.open_duck import OpenDuckSim

    class Rollbot(OpenDuckSim):
        koerper_art = "rollbot"

    return K.Koerper("rollbot", "Rollbot", "Beispiel", "fahrend",
                     frozenset({"beine", "kopf", "antennen", "stimmbank", "kamera", "mikrofon", "lautsprecher",
                                "augen_leds"}),
                     lambda cfg: Rollbot(realtime=True))


def test_erweiterung_wird_aufgenommen_und_kaputte_abgelehnt():
    eintraege = [_EP("rollbot", _rollbot), _EP("kaputt", ImportError("fehlt")),
                 _EP("falsch", lambda: "kein Profil"),
                 _EP("dieb", lambda: K.Koerper("duckpilot", "Fake", "x", "ente", frozenset(), "a:b"))]
    abgelehnt = K.erweiterungen_laden(eintraege)
    assert "rollbot" in K.ids() and not K.holen("rollbot").eingebaut
    assert set(abgelehnt) == {"kaputt", "falsch", "dieb"}
    assert "gibt es schon" in abgelehnt["dieb"]
    assert K.holen("duckpilot").name == "Microduck"          # eingebaute gewinnen immer
    S.validate({"modul": "rollbot"})                         # Einstellung kennt die Erweiterung


def test_erweiterung_besteht_die_konformitaetspruefung():
    K.erweiterungen_laden([_EP("rollbot", _rollbot)])
    erg = asyncio.run(KP._sim_pruefen(K.holen("rollbot")))
    assert KP.bestanden(erg), [e.zeile() for e in erg if not e.ok]


# ── Bauen über das Profil ────────────────────────────────────────────────────
def test_build_backend_baut_ueber_das_profil():
    assert type(build_backend(_cfg())).__name__ == "SimBackend"
    assert type(build_backend(_cfg(modul="reachy_mini"))).__name__ == "ReachyMiniSim"
    assert type(build_backend(_cfg(modul="open_duck_mini"))).__name__ == "OpenDuckSim"
    assert type(build_backend(_cfg(modul="weg_deinstalliert"))).__name__ == "SimBackend"   # Rückfall Microduck
    nv = build_backend(_cfg(modul="lerobot"))
    assert isinstance(nv, NichtVerfuegbar) and "Simulator" in nv.state().limited_by[0]
    with pytest.raises(ValueError):
        build_backend(_cfg(backend="quatsch"))


@pytest.mark.parametrize("kid", ["duckpilot", "reachy_mini", "open_duck_mini"])
def test_eingebaute_koerper_bestehen_die_pflichten(kid):
    erg = asyncio.run(KP._sim_pruefen(K.holen(kid)))
    assert KP.bestanden(erg), [e.zeile() for e in erg if not e.ok]
    assert {e.pflicht for e in erg} >= {"P1", "P2", "P3", "P4", "P5", "P9"}


def test_gehirn_liest_faehigkeiten_aus_dem_profil():
    assert kann("duckpilot", "walk") and not kann("reachy_mini", "walk")
    assert kann("duckpilot", "sound")                       # Stimmbank stand früher nicht in der Liste des Gehirns
    assert not kann("reachy_mini", "sound") and not kann("gibt_es_nicht", "walk")


# ── LeRobot ──────────────────────────────────────────────────────────────────
class _Bus:
    def __init__(self):
        self.torque = False

    def enable_torque(self):
        self.torque = True

    def disable_torque(self):
        self.torque = False


class FakeLeKiwi:
    """Wie LeRobots LeKiwi: Arm mit Greifer, Räder, eine Kamera."""

    name = "lekiwi"

    def __init__(self, bus=True):
        self.is_connected = False
        self.bus = _Bus() if bus else None
        self.gesendet = []
        self.pos = {"shoulder_pan": 0.0, "elbow_flex": 0.0, "gripper": 50.0}
        self.action_features = {**{f"{g}.pos": float for g in self.pos}, "x.vel": float, "y.vel": float,
                                "theta.vel": float}
        self.observation_features = {**self.action_features, "front": (480, 640, 3)}

    def connect(self, calibrate=True):
        self.is_connected = True

    def disconnect(self):
        self.is_connected = False
        if self.bus:
            self.bus.torque = False

    def get_observation(self):
        return {f"{g}.pos": v for g, v in self.pos.items()} | {"front": object()}

    def send_action(self, a):
        self.gesendet.append(dict(a))
        for k, v in a.items():
            if k.endswith(".pos"):
                self.pos[k[:-4]] = v
        return a


def test_lerobot_faehigkeiten_aus_den_merkmalen():
    r = FakeLeKiwi()
    assert faehigkeiten_aus(r.action_features, r.observation_features) == {"arm", "greifer", "raeder", "kamera"}
    assert faehigkeiten_aus({"gripper.pos": float}, {}) == {"greifer"}


def test_lerobot_faehrt_in_grad_haelt_an_und_not_aus_macht_stromlos():
    async def ablauf():
        r = FakeLeKiwi()
        be = LeRobotKoerper(r, typ="lekiwi")
        await be.connect()
        await asyncio.sleep(0.15)
        assert be.state().connected and not be.state().powered
        await be.move(Twist(0.1, 0.0, 0.5))
        assert r.gesendet == []                               # ohne Strom wird nichts gesendet
        await be.init()
        assert r.bus.torque and be.state().powered
        await be.move(Twist(9.0, 0.0, 0.5))
        letzte = r.gesendet[-1]
        assert letzte["x.vel"] == pytest.approx(0.25) and letzte["theta.vel"] == pytest.approx(28.6479, rel=1e-3)
        res = await be.haltung({"shoulder_pan": 500.0, "greifer": 10.0}, 0.5)
        assert res.accepted
        await asyncio.sleep(0.8)
        assert r.pos["shoulder_pan"] == pytest.approx(100.0) and r.pos["gripper"] == pytest.approx(10.0)
        assert not (await be.haltung({"knie": 1.0}, 1.0)).accepted
        await be.relax()
        assert not r.bus.torque and not be.state().powered
        assert r.gesendet[-1] == {"x.vel": 0.0, "y.vel": 0.0, "theta.vel": 0.0}
        assert not (await be.haltung({"shoulder_pan": 0.0}, 1.0)).accepted
        await be.close()
        assert not r.is_connected
    asyncio.run(ablauf())


def test_lerobot_ohne_bus_trennt_beim_not_aus():
    async def ablauf():
        r = FakeLeKiwi(bus=False)
        be = LeRobotKoerper(r)
        await be.connect()
        await be.init()
        res = await be.relax()
        assert res.accepted and "getrennt" in (res.reason or "") and not r.is_connected
        await be.close()
    asyncio.run(ablauf())


def test_lerobot_besteht_die_pflichten():
    async def ablauf():
        return await KP.pruefen(LeRobotKoerper(FakeLeKiwi()), K.holen("lerobot"), echt=True)
    erg = asyncio.run(ablauf())
    assert KP.bestanden(erg), [e.zeile() for e in erg if not e.ok]


def test_lerobot_fabrik_sagt_ehrlich_was_fehlt(monkeypatch):
    import builtins

    echt_import = builtins.__import__

    def ohne_lerobot(name, *a, **kw):
        if name.startswith("lerobot"):
            raise ImportError("No module named 'lerobot'")
        return echt_import(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", ohne_lerobot)
    be = baue_lerobot(_cfg(backend="robotd", modul="lerobot", koerper_optionen={"typ": "so101_follower"}))
    assert isinstance(be, NichtVerfuegbar) and "pip install lerobot" in be.state().limited_by[0]


def test_koerper_optionen_werden_geprueft():
    assert S.validate({"koerper_optionen": {"typ": " so101_follower ", "port": "COM5"}}) == {
        "koerper_optionen": {"typ": "so101_follower", "port": "COM5"}}
    for falsch in ({"passwort": "x"}, {"port": "a\nb"}, "kein dict"):
        with pytest.raises(ValueError):
            S.validate({"koerper_optionen": falsch})


# ── Oberfläche / API ─────────────────────────────────────────────────────────
def test_api_listet_koerper_und_wortschatz(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "s.json"))
    monkeypatch.setattr(S, "_keyring", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "m.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        d = c.get("/api/koerper").json()
        assert d["aktiv"] == "duckpilot" and d["schnittstelle"] == "1.0"
        assert {k["id"] for k in d["koerper"]} >= {"duckpilot", "reachy_mini", "open_duck_mini", "lerobot"}
        assert "beine" in c.get("/api/koerper/wortschatz").json()["faehigkeiten"]
        h = {"Origin": "http://127.0.0.1:8765"}
        r = c.post("/api/koerper/wechseln", json={"modul": "lerobot"}, headers=h)
        assert r.status_code == 409 and "keinen Simulator" in r.json()["fehler"]


def test_erweiterung_erscheint_als_modul_auf_der_startseite():
    from duckpilot import suite

    vorher = [m["id"] for m in suite.module()]
    assert "lerobot" not in vorher                           # eingebaut, aber ohne Simulator: noch kein Modul
    K.erweiterungen_laden([_EP("rollbot", _rollbot)])
    m = {x["id"]: x for x in suite.module(aktiv="rollbot")}
    assert m["rollbot"]["erweiterung"] and m["rollbot"]["aktiv"] and m["rollbot"]["modul"] == "rollbot"
    assert [x["id"] for x in suite.module()].index("rollbot") == 3     # nach den drei eingebauten Körpern


def test_vorlage_fuer_eigene_koerper_besteht_die_pflichten(monkeypatch):
    """Die Vorlage in examples/ ist die Anleitung für die Community – sie muss immer bestehen."""
    import sys
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "examples" / "knowlin-koerper-vorlage"))
    sys.modules.pop("knowlin_koerper_vorlage", None)
    from knowlin_koerper_vorlage import profil

    p = profil()
    assert p.fehler() == []
    erg = asyncio.run(KP.pruefen(p.bauen(None), p))
    assert KP.bestanden(erg), [e.zeile() for e in erg if not e.ok]
