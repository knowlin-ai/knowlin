"""Alltag 2 (seit 0.42): Routinen, Kalender-Abo aus einer lokalen Datei, Aris Beispiele auf den Hub."""

import io
import json
import os
import time
import zipfile
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from duckpilot import ari_hub, kalender_abo, routinen
from duckpilot import settings as S
from duckpilot.arm_export import paket
from duckpilot.buddy import Planner
from duckpilot.config import load
from duckpilot.remote import pc_only
from duckpilot.server.app import Runtime, create_app
from duckpilot.server.oberflaeche import seite
from duckpilot.skills.alltag import quick

H = {"Origin": "http://127.0.0.1:8765"}
NOW = datetime(2026, 10, 28, 7, 40).astimezone()      # Mittwoch


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


# ── Routinen ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("roh,ziel", [("7", "07:00"), ("7:30", "07:30"), ("um 7.30 Uhr", "07:30"), ("", "")])
def test_zeit(roh, ziel):
    assert routinen.zeit_pruefen(roh) == ziel


@pytest.mark.parametrize("felder,teil", [
    ({"name": ""}, "Wie heißt"),
    ({"name": "X", "schritte": ["tanzen"]}, "Unbekannter Schritt"),
    ({"name": "X", "schritte": ["aktiv", "ruhe"]}, "nur eins"),
    ({"name": "X"}, "mindestens einen"),
    ({"name": "X", "zeit": "25:00", "ansage": "Hallo"}, "gibt es nicht"),
    ({"name": "X", "zeit": "abends", "ansage": "Hallo"}, "Uhrzeit wie"),
    ({"name": "X", "tage": "montags", "ansage": "Hallo"}, "Tage"),
])
def test_routine_pruefen_sagt_was_fehlt(felder, teil):
    with pytest.raises(ValueError, match=teil):
        routinen.pruefen(**felder)


def test_routine_faellig_einmal_je_tag_und_nur_an_ihren_tagen(tmp_path):
    clock = Clock(NOW.replace(hour=7, minute=0))
    p = Planner(tmp_path / "a.json", clock)
    r = p.add_routine(name="Morgen", zeit="7:30", tage="werktags", schritte="ueberblick, wetter", ansage="Guten Morgen")
    assert r["schritte"] == ["ueberblick", "wetter"] and r["zuletzt"] == ""
    assert p.routinen_faellig() == []
    clock.t = NOW.replace(hour=7, minute=31)
    assert [x["name"] for x in p.routinen_faellig()] == ["Morgen"]
    assert p.routinen_faellig() == []                                       # heute nicht noch einmal
    assert Planner(tmp_path / "a.json", clock).data["routinen"][0]["zuletzt"] == NOW.date().isoformat()
    clock.t = NOW.replace(hour=7, minute=31) + timedelta(days=3)            # Samstag
    assert p.routinen_faellig() == []
    clock.t = NOW.replace(hour=9, minute=0) + timedelta(days=5)             # Montag, PC war bis 9 Uhr aus
    assert p.routinen_faellig() == []
    assert p.data["routinen"][0]["zuletzt"] == clock.t.date().isoformat()   # nicht später noch nachholen


def test_routine_finden_anlegen_loeschen(tmp_path):
    p = Planner(tmp_path / "a.json", Clock(NOW))
    a = p.add_routine(name="Morgen", zeit="7:00", ansage="Hallo")          # 7:00 ist schon vorbei: ab morgen
    assert a["zuletzt"] == NOW.date().isoformat()
    p.add_routine(name="Abendrunde", schritte=["todos", "ruhe"])
    with pytest.raises(ValueError, match="gibt es schon"):
        p.add_routine(name="morgen", ansage="x")
    assert p.routine("morgen")["id"] == a["id"] and p.routine("Morgenroutine")["id"] == a["id"]
    assert p.routine("abend")["name"] == "Abendrunde" and p.routine("") is None
    assert p.routine_an("morgen", False)["an"] is False
    assert "pausiert" in routinen.beschreiben(p.routine("morgen"))
    assert "nur auf Zuruf" in routinen.beschreiben(p.routine("abend"))
    snap = p.snapshot()
    assert [r["name"] for r in snap["routinen"]] == ["Morgen", "Abendrunde"] and snap["routinen"][0]["beschreibung"]
    assert p.remove("routine", "abend")["name"] == "Abendrunde"


@pytest.mark.parametrize("text,ziel", [
    ("Starte die Morgenroutine", {"aktion": "routine", "text": "morgen"}),
    ("Ente, starte die Abend-Routine", {"aktion": "routine", "text": "abend"}),
    ("Routine Morgen starten", {"aktion": "routine", "text": "morgen"}),
    ("Welche Routinen gibt es?", {"aktion": "routinen"}),
])
def test_routine_saetze(text, ziel):
    assert quick(text) == ziel


def test_routine_satz_ohne_name_ist_kein_auftrag():
    assert quick("routine") is None and quick("Ich mag meine Routine") is None


# ── Kalender-Abo ──────────────────────────────────────────────────────────
def _ics(*termine):
    teile = ["BEGIN:VCALENDAR", "VERSION:2.0"]
    for uid, start, titel in termine:
        teile += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTART:{start}", f"SUMMARY:{titel}", "END:VEVENT"]
    return "\r\n".join([*teile, "END:VCALENDAR", ""])


def test_abo_pfad_pruefen(tmp_path):
    (tmp_path / "k.txt").write_text("x")
    for roh, teil in [("", "Welche Datei"), ("k.ics", "vollständigen Pfad"), (tmp_path / "k.txt", "auf .ics"),
                      (tmp_path / "fehlt.ics", "gibt es nicht")]:
        with pytest.raises(ValueError, match=teil):
            kalender_abo.pfad_pruefen(roh)


def test_abo_liest_bei_aenderung_neu_und_raeumt_nur_eigene_termine(tmp_path):
    clock = Clock(NOW)
    p = Planner(tmp_path / "a.json", clock)
    p.add_event("Von Hand", NOW + timedelta(days=1))
    datei = tmp_path / "privat.ics"
    datei.write_text(_ics(("a", "20261029T090000", "Zahnarzt"), ("b", "20261030T100000", "Friseur")))
    stand = kalender_abo.setzen(p, str(datei))
    assert stand == {"an": True, "datei": "privat.ics", "stand": NOW.isoformat(timespec="minutes"), "anzahl": 2,
                     "fehler": ""}
    assert {e["titel"]: e["quelle"] for e in p.data["termine"]} == {"Von Hand": "manuell", "Zahnarzt": "abo",
                                                                     "Friseur": "abo"}
    assert kalender_abo.lesen(p) is None                                    # unverändert: nichts zu tun
    datei.write_text(_ics(("a", "20261029T110000", "Zahnarzt"), ("c", "20261031T100000", "Kino")))
    os.utime(datei, (time.time() + 5, time.time() + 5))
    neu = kalender_abo.lesen(p)
    assert neu["anzahl"] == 2 and neu["entfernt"] == 1
    titel = {e["titel"]: e["start"][11:16] for e in p.data["termine"]}
    assert titel == {"Von Hand": NOW.strftime("%H:%M"), "Zahnarzt": "11:00", "Kino": "10:00"}
    datei.write_text("kein Kalender")
    os.utime(datei, (time.time() + 9, time.time() + 9))
    assert "keine Kalenderdatei" in kalender_abo.lesen(p)["fehler"]
    assert kalender_abo.lesen(p) is None                                    # Fehler nur einmal melden
    assert len(p.data["termine"]) == 3                                      # kaputte Datei löscht nichts
    datei.unlink()
    assert "nicht da" in kalender_abo.lesen(p)["fehler"]
    assert kalender_abo.beenden(p) == 2
    assert [e["titel"] for e in p.data["termine"]] == ["Von Hand"] and kalender_abo.anzeige(p) == {"an": False}


def test_abo_wechsel_raeumt_altes_abo(tmp_path):
    p = Planner(tmp_path / "a.json", Clock(NOW))
    eins, zwei = tmp_path / "eins.ics", tmp_path / "zwei.ics"
    eins.write_text(_ics(("a", "20261029T090000", "Eins")))
    zwei.write_text(_ics(("b", "20261029T090000", "Zwei")))
    kalender_abo.setzen(p, eins)
    kalender_abo.setzen(p, str(zwei))
    assert [e["titel"] for e in p.data["termine"]] == ["Zwei"]


# ── Mit dem Server ────────────────────────────────────────────────────────
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        c.runtime = rt
        yield c


def test_routine_ueber_befehl_mit_ansage_und_todos(client):
    rt = client.runtime
    gesendet = []
    orig = rt.broadcast

    async def spion(msg):
        gesendet.append(msg)
        await orig(msg)

    rt.broadcast = spion
    r = client.post("/api/alltag/befehl", json={"aktion": "routine_anlegen", "text": "Abend", "schritte": ["todos"],
                                                 "ansage": "Feierabend!"}, headers=H).json()
    assert r["ok"] and "nur auf Zuruf" in r["antwort"]
    client.post("/api/alltag/befehl", json={"aktion": "todo", "text": "Müll rausbringen"}, headers=H)
    los = client.post("/api/alltag/befehl", json={"aktion": "routine", "text": "abend"}, headers=H).json()
    assert los["ok"] and los["antwort"] == "Feierabend! Auf der Liste: Müll rausbringen."
    assert any(m.get("type") == "alltag_routine" and m.get("name") == "Abend" for m in gesendet)
    assert any(m.get("source") == "alltag" and m.get("text") == los["antwort"] for m in gesendet)
    weg = client.post("/api/alltag/befehl", json={"aktion": "routine", "text": "morgen"}, headers=H).json()
    assert not weg["ok"] and "Es gibt: Abend" in weg["fehler"]
    liste = client.post("/api/alltag/befehl", json={"aktion": "routinen"}, headers=H).json()
    assert liste["routinen"] == ["Abend"]
    rid = rt.alltag.planner.data["routinen"][0]["id"]
    assert client.post(f"/api/alltag/routine/{rid}", json={"an": False}, headers=H).json()["ok"]
    assert client.delete(f"/api/alltag/routine/{rid}", headers=H).json()["ok"]
    assert rt.alltag.planner.data["routinen"] == []


def test_routine_nach_not_aus_ohne_geste_und_ohne_aufstehen(client):
    rt = client.runtime
    gerufen = []
    orig = rt.runner.run

    async def spion(name, args):
        gerufen.append(name)
        return await orig(name, args)

    rt.runner.run = spion
    client.post("/api/alltag/optionen", json={"modus": "ruhe"}, headers=H)
    rt.alltag.emergency_stop()
    gerufen.clear()
    r = client.post("/api/alltag/befehl", json={"aktion": "routine_anlegen", "text": "Wach", "schritte": ["aktiv", "freuen"],
                                                 "ansage": "Hallo"}, headers=H).json()
    assert r["ok"]
    assert client.post("/api/alltag/befehl", json={"aktion": "routine", "text": "wach"}, headers=H).json()["ok"]
    assert "emote" not in gerufen and "power" not in gerufen
    assert not rt.backend.state().powered


def test_abo_api_und_nur_am_pc(client, tmp_path):
    assert pc_only("POST", "/api/alltag/abo") and pc_only("DELETE", "/api/alltag/abo")
    assert pc_only("POST", "/api/alltag/abo/lesen") and pc_only("POST", "/api/ari_lernen/hub")
    assert not pc_only("POST", "/api/alltag/routine/x") and not pc_only("POST", "/api/alltag/befehl")
    assert client.post("/api/alltag/abo", json={"pfad": "relativ.ics"}, headers=H).status_code == 400
    datei = tmp_path / "kal.ics"
    morgen = (datetime.now() + timedelta(days=1)).strftime("%Y%m%dT090000")
    datei.write_text(_ics(("x", morgen, "Arzt")))
    r = client.post("/api/alltag/abo", json={"pfad": str(datei)}, headers=H).json()
    assert r["ok"] and r["abo"]["anzahl"] == 1 and r["abo"]["datei"] == "kal.ics"
    snap = client.get("/api/alltag").json()
    assert snap["abo"]["datei"] == "kal.ics" and str(tmp_path) not in json.dumps(snap["abo"])   # kein ganzer Pfad
    assert client.post("/api/alltag/abo/lesen", headers=H).json()["abo"]["anzahl"] == 1
    assert client.delete("/api/alltag/abo", headers=H).json()["entfernt"] == 1


def test_oberflaeche_hat_routinen_abo_und_hub():
    html = seite()
    for kennung in ('id="al-routinen"', 'id="al-rt-form"', 'id="al-abo"', 'id="al-abo-form" ', 'id="ari-hub"',
                    'id="ari-hub-oeffentlich"', 'id="ari-hub-los"', "bereiche/alltag.css"):
        assert kennung in html, kennung
    assert 'class="al-form al-form--one pc-only" id="al-abo-form"' in html


# ── Aris Beispiele auf den Hub ────────────────────────────────────────────
class FakeApi:
    def __init__(self):
        self.repos, self.hoch = [], {}

    def whoami(self):
        return {"name": "jemand"}

    def create_repo(self, repo_id, repo_type, private, exist_ok):
        self.repos.append((repo_id, repo_type, private))

    def upload_folder(self, folder_path, repo_id, repo_type, commit_message):
        for wurzel, _ordner, namen in os.walk(folder_path):
            for n in namen:
                pfad = os.path.join(wurzel, n)
                self.hoch[os.path.relpath(pfad, folder_path).replace(os.sep, "/")] = open(pfad, "rb").read()


def _beispiel():
    schritt = [[0.0] * 11, 0, [0.0] * 6, [1.0] * 6]
    return [{"schritte": [schritt, schritt], "von": "hand"}]


def test_hub_upload_privat_ein_commit_mit_karte():
    zipdaten = paket(_beispiel(), {"wuerfel": "roter Würfel", "kiste": "blaue Kiste"}, "0.42.0")
    api = FakeApi()
    out = ari_hub.teile(zipdaten, "tok", name="ari-roter-blaue", api=api)
    assert out == {"repo": "jemand/ari-roter-blaue", "url": "https://huggingface.co/datasets/jemand/ari-roter-blaue",
                   "oeffentlich": False}
    assert api.repos == [("jemand/ari-roter-blaue", "dataset", True)]
    assert set(api.hoch) == {"episoden.jsonl", "meta/info.json", "meta/tasks.jsonl", "nach_lerobot.py", "LIESMICH.md",
                             "README.md"}
    karte = api.hoch["README.md"].decode()
    assert "- LeRobot\n" in karte and "- so101\n" in karte and "1 Beispiel, 2 Takte" in karte
    assert "roten Würfel" in karte or "roter Würfel" in karte
    ari_hub.teile(zipdaten, "tok", name="Ari Test!", oeffentlich=True, api=api)
    assert api.repos[-1] == ("jemand/ari-test", "dataset", False)


def test_hub_upload_lehnt_fremde_und_boese_pakete_ab():
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("x.txt", "hallo")
    with pytest.raises(ari_hub.HubFehler, match="kein Export"):
        ari_hub.dateien(puffer.getvalue())
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("meta/info.json", "{}")
        z.writestr("../boese.py", "x")
    with pytest.raises(ari_hub.HubFehler, match="ungültigen"):
        ari_hub.dateien(puffer.getvalue())


def test_hub_route_braucht_zweiten_klick_und_schluessel(client):
    assert client.post("/api/ari_lernen/hub", json={}, headers=H).status_code == 400
    r = client.post("/api/ari_lernen/hub", json={"bestaetigt": True}, headers=H)
    assert r.status_code in (400, 404) and not r.json()["ok"]
