"""G1 (0.38.27): „Was Knowlin über deine Welt weiß“ – Themenkarten aus dem Erfahrungsnetz."""

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from duckpilot.brain.erfahrung import Erfahrungsnetz, key
from duckpilot.server.oberflaeche import seite

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"


def _netz():
    n = Erfahrungsnetz(None)
    for _ in range(12):
        n.akt.clear()
        n.erleben({key("ding", "Ball"): "Ball", key("gefuehl", "freude"): "Freude", key("rueckmeldung", "lob"): "Lob"})
    for _ in range(3):
        n.akt.clear()
        n.erleben({key("ort", "Treppe"): "Treppe", key("sinn", "sturz"): "gestürzt", key("gefuehl", "schreck"): "Schreck"})
    n.akt.clear()
    n.erleben({key("ort", "Küche"): "Küche", key("zeit", "abends"): "abends"})
    n.akt.clear()
    n.erleben({key("person", "momo"): "Momo"})
    return n


def test_gefuehlston_umfang_frische_sicherheit():
    n = _netz()
    ball = n.thema(key("ding", "Ball"))
    assert ball["ton"]["zeichen"] == "+" and ball["ton"]["wort"] == "eher schön"
    assert ball["erlebnisse"] == 12 and ball["sicherheit"] == "oft bestätigt" and ball["zuletzt"]["wort"] == "heute"
    treppe = n.thema(key("ort", "Treppe"))
    assert treppe["ton"]["zeichen"] == "−" and treppe["sicherheit"] == "ein paar Mal erlebt"
    kueche = n.thema(key("ort", "Küche"))
    assert kueche["ton"]["wert"] is None and kueche["mit"] == ["abends"] and kueche["sicherheit"] == "erst einmal erlebt"
    n.knoten[key("ort", "Küche")]["zuletzt"] = time.time() - 20 * 86400
    assert n.thema(key("ort", "Küche"))["zuletzt"]["wort"] == "vor 2 Wochen"
    n.knoten[key("ort", "Küche")]["zuletzt"] = time.time() - 9 * 86400
    assert n.thema(key("ort", "Küche"))["zuletzt"]["wort"] == "vor einer Woche"


def test_themen_je_art_und_personen_nur_am_pc():
    n = _netz()
    g = {x["art"]: x for x in n.themen()["gruppen"]}
    assert [e["name"] for e in g["ort"]["eintraege"]] == ["Treppe", "Küche"]          # meist Erlebtes zuerst
    assert g["person"]["eintraege"][0]["name"] == "Momo"
    assert "person" not in {x["art"] for x in n.themen(ohne_personen=True)["gruppen"]}


def test_route_und_karte(tmp_path, monkeypatch):
    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        r = c.get("/api/erfahrung/themen").json()
        assert r["ok"] and "gruppen" in r
    html = seite()
    assert html.index('id="welt"') < html.index('id="card-brain"')            # Nutzen zuerst, dann das Netz
    assert "Leuchten: gerade aktiv." in html                                          # G2: Legende in Worten
    assert "initWelt" in (STATIC / "gedaechtnis_ui.js").read_text(encoding="utf-8")
    en = json.loads((STATIC.parents[1] / "i18n" / "ui_en.json").read_text(encoding="utf-8"))
    for s in ("eher schön", "eher heikel", "gemischt", "noch ohne Gefühl", "oft bestätigt", "zuletzt *", "verknüpft mit *"):
        assert s in en, s
