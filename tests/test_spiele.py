"""Kamera-Spiele mit Reachy Mini (seit 0.38.13, ausgebaut 0.38.14): Ampel, Hand folgen, Mach mir nach, Schere-Stein-Papier.

Geprüft: nur mit Reachy als Körper, Blickziele begrenzt und über die Engine umgesetzt, Not-Aus beendet sofort (auch
eine laufende Vorführung) und sperrt so lange wie die Engine sagt, nur am PC – und die Oberfläche schickt nie Bilder,
nur Zahlen und Wörter. Die Handerkennung lädt nur auf Klick, mit Prüfsummen (hier mit Ersatzdateien, ohne Netz), und
kommt vom eigenen Server. Bilddifferenz und Handpunkte rechnet der Browser; ihre reinen Funktionen prüft node.
"""

import asyncio
import hashlib
import io
import json
import math
import random
import re
import shutil
import subprocess
import tarfile
import time
from pathlib import Path

import pytest
from helpers import run_for
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot import remote as R
from duckpilot.backends.reachy import ReachyMiniSim
from duckpilot.motion.engine import EngineConfig, MotionEngine
from duckpilot.motion.reachy_spiel import KOERPER_MAX, KOPF_PITCH_MAX, KOPF_YAW_MAX, NUR_KOPF, SpielHaltung, aufteilen
from duckpilot.server.routes import spiele as SP

STATIC = Path(__file__).resolve().parent.parent / "duckpilot" / "server" / "static"


# ── Bewegung (Motorik) ─────────────────────────────────────────────────
def test_aufteilen_kleine_winkel_nur_kopf_grosse_mit_koerper():
    assert aufteilen(math.radians(20)) == 0.0
    assert aufteilen(math.radians(-70)) == pytest.approx(math.radians(-40))
    assert aufteilen(math.radians(400)) == pytest.approx(KOERPER_MAX)


def test_spielhaltung_dreht_koerper_und_kopf_und_endet_ohne_ziele():
    async def go():
        sim = ReachyMiniSim(realtime=False, seed=1)
        sim._task = object()
        eng = MotionEngine(sim, EngineConfig(seed=1))
        await eng.stand_up()
        await run_for(sim, eng, 2.5)
        h = SpielHaltung("ampel", frist_s=5.0)
        eng.run(h)
        h.setze(math.radians(180), 0.0, koerper=math.radians(150))     # grünes Licht: weggedreht
        await run_for(sim, eng, 4.0)
        weg = dict(sim.state().kopf_lage)
        h.setze(math.radians(-70), math.radians(60))                    # Hand folgen: groß nach rechts, Nicken begrenzt
        await run_for(sim, eng, 4.8)                                    # einmal ganz herum (≈ 190°)
        rechts = dict(sim.state().kopf_lage)
        await run_for(sim, eng, 2.0)                                    # keine neuen Ziele mehr → Frist
        return weg, rechts, h, eng
    weg, rechts, h, eng = asyncio.run(go())
    assert math.degrees(weg["koerper"]) > 140 and abs(math.degrees(weg["yaw"]) - 30) < 5
    assert math.degrees(rechts["koerper"]) == pytest.approx(-40, abs=4) and rechts["yaw"] < 0
    assert abs(rechts["yaw"]) <= KOPF_YAW_MAX + 0.01 and h.pitch == pytest.approx(KOPF_PITCH_MAX)
    assert h.done and "keine Ziele" in h.result and eng.current is None
    assert math.radians(30) == NUR_KOPF


# ── Server ─────────────────────────────────────────────────────────────
@pytest.fixture()
def reachy_rt(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    gesendet = []
    echt = rt.broadcast

    async def mitschreiben(msg):
        gesendet.append(msg)
        await echt(msg)
    rt.broadcast = mitschreiben
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        yield rt, c, gesendet


def rt_daten(rt):
    from duckpilot import settings as S

    return S.settings_path().parent


def _wach(rt, c):
    c.portal.call(rt.koerper_betreten)
    ende = time.monotonic() + 8
    while time.monotonic() < ende:
        st = rt.backend.state()
        if st.powered and not st.sitting:
            return
        time.sleep(0.1)
    raise AssertionError("Reachy wacht nicht auf")


def test_ohne_reachy_lehnt_der_server_ab(reachy_rt):
    rt, c, _ = reachy_rt
    r = c.post("/api/spiele/start", json={"art": "folgen"})
    assert r.status_code == 409 and "Reachy" in r.json()["fehler"]
    assert c.post("/api/spiele/blick", json={"yaw": 10}).status_code == 409
    assert c.post("/api/spiele/ampel", json={"phase": "gruen"}).status_code == 409
    s = c.get("/api/spiele").json()
    assert s["aktiv"] is False and s["laeuft"] is None


def test_blickziel_wird_begrenzt_und_umgesetzt_not_aus_stoppt(reachy_rt):
    rt, c, gesendet = reachy_rt
    assert c.post("/api/settings", json={"modul": "reachy_mini", "backend": "sim", "sim_physik": False}).json()["ok"]
    assert isinstance(rt.backend, ReachyMiniSim)
    _wach(rt, c)
    assert c.post("/api/spiele/start", json={"art": "unsinn"}).status_code == 409
    r = c.post("/api/spiele/start", json={"art": "folgen"}).json()
    assert r["ok"] and c.get("/api/spiele").json()["laeuft"] == "folgen"
    assert c.post("/api/spiele/ampel", json={"phase": "rot"}).status_code == 409        # falsches Spiel
    r = c.post("/api/spiele/blick", json={"yaw": 500, "pitch": -80, "staerke": 3}).json()
    assert r["ok"] and r["yaw"] == 90 and r["pitch"] == pytest.approx(-math.degrees(KOPF_PITCH_MAX), abs=0.1)
    assert r["koerper"] == pytest.approx(60, abs=0.1)                                  # 90° = 30° Kopf + 60° Körper
    time.sleep(0.1)
    for _ in range(25):                                                                 # ≈ 8 Ziele je Sekunde, 3 s lang
        assert c.post("/api/spiele/blick", json={"yaw": 80, "pitch": 0, "staerke": 0.5}).json()["ok"]
        time.sleep(0.12)
    lage = rt.backend.state().kopf_lage
    assert math.degrees(lage["koerper"]) > 30 and lage["yaw"] > 0.2                     # Körper und Kopf nach links
    assert rt.engine.current is rt.spiele.haltung

    c.portal.call(rt.handle_client_message, {"type": "stop"})                          # Not-Aus
    assert rt.engine.current is None
    time.sleep(0.1)
    assert any(m.get("type") == "spiel" and m.get("notaus") and m.get("laeuft") is None for m in gesendet)
    r = c.post("/api/spiele/blick", json={"yaw": 10})
    assert r.status_code == 409 and r.json()["laeuft"] is None
    r = c.post("/api/spiele/start", json={"art": "ampel"})                              # 120 s Sperre gilt auch hier
    assert r.status_code == 409 and "Not-Aus" in r.json()["fehler"]


def test_ampel_dreht_weg_und_um_und_spricht_ohne_entenlaute(reachy_rt):
    rt, c, gesendet = reachy_rt
    c.post("/api/settings", json={"modul": "reachy_mini", "backend": "sim", "sim_physik": False})
    _wach(rt, c)
    r = c.post("/api/spiele/start", json={"art": "ampel", "stufe": "schwer"}).json()
    assert r["ok"] and r["stufe"] == "schwer" and r["simulator"] is True                  # ohne Roboter: Simulator
    r = c.post("/api/spiele/ampel", json={"phase": "gruen"}).json()
    assert r["ok"] and abs(rt.spiele.haltung.koerper_ziel) == pytest.approx(KOERPER_MAX) and r["punkte"] == 0
    r = c.post("/api/spiele/ampel", json={"phase": "rot"}).json()
    assert r["ok"] and r["runde"] == 1 and rt.spiele.haltung.koerper_ziel == 0 and r["dreh_s"] > 0
    r = c.post("/api/spiele/ampel", json={"phase": "gruen"}).json()                     # rotes Licht überstanden
    assert r["ueberlebt"] and r["punkte"] == 30                                          # 10 × Stufe „schwer“
    c.post("/api/spiele/ampel", json={"phase": "rot"})
    r = c.post("/api/spiele/ampel", json={"phase": "erwischt"}).json()
    assert r["ok"] and r["runde"] == 0 and rt.engine.overlay is not None and r["punkte"] == 30   # Geste läuft
    r = c.post("/api/spiele/ampel", json={"phase": "geschafft"}).json()
    assert r["ok"] and r["zeit_s"] >= 0 and r["neue_bestzeit"] is True and r["bestzeit_s"] == r["zeit_s"]
    assert r["punkte"] >= 30 + 80 * 3                                                    # Zeitbonus × Stufe
    saetze = [m["text"] for m in gesendet if m.get("type") == "chat" and m.get("source") == "spiel"]
    assert saetze[0] in SP.SAETZE["gruen"] and saetze[1] in SP.SAETZE["rot"]
    assert any(saetze[2] == f"{u} {g}" for u in SP.SAETZE["ueberlebt"] for g in SP.SAETZE["gruen"])
    assert saetze[4] in SP.SAETZE["erwischt"] and "Neue Bestzeit" in saetze[5]
    assert not any("quak" in s.lower() for s in saetze)
    assert c.post("/api/spiele/stopp").json()["ok"] and rt.engine.current is None
    s = c.get("/api/spiele").json()
    assert s["laeuft"] is None and s["bestwerte"]["ampel"]["schwer"]["bestzeit_s"] == r["zeit_s"]
    gespeichert = json.loads((rt_daten(rt) / "spiele.json").read_text(encoding="utf-8"))
    assert set(gespeichert["ampel"]["schwer"]) == {"bestzeit_s", "punkte"}               # nur Zahlen, keine Bilder
    # nächste Runde langsamer: Bestzeit bleibt
    assert c.post("/api/spiele/start", json={"art": "ampel", "stufe": "schwer"}).json()["bestwerte"]["schwer"]
    rt.spiele.t_start = time.monotonic() - 500
    r = c.post("/api/spiele/ampel", json={"phase": "geschafft"}).json()
    assert r["neue_bestzeit"] is False and r["bestzeit_s"] < r["zeit_s"]
    c.post("/api/spiele/stopp")


def test_mach_mir_nach_folge_punkte_leben_und_rekord(reachy_rt):
    rt, c, gesendet = reachy_rt
    c.post("/api/settings", json={"modul": "reachy_mini", "backend": "sim", "sim_physik": False})
    _wach(rt, c)
    assert c.post("/api/spiele/spiegel", json={"aktion": "zeigen"}).status_code == 409             # läuft nicht
    assert c.post("/api/spiele/start", json={"art": "spiegel", "stufe": "leicht"}).json()["ok"]
    assert c.post("/api/spiele/spiegel", json={"aktion": "antwort", "richtung": "links"}).status_code == 409  # erst zeigen
    r = c.post("/api/spiele/spiegel", json={"aktion": "zeigen"}).json()
    assert r["ok"] and len(r["folge"]) == 1 and r["leben"] == 3 and r["schritt_s"] == SP.SPIEGEL_SCHRITT_S["leicht"]
    erste = r["folge"][0]
    time.sleep(0.4)                                                    # Reachy macht vor: Kopf in die Richtung
    h = rt.spiele.haltung
    soll = SP.RICHTUNGEN[erste]
    assert h.blick_yaw == pytest.approx(math.radians(soll["yaw"])) and h.pitch == pytest.approx(math.radians(soll["pitch"]))
    assert h.koerper_ziel == 0
    a = c.post("/api/spiele/spiegel", json={"aktion": "antwort", "richtung": erste}).json()
    assert a["richtig"] and a["fertig"] and a["runde"] == 1 and a["punkte"] == 15
    r = c.post("/api/spiele/spiegel", json={"aktion": "zeigen"}).json()
    folge = r["folge"]
    falsch = next(x for x in SP.RICHTUNGEN if x != folge[0])
    a = c.post("/api/spiele/spiegel", json={"aktion": "antwort", "richtung": falsch}).json()
    assert a["ok"] and not a["richtig"] and a["erwartet"] == folge[0] and a["leben"] == 2
    assert c.post("/api/spiele/spiegel", json={"aktion": "zeigen"}).json()["folge"] == folge       # dieselbe noch mal
    a = c.post("/api/spiele/spiegel", json={"aktion": "antwort", "richtung": "keine"}).json()       # zu langsam
    assert not a["richtig"] and a["leben"] == 1
    c.post("/api/spiele/spiegel", json={"aktion": "zeigen"})
    a = c.post("/api/spiele/spiegel", json={"aktion": "antwort", "richtung": falsch}).json()
    assert a["vorbei"] and a["gewonnen"] is False and a["bestpunkte"] == 15 and a["neuer_rekord"] is True
    saetze = [m["text"] for m in gesendet if m.get("type") == "chat" and m.get("source") == "spiel"]
    assert saetze[0] in SP.SPIEGEL_SAETZE["start"] and any("15 Punkte" in s for s in saetze)
    assert json.loads((rt_daten(rt) / "spiele.json").read_text(encoding="utf-8"))["spiegel"]["leicht"] == {"punkte": 15}
    c.post("/api/spiele/stopp")
    # Mittel: wie ein Merkspiel – die alte Folge plus eine neue Bewegung
    assert c.post("/api/spiele/start", json={"art": "spiegel", "stufe": "mittel"}).json()["ok"]
    f1 = c.post("/api/spiele/spiegel", json={"aktion": "zeigen"}).json()["folge"]
    assert c.post("/api/spiele/spiegel", json={"aktion": "antwort", "richtung": f1[0]}).json()["fertig"]
    f2 = c.post("/api/spiele/spiegel", json={"aktion": "zeigen"}).json()["folge"]
    assert len(f2) == 2 and f2[0] == f1[0] and f2[1] != f2[0]
    c.post("/api/spiele/stopp")


def test_schere_stein_papier_nur_mit_handerkennung(reachy_rt, monkeypatch):
    rt, c, gesendet = reachy_rt
    c.post("/api/settings", json={"modul": "reachy_mini", "backend": "sim", "sim_physik": False})
    _wach(rt, c)
    r = c.post("/api/spiele/start", json={"art": "ssp"})
    assert r.status_code == 409 and "Handerkennung" in r.json()["fehler"]                # ohne Modell kein Spiel

    class Bereit:
        def bereit(self):
            return True
    monkeypatch.setattr(rt, "hand", Bereit())
    echt = random.choice
    monkeypatch.setattr(SP.random, "choice", lambda seq: "schere" if tuple(seq) == SP.SSP else echt(seq))
    assert c.post("/api/spiele/start", json={"art": "ssp"}).json()["ok"]
    z = c.post("/api/spiele/ssp", json={"aktion": "zaehlen"}).json()
    assert z["ok"] and z["zaehl_s"] == SP.SSP_ZAEHL_S
    u = c.post("/api/spiele/ssp", json={"aktion": "zug", "geste": "unklar"}).json()
    assert u["ok"] and u["unklar"] and u["stand"] == {"mensch": 0, "reachy": 0}
    for i in range(3):
        r = c.post("/api/spiele/ssp", json={"aktion": "zug", "geste": "stein"}).json()
        assert r["reachy"] == "schere" and r["sieger"] == "mensch" and r["stand"]["mensch"] == i + 1
        assert "Stein schleift die Schere" in r["satz"]
    assert r["vorbei"] and r["gewonnen"] and r["siege"] == 1
    assert rt.spiele.haltung is None or rt.spiele.haltung.pitch == pytest.approx(0.0)
    r = c.post("/api/spiele/ssp", json={"aktion": "zug", "geste": "schere"}).json()
    assert r["sieger"] == "gleich" and r["stand"] == {"mensch": 0, "reachy": 0}          # Revanche bei null
    saetze = [m["text"] for m in gesendet if m.get("type") == "chat" and m.get("source") == "spiel"]
    assert "Schnick, Schnack, Schnuck!" in saetze and not any("quak" in s.lower() for s in saetze)
    c.post("/api/spiele/stopp")
    assert json.loads((rt_daten(rt) / "spiele.json").read_text(encoding="utf-8"))["ssp"]["alle"] == {"siege": 1}


def test_saetze_ohne_stopp_und_ohne_entenlaute():
    """Reachy sagt nie „Stopp“ (das Mikrofon würde es als Not-Aus hören) und quakt nicht."""
    for tabelle in (SP.SAETZE, SP.SPIEGEL_SAETZE, SP.SSP_SAETZE):
        for liste in tabelle.values():
            assert len(liste) >= 2                                              # Abwechslung
            for satz in liste:
                assert "stopp" not in satz.lower() and "quak" not in satz.lower(), satz


def test_not_aus_beendet_vorfuehrung_und_sperre_aus_der_engine(reachy_rt):
    rt, c, _ = reachy_rt
    c.post("/api/settings", json={"modul": "reachy_mini", "backend": "sim", "sim_physik": False})
    _wach(rt, c)
    assert c.post("/api/spiele/start", json={"art": "spiegel", "stufe": "schwer"}).json()["ok"]
    h = rt.spiele.haltung
    aufrufe = []
    echt = h.setze
    h.setze = lambda *a, **k: (aufrufe.append(time.monotonic()), echt(*a, **k))[1]
    r = c.post("/api/spiele/spiegel", json={"aktion": "zeigen"}).json()
    assert len(r["folge"]) == 2
    time.sleep(0.2)
    rt.engine.config.notaus_sperre_s = 300                                       # länger eingestellt (nie kürzer)
    c.portal.call(rt.handle_client_message, {"type": "stop"})                   # Not-Aus mitten im Vormachen
    stopp = time.monotonic()
    time.sleep(2.5)
    assert not [t for t in aufrufe if t > stopp + 0.05]                          # Reachy bewegt sich nicht weiter
    assert rt.engine.current is None and rt.spiele.laeuft() is None
    assert c.post("/api/spiele/spiegel", json={"aktion": "antwort", "richtung": "links"}).status_code == 409
    r = c.post("/api/spiele/start", json={"art": "folgen"})
    assert r.status_code == 409 and "Not-Aus" in r.json()["fehler"] and "5 Minuten" in r.json()["fehler"]


def test_kamera_spiele_nur_am_pc():
    for methode, pfad in (("POST", "/api/spiele/start"), ("POST", "/api/spiele/blick"), ("GET", "/api/spiele"),
                          ("POST", "/api/spiele/spiegel"), ("POST", "/api/spiele/ssp"), ("GET", "/api/spiele/hand"),
                          ("POST", "/api/spiele/hand/laden"), ("GET", "/api/spiele/hand/dateien/hand_landmarker.task")):
        assert R.pc_only(methode, pfad), pfad


# ── Handerkennung: nur auf Klick, Prüfsummen, vom eigenen Server ──────
def _falsche_quellen(monkeypatch, tmp_path, boese_im_paket=True):
    """Ersatz-Laufzeit (Tarball) und Ersatz-Modell mit eigenen Prüfsummen – ohne Netz."""
    from duckpilot.modell import hand as H

    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    inhalt = {name: f"// {name}\n".encode() * (i + 3) for i, name in enumerate(H.LAUFZEIT["dateien"])}
    puffer = io.BytesIO()
    with tarfile.open(fileobj=puffer, mode="w:gz") as tar:
        def dazu(pfad, daten):
            info = tarfile.TarInfo(pfad)
            info.size = len(daten)
            tar.addfile(info, io.BytesIO(daten))
        for name, daten in inhalt.items():
            dazu(H.LAUFZEIT["dateien"][name]["im_paket"], daten)
        if boese_im_paket:
            dazu("../../boese.txt", b"nie entpacken")
            dazu("package/extra.js", b"nie entpacken")
    tgz = puffer.getvalue()
    modell = b"MODELL" * 100
    sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    laufzeit = {**H.LAUFZEIT, "sha256": sha(tgz), "bytes": len(tgz), "dateien": {
        n: {**H.LAUFZEIT["dateien"][n], "sha256": sha(d), "bytes": len(d)} for n, d in inhalt.items()}}
    mod = {**H.MODELL, "sha256": sha(modell), "bytes": len(modell)}
    monkeypatch.setattr(H, "LAUFZEIT", laufzeit)
    monkeypatch.setattr(H, "MODELL", mod)
    monkeypatch.setattr(H, "DATEIEN", {**{n: {"sha256": m["sha256"], "bytes": m["bytes"]} for n, m in laufzeit["dateien"].items()},
                                       mod["datei"]: {"sha256": mod["sha256"], "bytes": mod["bytes"]}})
    abrufe = []

    def holen(url, max_bytes, fortschritt=None):
        abrufe.append(url)
        daten = tgz if url == laufzeit["url"] else modell if url == mod["url"] else b""
        assert len(daten) <= max_bytes
        if fortschritt:
            fortschritt(len(daten))
        return daten
    return H, holen, abrufe, inhalt, modell


def test_handerkennung_quellen_fest_und_mit_pruefsumme():
    from duckpilot.modell import hand as H

    assert H.LAUFZEIT["url"].startswith("https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-0.10.21.tgz")
    assert H.MODELL["url"].startswith("https://storage.googleapis.com/mediapipe-models/hand_landmarker/")
    assert "/float16/1/" in H.MODELL["url"] and "latest" not in H.MODELL["url"]
    assert H.QUELLEN["lizenz"] == "Apache-2.0"
    for meta in [*H.LAUFZEIT["dateien"].values(), H.MODELL, H.LAUFZEIT]:
        assert re.fullmatch(r"[0-9a-f]{64}", meta["sha256"]) and meta["bytes"] > 0
    assert set(H.DATEIEN) == {"vision_bundle.mjs", "vision_wasm_internal.js", "vision_wasm_internal.wasm",
                              "vision_wasm_nosimd_internal.js", "vision_wasm_nosimd_internal.wasm", "hand_landmarker.task"}
    assert H.medientyp("vision_wasm_internal.wasm") == "application/wasm" and H.medientyp("x.mjs") == "text/javascript"
    assert 10 < H.DOWNLOAD_BYTES / 1e6 < 20                                         # „≈ 14 MB“ steht auf dem Knopf
    notice = (Path(__file__).resolve().parent.parent / "NOTICE").read_text(encoding="utf-8")
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for text in (notice, readme, html):
        assert "MediaPipe Hand Landmarker" in text and "0.10.21" in text


def test_handerkennung_laedt_prueft_und_entpackt_nur_bekanntes(tmp_path, monkeypatch):
    H, holen, abrufe, inhalt, modell = _falsche_quellen(monkeypatch, tmp_path)
    st = H.HandStore(tmp_path, fetch=holen)
    assert not st.bereit() and st.datei("hand_landmarker.task") is None and not abrufe
    meldungen = []
    assert st.ensure(meldungen.append) == {"geladen": ["laufzeit", "modell"]}
    assert st.bereit() and any("%" in m for m in meldungen)
    assert sorted(p.name for p in st.dir.iterdir()) == sorted([*H.DATEIEN, "geladen.txt"])  # nur die bekannten Dateien
    assert not (tmp_path / "boese.txt").exists() and not (tmp_path.parent / "boese.txt").exists()
    assert st.datei("vision_bundle.mjs").read_bytes() == inhalt["vision_bundle.mjs"]
    assert st.datei("../settings.json") is None and st.datei("geladen.txt") is None
    assert st.ensure() == {"geladen": []} and len(abrufe) == 2                     # schon da: nichts laden
    # Jemand ändert eine Datei (gleiche Größe): nicht mehr bereit, nichts wird ausgeliefert
    pfad = st.dir / "hand_landmarker.task"
    pfad.write_bytes(b"X" * len(modell))
    assert not st.bereit() and st.datei("hand_landmarker.task") is None
    assert st.ensure() == {"geladen": ["modell"]} and st.bereit()                  # nur das Modell neu


def test_handerkennung_falsche_pruefsumme_speichert_nichts(tmp_path, monkeypatch):
    H, holen, _, _, _ = _falsche_quellen(monkeypatch, tmp_path)

    def kaputt(url, max_bytes, fortschritt=None):
        daten = holen(url, max_bytes, fortschritt)
        return daten[:-1] + bytes([daten[-1] ^ 1])
    st = H.HandStore(tmp_path, fetch=kaputt)
    with pytest.raises(ValueError, match="Prüfsumme"):
        st.ensure()
    assert not st.dir.exists() or not any(st.dir.iterdir())
    monkeypatch.setenv("DUCKPILOT_OFFLINE", "1")
    with pytest.raises(RuntimeError, match="Offline"):
        H.HandStore(tmp_path, fetch=holen).ensure()


def test_handerkennung_nur_auf_klick_und_vom_eigenen_server(reachy_rt, monkeypatch, tmp_path):
    rt, c, _ = reachy_rt
    H, holen, abrufe, inhalt, modell = _falsche_quellen(monkeypatch, tmp_path)
    rt.hand.fetch = holen
    s = c.get("/api/spiele/hand").json()
    assert s["bereit"] is False and not s["job"] and s["lizenz"] == "Apache-2.0" and not abrufe   # Start lädt nichts
    assert c.get("/api/spiele/hand/dateien/hand_landmarker.task").status_code == 404
    assert c.post("/api/spiele/hand/laden").json()["ok"]                       # der Klick
    ende = time.monotonic() + 10
    while time.monotonic() < ende and c.get("/api/spiele/hand").json()["job"].get("laeuft"):
        time.sleep(0.05)
    s = c.get("/api/spiele/hand").json()
    assert s["bereit"] is True and s["job"]["fehler"] is None and len(abrufe) == 2
    r = c.get("/api/spiele/hand/dateien/vision_wasm_internal.wasm")
    assert r.status_code == 200 and r.headers["content-type"] == "application/wasm"
    assert r.content == inhalt["vision_wasm_internal.wasm"]
    r = c.get("/api/spiele/hand/dateien/vision_bundle.mjs")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/javascript")
    assert c.get("/api/spiele/hand/dateien/hand_landmarker.task").content == modell
    for boese in ("..%2Fspiele.json", "geladen.txt", "settings.json", "%2E%2E"):
        assert c.get(f"/api/spiele/hand/dateien/{boese}").status_code == 404, boese
    monkeypatch.setenv("DUCKPILOT_OFFLINE", "1")
    r = c.post("/api/spiele/hand/laden")
    assert r.status_code == 409 and "Offline" in r.json()["fehler"]


# ── Oberfläche ─────────────────────────────────────────────────────────
SPIEL_JS = ("kamera_spiele.js", "spiele_runden.js", "hand.js")
SPIEL_PFADE = {"/api/spiele", "/api/spiele/start", "/api/spiele/stopp", "/api/spiele/blick", "/api/spiele/ampel",
               "/api/spiele/spiegel", "/api/spiele/ssp", "/api/spiele/hand", "/api/spiele/hand/laden",
               "/api/spiele/hand/dateien"}


def _code(name):
    return re.sub(r"//[^\n]*", "", (STATIC / name).read_text(encoding="utf-8"))


def test_oberflaeche_schickt_keine_bilder():
    """Bilder bleiben im Browser: kein Hochladen, kein Speichern, nur die Spiel-Endpunkte mit Zahlen und Wörtern."""
    pfade = set()
    for name in SPIEL_JS:
        code = _code(name)
        for verboten in ("toBlob", "toDataURL", "FormData", "fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon",
                         "localStorage", "sessionStorage", "indexedDB", "/api/augen", "send(", "MediaRecorder",
                         "download", "http:", "https:", "cdn", "jsdelivr", "unpkg", "googleapis"):
            assert verboten not in code, (name, verboten)
        pfade |= set(re.findall(r"'(/api/[^'$`]+)'", code))
        for nutzlast in re.findall(r"(?:api|post)\('[^']+', (?:'POST', )?(\{[^}]*\})", code):
            assert not re.search(r"bild|grau|vorher|jetzt\b|data|rgba|canvas|video|punkte|landmark", nutzlast, re.I), nutzlast
    assert pfade == SPIEL_PFADE, pfade ^ SPIEL_PFADE
    kern = _code("kamera_spiele.js")
    assert "isRemote()" in kern and "getTracks()" in kern and "badge-spiel-cam" in kern       # nur am PC, Kamera aus, Hinweis
    # Die Laufzeit kommt nur vom eigenen Server (fester Pfad), geladen wird sie erst im Spiel
    hand = _code("hand.js")
    assert "export const BASIS = '/api/spiele/hand/dateien';" in hand
    assert "await import(`${this.basis}/vision_bundle.mjs`)" in hand and hand.count("import(") == 1
    assert "modelAssetPath: `${this.basis}/hand_landmarker.task`" in hand
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "initKameraSpiele({ $, api, toast, scene," in app and "case 'spiel':" in app and "part: 'spiele'" in app
    assert "hand.js" not in app and "vision_bundle" not in app                                   # nichts beim Start
    assert "'tricks/spiele'" in (STATIC / "modul.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for needle in ('data-part="spiele"', 'id="ks-ampel-start"', 'id="ks-folgen-start"', 'id="badge-spiel-cam"',
                   'role="meter"', 'aria-live="assertive"', 'id="ks-hinweis"', 'id="ks-hand-laden"', 'id="ks-hand-an"',
                   'id="ks-sp-start"', 'id="ks-ssp-start"', 'id="ks-ssp-runde"', 'id="ks-sim-ansicht"', 'id="ks-echt"',
                   'id="ks-stufe"', 'id="ks-ampel-best"', 'id="ks-ssp-braucht"'):
        assert needle in html, needle


def test_handerkennung_laden_nur_auf_klick_im_browser():
    """Der Download startet nur im Klick-Handler; das Modell lädt der Browser erst, wenn ein Spiel es braucht."""
    hand = _code("hand.js")
    klick = hand.index("knopf.addEventListener('click'")
    assert hand.count("'/api/spiele/hand/laden'") == 1 and hand.index("'/api/spiele/hand/laden'") > klick
    kern = _code("kamera_spiele.js")
    assert kern.count("hand.erkenner.laden()") == 1
    start = kern[kern.index("async function starten("):kern.index("function pruefen(")]
    assert "art !== 'ampel' && hand.an()" in start and start.index("hand.erkenner.laden()") < start.index("'/api/spiele/start'")
    # Rückfall ehrlich beschriftet
    assert "Erkennung: Bewegung (ohne Modell)" in kern and "Erkennung: Hand (MediaPipe" in kern


def test_uebergang_zum_simulator_und_not_aus_vorn():
    kern = _code("kamera_spiele.js")
    for needle in ("simulator = !!r.simulator", "box.prepend(scene.canvas)", "scene.paused = false", "scene.anfahren()",
                   "heimat.parent.prepend(scene.canvas)", "scene.paused = heimat.paused", "Reachy spielt am echten Roboter",
                   "prefers-reduced-motion", "buehne(false, war)", "$('stop').addEventListener('click', notAus)",
                   "e.key === 'Escape'", "zeitgeberAus()"):
        assert needle in kern, needle
    d3 = _code("duck3d.js")
    assert "anfahren({" in d3 and "if (REDUCED) {" in d3[d3.index("anfahren({"):]
    css = re.sub(r"/\*.*?\*/", "", (STATIC / "style.css").read_text(encoding="utf-8"), flags=re.S)
    assert ".ks-raster[data-spielt] > .ks-karte:not(.is-aktiv) { display: none; }" in css
    assert re.search(r"prefers-reduced-motion: reduce\)[^\n]*\.ks-raster\[data-spielt\] > \.ks-sim \{ animation: none; \}", css)


NODE_PRUEFUNG = r"""
const m = await import(process.argv[2]);
const hd = await import(process.argv[3]);
const sr = await import(process.argv[4]);
const W = m.BREITE, H = m.HOEHE, n = W * H;
const leer = new Uint8Array(n).fill(100);
const rauschen = leer.map((v, i) => v + (i % 7) - 3);                 // ±3 Grauwerte: kein Bewegen
const links = Uint8Array.from(leer);
for (let y = 10; y < 30; y++) for (let x = 2; x < 14; x++) links[y * W + x] = 220;
const r1 = m.bewegung(leer, rauschen), r2 = m.bewegung(leer, links), r0 = m.bewegung(null, links);
const rgba = new Uint8ClampedArray(n * 4).fill(255);
// Eine gezeichnete Hand (21 Punkte): Handgelenk unten, Finger nach oben; gestreckt = Spitze weit oben
function hand(f, dx = 0, dy = 0) {
  const P = (x, y) => ({ x: x + dx, y: y + dy, z: 0 });
  const lm = new Array(21);
  lm[0] = P(0.5, 0.8);
  lm[1] = P(0.42, 0.75); lm[2] = P(0.38, 0.7); lm[3] = P(0.35, 0.66);
  lm[4] = f[0] ? P(0.30, 0.6) : P(0.46, 0.66);
  [[5, 0.44], [9, 0.5], [13, 0.56], [17, 0.62]].forEach(([i, x], k) => {
    lm[i] = P(x, 0.6); lm[i + 1] = P(x, 0.5); lm[i + 2] = P(x, 0.47);
    lm[i + 3] = f[k + 1] ? P(x, 0.35) : P(x, 0.66);
  });
  return lm;
}
const out = {
  rauschen: r1.anteil, links: r2, ohne: r0.anteil,
  grau: m.grauwerte(rgba)[0],
  blickLinks: m.blickAusBild(0.1, 0.5), blickRechts: m.blickAusBild(0.9, 0.5), blickOben: m.blickAusBild(0.5, 0.0),
  grenzeRuhe: m.grenzeAusRuhe([0.001, 0.002, NaN]), grenzeStreng: m.grenzeAusRuhe([0.001], 1.6),
  grenzeLaut: m.grenzeAusRuhe([0.02]),
  erwischt: m.erwischt([0, 0.05, 0.06], 0.02), flackern: m.erwischt([0, 0.05, 0.0], 0.02),
  glatt: m.glaetten(0, 1, 0.5), start: m.glaetten(null, 0.7),
  zeit: [m.zeitText(75), m.zeitText(0), m.zeitText(null)], stufen: m.STUFEN_AMPEL,
  stein: hd.gesteAus(hand([0, 0, 0, 0, 0])), papier: hd.gesteAus(hand([1, 1, 1, 1, 1])),
  schere: hd.gesteAus(hand([0, 1, 1, 0, 0])), unklar: hd.gesteAus(hand([0, 1, 0, 0, 1])),
  papierOhneDaumen: hd.gesteAus(hand([0, 1, 1, 1, 1])), kaputt: hd.gesteAus([{ x: 0, y: 0 }]),
  gestreckt: hd.gestreckt(hand([1, 0, 1, 0, 1])),
  mitte: hd.handMitte(hand([1, 1, 1, 1, 1])),
  richtung: [hd.richtungAus(0.9, 0.5), hd.richtungAus(0.1, 0.5), hd.richtungAus(0.5, 0.1), hd.richtungAus(0.5, 0.9),
             hd.richtungAus(0.55, 0.45), hd.richtungAus(null, 0.5)],
  stabil: [hd.stabil(['links', 'links', 'links', 'links']), hd.stabil(['links', 'links', 'rechts', 'links']),
           hd.stabil(['mitte', 'mitte', 'mitte', 'mitte']), hd.stabil(['oben', 'oben'], 4)],
  haeufig: [hd.haeufigste(['stein', null, 'papier', 'stein']), hd.haeufigste(['stein', null, null]), hd.haeufigste([])],
  verbindungen: hd.VERBINDUNGEN.length, pfeile: sr.PFEIL, ssp: sr.SSP_NAME,
};
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node fehlt")
def test_bilddifferenz_und_handpunkte_im_browser_reine_funktionen(tmp_path):
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")       # als ES-Module laden
    for name in SPIEL_JS:
        (tmp_path / name).write_text((STATIC / name).read_text(encoding="utf-8"), encoding="utf-8")
    skript = tmp_path / "pruefen.mjs"
    skript.write_text(NODE_PRUEFUNG, encoding="utf-8")
    p = subprocess.run(["node", str(skript), *((tmp_path / n).as_uri() for n in ("kamera_spiele.js", "hand.js", "spiele_runden.js"))],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    o = json.loads(p.stdout)
    assert o["rauschen"] == 0 and o["ohne"] == 0 and o["grau"] == 255
    assert o["links"]["anteil"] == pytest.approx(240 / 3072) and o["links"]["x"] < 0.25 and 0.3 < o["links"]["y"] < 0.5
    # links im (ungespiegelten) Kamerabild = links von Reachy = + ; oben = hochschauen (Nicken −)
    assert o["blickLinks"]["yaw"] == pytest.approx(56) and o["blickRechts"]["yaw"] == pytest.approx(-56)
    assert o["blickOben"]["pitch"] == pytest.approx(-20) and o["blickOben"]["yaw"] == 0
    assert o["grenzeRuhe"] == pytest.approx(0.012) and o["grenzeStreng"] < o["grenzeRuhe"]
    assert o["grenzeLaut"] == pytest.approx(0.054)
    assert o["erwischt"] is True and o["flackern"] is False
    assert o["glatt"] == 0.5 and o["start"] == 0.7
    assert o["zeit"] == ["1:15", "0:00", "–"]
    st = o["stufen"]
    assert st["leicht"]["gruen"][0] > st["schwer"]["gruen"][0] and st["leicht"]["empf"] < st["schwer"]["empf"]
    # Handpunkte → Geste, Mitte, Richtung (aus Sicht des Menschen, gespiegelt)
    assert (o["stein"], o["papier"], o["schere"], o["unklar"]) == ("stein", "papier", "schere", None)
    assert o["papierOhneDaumen"] == "papier" and o["kaputt"] is None
    assert o["gestreckt"] == [True, False, True, False, True]
    assert o["mitte"]["x"] == pytest.approx(0.524) and o["mitte"]["y"] == pytest.approx(0.64)
    # Hand im Kamerabild rechts (x 0,9) = für den Menschen links
    assert o["richtung"] == ["links", "rechts", "oben", "unten", "mitte", None]
    assert o["stabil"] == ["links", None, None, None]
    assert o["haeufig"] == ["stein", None, None]
    assert o["verbindungen"] == 21 and set(o["pfeile"]) == set(SP.RICHTUNGEN) and set(o["ssp"]) == set(SP.SSP)
