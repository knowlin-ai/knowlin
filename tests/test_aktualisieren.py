"""Updates aus dem Netz (0.38.32, Frage beim Launch: „Bekommen die Leute eine Update-Info und können aus dem Programm
heraus aktualisieren?“)."""

import hashlib
import json

import pytest

from duckpilot import __version__
from duckpilot import aktualisieren as A


def _release(version="99.0.0", mit_installer=True, daten=b"setup", digest=None, **extra):
    assets = []
    if mit_installer:
        assets.append({"name": f"Knowlin-Setup-{version}.exe", "size": len(daten),
                       "browser_download_url": f"https://github.com/knowlin-ai/knowlin/releases/download/v{version}/Knowlin-Setup-{version}.exe",
                       "digest": digest or "sha256:" + hashlib.sha256(daten).hexdigest()})
    return {"tag_name": f"v{version}", "name": f"Knowlin {version}", "html_url":
            f"https://github.com/knowlin-ai/knowlin/releases/tag/v{version}", "body": "Neu: …", "assets": assets, **extra}


def test_versionen_vergleichen():
    assert A.neuer("0.38.32", "0.38.31") and A.neuer("v1.0.0", "0.99.99") and not A.neuer("0.38.31", "0.38.31")
    assert not A.neuer("0.38.9", "0.38.10") and not A.neuer("kaputt", "0.38.31")


def test_auswerten_nur_mit_pruefsumme_und_ohne_vorabversion():
    r = A.auswerten(_release())
    assert r["version"] == "99.0.0" and r["installer"]["sha256"] == hashlib.sha256(b"setup").hexdigest()
    assert A.auswerten(_release(digest="md5:abc"))["installer"] is None          # ohne SHA-256 kein Selbst-Update
    assert A.auswerten(_release(prerelease=True)) is None and A.auswerten({"tag_name": "nightly"}) is None
    fremd = A.auswerten(_release(html_url="https://example.com/x"))
    assert fremd["seite"].startswith("https://github.com/knowlin-ai/knowlin/")


def test_pruefen_hoechstens_einmal_am_tag_und_offline_nie(tmp_path, monkeypatch):
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    aufrufe = []

    def lesen(url, limit=0):
        aufrufe.append(url)
        return json.dumps(_release()).encode()

    akt = A.Aktualisierer(tmp_path, lesen=lesen)
    akt.art = "installer"
    st = akt.pruefen()
    assert aufrufe == [A.API] and st["neu"]["version"] == "99.0.0" and st["kann"]
    akt.pruefen()
    assert len(aufrufe) == 1                                                    # zwischengespeichert
    akt.pruefen(erzwingen=True)
    assert len(aufrufe) == 2
    monkeypatch.setenv("DUCKPILOT_OFFLINE", "1")
    with pytest.raises(A.UpdateFehler, match="offline"):
        akt.pruefen(erzwingen=True)


def test_gleiche_oder_aeltere_version_ist_kein_update(tmp_path, monkeypatch):
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    akt = A.Aktualisierer(tmp_path, lesen=lambda url, limit=0: json.dumps(_release(__version__)).encode())
    assert akt.pruefen()["neu"] is None


def test_installer_nur_mit_passender_pruefsumme_und_von_github(tmp_path):
    info = A.auswerten(_release(daten=b"echter installer"))["installer"]
    akt = A.Aktualisierer(tmp_path, lesen=lambda url, limit=0: b"echter installer")
    pfad = akt.installer_laden(info)
    assert pfad.read_bytes() == b"echter installer" and pfad.name == "Knowlin-Setup-99.0.0.exe"
    boese = A.Aktualisierer(tmp_path, lesen=lambda url, limit=0: b"untergeschoben")
    with pytest.raises(A.UpdateFehler, match="Prüfsumme"):
        boese.installer_laden(info)
    with pytest.raises(A.UpdateFehler, match="Adresse"):
        akt.installer_laden({**info, "url": "https://example.com/knowlin-ai/knowlin/releases/download/x.exe"})
    with pytest.raises(A.UpdateFehler, match="Prüfsumme"):
        akt.installer_laden({**info, "sha256": ""})


def test_befehle(tmp_path):
    akt = A.Aktualisierer(tmp_path)
    cmd = akt.installer_befehl(tmp_path / "Knowlin-Setup-99.0.0.exe", pid=4242)
    import base64

    skript = base64.b64decode(cmd[-1]).decode("utf-16-le")
    assert cmd[-2] == "-EncodedCommand" and skript == akt.installer_skript(4242)
    assert "Wait-Process -Id 4242" in skript and "/VERYSILENT" in skript and "$env:KN_SETUP" in skript
    # seit 0.38.34: Protokoll und belegte Dateien nicht mehr still scheitern lassen
    assert "update.log" in skript and "/LOG=" in skript and "/FORCECLOSEAPPLICATIONS" in skript and "ExitCode" in skript
    # nur auf den Installer warten, nicht auf das danach gestartete Knowlin (Update-Probe hing sonst endlos)
    assert "WaitForExit()" in skript and "-Wait " not in skript
    assert akt.paket_befehl("1.2.3")[-1] == "knowlin==1.2.3"
    with pytest.raises(A.UpdateFehler):
        akt.paket_befehl("1.2.3; rm -rf /")


def test_installart(tmp_path):
    prog = tmp_path / "Programs" / "Knowlin"
    (prog / "python").mkdir(parents=True)
    (prog / "unins000.exe").write_bytes(b"")
    assert A.installart(prog / "python" / "pythonw.exe") == "installer"
    projekt = tmp_path / "repo"
    (projekt / "duckpilot").mkdir(parents=True)
    (projekt / "start.bat").write_text("")
    assert A.installart(tmp_path / "venv" / "python.exe", projekt / "duckpilot") == "quelle"
    site = tmp_path / "site-packages"
    (site / "duckpilot").mkdir(parents=True)
    assert A.installart(tmp_path / "venv" / "python.exe", site / "duckpilot") == "paket"


def test_route_nur_am_pc_nie_mit_echtem_roboter(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.remote import pc_only
    from duckpilot.server.app import Runtime, create_app

    assert pc_only("POST", "/api/update/installieren") and pc_only("POST", "/api/update/pruefen")
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    rt.aktualisierer._lesen = lambda url, limit=0: json.dumps(_release()).encode()
    rt.aktualisierer.art = "installer"
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        h = {"origin": "http://127.0.0.1:8765"}
        assert c.get("/api/update").json()["neu"] is None
        r = c.post("/api/update/pruefen", headers=h).json()
        assert r["ok"] and r["neu"]["version"] == "99.0.0" and r["kann"]
        assert rt.quit_message()["online"]["neu"]["version"] == "99.0.0"
        r = c.post("/api/update/installieren", headers=h)
        assert r.status_code == 400 and "Programmfenster" in r.json()["fehler"]     # Konsole: nichts beenden
        rt.config.backend = "robotd"
        r = c.post("/api/update/installieren", headers=h)
        assert r.status_code == 409 and "echten Roboter" in r.json()["fehler"]


def test_letztes_update_aus_dem_protokoll(tmp_path):
    akt = A.Aktualisierer(tmp_path)
    assert akt.status()["letztes_update"] is None
    (tmp_path / "updates").mkdir()
    (tmp_path / "updates" / "update.log").write_text("2026-11-09T00:01:00 starte Knowlin-Setup-0.38.34.exe\n"
                                                     "2026-11-09T00:02:10 fertig, Code 0\n", encoding="utf-8")
    assert akt.status()["letztes_update"] == "am 09.11.2026 um 00:02 ohne Fehler installiert"   # in Worten (seit 0.38.43)


def test_koerper_wechseln_vom_handy_nur_im_simulator(tmp_path, monkeypatch):
    """Gemeldet nach 0.38.33: Vom Handy ließ sich nur die zuletzt aktive Verkörperung wecken, kein anderer Körper."""
    from fastapi.testclient import TestClient

    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.remote import pc_only
    from duckpilot.server.app import Runtime, create_app

    assert not pc_only("POST", "/api/koerper/wechseln")
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        h = {"origin": "http://127.0.0.1:8765"}
        assert c.post("/api/koerper/wechseln", json={"modul": "gibtsnicht"}, headers=h).status_code == 400
        r = c.post("/api/koerper/wechseln", json={"modul": "open_duck_mini"}, headers=h).json()
        assert r["ok"] and rt.config.modul == "open_duck_mini" and rt.config.backend == "sim"
        rt.config.backend = "robotd"
        r = c.post("/api/koerper/wechseln", json={"modul": "duckpilot"}, headers=h)
        assert r.status_code == 409 and "echten Roboter" in r.json()["fehler"]


def test_herunterladen_meldet_fortschritt_und_pruefen(tmp_path):
    """Seit 0.38.38 (Hinweis: „man sieht immer nicht, was gerade passiert oder ob es hängt“): Das Herunterladen
    meldet geladene und gesamte Bytes, danach den Schritt „prüfen“; ein Fehler steht ebenfalls im Fortschritt."""
    daten = b"x" * 1000
    info = A.auswerten(_release(daten=daten))["installer"]
    gesehen = []

    def laden(url, limit, melden=None):
        for n in (250, 500, 1000):
            melden(n, 1000)
            gesehen.append(dict(akt.fortschritt))
        return daten

    akt = A.Aktualisierer(tmp_path, laden=laden)
    assert akt.fortschritt["schritt"] is None
    akt.installer_laden(info)
    assert [(g["schritt"], g["geladen"], g["gesamt"]) for g in gesehen] == [("laden", 250, 1000), ("laden", 500, 1000),
                                                                         ("laden", 1000, 1000)]
    assert akt.fortschritt["schritt"] == "pruefen"


def test_laden_in_stuecken_mit_groessenangabe(monkeypatch):
    """Der echte Download liest in Stücken und meldet nach jedem Stück (Content-Length als Gesamtgröße)."""
    import io

    class Antwort(io.BytesIO):
        headers = {"Content-Length": str(600 * 1024)}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(A.urllib.request, "urlopen", lambda req, timeout=0: Antwort(b"a" * 600 * 1024))
    meldungen = []
    roh = A._laden("https://github.com/knowlin-ai/knowlin/releases/download/v1/x.exe", A.MAX_BYTES,
                   lambda n, g: meldungen.append((n, g)))
    assert len(roh) == 600 * 1024
    assert meldungen == [(256 * 1024, 600 * 1024), (512 * 1024, 600 * 1024), (600 * 1024, 600 * 1024)]


def test_fortschritt_route(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        assert c.get("/api/update/fortschritt").json() == {"ok": True, "laeuft": False, "schritt": None}
        rt.aktualisierer.melden("laden", geladen=5, gesamt=10)
        r = c.get("/api/update/fortschritt").json()
        assert r["schritt"] == "laden" and r["geladen"] == 5 and r["gesamt"] == 10


def test_installer_noch_im_bau_bald_wieder_nachsehen(tmp_path, monkeypatch):
    """Maintainer 12.11.: „wenn das Update noch nicht ganz abrufbereit ist“ – das Release steht, der Installer wird noch
    gebaut. Dann nicht erst morgen wieder fragen, sondern nach einer Viertelstunde."""
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    akt = A.Aktualisierer(tmp_path, lesen=lambda url, limit=0: json.dumps(_release(mit_installer=False)).encode())
    akt.art = "installer"
    st = akt.pruefen()
    assert st["neu"]["installer"] is None and not st["kann"]
    alter = json.loads((tmp_path / "update.json").read_text(encoding="utf-8"))["zeit_s"]
    import time
    assert A.TAG_S - A.BALD_S - 5 <= time.time() - alter <= A.TAG_S - A.BALD_S + 5


def test_letztes_update_in_worten(tmp_path):
    """Maintainer 12.11.: „fertig, Code 0 – wieso Code 0?“ – Code 0 heißt „ohne Fehler“; das steht jetzt so da."""
    assert A.update_in_worten("2026-11-11T22:41:16 fertig, Code 0") == "am 11.11.2026 um 22:41 ohne Fehler installiert"
    assert "mit Fehler beendet (Code 5" in A.update_in_worten("2026-11-11T22:41:16 fertig, Code 5")
    (tmp_path / "updates").mkdir()
    (tmp_path / "updates" / "update.log").write_text("2026-11-11T22:40:01 Installer gestartet\n"
                                                     "2026-11-11T22:41:16 fertig, Code 0\n", encoding="utf-8")
    assert A.Aktualisierer(tmp_path).letztes_update() == "am 11.11.2026 um 22:41 ohne Fehler installiert"


def test_hoechste_version_gewinnt_nicht_das_zuletzt_angelegte_release():
    # Fund 12.11.: 0.38.47 wurde nach 0.38.48 angelegt – GitHub nannte 0.38.47 „latest“
    from duckpilot.aktualisieren import neuestes

    liste = [{"tag_name": "v0.38.47", "assets": []}, {"tag_name": "v0.38.48", "assets": []},
             {"tag_name": "v0.39.0", "draft": True}, {"tag_name": "v0.40.0", "prerelease": True}, {"tag_name": "x"}]
    assert neuestes(liste)["version"] == "0.38.48"
    assert neuestes({"tag_name": "v0.38.46"})["version"] == "0.38.46"          # einzelnes Release geht weiter
    assert neuestes([]) is None
