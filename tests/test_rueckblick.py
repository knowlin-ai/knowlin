"""Rückblick in Ruhephasen (seit 0.38.45, Etappe G4). Wunsch des Maintainers: „nicht erzählen, aber dokumentieren – so
dass man ggf. korrigieren oder löschen kann“. Lehren wirken nur auf Gewichte, betreffen nie Personen, Knowlin sagt
nichts dazu."""

import pytest

from duckpilot import remote as R
from duckpilot.gedankenspur import Gedankenspur
from duckpilot.rueckblick import MAX_FAKTOR, MIN_FAKTOR, Lehrbuch, ableiten


def _spur(*eintraege):
    g = Gedankenspur()
    for i, (art, ergebnis) in enumerate(eintraege):
        g.merken(f"{art} von sich aus", "Neugier (etwas)", art=art, ergebnis=ergebnis, zeit=1000 + i * 60)
    return g.liste()


def test_lehren_aus_der_spur():
    zeilen = _spur(("erkunden", "ging nicht"), ("erkunden", "ging nicht"), ("trick", "getan"), ("trick", "getan"),
                   ("trick", "getan"), ("umschauen", "getan"))
    lehren = {x["art"]: x for x in ableiten(zeilen, 0)}
    assert set(lehren) == {"erkunden", "trick"}
    assert lehren["erkunden"]["faktor"] < 1 and "Den Raum erkunden klappt hier gerade oft nicht" in lehren["erkunden"]["was"]
    assert lehren["erkunden"]["woraus"].startswith("2× nicht geklappt")
    assert lehren["trick"]["faktor"] > 1 and lehren["trick"]["was"] == "Mag Tricks üben"
    assert ableiten(zeilen, 10_000) == []                                 # nur Neues seit dem letzten Rückblick


def test_lehren_ohne_personen_und_nur_aus_eigenem_tun():
    g = Gedankenspur()
    for i in range(2):                                                    # Bitten im Gespräch lehren nichts
        g.merken("wollte Freude zeigen", "gewünscht", quelle="gespraech", ergebnis="nicht getan: Sperre", zeit=1 + i)
    for i in range(3):                                                    # Text der Spur (evtl. mit Namen) wird nie übernommen
        g.merken("dreht sich zu Anna", "Nähe (stark)", art="zuwenden", person=True, zeit=10 + i)
    lehren = ableiten(g.liste(), 0)
    assert [x["art"] for x in lehren] == ["zuwenden"]
    assert "Anna" not in lehren[0]["was"] + lehren[0]["woraus"] and lehren[0]["was"] == "Mag sich dir zuwenden"


def test_lehrbuch_dokumentiert_korrigiert_loescht(tmp_path):
    buch = Lehrbuch(tmp_path / "rueckblick.json")
    zeilen = _spur(("erkunden", "ging nicht"), ("erkunden", "ging nicht"))
    neu = buch.zurueckblicken(zeilen, "microduck", jetzt=5000)
    assert len(neu) == 1 and buch.faktor("microduck", "erkunden") == 0.5
    assert buch.faktor("reachy_mini", "erkunden") == 1.0                    # je Verkörperung
    lid = neu[0]["id"]
    buch.korrigieren(lid, "oefter")
    nochmal = Lehrbuch(tmp_path / "rueckblick.json")                        # bleibt nach dem Neustart
    assert nochmal.liste()[0]["korrigiert"] == "oefter" and nochmal.faktor("microduck", "erkunden") == 1.3
    # neue Fehlschläge überschreiben die Korrektur des Menschen nicht
    mehr = _spur(("erkunden", "ging nicht"), ("erkunden", "ging nicht"))
    for z in mehr:
        z["zeit"] += 10_000
    assert nochmal.zurueckblicken(mehr, "microduck", jetzt=20_000) == []
    assert nochmal.faktor("microduck", "erkunden") == 1.3
    with pytest.raises(ValueError):
        nochmal.korrigieren(lid, "immer")
    assert nochmal.loeschen(lid) and nochmal.liste() == [] and not nochmal.loeschen(lid)


def test_faktor_bleibt_in_grenzen(tmp_path):
    buch = Lehrbuch(tmp_path / "r.json")
    buch.lehren.append({"id": "x", "zeit": 1, "koerper": "m", "art": "tanzen", "faktor": 99})
    buch.lehren.append({"id": "y", "zeit": 1, "koerper": "m", "art": "laufen", "faktor": 0})
    assert buch.faktor("m", "tanzen") == MAX_FAKTOR and buch.faktor("m", "laufen") == MIN_FAKTOR


def test_aendern_nur_am_pc():
    for methode, pfad in (("POST", "/api/rueckblick/jetzt"), ("POST", "/api/rueckblick/abc"), ("DELETE", "/api/rueckblick/abc")):
        assert any(m == methode and p.match(pfad) for m, p in R.PC_ONLY), pfad
