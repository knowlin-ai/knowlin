"""Sicherungspunkte (0.38.24, Wunsch): „in den Einstellungen sollten bestimmte Sachen wieder resettet werden
können … Zwischenstände exportieren oder mehrere Versionen mit Historie – wie im Leben – manchmal will man bestimmte
Erlebnisse am besten wieder rückgängig machen“."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot import sicherungspunkte as SP
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app


@pytest.fixture
def client(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tmp_settings.write_text(json.dumps({"modul": "duckpilot", "backend": "sim", "sim_physik": False}))
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        yield c, rt


def _erleben(rt):
    rt.memory.remember_fact("Alex trinkt gern Tee")
    rt.memory.remember_preference("mag ruhige Musik")
    rt.erfahrung.netz.staerken = getattr(rt.erfahrung.netz, "staerken", None)
    netz = rt.erfahrung.netz
    netz.knoten["ort:kueche"] = {"label": "Küche", "n": 3}
    netz.kanten["ort:kueche|taetigkeit:tanzen"] = {"w": 0.4}
    netz._dirty = True
    netz.save()


def test_anlegen_zuruecksetzen_und_zurueckholen(client):
    c, rt = client
    _erleben(rt)
    d = c.post("/api/sicherung", json={"aktion": "anlegen", "name": "Vor dem Experiment"}).json()
    assert d["ok"] and d["punkt"]["art"] == "hand" and d["punkt"]["name"] == "Vor dem Experiment"
    p = d["punkt"]
    assert p["zahlen"]["gedaechtnis"]["wissen"] == 1 and p["zahlen"]["erfahrung"]["verbindungen"] == 1
    assert set(p["bereiche"]) == set(SP.BEREICHE)

    # ein „Erlebnis“, das rückgängig gemacht werden soll
    rt.memory.remember_fact("Odi ist vom Tisch gefallen")
    assert len(rt.memory.data["wissen"]) == 2

    # Zurücksetzen nur mit zweitem Klick
    assert c.post("/api/sicherung", json={"aktion": "zuruecksetzen", "bereiche": ["gedaechtnis"]}).status_code == 409
    r = c.post("/api/sicherung", json={"aktion": "zuruecksetzen", "bereiche": ["gedaechtnis"], "bestaetigt": True}).json()
    assert r["ok"] and r["vorher"]["art"] == "vor-zuruecksetzen"
    assert rt.memory.data["wissen"] == [] and rt.memory.data["vorlieben"] == []
    assert rt.erfahrung.netz.kanten                         # andere Bereiche bleiben

    # den Stand vor dem Experiment wiederherstellen – nur das Gedächtnis
    r = c.post("/api/sicherung", json={"aktion": "wiederherstellen", "id": p["id"], "bereiche": ["gedaechtnis"],
                                       "bestaetigt": True}).json()
    assert r["ok"] and r["betroffen"] == ["gedaechtnis"]
    assert [w["text"] if isinstance(w, dict) else w for w in rt.memory.data["wissen"]] and len(rt.memory.data["wissen"]) == 1
    # und auch das Zurücksetzen lässt sich rückgängig machen (Punkt „vor dem Zurücksetzen“)
    arten = [x["art"] for x in r["punkte"]]
    assert "vor-zuruecksetzen" in arten and "vor-wiederherstellen" in arten


def test_erfahrung_und_charakter(client):
    c, rt = client
    _erleben(rt)
    vorher = rt.config.energie
    p = c.post("/api/sicherung", json={"aktion": "anlegen"}).json()["punkt"]
    c.post("/api/settings", json={"energie": 0.1, "humor": 0.9})
    assert rt.config.energie == 0.1
    r = c.post("/api/sicherung", json={"aktion": "zuruecksetzen", "bereiche": ["erfahrung", "charakter"],
                                       "bestaetigt": True}).json()
    assert r["ok"] and not rt.erfahrung.netz.kanten and not rt.erfahrung.netz.knoten
    assert rt.config.energie == 0.7 and rt.config.humor == 0.45     # Quackis Startcharakter
    c.post("/api/sicherung", json={"aktion": "wiederherstellen", "id": p["id"], "bestaetigt": True})
    assert "ort:kueche|taetigkeit:tanzen" in rt.erfahrung.netz.kanten
    assert rt.config.energie == vorher                               # Stand beim Anlegen (vor der Änderung)


def test_export_import_und_loeschen(client):
    c, rt = client
    _erleben(rt)
    p = c.post("/api/sicherung", json={"aktion": "anlegen", "name": "Mitnehmen"}).json()["punkt"]
    r = c.get(f"/api/sicherung/{p['id']}/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    namen = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "punkt.json" in namen and "memory.json" in namen and "erfahrung.json" in namen
    assert not [n for n in namen if "personen" in n or "settings" in n]   # nie Personen oder Einstellungen
    neu = c.post("/api/sicherung/import", content=r.content).json()
    assert neu["ok"] and neu["punkt"]["art"] == "import" and neu["punkt"]["name"] == "Mitnehmen"
    assert neu["punkt"]["zahlen"]["gedaechtnis"]["wissen"] == 1
    # kaputte oder fremde Dateien werden abgelehnt
    assert not c.post("/api/sicherung/import", content=b"kein zip").json()["ok"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("punkt.json", "{}")
        z.writestr("../../settings.json", "{}")
    assert "Unbekannte Datei" in c.post("/api/sicherung/import", content=buf.getvalue()).json()["fehler"]
    # löschen nur bestätigt
    assert c.post("/api/sicherung", json={"aktion": "loeschen", "id": p["id"]}).status_code == 409
    assert c.post("/api/sicherung", json={"aktion": "loeschen", "id": p["id"], "bestaetigt": True}).json()["ok"]
    assert c.post("/api/sicherung", json={"aktion": "loeschen", "id": "../x", "bestaetigt": True}).status_code == 404


def test_nur_am_pc(client):
    c, _ = client
    for hdr in ({"X-Forwarded-For": "192.168.1.20"},):
        assert c.get("/api/sicherung", headers=hdr).status_code == 403
        assert c.post("/api/sicherung", json={"aktion": "anlegen"}, headers=hdr).status_code == 403


def test_taeglich_und_aufraeumen(tmp_path):
    (tmp_path / "erfahrung.json").write_text(json.dumps({"knoten": {"a": {}}, "kanten": {}}))
    sp = SP.Sicherungspunkte(tmp_path, tmp_path / "memory.json")
    assert sp.taeglich() is not None and sp.taeglich() is None       # einmal am Tag
    for _ in range(SP.AUTO_BEHALTEN + 3):
        sp.anlegen("auto")
    hand = sp.anlegen("hand", "bleibt")
    sp.aufraeumen()
    punkte = sp.liste()
    assert len([p for p in punkte if p["art"] == "auto"]) == SP.AUTO_BEHALTEN
    assert hand["id"] in [p["id"] for p in punkte]                   # selbst angelegte bleiben
    leer = SP.Sicherungspunkte(tmp_path / "leer", tmp_path / "leer" / "memory.json")
    assert leer.taeglich() is None                                   # nichts zu sichern


def test_oberflaeche():
    from duckpilot.server.app import STATIC

    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="set-sicherung"' in html and "Sicherungspunkt anlegen" in html
    js = (STATIC / "sicherung.js").read_text(encoding="utf-8")
    assert "bestaetigt: true" in js and "/api/sicherung/import" in js and "/export" in js
    assert "initSicherung" in (STATIC / "app.js").read_text(encoding="utf-8")


def test_uebungen_taenze_und_raum(client):
    """Alle Bereiche einmal hin und zurück – die laufenden Teile übernehmen den zurückgeholten Stand sofort."""
    c, rt = client
    daten = SP.Sicherungspunkte(rt.sicherung.punkte.quellen["daten"], rt.sicherung.punkte.quellen["gedaechtnis"]).quellen["daten"]
    with rt.acro._book_lock:
        rt.acro.book["posen"]["Flamingo"] = {"gelenke": [0.1] * 14}
        rt.acro._save()
    (daten / "choreos.json").write_text(json.dumps({"abend": {"name": "Abendtanz", "schritte": []}}), encoding="utf-8")
    raum = rt.raum
    raum.speichern()
    p = c.post("/api/sicherung", json={"aktion": "anlegen", "name": "alles"}).json()["punkt"]
    assert p["zahlen"]["uebungen"]["posen"] == 1 and p["zahlen"]["taenze"]["taenze"] == 1
    r = c.post("/api/sicherung", json={"aktion": "zuruecksetzen", "bereiche": ["uebungen", "taenze", "raum"],
                                       "bestaetigt": True}).json()
    assert r["ok"] and rt.acro.book["posen"] == {}
    assert json.loads((daten / "choreos.json").read_text(encoding="utf-8")) == {}
    assert rt.raum is not raum                                       # frischer Raum aus den geleerten Dateien
    r = c.post("/api/sicherung", json={"aktion": "wiederherstellen", "id": p["id"], "bereiche": ["uebungen", "taenze"],
                                       "bestaetigt": True}).json()
    assert r["ok"] and "Flamingo" in rt.acro.book["posen"]
    assert "abend" in json.loads((daten / "choreos.json").read_text(encoding="utf-8"))
    # Bereiche, die gar nicht im Punkt sind, werden nicht angefasst; unbekannte Bereiche: Fehler
    nur = c.post("/api/sicherung", json={"aktion": "zuruecksetzen", "bereiche": ["quatsch"], "bestaetigt": True})
    assert nur.status_code == 400 and "Bereich" in nur.json()["fehler"]


def test_alles_vergessen_legt_punkt_an(client):
    c, rt = client
    _erleben(rt)
    c.portal.call(rt.handle_client_message, {"type": "memory_clear"})
    assert rt.memory.data["wissen"] == []
    punkte = c.get("/api/sicherung").json()["punkte"]
    vorher = [p for p in punkte if p["art"] == "vor-zuruecksetzen" and "Alles vergessen" in p["name"]]
    assert vorher and vorher[0]["zahlen"]["gedaechtnis"]["wissen"] == 1
