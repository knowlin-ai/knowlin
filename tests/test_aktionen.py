"""Aktionskatalog und Selbstbild (seit 0.38.43, Etappe G2): Absicht statt Gelenkwinkel – der Körper handelt aus, ob er
kann, was er stattdessen tut oder warum nicht."""

import asyncio
from types import SimpleNamespace

from helpers import make

from duckpilot import aktionen as A
from duckpilot.brain.tools import ToolRunner
from duckpilot.motion import behaviors as B

ENTE = {"beine", "kopf", "schnabel", "stimmbank"}


def test_katalog_nutzt_nur_bekannte_faehigkeiten_gefuehle_und_laute():
    from duckpilot import koerper
    from duckpilot.api import SOUND_TAGS

    for name, a in A.AKTIONEN.items():
        assert a["absicht"] and a["umsetzungen"], name
        for braucht, werkzeug, argumente, wie in a["umsetzungen"]:
            assert braucht <= set(koerper.FAEHIGKEITEN) and wie
            assert (argumente["emotion"] in B.EMOTIONS) if werkzeug == "emote" else (argumente["tag"] in SOUND_TAGS)


def test_kann_ersatz_nein():
    frei = {"gesperrt": False, "gefallen": False, "hochgehoben": False, "stromlos": False}
    assert A.aushandeln("freuen", ENTE, frei)["antwort"] == "kann"
    ersatz = A.aushandeln("freuen", {"kopf", "antennen"}, frei)           # Reachy: ohne Beine nur mit dem Kopf
    assert ersatz["antwort"] == "ersatz" and ersatz["argumente"] == {"emotion": "freude"}
    arm = A.aushandeln("neugierig", {"arm", "greifer"}, frei)              # ein Arm ohne Kopf
    assert arm["antwort"] == "nein" and "kopf" in arm["grund"]
    assert A.aushandeln("fliegen", ENTE, frei)["antwort"] == "nein"


def test_lage_geht_vor():
    assert "Not-Aus" in A.aushandeln("gruessen", ENTE, {"gesperrt": True})["grund"]
    assert "liege" in A.aushandeln("gruessen", ENTE, {"gefallen": True})["grund"]
    gehalten = A.aushandeln("freuen", ENTE, {"hochgehoben": True})         # gehalten: nur Kopf, nicht die Beine
    assert gehalten["antwort"] == "ersatz" and gehalten["argumente"] == {"emotion": "freude"}


def test_werkzeuge_im_simulator():
    async def go():
        sim, eng = await make()
        runner = ToolRunner(eng)
        namen = {t["name"] for t in runner.tools()}
        assert {"absicht", "selbstbild"} <= namen
        bild = await runner.run("selbstbild", {})
        assert bild["ok"] and bild["haltung"] in ("steht", "sitzt") and "Kopf und Blick bewegen" in bild["kann"]
        out = await runner.run("absicht", {"aktion": "zustimmen"})
        assert out["ok"] and out["antwort"] == "kann" and out["wie"] == "nickt"
        eng.notaus()
        gesperrt = await runner.run("absicht", {"aktion": "gruessen"})
        assert not gesperrt["ok"] and "Not-Aus" in gesperrt["grund"]
        assert (await runner.run("selbstbild", {}))["sperre_nach_notaus"]
    asyncio.run(go())


def test_selbstbild_sagt_was_unsicher_ist():
    st = SimpleNamespace(connected=True, fallen=False, picked_up=False, powered=True, sitting=False, battery=None,
                         koerper="microduck", backend="sim", holding="Socke", skill=None)
    bild = A.selbstbild(st, ENTE, {"kopf": "Kopf bewegen"}, False)
    assert bild["haltung"] == "steht" and bild["haelt"] == "Socke" and "Akkustand unbekannt" in bild["unsicher"]


def test_wissen_lesbare_namen_und_volle_breite():
    """Fund 12.11. (Bild Gedächtnis): technische Trick-Namen als Tätigkeiten, Infozeile umgebrochen, rechts ein leeres
    Drittel – Namen jetzt lesbar, Spalten über die ganze Breite."""
    from pathlib import Path

    from duckpilot.brain.erfahrung import lesbarer_name

    assert lesbarer_name("Duck Skill 20261105 Got A Talent") == "Got A Talent"
    assert lesbarer_name("Got A Talent Run 1106 0803 009") == "Got A Talent" and lesbarer_name("spielen") == "spielen"
    css = (Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static" / "style.css").read_text(encoding="utf-8")
    regel = css[css.index(".welt-gruppen {"):]
    assert "1fr" in regel[:regel.index("}")]
