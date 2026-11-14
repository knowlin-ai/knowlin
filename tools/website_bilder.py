"""Bilder für knowlin.de und die README aus dem laufenden Programm aufnehmen (seit 0.38.39).

Hinweis zur Website: „Einige Bilder sind noch nicht gut … besonders die, wo du nur Ränder ergänzt hast, weil das
Format nicht gepasst hatte“ – und: „zeig mehr Features, das soll ja WOW-Effekt erzeugen“. Bisher entstanden die Bilder
von Hand und einzelne Ausschnitte wurden mit Rand aufs Format gebracht. Jetzt nimmt dieses Werkzeug jedes Bild als ganzes
Programmfenster auf – gleich groß, in voller Breite (1600 px), auf Deutsch und Englisch, bei jeder Version gleich:

    python tools/website_bilder.py <arbeitsordner> [--nur start,tanz] [--probe]

Ergebnis: `website/bilder/<name>-<de|en>-1600.webp` und `-900.webp`. Mit `--probe` landen die Bilder nur im
Arbeitsordner (zum Ansehen), die Website bleibt unberührt.

Läuft wie die Abnahme im Simulator ohne Netz und ohne Claude, mit leerem Datenordner. Seit 0.38.40 mit Pollens
Originalmodellen für Microduck und Reachy Mini (Entscheidung vom 9.11.: „dürfen wir nicht Bilder mit den echten
Modellen verwenden mit entsprechendem Hinweis?“ – „ja“). Die Modelle stehen unter CC BY-NC-SA 4.0: Jedes Bild, auf
dem eines zu sehen ist, trägt auf der Website und in der README den Hinweis „© Pollen Robotics, CC BY-NC-SA 4.0“ und
steht selbst unter dieser Lizenz (`website.POLLEN_BILDER`, geprüft von `tools/website_pruefen.py`). Die Modelldateien selbst
kommen nie auf die Website und nie in die öffentliche Fassung. Das Gedächtnis bekommt vorher eine erfundene Woche mit
Erlebnissen, damit das Netz zu sehen ist; Personen kommen darin nicht vor.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import abnahme as A  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BREITE, HOEHE = 1600, 965
ZIEL = ROOT / "website" / "bilder"


# ── Vorbereitung: eine erfundene Woche für das Erfahrungsnetz ─────────────
WOCHE = [
    ({"ort": "Wohnzimmer", "ding": "Ball", "taetigkeit": "spielen", "gefuehl": "Freude", "zeit": "abends"}, 1.6),
    ({"ort": "Wohnzimmer", "ding": "Teppich", "taetigkeit": "tanzen", "gefuehl": "Freude", "zeit": "abends"}, 1.4),
    ({"ort": "Wohnzimmer", "taetigkeit": "tanzen", "sinn": "Musik", "gefuehl": "Freude", "zeit": "Wochenende"}, 1.8),
    ({"ort": "Küche", "ding": "Tasse", "taetigkeit": "erkunden", "gefuehl": "Neugier", "zeit": "morgens"}, 1.2),
    ({"ort": "Küche", "ding": "Klötzchen", "taetigkeit": "aufräumen", "rueckmeldung": "Lob", "zeit": "mittags"}, 1.5),
    ({"ort": "Flur", "ding": "Socke", "taetigkeit": "suchen", "gefuehl": "Neugier", "zeit": "nachmittags"}, 1.1),
    ({"ort": "Flur", "ding": "Schachfigur", "taetigkeit": "suchen", "rueckmeldung": "Lob", "zeit": "abends"}, 1.3),
    ({"ort": "Arbeitszimmer", "ding": "Schreibtisch", "taetigkeit": "zuschauen", "gefuehl": "Ruhe", "zeit": "morgens"}, 1.0),
    ({"ort": "Wohnzimmer", "ding": "Sofa", "taetigkeit": "ausruhen", "gefuehl": "Ruhe", "zeit": "nachts"}, 0.9),
    ({"ort": "Wohnzimmer", "ding": "Ball", "taetigkeit": "schießen", "rueckmeldung": "Lob", "gefuehl": "Stolz"}, 1.7),
    ({"ort": "Küche", "sinn": "Geräusch", "gefuehl": "Schreck", "taetigkeit": "stolpern", "zeit": "abends"}, 1.9),
    ({"ort": "Wohnzimmer", "taetigkeit": "Purzelbaum", "gefuehl": "Stolz", "rueckmeldung": "Lob", "zeit": "Wochenende"}, 1.6),
    ({"ort": "Balkon", "sinn": "Sonne", "taetigkeit": "umherspähen", "gefuehl": "Freude", "zeit": "mittags"}, 1.2),
    ({"ort": "Arbeitszimmer", "ding": "Buch", "taetigkeit": "erkunden", "gefuehl": "Neugier", "zeit": "nachmittags"}, 1.0),
]


def gedaechtnis_fuellen(ordner: Path) -> None:
    sys.path.insert(0, str(ROOT))
    from duckpilot.brain.erfahrung import Erfahrungsnetz, key

    netz = Erfahrungsnetz(ordner / "erfahrung.json")
    for runde in range(3):
        for ereignis, salienz in WOCHE:
            herkunft = ("duckpilot:sim", "reachy_mini:sim", "kopf")[(runde + len(ereignis)) % 3]
            netz.erleben({key(art, name): name for art, name in ereignis.items()}, salienz=salienz,
                         warum="Woche für die Website-Bilder", herkunft=herkunft)
            netz.tick(1.0)
    netz.save()


def musik(datei: Path, sekunden: float = 24.0, bpm: float = 112.0) -> None:
    """Ein erfundenes Stück: Bass auf jedem Schlag, heller Klang auf der Zwei und Vier – genug für die Taktanalyse."""
    rate = 22050
    takt = 60.0 / bpm
    werte = []
    for i in range(int(sekunden * rate)):
        t = i / rate
        schlag = t % takt
        n = int(t / takt)
        bass = math.sin(2 * math.pi * 55 * t) * math.exp(-schlag * 9)
        hell = (math.sin(2 * math.pi * 1760 * t) * math.exp(-schlag * 30)) if n % 2 else 0.0
        melodie = 0.25 * math.sin(2 * math.pi * (330 if (n // 4) % 2 else 392) * t)
        werte.append(max(-1.0, min(1.0, 0.6 * bass + 0.3 * hell + melodie)))
    puffer = io.BytesIO()
    with wave.open(puffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(v * 32000)) for v in werte))
    datei.write_bytes(puffer.getvalue())


# ── Szenen ──────────────────────────────────────────────────────────────
def zu(page, ansicht: str, teil: str | None = None, ms: int = 2500) -> None:
    """Ansicht wechseln wie ein Klick im Menü (eine Körperseite weckt den Körper)."""
    page.evaluate("([v, t]) => window.duckpilot.showView(v, t)", [ansicht, teil])
    page.wait_for_timeout(ms)


def klick(page, sel: str) -> None:
    """Klick ohne Playwrights Warten auf ein „ruhiges“ Element – die 3D-Ansicht hält die Seite ständig beschäftigt."""
    page.wait_for_selector(sel, state="attached", timeout=120000)
    page.evaluate("s => document.querySelector(s).click()", sel)


def verbunden(page) -> None:
    """Erst aufnehmen, wenn die Kopfleiste „verbunden“ zeigt – nie mit „Knowlin getrennt“."""
    page.wait_for_function("() => { const b = document.querySelector('#badge-link .dot');"
                           " return b && b.classList.contains('dot--good'); }", timeout=120000)


def bild_da(page, wo: str, timeout_ms: int = 90000) -> None:
    """Warten, bis die 3D-Ansicht in `wo` wirklich etwas zeigt – mit Pollens vollem Modell und Software-Grafik dauert ein
    Bild nach dem Umziehen der Leinwand manchmal Sekunden; vorher ist die Fläche einfarbig grau."""
    page.wait_for_function("""(wo) => { const c = document.querySelector(wo + ' canvas'); if (!c || !c.width) return false;
        const k = document.createElement('canvas'); k.width = 32; k.height = 32; const g = k.getContext('2d');
        g.drawImage(c, 0, 0, 32, 32); const d = g.getImageData(0, 0, 32, 32).data; let min = 255, max = 0;
        for (let i = 0; i < d.length; i += 4) { const v = d[i] + d[i + 1] + d[i + 2]; min = Math.min(min, v); max = Math.max(max, v); }
        return max - min > 60; }""", arg=wo, timeout=timeout_ms, polling=1000)


def punkt_gruen(png: bytes, page) -> bool:
    """Zeigt das aufgenommene Bild selbst den grünen Punkt „verbunden“? Unter Last hinkt das gemalte Bild dem DOM
    hinterher – dann kann im Bild noch „Knowlin getrennt“ stehen, obwohl die Seite schon wieder verbunden ist."""
    from PIL import Image

    box = page.evaluate("""() => { const d = document.querySelector('#badge-link .dot'); if (!d) return null;
        const r = d.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; }""")
    if not box:                                     # ohne Playwrights Warten auf Ruhe – die 3D-Ansicht rechnet ständig
        return False
    r, g, b = Image.open(io.BytesIO(png)).convert("RGB").getpixel((int(box["x"] + box["width"] / 2),
                                                                  int(box["y"] + box["height"] / 2)))
    return g > r + 30


def sagen(page, feld: str, text: str, warten_s: float = 5.0) -> None:
    verbunden(page)
    page.fill(feld, text, timeout=120000)
    page.press(feld, "Enter", timeout=120000)
    page.wait_for_timeout(int(warten_s * 1000))


def warten(page, ms: int = 1500) -> None:
    page.wait_for_timeout(ms)
    A.ruhig(page)


def szene_start(page, base, sprache):
    A.oeffnen(page, base)
    A.zum_kopf(page)
    for frage in (("Wer bist du?", "Who are you?"), ("Was kannst du?", "What can you do?")):
        sagen(page, "#kopf-text", frage[0 if sprache == "de" else 1], 2.5)
    verbunden(page)


def _koerper(page, base, modul, sprache, satz):
    A.einstellen(page, {"modul": modul, "backend": "sim", "sim_physik": False, "sprache": sprache})
    A.oeffnen(page, base)
    zu(page, "cockpit", ms=4000)
    sagen(page, "#say-text", satz, 5.0)
    verbunden(page)


def szene_cockpit(page, base, sprache):
    _koerper(page, base, "duckpilot", sprache, "Zeig mir, wie du dich freust" if sprache == "de" else "Show me how happy you are")


def szene_reachy(page, base, sprache):
    _koerper(page, base, "reachy_mini", sprache, "Schau dich mal um" if sprache == "de" else "Look around")


def szene_odi(page, base, sprache):
    _koerper(page, base, "open_duck_mini", sprache, "Tanz ein bisschen" if sprache == "de" else "Dance a little")


def szene_ari(page, base, sprache):
    """SO-101 an seiner Werkbank (seit 0.38.48): aufwecken, den roten Würfel greifen, Blick auf die Werkbank."""
    A.einstellen(page, {"modul": "so101", "backend": "sim", "sim_physik": False, "sprache": sprache})
    A.oeffnen(page, base)
    zu(page, "cockpit", ms=4000)
    senden = "([n, a]) => window.duckpilot.send({type: 'tool', name: n, args: a})"
    page.evaluate(senden, ["szene", {"aktion": "zuruecksetzen"}])     # die zweite Sprache beginnt mit leerem Greifer
    page.evaluate(senden, ["power", {"action": "stand_up"}])
    page.wait_for_timeout(5000)
    page.evaluate(senden, ["greifen", {"ding": "roter Würfel"}])
    page.wait_for_function("() => window.duckpilot.state && window.duckpilot.state.holding", timeout=180000)
    page.wait_for_timeout(4000)
    page.evaluate("() => { const s = window.duckpilot.scene; s.paused = false;"
                  " s.camera.position.set(-1.2, 1.2, -0.0); s.controls.target.set(-1.72, 0.82, -0.25); s.controls.update(); }")
    page.wait_for_timeout(3000)


def szene_stackchan(page, base, sprache):
    """Stack-chan (seit 0.38.58): auf dem Couchtisch, nah herangeholt, mit fröhlichem Gesicht – ein paar Bilder von Hand
    rechnen, dann die 3D-Ansicht anhalten, damit das Bild so bleibt."""
    satz = "Hallo Stacki, wie geht's dir?" if sprache == "de" else "Hi Stacki, how are you?"
    _koerper(page, base, "stackchan", sprache, satz)
    try:                                  # unter Last kommt die Antwort spät – abwarten, nur wenn sie ausbleibt: noch einmal
        page.wait_for_function("() => { const l = [...document.querySelectorAll('#log .msg')];"
                               " return l.some((m) => m.classList.contains('msg-user'))"
                               " && l[l.length - 1].classList.contains('msg-duck'); }", timeout=30000)
    except Exception:  # noqa: BLE001
        sagen(page, "#say-text", satz, 5.0)
    senden = "([n, a]) => window.duckpilot.send({type: 'tool', name: n, args: a})"
    page.evaluate(senden, ["emote", {"emotion": "freude"}])
    page.wait_for_timeout(600)
    # das fröhliche Gesicht fest fürs Bild (unter der Last der Aufnahme kommt der Zustand sonst manchmal zu spät an)
    page.evaluate("""() => { const s = window.duckpilot.scene; s.follow = false; if (s.intro) s.intro.done = true;
        s.camera.position.set(0.36, 0.56, -0.58); s.controls.target.set(0.56, 0.46, -0.22); s.controls.update();
        const d = s.duck, alt = d.update;
        d.update = (st, dt) => alt.call(d, { ...st, gesicht: { ...(st.gesicht || {}), ausdruck: 'froh', wach: true } }, dt);
        for (let i = 0; i < 12; i++) s._frame(); s.paused = true; d.update = alt;
        document.getElementById('ticker').replaceChildren(); }""")
    page.wait_for_timeout(500)


def szene_bittle(page, base, sprache):
    """Bittle X (seit 0.38.59): Bello mitten im Trab, schräg von vorn – wie bei Stacki ein paar Bilder von Hand rechnen
    (Trabschritt fest vorgegeben, damit keine Leerlauf-Geste dazwischenkommt), dann die 3D-Ansicht anhalten."""
    _koerper(page, base, "bittle", sprache, "Hallo Bello, wie geht's dir?" if sprache == "de" else "Hi Bello, how are you?")
    page.evaluate("""() => { const s = window.duckpilot.scene; s.follow = false; if (s.intro) s.intro.done = true;
        const d = s.duck, alt = d.update, st0 = window.duckpilot.state || {};
        const trab = { ...st0, powered: true, sitting: false, fallen: false, twist: { vx: 0.15, vy: 0, vyaw: 0 },
          gait_phase: 0.9, kopf_lage: { yaw: 0.25, pitch: 0.1 } };
        d.update = () => alt.call(d, trab, 0.2);
        for (let i = 0; i < 12; i++) d.update();
        const r = d.root.position, y = d.root.rotation.y, fx = Math.cos(y), fz = -Math.sin(y);
        s.camera.position.set(r.x + fx * 0.4 - fz * 0.3, 0.2, r.z + fz * 0.4 + fx * 0.3);
        s.controls.target.set(r.x + fx * 0.03, 0.07, r.z + fz * 0.03); s.controls.update();
        const rechts = s.camera.position.clone().setFromMatrixColumn(s.camera.matrixWorld, 0).multiplyScalar(0.11);
        s.camera.position.add(rechts); s.controls.target.add(rechts); s.controls.update();
        for (let i = 0; i < 6; i++) s._frame(); s.paused = true; d.update = alt;
        document.getElementById('ticker').replaceChildren(); }""")
    page.wait_for_timeout(500)


def szene_werte(page, base, sprache):
    """Knowlins Kopf (seit 0.38.42–0.38.45): Werte und Grenzen, darunter die Gedankenspur."""
    A.einstellen(page, {"modul": "so101", "backend": "sim", "sim_physik": False, "sprache": sprache})
    A.oeffnen(page, base)
    zu(page, "cockpit", ms=3000)
    zu(page, "persoenlichkeit", ms=3000)
    page.evaluate("() => document.getElementById('werte-karte').scrollIntoView({block: 'start'})")
    page.wait_for_timeout(2500)


def szene_synapsen(page, base, sprache):
    A.einstellen(page, {"modul": "duckpilot", "sprache": sprache})
    A.oeffnen(page, base)
    A.zum_kopf(page)
    A.ansicht(page, "memory")
    page.evaluate("() => document.getElementById('brain').closest('section, .card').scrollIntoView({block: 'start'})")
    page.wait_for_timeout(5000)


def szene_charakter(page, base, sprache):
    A.einstellen(page, {"modul": "duckpilot", "sprache": sprache})
    A.oeffnen(page, base)
    zu(page, "cockpit")
    zu(page, "persoenlichkeit")


def szene_tanz(page, base, sprache, ordner):
    A.einstellen(page, {"modul": "duckpilot", "sprache": sprache})
    A.oeffnen(page, base)
    zu(page, "cockpit")
    zu(page, "tricks", "tanz")
    datei = ordner / "stueck.wav"
    if not datei.exists():
        musik(datei)
    page.set_input_files("#tanz-datei", str(datei), timeout=120000)
    page.wait_for_selector("#tanz-aktionen:not([hidden])", timeout=180000)
    page.check("input[name=enten-tanz][value='3']", force=True)
    page.wait_for_timeout(2500)
    klick(page, "#tanz-probe")
    page.wait_for_timeout(5000)
    bild_da(page, "#tanz-vorschau")
    verbunden(page)


def szene_team(page, base, sprache):
    A.einstellen(page, {"modul": "duckpilot", "sprache": sprache})
    A.oeffnen(page, base)
    zu(page, "cockpit")
    zu(page, "tricks", "team")
    page.evaluate("() => document.querySelector(\"input[name=enten-team][value='4']\").click()")
    page.wait_for_function("() => !document.querySelector('[data-enten-modus=tanzen]').disabled", timeout=120000)
    klick(page, "[data-enten-modus=tanzen]")
    page.wait_for_timeout(5000)
    # erst die Anfahrt beim Öffnen abwarten – sie setzt die Kamera Bild für Bild und überschriebe sonst die Einstellung
    # (mit Pollens vollem Modell und Software-Grafik dauert sie lange; ihr Startpunkt liegt hinter der Wand: graues Bild)
    page.wait_for_function("() => { const s = window.duckpilot.scene; return !s.intro || s.intro.done; }",
                           timeout=180000, polling=1000)
    # Kamera schräg von oben auf die Mitte des Rudels – die Website zeigt nur die Vorschau, da soll das ganze Rudel
    # drin sein. _wunsch ist der Abstand, den die Kamera beim Ausweichen hält (duck3d.js)
    page.evaluate("""() => { const s = window.duckpilot.scene; s.follow = false;
      const alle = [s.duck.root.position, ...[...(s.enten || new Map()).values()].map((e) => e.root.position)];
      const m = alle.reduce((a, v) => ({ x: a.x + v.x / alle.length, z: a.z + v.z / alle.length }), { x: 0, z: 0 });
      s.controls.target.set(m.x, 0.08, m.z); s.camera.position.set(m.x - 1.9, 1.2, m.z - 1.0);
      s._wunsch = s.camera.position.distanceTo(s.controls.target); s.controls.update(); }""")
    page.wait_for_timeout(6000)
    bild_da(page, "#team-vorschau")
    verbunden(page)


def szene_akrobatik(page, base, sprache):
    A.einstellen(page, {"modul": "duckpilot", "sprache": sprache})
    A.oeffnen(page, base)
    zu(page, "cockpit")
    zu(page, "akrobatik", ms=4000)
    klick(page, "#ak-exercises li:nth-child(2) button")
    # erst warten, bis das Üben läuft (ein Ergebnis aus der anderen Sprache steht sonst schon da), dann bis es fertig ist
    page.wait_for_function("() => !!document.querySelector('#ak-exercises .btn--ghost')", timeout=60000)
    page.wait_for_function("() => !document.querySelector('#ak-exercises .btn--ghost')", timeout=300000)
    page.wait_for_timeout(3000)


TRAINING_BLICK = "3.6,2.6,5.2,-0.6,0,-0.6"    # Kamera x,y,z und Blickziel x,y,z im Trainingsfeld (Meter)


def szene_training(page, base, sprache):
    A.einstellen(page, {"modul": "duckpilot", "sprache": sprache})
    A.oeffnen(page, base)
    zu(page, "cockpit")
    zu(page, "training", ms=3000)
    # seit 0.38.40 („bei Lernen ist auf der Website noch ein Bild mit der Backup-Ente“): warten, bis das Feld die
    # Originalfigur zeigt – sie wird erst nach der einfachen Ente in den Bildbogen gezeichnet
    page.wait_for_function("() => /^original/.test(document.getElementById('tr-feld-canvas')?.dataset.figur || '')",
                           timeout=420000)
    # Bildbogen steht jetzt – Ansicht neu öffnen, damit die Kamera wieder nah beginnt (vorher war sie schon weit weg)
    zu(page, "cockpit")
    zu(page, "training", ms=3000)
    page.wait_for_function("() => /^original/.test(document.getElementById('tr-feld-canvas')?.dataset.figur || '')",
                           timeout=420000)
    page.wait_for_timeout(8000)
    # seit 0.38.56 („nimm mal lieber das Bild bei Lernen“): fester Blick schräg von oben übers volle Feld – Rampen vorn,
    # Matten rechts – statt des Moments der gleitenden Keynote-Kamera, die headless weit draußen und flach stand
    page.evaluate(f"() => {{ const c = document.getElementById('tr-feld-canvas'); c.dataset.blick = '{TRAINING_BLICK}';"
                  " c.feldZeichnen(); }")
    page.wait_for_timeout(1500)


SZENEN = {"start": szene_start, "cockpit": szene_cockpit, "reachy": szene_reachy, "odi": szene_odi, "ari": szene_ari,
          "stackchan": szene_stackchan, "bittle": szene_bittle,
          "werte": szene_werte,
          "synapsen": szene_synapsen, "charakter": szene_charakter, "tanz": szene_tanz, "team": szene_team,
          "akrobatik": szene_akrobatik, "training": szene_training}


def pollen_modelle_verlinken(ordner: Path) -> bool:
    """Pollens gebaute Modelle aus dem eigenen Datenordner (Knowlin lädt sie beim ersten Start) in den leeren Datenordner
    der Aufnahmen verlinken – erst nach dem Startbild (seit 0.38.56): Die Startseite rendert sonst Porträts aus ihnen,
    und Startbild, README-Banner und Vorschaubild sollen ohne Pollens Material auskommen (kein Bildnachweis nötig)."""
    from duckpilot.settings import data_dir

    # Knowlin sucht sie neben der Einstellungsdatei (`modell.store()`: settings_path().parent) – hier also im Arbeitsordner
    quelle, ziel = data_dir() / "pollen-modell", ordner / "pollen-modell"
    if not (quelle / "ansicht.dpm").exists():
        print(f"Hinweis: Pollens Modelle fehlen in {quelle} – Microduck und Reachy erscheinen als einfache Gestalt. "
              "Einmal Knowlin starten (lädt sie) oder: python -m duckpilot.modell", flush=True)
        return False
    if not ziel.exists():
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.symlink_to(quelle, target_is_directory=True)
    return True


def server_starten(ordner: Path, port: int) -> subprocess.Popen:
    """Server aus diesem Stand (mit Pollens Ansichtsmodellen), mit leerem Datenordner und eigenen Einstellungen."""
    env = dict(os.environ, DUCKPILOT_SETTINGS=str(ordner / "settings.json"), DUCKPILOT_OFFLINE="1",
               XDG_DATA_HOME=str(ordner / "daten"), LOCALAPPDATA=str(ordner / "daten"), PYTHONPATH=str(ROOT))
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("DUCKPILOT_MODELL", None)
    (ordner / "settings.json").write_text(json.dumps({"backend": "sim", "sim_physik": False, "gehirn": "claude"}),
                                          encoding="utf-8")
    log = open(ordner / "server.log", "w", encoding="utf-8")  # noqa: SIM115 – lebt so lange wie der Server
    proc = subprocess.Popen([sys.executable, "-m", "duckpilot", "--no-browser", "--port", str(port), "--memory",
                             str(ordner / "mem.json")], cwd=ROOT, env=env, stdout=log, stderr=log)
    for _ in range(120):
        try:
            import socket

            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return proc
        except OSError:
            if proc.poll() is not None:
                raise SystemExit(f"Server ist abgebrochen, siehe {ordner / 'server.log'}") from None
            time.sleep(0.5)
    proc.terminate()
    raise SystemExit("Server antwortet nicht")


def speichern(png: bytes, name: str, sprache: str, ziel: Path) -> None:
    from PIL import Image

    roh = Image.open(io.BytesIO(png)).convert("RGB")
    ziel.mkdir(parents=True, exist_ok=True)
    bild = roh.resize((BREITE, HOEHE), Image.LANCZOS)
    bild.save(ziel / f"{name}-{sprache}-1600.webp", quality=88, method=6)
    bild.resize((900, round(900 * HOEHE / BREITE)), Image.LANCZOS).save(ziel / f"{name}-{sprache}-900.webp",
                                                                        quality=86, method=6)


# README: dieselben Aufnahmen als PNG (GitHub zeigt WebP zwar an, die README soll aber überall gehen)
README = {"start": "startseite", "cockpit": "cockpit", "synapsen": "synapsen", "charakter": "charakter", "reachy": "reachy"}


def readme_bilder() -> None:
    from PIL import Image

    for name, ziel in README.items():
        for sprache, endung in (("de", ""), ("en", "-en")):
            quelle = ZIEL / f"{name}-{sprache}-1600.webp"
            if quelle.exists():
                Image.open(quelle).convert("RGB").save(ROOT / "docs" / "bilder" / f"{ziel}{endung}.png", optimize=True)


def main(argv: list[str] | None = None) -> int:
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ordner")
    ap.add_argument("--nur", default="", help="nur diese Szenen, durch Komma getrennt")
    ap.add_argument("--probe", action="store_true", help="Bilder nur in den Arbeitsordner, Website unverändert")
    ap.add_argument("--sprachen", default="de,en")
    a = ap.parse_args(argv)
    ordner = Path(a.ordner).resolve()
    ordner.mkdir(parents=True, exist_ok=True)
    gedaechtnis_fuellen(ordner)
    ziel = ordner / "bilder" if a.probe else ZIEL
    namen = [n for n in a.nur.split(",") if n] or list(SZENEN)
    port = A.freier_port()
    proc = server_starten(ordner, port)
    base = f"http://127.0.0.1:{port}"
    t0 = time.monotonic()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            # erst die Startbilder (ohne Pollens Modelle), dann alle übrigen mit ihnen
            reihe = [(n, s) for n in namen if n == "start" for s in a.sprachen.split(",")] + \
                [(n, s) for s in a.sprachen.split(",") for n in namen if n != "start"]
            for name, sprache in reihe:
                if name != "start":
                    pollen_modelle_verlinken(ordner)
                page = b.new_page(viewport={"width": BREITE, "height": HOEHE})
                A.oeffnen(page, base)
                # weitere Enten bleiben sonst aus der Team-Szene stehen und laufen durch die nächsten Bilder
                A.einstellen(page, {"sprache": sprache, "weitere_enten": 0})
                fn = SZENEN[name]
                fn(page, base, sprache, ordner) if name == "tanz" else fn(page, base, sprache)
                # unter Last (Pollens volles Modell, Software-Grafik) reißt die Verbindung beim Aufnehmen manchmal
                # kurz ab – dann stünde „Knowlin getrennt“ im Bild: nachsehen und notfalls neu aufnehmen
                gut = "() => !!document.querySelector('#badge-link .dot.dot--good')"
                for _ in range(6):
                    verbunden(page)
                    # zwei gezeichnete Bilder abwarten: bei langsamer Software-Grafik hinkt das Bild dem DOM hinterher
                    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
                    page.wait_for_timeout(1500)
                    vorher = page.evaluate(gut)
                    png = page.screenshot(timeout=180000)
                    if vorher and page.evaluate(gut) and punkt_gruen(png, page):
                        break
                speichern(png, name, sprache, ziel)
                print(f"{name} ({sprache}) → {ziel}", flush=True)
                page.close()
            b.close()
    finally:
        proc.terminate()
    if not a.probe:
        readme_bilder()
    print(f"fertig in {time.monotonic() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
