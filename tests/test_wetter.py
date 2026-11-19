"""Wetter (0.40): Open-Meteo nur auf Nachfrage, Ort nur als Stadt, Sätze ohne Sprachmodell."""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

import pytest

from duckpilot import wetter as W
from duckpilot.brain.fallback import wetter_frage

GEO = {"results": [{"name": "Wien", "country": "Österreich", "latitude": 48.2085, "longitude": 16.3721}]}
DATEN = {"current": {"temperature_2m": 7.4, "apparent_temperature": 4.9, "weather_code": 3, "wind_speed_10m": 12.0,
                     "precipitation": 0.0},
         "daily": {"weather_code": [61, 0], "temperature_2m_max": [9.2, 11.6], "temperature_2m_min": [3.1, 2.4],
                   "precipitation_probability_max": [70, 10]}}


class Netz:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str) -> dict:
        self.urls.append(url)
        return GEO if "geocoding" in url else DATEN


@pytest.fixture(autouse=True)
def online(monkeypatch):
    monkeypatch.setattr(W, "offline", lambda: False)


def test_heute_morgen_und_nur_stadt_und_koordinaten_gehen_raus():
    netz = Netz()
    w = W.Wetter(fetch=netz)
    r = w.abfrage("Wien")
    assert r["ok"] and r["ort"] == "Wien" and r["jetzt"]["temperatur"] == 7.4
    assert r["text"] == ("In Wien sind es gerade 7 Grad, bedeckt. Heute leichter Regen, 3 bis 9 Grad. "
                         "Nimm lieber einen Schirm mit.")
    m = w.abfrage("Wien", "morgen")
    assert m["max"] == 11.6 and "jetzt" not in m and m["text"] == "Morgen in Wien klar, 2 bis 12 Grad."
    assert len(netz.urls) == 2                                           # Ort und Wetter je einmal, danach aus dem Speicher
    geo, fc = (parse_qs(urlparse(u).query) for u in netz.urls)
    assert geo["name"] == ["Wien"] and set(fc) == {"latitude", "longitude", "timezone", "forecast_days", "current", "daily"}
    assert all(u.startswith(("https://geocoding-api.open-meteo.com/", "https://api.open-meteo.com/")) for u in netz.urls)
    en = W.Wetter(fetch=Netz()).abfrage("Wien", en=True)["text"]
    assert en.startswith("In Wien it is 7 °C and overcast right now.") and "umbrella" in en


def test_ehrlich_ohne_ort_offline_unbekannt_und_netzfehler(monkeypatch):
    w = W.Wetter(fetch=Netz())
    assert w.abfrage("")["ort_fehlt"]
    assert not W.Wetter(fetch=lambda u: {"results": []}).abfrage("Xyzzy")["ok"]

    def kaputt(url):
        raise OSError("weg")

    r = W.Wetter(fetch=kaputt).abfrage("Wien")
    assert not r["ok"] and "nicht erreichbar" in r["fehler"]
    with pytest.raises(ValueError):
        W.ort_pruefen("x" * 61)
    with pytest.raises(ValueError):
        W.ort_pruefen("Wien\x00")
    monkeypatch.setattr(W, "offline", lambda: True)
    netz = Netz()
    assert not W.Wetter(fetch=netz).abfrage("Wien")["ok"] and not netz.urls


def test_fragen_ohne_sprachmodell():
    assert wetter_frage("Wie wird das Wetter morgen in Wien?") == {"tag": "morgen", "ort": "Wien"}
    assert wetter_frage("Brauche ich heute einen Schirm?") == {"tag": "heute"}
    assert wetter_frage("what's the weather in New York tomorrow") == {"tag": "morgen", "ort": "New York"}
    assert wetter_frage("Das Wetter ist schön") is None and wetter_frage("Wie spät ist es?") is None


def test_werkzeug_einstellung_und_nur_am_pc(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from duckpilot import settings as S
    from duckpilot.brain.fallback import FallbackBrain
    from duckpilot.config import load
    from duckpilot.remote import PC_ONLY_SETTINGS
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "s.json"))
    monkeypatch.setattr(S, "_keyring", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "m.json")))
    rt.wetter.fetch = Netz()
    assert "wetter_ort" in PC_ONLY_SETTINGS
    assert "wetter" in {t["name"] for t in rt.runner.tools()}
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        assert c.post("/api/settings", json={"wetter_ort": "Wien"}).status_code == 200
        assert c.post("/api/settings", json={"wetter_ort": "x" * 80}).status_code == 400
    assert rt.config.wetter_ort == "Wien"
    r = asyncio.run(FallbackBrain(rt.runner).handle("Wie ist das Wetter?"))
    assert r.text.startswith("In Wien sind es gerade 7 Grad") and r.actions[0]["tool"] == "wetter"
