"""Knowlin-Startseite und neue Gliederung (seit 0.38, Entscheidungen des Maintainers vom 4.11.)."""

import json
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot import __version__, desktop, suite
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app
from duckpilot.server.oberflaeche import seite

STATIC = Path(__file__).resolve().parent.parent / "duckpilot" / "server" / "static"
HTML = seite()
APP = (STATIC / "app.js").read_text(encoding="utf-8")


def _block(start: str) -> str:
    """Inhalt einer Ansicht (von ihrem <section …> bis zur nächsten Ansicht)."""
    i = HTML.index(start)
    j = HTML.find('<section class="view ', i + 10)
    return HTML[i:j if j > 0 else len(HTML)]


def test_module_ehrlich_fertig_oder_geplant():
    ms = suite.module("sim")
    assert ms[0]["id"] == "duckpilot" and ms[0]["stand"] == "fertig" and ms[0]["verbunden"] == "Simulator"
    # seit 0.38.1 ist Reachy Mini fertig (im Simulator) – nicht aktiv, also ohne „verbunden“
    reachy = next(m for m in ms if m["id"] == "reachy-mini")
    assert reachy["stand"] == "fertig" and reachy["modul"] == "reachy_mini" and not reachy["aktiv"] and "verbunden" not in reachy
    rest = [m for m in ms[1:] if m["id"] not in ("reachy-mini", "open-duck-mini", "so101", "knowlets")]   # fertig seit 0.38.4/.5/.51
    kn = next(m for m in ms if m["id"] == "knowlets")
    assert kn["stand"] == "fertig" and kn["ansicht"] == "knowlets" and kn["art"] == "werkzeug" and "modul" not in kn
    assert rest and all(m["stand"] in ("geplant", "anleitung") for m in rest)
    umgeschaltet = suite.module("sim", "reachy_mini")
    assert not umgeschaltet[0]["aktiv"] and "verbunden" not in umgeschaltet[0]
    assert next(m for m in umgeschaltet if m["id"] == "reachy-mini")["verbunden"] == "Simulator"
    namen = {m["name"] for m in ms}
    assert {"Reachy Mini", "Open Duck Mini", "Knowlin Lab", "Mentor", "Eigenes Modul"} <= namen
    aktuell = tuple(int(x) for x in __version__.split("."))
    for m in ms[1:]:
        if re.fullmatch(r"\d+\.\d+(\.\d+)?", m["version"]):
            assert tuple(int(x) for x in m["version"].split(".")) > aktuell, m
    # seit 0.38.3: nur, was alle Figuren teilen – Charakter gehört der Figur
    assert {k["ansicht"] for k in suite.kern()} == {"memory", "umgebung", "alltag", "settings"}


def test_api_module_und_verknuepfung(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        r = c.get("/api/module").json()
        assert r["ok"] and r["module"][0]["name"] == "duckpilot" and r["kern"]
        if sys.platform != "win32":
            r = c.post("/api/verknuepfung", json={"modul": "duckpilot"})
            assert r.status_code == 400 and "Windows" in r.json()["fehler"]


def test_verknuepfungen_knowlin_und_direktstart():
    assert desktop.VERKNUEPFUNGEN[""][0] == "Knowlin.lnk" and "--modul" not in desktop.VERKNUEPFUNGEN[""][1]
    assert desktop.VERKNUEPFUNGEN["duckpilot"][1].endswith("--modul duckpilot")
    # seit 0.38.27: sichtbar überall „Knowlin“; die Startseite trägt das Knowlin-Zeichen, die Microduck ihre Ente
    assert all(v[0].startswith("Knowlin") and "duckpilot" not in v[0] + v[2] for v in desktop.VERKNUEPFUNGEN.values())
    assert desktop.VERKNUEPFUNGEN[""][3] == "knowlin.ico" and desktop.VERKNUEPFUNGEN["duckpilot"][3] == "duckpilot.ico"
    assert desktop.ALTE_NAMEN["duckpilot.lnk"] == desktop.VERKNUEPFUNGEN["duckpilot"][0]
    root = Path(__file__).resolve().parent.parent
    assert (root / "knowlin.ico").exists() and desktop.symbol("knowlin.ico") == root / "knowlin.ico"
    bat = (root / "start.bat").read_text(encoding="utf-8")
    assert "Knowlin.lnk" in bat and "--app --modul duckpilot" in bat and "Knowlin - Microduck.lnk" in bat
    assert "knowlin.ico" in bat and "'duckpilot.lnk'" in bat        # alte Verknüpfung da → keine zweite anlegen
    src = (root / "duckpilot" / "__main__.py").read_text(encoding="utf-8")
    assert '"--modul"' in src and "?modul=" in src
    # Auffrischen: nur eigene (Ziel „-m duckpilot“), Ziel umbiegen nur außerhalb von „Zweige“
    d = (root / "duckpilot" / "desktop.py").read_text(encoding="utf-8")
    assert d.count("-like '*-m duckpilot*'") + d.count("-notlike '*-m duckpilot*'") >= 2 and "Rename-Item" in d
    assert "Remove-Item" not in d


def test_start_bat_startet_knowlin():
    """Regression 0.38.27: Beim Umbenennen der Verknüpfungen fielen Start-Zeile und Sprungmarke weg – nichts startete."""
    bat = (Path(__file__).resolve().parent.parent / "start.bat").read_text(encoding="utf-8")
    zeilen = [z.strip() for z in bat.splitlines()]
    assert 'start "" "%VENV%\\Scripts\\pythonw.exe" -m duckpilot --app' in zeilen
    aufruf = zeilen.index("call :verknuepfung")
    start = zeilen.index('start "" "%VENV%\\Scripts\\pythonw.exe" -m duckpilot --app')
    ende, marke = zeilen.index("goto :eof", start), zeilen.index(":verknuepfung")
    assert aufruf < start < ende < marke                      # erst Verknüpfungen, dann starten, dann Ende
    # jede angesprungene Marke gibt es auch
    import re
    for ziel in set(re.findall(r"(?:call|goto) :(\w+)", bat)) - {"eof"}:
        assert f":{ziel}" in zeilen, ziel


def test_zweig_biegt_verknuepfungen_nicht_um():
    assert desktop.ist_zweig(Path("C:/Users/x/OneDrive/Duckpilot/Zweige/etappe-0.38.27"))
    assert not desktop.ist_zweig(Path("C:/Users/x/OneDrive/Duckpilot"))
    m = json.loads((Path(__file__).resolve().parent.parent / "duckpilot" / "server" / "static" / "manifest.webmanifest")
                   .read_text(encoding="utf-8"))
    assert m["name"] == m["short_name"] == "Knowlin"


def test_startseite_ist_standard_modul_direkt():
    assert 'id="view-start"' in HTML and 'id="rail-start"' in HTML
    assert "['duckpilot', 'reachy_mini', 'open_duck_mini'].includes(direktModul)" in APP and "else showView('start');" in APP
    assert "imKopf ? 'Knowlin' : `${appName} – Knowlin`" in APP          # Fenstertitel: im Kopf nur Knowlin (0.38.7)


def test_neue_gliederung():
    umgebung = _block('<section class="view view-umgebung"')
    assert 'id="raum-karte"' in umgebung
    tricks = _block('<section class="view view-tricks"')
    assert 'data-part="team"' in tricks and 'id="raum-karte"' not in tricks
    team = tricks[tricks.index('data-part="team"'):tricks.index('data-part="hub"')]
    assert 'id="enten-karte"' in team
    gedaechtnis = _block('<section class="view view-memory"')
    assert 'id="card-brain"' in gedaechtnis and 'id="chart-mood"' in gedaechtnis
    koerper = _block('<section class="view view-dashboard"')
    assert 'aria-label="Körper"' in koerper and 'id="card-brain"' not in koerper and 'id="map"' in koerper
    einst = _block('<section class="view view-settings"')
    assert 'id="set-ki"' in einst and 'id="anbieter-card"' in einst and 'id="local-card"' in einst
    stimme = _block('<section class="view view-stimme"')
    assert 'id="anbieter-card"' not in stimme and 'id="goto-ki"' in stimme
    assert 'data-group="umgebung"' in HTML
    assert "part: 'team', label: 'Team'" in APP and "{ id: 'umgebung', tabs: [{ view: 'umgebung' }] }" in APP
    assert "view: 'dashboard', label: 'Körper'" in APP
    # jede ID nur einmal – nichts doppelt verschoben
    ids = re.findall(r'\sid="([^"]+)"', HTML)
    doppelt = {i for i in ids if ids.count(i) > 1}
    assert not doppelt, doppelt


def test_jede_verkoerperung_hat_eine_kachel():
    """Fund 12.11.: Ari (SO-101) war nur über Einstellungen → Körper zu finden. Jede eingebaute Verkörperung braucht eine
    Kachel auf der Startseite und eine Verknüpfung zum Direktstart."""
    from duckpilot.desktop import VERKNUEPFUNGEN
    from duckpilot.figuren import FIGUREN

    ms = suite.module("sim")
    kacheln = {m["modul"]: m for m in ms if m.get("modul")}
    assert set(FIGUREN) <= set(kacheln)
    ari = kacheln["so101"]
    assert ari["art"] == "koerper" and ari["stand"] == "fertig" and ari["koerper_name"] == "SO-101"
    assert set(suite.KOERPER_MODUL) <= set(VERKNUEPFUNGEN)
    js = (Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static" / "start.js").read_text(encoding="utf-8")
    assert all(f"'{k}'" in js or f"{k}:" in js for k in suite.KOERPER_MODUL)       # Umriss je Körper


def test_portraets_rendert_die_startseite_selbst(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    """Frage des Maintainers: „Wieso laden wir nicht die Bilder der Roboter?“ – Pollens Porträts liegen nicht im Repo;
    die Startseite rendert sie aus den geladenen Modellen und legt sie am PC ab (seit 0.38.51)."""
    from duckpilot import remote

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "daten"))
    monkeypatch.setattr(sys, "platform", "linux")
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        assert next(m for m in suite.module() if m["id"] == "so101")["bild"] is False
        assert c.get("/api/portraet/so101.png").status_code == 404
        assert c.post("/api/portraet/so101", content=b"kein Bild").status_code == 400
        assert c.post("/api/portraet/fremd", content=png).status_code == 400
        assert c.post("/api/portraet/so101", content=png + b"\0" * 700_000).status_code == 400
        assert c.post("/api/portraet/so101", content=png).json()["ok"]
        r = c.get("/api/portraet/so101.png")
        assert r.status_code == 200 and r.content == png and r.headers["content-type"] == "image/png"
        assert next(m for m in suite.module() if m["id"] == "so101")["bild"] is True
        if (suite.FIGUREN_BILDER / "open-duck-mini.png").is_file():                 # Mitgeliefertes geht vor
            assert c.get("/api/portraet/open-duck-mini.png").content == (suite.FIGUREN_BILDER / "open-duck-mini.png").read_bytes()
    assert remote.pc_only("POST", "/api/portraet/so101") and not remote.pc_only("GET", "/api/portraet/so101.png")
    js = (Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static" / "portraet3d.js").read_text(encoding="utf-8")
    assert all(f"'{k}'" in js or f"{k}:" in js for k in suite.BILD_DATEI)        # jeder Körper lässt sich rendern
