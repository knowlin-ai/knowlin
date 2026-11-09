"""Qualität der Oberfläche (seit 0.38.18): Kompression, Hover nur mit Maus, sichtbarer Text im Namen von Knöpfen."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app
from duckpilot.server.oberflaeche import seite, stil, stil_dateien

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"


def test_skripte_und_stil_kommen_komprimiert(tmp_settings, vault, tmp_path):  # noqa: F811
    """Fürs Handy übers WLAN: Text wird komprimiert ausgeliefert, Bilder nicht noch einmal."""
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        for pfad in ("/static/app.js", "/static/style.css", "/"):
            r = c.get(pfad, headers={"Accept-Encoding": "gzip"})
            assert r.status_code == 200 and r.headers.get("content-encoding") == "gzip", pfad
        r = c.get("/static/knowlin-zeichen.png", headers={"Accept-Encoding": "gzip"})
        assert r.headers.get("content-encoding") is None


def _regeln_ausserhalb_von_media(css: str) -> list[str]:
    """Selektoren mit :hover, die nicht in einer @media-Regel stehen (grob, aber für unsere Dateien genau genug)."""
    ohne_kommentare = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    funde, tiefe, media_tiefe, puffer = [], 0, [], ""
    for z in ohne_kommentare:
        if z == "{":
            kopf = puffer.strip()
            if kopf.startswith("@media"):
                media_tiefe.append(tiefe)
            elif ":hover" in kopf and not media_tiefe:
                funde.append(kopf[:80])
            tiefe += 1
            puffer = ""
        elif z == "}":
            tiefe -= 1
            if media_tiefe and media_tiefe[-1] == tiefe:
                media_tiefe.pop()
            puffer = ""
        elif z == ";":
            puffer = ""
        else:
            puffer += z
    return funde


def test_hover_nur_mit_maus():
    """Auf dem Handy (Fernbedienung) bleiben sonst Hover-Farben nach dem Tippen hängen."""
    for datei in (*(STATIC / p for p in stil_dateien()), STATIC / "ds" / "components.css"):
        assert not _regeln_ausserhalb_von_media(datei.read_text(encoding="utf-8")), datei.name


def test_not_aus_name_enthaelt_den_sichtbaren_text():
    """WCAG 2.5.3: Wer „Not-Aus Esc“ sieht und per Sprache bedient, muss den Knopf mit diesen Worten treffen."""
    html = seite()
    knopf = re.search(r'<button class="rail-stop" id="stop"[^>]*aria-label="([^"]+)"', html).group(1)
    assert knopf.startswith("Not-Aus Esc")


def test_not_aus_klar_ohne_strichelring_und_leiste_unten_deckt():
    """Hinweis 7.11.: Not-Aus „gefällt mir nicht – schon gar nicht mit der gestrichelten Linie“. Jetzt ein
    klarer roter Knopf mit Stopp-Zeichen, Ring durchgehend; am Handy deckt die feste Leiste den Inhalt dahinter ab."""
    html = seite()
    css = stil()
    for teil in re.findall(r'<svg class="estop".*?</svg>', html, re.S):
        assert "estop-zeichen" in teil and "estop-ring" in teil and "radialGradient" not in teil
    regeln = re.findall(r"\.estop[^{]*\{[^}]*\}", css)
    assert regeln and not any("dasharray" in r for r in regeln)
    assert "--surface-glass-fest" in css


def test_praegung_grund_ist_uebersetzt():
    """Gefunden beim Website-Bild: „imprint: a little livelier (viel Spiel und Lob)“ – der Grund blieb deutsch."""
    import json

    from duckpilot.brain.erfahrung import Erfahrungsnetz

    en = json.loads((Path(__file__).resolve().parents[1] / "duckpilot" / "i18n" / "ui_en.json").read_text(encoding="utf-8"))
    netz = Erfahrungsnetz(None)
    gruende = set()
    for hoch, tief in ((60, 0), (0, 60)):
        netz.knoten = {"gefuehl:freude": {"art": "gefuehl", "name": "Freude", "n": hoch},
                       "gefuehl:schreck": {"art": "gefuehl", "name": "Schreck", "n": tief}}
        gruende.add(netz.praegung()["grund"])
    assert gruende == {"viel Spiel und Lob", "einige Schrecken und Pannen"}
    assert all(g in en for g in gruende)
