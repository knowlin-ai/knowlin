"""Trainingsfeld wie in der Keynote (0.38.23): Originalmodelle, viele Enten, Sparen auf schwacher Grafik; seit 0.38.24
als Bild-Enten aus dem vollen Modell mit der Gangart des Simulators und ehrlicher Beschriftung. Dazu die Farbe der Microduck unter Charakter und die ruhige Handanzeige bei Reachys Spielen.

Wünsche vom 7.11.: „nutze bei Training auch Originalmodelle, wenn sie auch sonst aktiviert sind“, „es soll so
wie in der Keynote aussehen“, „wo sehe ich die neuen Farben der Enten?“, „wenn nur der Punkt ist, flimmert er zu sehr“.
"""
import json
import math
import shutil
import subprocess

import pytest

from duckpilot.api import Head, Twist
from duckpilot.backends.sim import display_joints
from duckpilot.server.app import STATIC


def test_gangart_wie_im_simulator():
    """0.38.24 (Fund „die Bewegung ist völlig unsinnig“): Die Enten im Feld gehen mit den Gelenkwinkeln des
    Simulators – nicht mehr nur mit schwingenden Hüften."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    phasen = [k * math.pi / 4 for k in range(8)]
    code = ("import { gelenke } from '" + (STATIC / "trainingsfeld.js").as_uri() + "';"
            f"console.log(JSON.stringify({json.dumps(phasen)}.map((p) => gelenke(p))));")
    r = subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, timeout=60)
    if r.returncode:
        pytest.skip("trainingsfeld.js lässt sich ohne Browser nicht laden: " + r.stderr[:200])
    js = json.loads(r.stdout)
    for ph, w in zip(phasen, js):
        py = display_joints(sitting=False, skill=None, progress=0.0, powered=True, fallen=False, twist=Twist(vx=0.15),
                            phase=ph, head=Head(), mouth=0.0)
        assert w == pytest.approx(py, abs=1e-6), ph


def test_trainingsfeld_oberflaeche():
    js = (STATIC / "trainingsfeld.js").read_text(encoding="utf-8")
    assert "SPALTEN = SCHMAL ? 8 : 16, REIHEN = SCHMAL ? 5 : 9" in js          # 144 Enten am PC, 40 am Handy
    # Bild-Enten aus dem vollen Modell statt löchriger Netze (0.38.24), einfache Ente bis das Original da ist
    assert "function bildbogen(" in js and "new RealDuck(modell)" in js and "new Duck(" in js and "MODEL_URL" in js
    assert "/api/modell/feld/" not in js and not (STATIC.parent.parent / "modell" / "feld.py").exists()
    # Hinweis 7.11.: „jede Ente beim Lernen soll ja auf ihrem Testfeld lernen“ (wie im NVIDIA-Bild):
    # jede hat ihre eigene Platte, quer im Raum gedreht, läuft darauf vom Start zum Ende und verlässt sie nie
    assert "function feldPlatte(" in js and "function lage(d)" in js and "GridHelper" in js
    assert "const yaw = d.dreh + d.richtung + d.kurs" in js                   # Richtung = Richtung ihres Feldes
    assert "d.lz = Math.max(-PB / 2 + 0.05, Math.min(PB / 2 - 0.05, d.lz))" in js   # bleibt auf ihrer Platte
    assert "if (d.lx > PL / 2 - RAND) { d.fall = 1.0; d.zeitum = true; }" in js    # am Ende: neuer Durchgang
    assert "d.richtung = zufall() * Math.PI * 2" not in js and "function hoehe(x, z)" not in js
    assert "d.zeitum" in js and "lerpVectors" in js                           # Episoden, Auftakt
    assert "felder.geometry.setDrawRange(0, felder.userData.ende[sichtbarAnzahl - 1])" in js   # spart: kein leeres Feld
    assert "schatten.visible = false" in js and "beiBau(fn)" in js            # erst Enten, dann Schatten; Hinweis
    assert "neuStart(d)" in js and "Math.log(" in js                           # Sturz → zurück an den Start, Quote passt
    assert "function sparen()" in js and "prefers-reduced-motion" in js and "IntersectionObserver" in js
    tr = (STATIC / "training.js").read_text(encoding="utf-8")
    assert "feld.setModell(figur())" in tr and "Vorschau – hier lernt nichts" in tr and "Gemessene Quote" in tr
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "original: scene.modelStyle === 'original'" in app
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "50 Enten" not in html and 'id="tr-feld-art"' in html and "Gelernt wird erst, wenn du unten einen Lauf startest" in html and "Runde ${runde}" not in tr


def test_farbe_auch_unter_charakter():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    seite = html[html.index('id="view-persoenlichkeit"'):]
    seite = seite[:seite.index("</section>\n      <section class=\"view")] if "</section>\n      <section class=\"view" in seite else seite
    for f in ("cream", "graphite", "lavender", "sky"):
        assert f'name="farbe-ch" value="{f}" data-set="farbe"' in seite
    # Hinweise zu Reachy und Odi stehen beim Feld „3D-Ansicht“ (vorher im Microduck-Feld versteckt)
    feld = html[html.index('aria-label="3D-Modell"'):html.index('id="farbe-label"')]
    assert "nur-reachy" in feld and "nur-open-duck" in feld


def test_handanzeige_ruhig_und_schoener():
    js = (STATIC / "kamera_spiele.js").read_text(encoding="utf-8")
    assert "const anzeige = new Map()" in js and "a.sicht - 0.22" in js       # glätten und weich ausblenden
    assert "FLAECHE" in js and "SPITZEN" in js and "devicePixelRatio" in js
    assert "drawImage(video" in js and js.count("drawImage(") == 1                # nie das Kamerabild zeigen


def test_startperspektive_flacher():
    js = (STATIC / "duck3d.js").read_text(encoding="utf-8")
    assert "new THREE.Vector3(p.x - 0.92 * s, p.y + 0.3 * s, p.z - 0.42 * s)" in js     # seit 0.38.25 nach Figurgröße


def test_kachel_zuege_einzeln_uebersetzbar():
    """Fund 7.11.: In der englischen Oberfläche blieb „Quacki · Ausgeglichen · 0 eigene Tricks“ deutsch, wenn die
    Kacheln vor der Übersetzung gezeichnet wurden – jetzt ist jeder Zug ein eigener Knoten."""
    js = (STATIC / "start.js").read_text(encoding="utf-8")
    assert "for (const zug of zuege) figur.append(document.createTextNode(' · '), el('span', null, zug));" in js


def test_gaeste_bunt_eigene_ente_waehlbar():
    """0.38.24, Wunsch: „andere Enten können immer zufällig die Farben bekommen. Meine möchte ich wählen können“
    – und das Trainingsfeld bleibt in der Farbe der eigenen Ente („da geht es ja um das Training meiner Ente“)."""
    js = (STATIC / "duck3d.js").read_text(encoding="utf-8")
    gast = js[js.index("setEnten(liste) {"):js.index("_entenZeichnen(dt) {")]
    assert "Object.keys(FARBEN)" in gast and "Math.random()" in gast and "e.setFarbe?.(this._gastFarben.get(st.id))" in gast
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "farbe: scene.farbe" in app                                    # Feld: Farbe der eigenen Ente
    feld = (STATIC / "trainingsfeld.js").read_text(encoding="utf-8")
    assert "Math.random()" not in feld


def test_uebungsfelder_ueberlappen_nie():
    """Klares Raster (Hinweis 7.11.: „noch etwas kreuz und quer“): alle Felder parallel, Reihen gegenläufig –
    zwei Nachbarfelder berühren sich nie."""
    import re

    js = (STATIC / "trainingsfeld.js").read_text(encoding="utf-8")
    m = re.search(r"const AX = ([\d.]+), AZ = ([\d.]+), PL = ([\d.]+), PB = ([\d.]+);", js)
    ax, az, pl, pb = (float(x) for x in m.groups())
    assert ax > pl + 0.2 and az > pb + 0.2                                   # Gang zwischen den Feldern
    assert "dreh: Math.floor(i / SPALTEN) % 2 ? Math.PI : 0" in js           # feste Winkel, kein Zufall mehr
