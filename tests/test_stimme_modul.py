"""Stimme entwerfen je Robotertyp (Hinweis aus dem Test 5.11.: „stimme entwerfen ist auch noch nicht auf die robotertypen
angepasst (zB bei reachy)“): eigene Vorlagen, Entwurf mit Namen, Probetext ohne Ente bei Reachy; Knowlins Kopf-Modus
bleibt."""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duckpilot import settings as S
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app
from duckpilot.server.oberflaeche import seite
from duckpilot.voice import describe as D
from duckpilot.voice import install as I
from duckpilot.voice import tts as T

STATIC = Path(__file__).resolve().parent.parent / "duckpilot" / "server" / "static"


def test_vorlagen_je_koerper():
    reachy = D.vorlagen("reachy_mini")
    assert reachy and all("Ente" not in k and "Ente" not in v and "quak" not in v.lower() for k, v in reachy.items())
    assert any("Tischroboter" in v for v in reachy.values()) and any("technisch" in v for v in reachy.values())
    odi = D.vorlagen("open_duck_mini")
    assert odi.keys() != D.vorlagen("duckpilot").keys() and any("tiefer" in v for v in odi.values())
    assert any("Bastler" in k or "Bastler" in v for k, v in odi.items())
    assert D.vorlagen("duckpilot") == D.PRESETS_DE and "Quirlige Ente" in D.vorlagen("unbekannt")   # Microduck bleibt
    assert "Ruhig und tief" in D.vorlagen("kopf")
    for art in D.PRESETS_DE_MODUL:                           # jede Vorlage hat ihre geprüfte englische Fassung
        assert D.vorlagen(art).keys() == T.DESIGN_PRESETS_MODUL[art].keys()


def test_vorlage_geht_ohne_netz_auf_englisch_ans_modell():
    de = D.vorlagen("reachy_mini")["Freundlicher Tischroboter"]
    assert asyncio.run(D.to_english(de)) == (T.DESIGN_PRESETS_MODUL["reachy_mini"]["Freundlicher Tischroboter"], "vorlage")
    en, weg = asyncio.run(D.to_english(D.vorlagen("open_duck_mini")["Große Ente"]))
    assert weg == "vorlage" and "duck" in en


def test_entwurf_und_probesatz_mit_namen():
    assert "Robbi" in D.entwurf("reachy_mini", "Robbi") and "Tischroboter" in D.entwurf("reachy_mini", "")
    assert "Reachy" in D.entwurf("reachy_mini", "") and D.entwurf("duckpilot", "Quacki") == ""
    assert "Odi" in D.entwurf("open_duck_mini", None)
    r = T.design_text("reachy_mini", "Robbi")
    assert "Robbi" in r and "Ente" not in r and "Roboter" in r
    assert "Ente" not in T.design_text("kopf", "Knowlin") and "Knowlin" in T.design_text("kopf", "")
    assert "selbstgebaute Ente" in T.design_text("open_duck_mini", "Odi")
    assert T.design_text("duckpilot", "Quacki") == T.DESIGN_TEXT.format(name="Quacki")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    monkeypatch.setattr(I, "detect_gpus", lambda: [])
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        c.runtime = rt
        yield c


def _als(rt, modul, name):
    rt.config.modul, rt.config.duck_name = modul, name       # nur, was die Stimmen-Seite liest


def test_server_liefert_vorlagen_und_probetext_je_koerper(client, monkeypatch):
    rt = client.runtime
    st = client.get("/api/stimme").json()["qwen"]
    assert "Quirlige Ente" in st["vorlagen"] and st["entwurf"] == "" and "Ruhig und tief" in st["vorlagen_kopf"]
    assert "quak" in client.post("/api/stimme/probe", json={}).json()["text"]
    _als(rt, "reachy_mini", "Robbi")
    st = client.get("/api/stimme").json()["qwen"]
    assert st["modul"] == "reachy_mini" and "Freundlicher Tischroboter" in st["vorlagen"]
    assert "Robbi" in st["entwurf"] and not any("Ente" in k for k in st["vorlagen"])
    probe = client.post("/api/stimme/probe", json={}).json()
    assert "Robbi" in probe["text"] and "quak" not in probe["text"].lower()
    kopf = client.post("/api/stimme/probe", json={"fuer": "kopf"}).json()          # Knowlins Kopf-Modus bleibt
    assert "Knowlin" in kopf["text"]
    _als(rt, "open_duck_mini", "Odi")
    st = client.get("/api/stimme").json()["qwen"]
    assert "Bastler-Ente" in st["vorlagen"] and "Odi" in st["entwurf"]
    assert "Selbst gebaut" in client.post("/api/stimme/probe", json={}).json()["text"]


def test_entwerfen_spricht_den_satz_des_koerpers(client, monkeypatch):
    rt = client.runtime
    gerufen = []

    async def entwurf(text, name, takes=3, art="duckpilot"):
        gerufen.append((name, art))
    monkeypatch.setattr(rt.speaker.synth.qwen, "installed", lambda: True)
    monkeypatch.setattr(rt.speaker, "design", entwurf)
    _als(rt, "reachy_mini", "Robbi")
    assert client.post("/api/stimme/entwerfen", json={"beschreibung": D.entwurf("reachy_mini", "Robbi")}).json()["ok"]
    assert client.post("/api/stimme/entwerfen", json={"beschreibung": "Eine ruhige tiefe Stimme bitte", "fuer": "kopf"}).json()["ok"]
    assert gerufen == [("Robbi", "reachy_mini"), ("Knowlin", "kopf")]


def test_speaker_entwurf_nutzt_den_satz_je_koerper(client, monkeypatch):
    sp = client.runtime.speaker
    saetze = []
    monkeypatch.setattr(sp.synth.qwen, "installed", lambda: True)
    monkeypatch.setattr(sp.synth.qwen, "design", lambda instruct, text, takes, progress=None: saetze.append(text) or [])
    asyncio.run(sp.design(D.vorlagen("reachy_mini")["Fröhlicher Helfer"], "Robbi", 1, "reachy_mini"))
    assert saetze and "Robbi" in saetze[0] and "Ente" not in saetze[0]


def test_oberflaeche_je_robotertyp():
    js = (STATIC / "stimme.js").read_text(encoding="utf-8")
    assert "q.vorlagen_kopf" in js and "q.entwurf" in js and "modulJetzt()" in js
    assert "open_duck_mini:" in js and "reachy_mini:" in js
    assert "const kopf = () =>" in js                                              # Kopf-Modus unverändert da
    html = seite()
    i = html.index('id="duckness"')
    assert "nur-ente" in html[html.rindex("<section", 0, i):i]                     # Entenhaft bei Reachy ausgeblendet
