"""Abgleich mit Pollens duck-ipc-proto (Stand 6.11.2026, API 50): robotd meldet den Akku als `battery: {volts, percent}`.
Vorher suchte Knowlin nur „fraction“ – am echten Roboter wäre der Akkustand nie angekommen. Fehlt `battery`, ist der Stand
unbekannt (nicht leer)."""

from duckpilot.backends.robotd import API_VERSION, _find_fraction


def test_akku_aus_pollens_feldern():
    assert _find_fraction({"healthy": True, "battery": {"volts": 7.6, "percent": 62.5}}) == 0.625
    assert _find_fraction({"healthy": True, "battery": {"volts": 6.0, "percent": -3}}) == 0.0
    assert _find_fraction({"healthy": True, "battery": {"volts": 8.5, "percent": 104}}) == 1.0


def test_fehlender_akku_ist_unbekannt_nicht_leer():
    assert _find_fraction({"healthy": False, "degraded": True, "reason": "no servo power"}) is None
    assert _find_fraction({"healthy": True}) is None


def test_protokollstand():
    assert API_VERSION >= 50
