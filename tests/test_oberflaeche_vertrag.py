"""Vertrag zwischen Skripten und Seite (Architektur-Etappe A2, seit 0.38.38).

Die Seite liegt in Teilen (`static/teile/`), die Stile je Bereich (`static/bereiche/`). Damit beim Aufteilen nichts
verloren geht – genau die Fehlerklasse „Cannot read properties of null“ –, prüft dieser Test:

* Jede ID, die ein Skript per `$('…')` oder `getElementById('…')` holt, gibt es auf der Seite (oder ein Skript legt sie an).
* IDs sind eindeutig; jedes Teil und jede Bereichs-Datei wird eingebunden und bleibt unter der Größengrenze.
"""

import re
from collections import Counter

from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot.server.oberflaeche import GRENZE_KB, STATIC, seite, stil_dateien, teile

ID_HTML = re.compile(r'\bid="([^"$]+)"')


def _skripte() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(STATIC.glob("*.js"))}


def test_jede_geholte_id_gibt_es():
    html = seite()
    da = set(ID_HTML.findall(html))
    js = _skripte()
    alle = "".join(js.values())
    angelegt = set(ID_HTML.findall(alle)) | set(re.findall(r"\.id\s*=\s*'([^']+)'", alle)) | \
        set(re.findall(r"id:\s*'([^']+)'", alle))
    fehlen = {}
    for name, text in js.items():
        geholt = set(re.findall(r"(?<![\w.])\$\('([\w-]+)'\)", text)) | set(re.findall(r"getElementById\('([\w-]+)'\)", text))
        f = sorted(geholt - da - angelegt)
        if f:
            fehlen[name] = f
    assert not fehlen, f"Skripte holen IDs, die es nicht gibt: {fehlen}"


def test_ids_sind_eindeutig():
    doppelt = [i for i, n in Counter(ID_HTML.findall(seite())).items() if n > 1]
    assert not doppelt, doppelt


def test_teile_und_bereiche_sind_eingebunden_und_klein():
    eingebunden = set(teile())
    vorhanden = {p.stem for p in (STATIC / "teile").glob("*.html")}
    assert eingebunden == vorhanden, (eingebunden ^ vorhanden)
    stile = set(stil_dateien())
    bereiche = {f"bereiche/{p.name}" for p in (STATIC / "bereiche").glob("*.css")}
    assert bereiche <= stile, bereiche - stile
    for p in [*(STATIC / "teile").glob("*.html"), *(STATIC / "bereiche").glob("*.css")]:
        assert p.stat().st_size <= GRENZE_KB * 1024, f"{p.name}: {p.stat().st_size // 1024} KB"


def test_teil_ist_nur_ein_stueck_ohne_seitenrahmen():
    for p in (STATIC / "teile").glob("*.html"):
        t = p.read_text(encoding="utf-8")
        assert "<html" not in t and "<body" not in t and "<!--#teil" not in t, p.name


def test_server_liefert_die_zusammengesetzte_seite(tmp_settings, vault, tmp_path):  # noqa: F811
    from fastapi.testclient import TestClient

    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    with TestClient(create_app(Runtime(load(memory_path=str(tmp_path / "mem.json")))), base_url="http://127.0.0.1:8765") as c:
        html = c.get("/").text
    assert "<!--#teil" not in html
    for name in teile():
        anfang = re.search(r'id="([^"]+)"', (STATIC / "teile" / f"{name}.html").read_text(encoding="utf-8")).group(1)
        assert f'id="{anfang}"' in html, name
