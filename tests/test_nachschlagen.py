"""Im Netz nachschlagen (seit 0.51): Wikipedia nur eingeschaltet, nur der Suchbegriff, ehrlich bei Fehlern."""

from __future__ import annotations

import asyncio

import pytest

from duckpilot import knowlets as K
from duckpilot import nachschlagen as N
from duckpilot import routinen as R


class Netz:
    def __init__(self, seiten=None, extract="Der Mond ist der einzige natürliche Satellit der Erde. Er ist 384.400 km "
                 "entfernt. Ein dritter Satz bleibt weg.", typ="standard"):
        self.urls = []
        self.seiten = [{"key": "Mond", "title": "Mond"}] if seiten is None else seiten
        self.extract, self.typ = extract, typ

    def __call__(self, url):
        self.urls.append(url)
        if "search/title" in url:
            return {"pages": self.seiten}
        return {"title": "Mond", "extract": self.extract, "type": self.typ,
                "content_urls": {"desktop": {"page": "https://de.wikipedia.org/wiki/Mond"}}}


def test_aus_heisst_aus_und_nichts_geht_raus():
    netz = Netz()
    r = N.Nachschlagen(netz).frage("Mond", an=False)
    assert not r["ok"] and r["aus"] and not netz.urls


def test_zwei_saetze_mit_quelle_und_nur_der_begriff_geht_raus(monkeypatch):
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    netz = Netz()
    d = N.Nachschlagen(netz)
    r = d.frage("  Mond? ", an=True)
    assert r["ok"] and r["text"].endswith("entfernt.") and "dritter" not in r["text"] and r["quelle"] == "Wikipedia"
    assert all(u.startswith("https://de.wikipedia.org/") for u in netz.urls) and "q=Mond&" in netz.urls[0]
    d.frage("mond", an=True)
    assert len(netz.urls) == 2                                            # aus dem Speicher


def test_ehrlich_bei_nichts_mehrdeutig_fehler_und_offline(monkeypatch):
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    assert "finde ich nichts" in N.Nachschlagen(Netz(seiten=[])).frage("Xyz", an=True)["fehler"]
    assert "mehrdeutig" in N.Nachschlagen(Netz(typ="disambiguation")).frage("Bank", an=True)["fehler"]

    def kaputt(url):
        raise OSError("weg")
    assert "nicht erreichbar" in N.Nachschlagen(kaputt).frage("Mond", an=True)["fehler"]
    assert not N.Nachschlagen(Netz()).frage("", an=True)["ok"]
    assert not N.Nachschlagen(Netz()).frage("x" * 200, an=True)["ok"]
    monkeypatch.setenv("DUCKPILOT_OFFLINE", "1")
    assert "Offline" in N.Nachschlagen(Netz()).frage("Mond", an=True)["fehler"]


def test_routine_mit_wissen_braucht_ein_thema():
    with pytest.raises(ValueError, match="Thema"):
        R.pruefen("Abend", schritte=["wissen"])
    r = R.pruefen("Abend", schritte=["wissen"], thema="Mond")
    assert r["thema"] == "Mond" and "Wissen über „Mond“" in R.beschreiben(r)
    assert "thema" not in R.pruefen("Morgen", schritte=["wetter"], thema="egal")


def test_knowlet_bringt_routinen_pausiert_mit_hinweis():
    paket = K.packe(titel="Abendrunde", modul="duckpilot", routinen={
        "Abend": {"name": "Abend", "zeit": "20:00", "schritte": ["wissen", "ruhe"], "thema": "Mond", "an": True,
                  "zuletzt": "x", "id": "boese"},
        "Kaputt": {"name": "Kaputt", "schritte": ["rm -rf"]}})
    p = K.pruefe(paket)
    assert list(p["routinen"]) == ["Abend"] and "id" not in p["routinen"]["Abend"] and "an" not in p["routinen"]["Abend"]
    v = K.vorschau(p, set(), set())
    assert v["nachschlagen"] and "Wissen über „Mond“" in v["routinen"][0]["beschreibung"]


def test_werkzeug_und_saetze_ohne_sprachmodell(monkeypatch):
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    from duckpilot.brain.tools_wissen import BEFEHL, WissenWerkzeuge

    assert BEFEHL.search("Schlag mal Ada Lovelace nach").group("b") == "Ada Lovelace"
    assert BEFEHL.search("Was steht in der Wikipedia über den Mond?").group("w").startswith("den Mond")
    assert BEFEHL.search("Wie spät ist es?") is None

    class W(WissenWerkzeuge):
        def __init__(self, an):
            self.nachschlagen_dienst = N.Nachschlagen(Netz())
            self.websuche_an = lambda: an

        async def run(self, name, args):
            return await self._nachschlagen(args)

    r = asyncio.run(W(True)._nachschlagen_befehl("Schau den Mond nach"))
    assert r["ok"] and r["antwort"].endswith("(Wikipedia)")
    assert "aus" in asyncio.run(W(False)._nachschlagen_befehl("Schlag Mond nach"))["fehler"]
