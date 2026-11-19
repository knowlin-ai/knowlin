"""Erfahrungsnetz 2 (0.39): Tagesrückblick aus dem Tagebuch und Weltbild aus den Sichtungen."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from duckpilot.brain.erfahrung import key
from duckpilot.brain.fallback import TAGESRUECKBLICK, WELTBILD, weltbild_text
from duckpilot.brain.tools_erinnern import tag_aus
from duckpilot.sichtungen import Sichtungen
from duckpilot.tagebuch import JE_TAG, TAGE, Tagebuch

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"
TAG = "2026-11-18"


def _ts(stunde: int, minute: int = 0, tag: str = TAG) -> float:
    return datetime.fromisoformat(f"{tag}T{stunde:02d}:{minute:02d}:00").timestamp()


def _tagebuch(pfad: Path | None = None) -> Tagebuch:
    tb = Tagebuch(pfad)
    for i in range(3):
        tb.notieren({key("ding", "Ball"): "Ball", key("gefuehl", "freude"): "Freude"}, "Ball getroffen", 0.8,
                    jetzt=_ts(9, i))
    tb.notieren({key("rueckmeldung", "lob"): "Lob", key("person", "Anna"): "Anna"}, "Anna hat mich gelobt", 1.2,
                jetzt=_ts(10))
    tb.notieren({key("ort", "Küche"): "Küche"}, "in der Küche", 0.4, jetzt=_ts(11))
    return tb


def test_rueckblick_fasst_den_tag_ohne_sprachmodell_zusammen():
    tb = _tagebuch()
    r = tb.rueckblick(TAG, erst={key("ort", "Küche"): _ts(11)}, heute=date(2026, 11, 18))
    assert r["anzahl"] == 5 and r["haeufig"][0]["name"] == "Ball" and r["haeufig"][0]["n"] == 3
    assert r["neu"] == ["Küche"] and r["lob"] == 1 and r["stimmung"] == "froh"
    assert r["text"].startswith("Heute habe ich 5 Dinge erlebt.") and "Ball" in r["text"] and "Küche" in r["text"]
    assert [m["zeit"] for m in r["momente"]] == ["09:00", "09:01", "09:02", "10:00", "11:00"]   # die stärksten, nach Uhrzeit
    assert key("ding", "Ball") in r["ids"]
    en = tb.rueckblick(TAG, en=True, heute=date(2026, 11, 18))["text"]
    assert en.startswith("Today I experienced 5 things.")


def test_vom_handy_ohne_personen():
    r = _tagebuch().rueckblick(TAG, ohne_personen=True, heute=date(2026, 11, 18))
    blob = json.dumps(r, ensure_ascii=False)
    assert "Anna" not in blob and r["anzahl"] == 4 and r["lob"] == 0


def test_loeschen_speichern_und_grenzen(tmp_path):
    pfad = tmp_path / "tagebuch.json"
    tb = _tagebuch(pfad)
    assert tb.loeschen(TAG, _ts(10)) and not tb.loeschen(TAG, _ts(10))
    tb.speichern()
    neu = Tagebuch(pfad)
    assert "Anna" not in pfad.read_text("utf-8") and len(neu.tage[TAG]) == 4
    assert neu.tag_loeschen(TAG) and not neu.tage
    voll = Tagebuch()                                     # je Tag begrenzt: schwache Momente weichen starken
    for i in range(JE_TAG + 20):
        voll.notieren({key("ding", f"D{i}"): f"D{i}"}, "", 0.1 if i < JE_TAG else 2.0, jetzt=_ts(8) + i)
    assert len(voll.tage[TAG]) == JE_TAG and sum(e["s"] == 2.0 for e in voll.tage[TAG]) == 20
    viele = Tagebuch()                                    # höchstens TAGE Tage
    for d in range(TAGE + 5):
        viele.notieren({"ding:x": "x"}, jetzt=datetime(2026, 1, 1 + d, 12).timestamp())
    assert len(viele.tage) == TAGE and min(viele.tage) == f"2026-01-{6:02d}"


def test_tag_aus_und_saetze_ohne_sprachmodell():
    heute = date(2026, 11, 19)
    assert tag_aus("", heute) == "2026-11-19" and tag_aus("gestern", heute) == "2026-11-18"
    assert tag_aus("2026-11-01", heute) == "2026-11-01" and tag_aus("morgen", heute) is None
    for s in ("Wie war dein Tag?", "Was hast du heute erlebt?", "what did you do today", "Was war gestern los?"):
        assert TAGESRUECKBLICK.search(s.lower()), s
    assert not TAGESRUECKBLICK.search("wie war das wetter")
    for s in ("Was weißt du über das Zimmer?", "Was liegt wo?", "what do you know about the room"):
        assert WELTBILD.search(s.lower()), s


def _st(x, y, objs):
    return SimpleNamespace(x=x, y=y, yaw=0.0, perception=SimpleNamespace(objects=objs))


def test_weltbild_kennt_den_ueblichen_platz_und_merkt_umzuege():
    s = Sichtungen()
    umzuege = []
    s.beim_umzug = lambda ding, moebel: umzuege.append((ding, moebel))
    sofa = {"name": "Sofa", "art": "möbel", "entfernung_m": 1.0, "richtung_grad": 0}
    kiste = {"name": "Kiste", "art": "möbel", "entfernung_m": 1.0, "richtung_grad": 90}
    t = 1000.0
    s.beobachte(_st(0, 0, [sofa, kiste]), t)
    for _ in range(4):                                    # die Socke liegt meistens beim Sofa
        t += 60
        s.beobachte(_st(0, 0, [{"name": "Socke", "art": "sock", "entfernung_m": 0.9, "richtung_grad": 0}]), t)
    g = s.glaube("Socke", t + 10)
    assert g["platz"] == "Sofa" and g["typisch"] == "Sofa" and not g["woanders"] and g["gewissheit"] == "sicher"
    t += 60
    s.beobachte(_st(0, 0, [{"name": "Socke", "art": "sock", "entfernung_m": 0.9, "richtung_grad": 90}]), t)
    g = s.glaube("Socke", t + 3 * 3600)
    assert g["platz"] == "Kiste" and g["typisch"] == "Sofa" and g["woanders"] and g["gewissheit"] == "unsicher"
    assert umzuege == [("Socke", "Sofa"), ("Socke", "Kiste")]
    assert [x["name"] for x in s.weltbild(t)] == ["Socke"]           # Möbel und Menschen nicht
    txt = s.antwort("Wo ist die Socke?", jetzt=t + 30)["text"]
    assert "bei der Kiste" in txt and "beim Sofa" in txt
    satz = weltbild_text({"ok": True, "dinge": s.weltbild(t)})
    assert satz.startswith("Was ich weiß: Socke bei der Kiste.") and "woanders als sonst" in satz


def test_umzug_wird_erfahrung_und_route_und_alles_vergessen(tmp_path, monkeypatch):
    from duckpilot import remote as R
    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "s.json"))
    monkeypatch.setattr(S, "_keyring", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "m.json")))
    svc = rt.erfahrung
    rt._ding_umgezogen("Socke", "Sofa")
    assert key("ding", "Socke") in svc.netz.knoten and key("ort", "Sofa") in svc.netz.knoten
    svc.person("Anna")
    heute = date.today().isoformat()
    assert svc.tagebuch.tage.get(heute)                     # der Haken notiert jedes Erlebnis
    tok = R.REMOTE_TURN.set(True)
    try:
        r = asyncio.run(rt.runner.run("tagesrueckblick", {}))
    finally:
        R.REMOTE_TURN.reset(tok)
    assert r["ok"] and "Anna" not in json.dumps(r, ensure_ascii=False)
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        d = c.get("/api/erfahrung/rueckblick").json()
        assert d["an"] and d["tag"] == heute and d["anzahl"] >= 1
        assert c.get("/api/erfahrung/rueckblick?tag=gestern").status_code == 400
        assert c.post("/api/erfahrung/rueckblick/loeschen", json={"tag": "x"}).status_code == 400
        t = svc.tagebuch.tage[heute][0]["t"]
        assert c.post("/api/erfahrung/rueckblick/loeschen", json={"tag": heute, "t": t},
                      headers={"X-Forwarded-For": "192.168.1.20"}).status_code in (401, 403)
        assert c.post("/api/erfahrung/rueckblick/loeschen", json={"tag": heute, "t": t}).json()["ok"]
    asyncio.run(rt.handle_client_message({"type": "memory_clear"}))
    assert not svc.tagebuch.tage


def test_oberflaeche():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="tages-karte"' in html and html.index('id="tages-karte"') < html.index('id="card-brain"')
    assert "Was Knowlin über das Zimmer glaubt" in html and "/static/bereiche/gedaechtnis.css" in html
    assert "initTagesrueckblick" in (STATIC / "gedaechtnis_ui.js").read_text(encoding="utf-8")
    assert "knowlin:hirn-tag" in (STATIC / "hirn.js").read_text(encoding="utf-8")
    css = (STATIC / "bereiche" / "gedaechtnis.css").read_text(encoding="utf-8")
    assert "rgb(" not in css and not __import__("re").search(r"#[0-9a-fA-F]{3,6}\b", css)   # Farben nur als Tokens
