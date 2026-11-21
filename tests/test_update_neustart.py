"""0.49.1: nach dem In-App-Update – Start in der Zwischenzeit, Startbeobachter, Installer, 3D-Wache."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from urllib.parse import unquote

from duckpilot import aktualisieren as AK
from duckpilot import startstatus as SS

ROOT = Path(__file__).resolve().parents[1]


def test_update_merker_laeuft_ab_und_wird_vergessen(tmp_path):
    assert AK.update_laeuft(tmp_path) is None
    AK.update_merken(tmp_path, "0.49.1")
    assert AK.update_laeuft(tmp_path) == "0.49.1"
    assert AK.update_laeuft(tmp_path, jetzt=time.time() + AK.MERKER_S + 1) is None      # alter Merker zählt nicht
    AK.update_vergessen(tmp_path)
    assert AK.update_laeuft(tmp_path) is None
    (tmp_path / "updates" / AK.MERKER).write_text("kaputt", encoding="utf-8")
    assert AK.update_laeuft(tmp_path) is None


def test_warteseite_geht_zu_knowlin_sobald_es_antwortet():
    s = AK.warteseite("http://127.0.0.1:8765", "0.49.1<x>")
    assert s.startswith("data:text/html")
    text = unquote(s)
    assert "0.49.1&lt;x&gt;" in text and "/api/ping" in text and "location.href=u" in text


def test_start_waehrend_des_updates_startet_nicht_die_alte_fassung():
    quelle = (ROOT / "duckpilot" / "__main__.py").read_text(encoding="utf-8")
    assert "AK.update_laeuft(S.data_dir())" in quelle and "AK.update_vergessen(S.data_dir())" in quelle
    route = (ROOT / "duckpilot" / "server" / "routes" / "aktualisieren.py").read_text(encoding="utf-8")
    assert route.index("update_merken(") < route.index("installer_starten, setup")


def test_installer_startet_geschlossene_programme_nicht_neu():
    iss = (ROOT / "tools" / "installer" / "knowlin.iss").read_text(encoding="utf-8")
    assert "RestartApplications=no" in iss


def test_startbeobachter_nennt_den_teil_und_die_stelle():
    assert SS.teil_von("voice/speech.py") == "Stimme"
    assert SS.teil_von("physics/lernen.py") == "Physik"
    assert SS.teil_von("server/runtime.py") == "Programmteile"
    st = SS.StartStatus("0.49.1")
    los, fertig = threading.Event(), threading.Event()

    def arbeiten():
        los.set()
        fertig.wait(3)

    t = threading.Thread(target=arbeiten)
    t.start()
    los.wait(1)
    stelle = SS.startstelle(sys._current_frames()[t.ident])
    fertig.set()
    t.join()
    assert stelle and stelle[2] in ("wait", "arbeiten")
    assert "teil" in st.stand()


def test_3d_wache_fuer_verlorenen_webgl_kontext():
    js = (ROOT / "duckpilot" / "server" / "static" / "webgl_wache.js").read_text(encoding="utf-8")
    assert "webglcontextlost" in js and "preventDefault" in js and "webglcontextrestored" in js
    assert "initWebglWache(" in (ROOT / "duckpilot" / "server" / "static" / "app.js").read_text(encoding="utf-8")
