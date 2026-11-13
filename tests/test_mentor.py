"""Vormachen (seit 0.38.57, erster Schritt zum Mentor aus 0.44): Ari folgt deiner Hand vor der Webcam.

Maintainer: „dann bin ich sozusagen die Körperschnittstelle“ – im Browser werden 21 Handpunkte erkannt, an Knowlin geht
nur die Zahlenliste. Hier: die Umrechnung (Spiegel, Höhe, Nähe, Zange), dass Ari greift und loslässt, dass er nichts
umfährt und nach dem Not-Aus nicht weitermacht, und dass die Webcam nur am PC und sichtbar läuft."""

import asyncio
from pathlib import Path

from duckpilot import mentor as M
from duckpilot.backends.so101 import So101Sim

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"


def _hand(mx=0.5, my=0.5, g=0.15, zange=1.2):
    """Eine flache Hand: Handgelenk unten, Mittelfinger-Ansatz `g` darüber; Daumen und Zeigefinger `zange`·g auseinander."""
    p = [(mx, my, 0.0)] * 21
    p = [list(x) for x in p]
    p[M.HANDGELENK] = [mx, my + g / 2, 0.0]
    p[M.MITTEL_ANSATZ] = [mx, my - g / 2, 0.0]
    p[M.ZEIGE_ANSATZ] = [mx + g * 0.3, my - g / 2, 0.0]
    p[M.KLEIN_ANSATZ] = [mx - g * 0.3, my - g / 2, 0.0]
    p[M.DAUMEN_SPITZE] = [mx + g * 0.3 - zange * g / 2, my - g, 0.0]
    p[M.ZEIGE_SPITZE] = [mx + g * 0.3 + zange * g / 2, my - g, 0.0]
    return {"punkte": p, "seite": "Right"}


def test_hand_wird_geprueft():
    assert M.hand_aus(_hand()) is not None
    assert M.hand_aus({"punkte": [[0.5, 0.5, 0]] * 20}) is None               # zu wenige
    assert M.hand_aus({"punkte": [[0.5, "x", 0]] * 21}) is None
    assert M.hand_aus({"punkte": [[9.0, 0.5, 0]] * 21}) is None               # weit außerhalb des Bildes
    assert M.hand_aus({"punkte": [[float("nan"), 0.5, 0]] * 21}) is None
    assert M.hand_aus("bild.png") is None


def test_wie_im_spiegel():
    n = M.Nachmacher()
    mitte = n.weiter(M.hand_aus(_hand()), 0.0)                                 # erste Hand = Aris Mitte
    assert abs(mitte["y"]) < 1e-6 and mitte["greifer"] == M.GREIFER_AUF
    t = 0.0
    for _ in range(30):                                                       # Hand nach deiner Rechten (im Bild links)
        t += 0.1
        rechts = n.weiter(M.hand_aus(_hand(mx=0.3)), t)
    assert rechts["y"] > 0.05                                                 # Ari zu deiner Rechten
    for _ in range(30):                                                       # Hand hoch
        t += 0.1
        hoch = n.weiter(M.hand_aus(_hand(mx=0.3, my=0.3)), t)
    assert hoch["z"] > mitte["z"] + 0.02
    for _ in range(30):                                                       # näher an die Kamera (größer)
        t += 0.1
        nah = n.weiter(M.hand_aus(_hand(mx=0.3, my=0.3, g=0.2)), t)
    assert nah["x"] > mitte["x"] + 0.02
    for v in (rechts, hoch, nah):
        assert M.BEREICH_X[0] <= v["x"] <= M.BEREICH_X[1] and M.BEREICH_Z[0] <= v["z"] <= M.BEREICH_Z[1]


def test_zange_mit_puffer():
    n = M.Nachmacher()
    assert n.weiter(M.hand_aus(_hand(zange=1.2)), 0.0)["greifer"] == M.GREIFER_AUF
    assert n.weiter(M.hand_aus(_hand(zange=0.2)), 0.1)["greifer"] == M.GREIFER_ZU
    assert n.weiter(M.hand_aus(_hand(zange=0.6)), 0.2)["greifer"] == M.GREIFER_ZU   # dazwischen: bleibt zu
    assert n.weiter(M.hand_aus(_hand(zange=1.0)), 0.3)["greifer"] == M.GREIFER_AUF


def test_ari_greift_traegt_und_laesst_los():
    async def go():
        s = So101Sim(realtime=False)
        await s.init()
        for _ in range(40):
            s.step(0.05)
        rot = s.werkbank.ding("rot")

        async def zu(x, y, z, g, schritte=6):
            r = await s.nachmachen({"x": x, "y": y, "z": z, "greifer": g})
            for _ in range(schritte):
                s.step(0.05)
            return r

        for z, g in ((0.08, 45), (0.016, 45), (0.016, 8)):
            assert (await zu(rot["x"], rot["y"], z, g)).accepted
        assert s.werkbank.haelt == "roter Würfel"
        await zu(rot["x"], rot["y"], 0.09, 8)                                  # erst anheben, dann hinüber
        await zu(0.22, 0.0, 0.05, 8)
        await zu(0.22, 0.0, 0.05, 45)
        assert s.werkbank.haelt is None
        assert abs(rot["x"] - 0.22) < 0.01 and abs(rot["y"]) < 0.01 and rot["z"] == 0.015
        weit = await zu(0.5, 0.0, 0.05, 45)
        assert not weit.accepted and "nicht hin" in weit.reason
    asyncio.run(go())


def test_faehrt_nicht_durch_wuerfel_und_nicht_nach_dem_not_aus():
    async def go():
        s = So101Sim(realtime=False)
        await s.init()
        for _ in range(40):
            s.step(0.05)
        gelb = s.werkbank.ding("gelb")
        # vom offenen Griff über dem roten Würfel quer durch den gelben auf Tischhöhe: der Weg ist versperrt
        rot = s.werkbank.ding("rot")
        for z in (0.08, 0.016):
            await s.nachmachen({"x": rot["x"], "y": rot["y"], "z": z, "greifer": 45})
            for _ in range(6):
                s.step(0.05)
        quer = await s.nachmachen({"x": gelb["x"] + 0.05, "y": gelb["y"], "z": 0.016, "greifer": 45})
        assert not quer.accepted and "stoßen" in quer.reason
        await s.relax()                                                     # Not-Aus: stromlos
        assert not (await s.nachmachen({"x": 0.22, "y": 0.0, "z": 0.06, "greifer": 45})).accepted
    asyncio.run(go())


def test_auftrag_und_spiel_gehen_vor():
    from duckpilot.werkbank_auftrag import AUFTRAEGE

    async def go():
        s = So101Sim(realtime=False)
        await s.init()
        for _ in range(40):
            s.step(0.05)
        assert (await s.auftrag_starten(AUFTRAEGE["sortieren"])).accepted
        assert "Auftrag" in (await s.nachmachen({"x": 0.22, "y": 0.0, "z": 0.06, "greifer": 45})).reason
    asyncio.run(go())


def test_webcam_nur_am_pc_sichtbar_und_nur_punkte():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'class="chip pc-only" id="vormachen-btn"' in html and 'class="hud hud-mentor pc-only" id="mentor-panel"' in html
    assert 'id="badge-mentor-cam"' in html
    js = (STATIC / "mentor_arm.js").read_text(encoding="utf-8")
    assert "type: 'mentor_hand'" in js and "toDataURL" not in js and "getImageData" not in js   # kein Bild geht raus
    assert "if (isRemote())" in js and "for (const t of stream.getTracks()) t.stop()" in js
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "mentor.aus(); send({ type: 'stop' })" in app                     # Not-Aus schließt Fenster und Webcam
    runtime = (STATIC.parent / "runtime.py").read_text(encoding="utf-8")
    assert 'elif kind == "mentor_hand":' in runtime and "hand_aus(msg)" in runtime
