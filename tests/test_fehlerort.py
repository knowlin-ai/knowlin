"""Wo liegt der Fehler – bei dir, beim Anbieter oder in Knowlin? (gemeldet 11.11.: „nicht ersichtlich, ob es im
Programm oder von den Servern Fehler gibt oder bei mir am PC“)"""

from duckpilot.fehlerort import einordnen


def test_netz_bei_dir():
    s = einordnen("ChunkedEncodingError: ('Connection broken: IncompleteRead(77187461 bytes read)')", "Hugging Face")
    assert "Internet oder WLAN bei dir" in s and "Hugging Face" in s and "IncompleteRead" not in s


def test_server_beim_anbieter():
    assert "beim Anbieter" in einordnen("HTTPError: HTTP Error 503: Service Unavailable", "GitHub")


def test_fehlt_ist_knowlins_fehler():
    assert "Fehler in Knowlin" in einordnen("HTTPError: HTTP Error 404: Not Found", "GitHub")


def test_sonst_kurz():
    assert len(einordnen(ValueError("x" * 4000))) < 320
