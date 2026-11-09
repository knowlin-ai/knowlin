"""Bilder für knowlin.de und die README aus dem laufenden Programm aufnehmen (seit 0.38.39).

Hinweis zur Website: „Einige Bilder sind noch nicht gut … besonders die, wo du nur Ränder ergänzt hast, weil das
Format nicht gepasst hatte“ – und: „zeig mehr Features, das soll ja WOW-Effekt erzeugen“. Bisher entstanden die Bilder
von Hand und einzelne Ausschnitte wurden mit Rand aufs Format gebracht. Jetzt nimmt dieses Werkzeug jedes Bild als ganzes
Programmfenster auf – gleich groß, in voller Breite (1600 px), auf Deutsch und Englisch, bei jeder Version gleich:

    python tools/website_bilder.py <arbeitsordner> [--nur start,tanz] [--probe]

Ergebnis: `website/bilder/<name>-<de|en>-1600.webp` und `-900.webp`. Mit `--probe` landen die Bilder nur im
Arbeitsordner (zum Ansehen), die Website bleibt unberührt.

Läuft wie die Abnahme im Simulator ohne Netz und ohne Claude – aber aus der **öffentlichen Fassung** (wird in den
Arbeitsordner exportiert): Dort fehlen Pollens Ansichtsmodelle für Microduck und Reachy (CC BY-NC-SA), sie erscheinen nie
auf der Website. Für die Akrobatik bekommt die Physik nur Pollens Physikmodell (`--physik-modell`, ohne `ansicht.dpm`):
gerechnet wird mit Pollens Maßen, gezeigt wird das eigene, einfache Modell. Das Gedächtnis bekommt vorher eine erfundene Woche mit Erlebnissen, damit das Netz zu
sehen ist; Personen kommen darin nicht vor.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import shutil
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
    # Kamera schräg von oben auf die Mitte des Rudels – die Website zeigt nur die Vorschau, da soll das ganze Rudel
    # drin sein. _wunsch ist der Abstand, den die Kamera beim Ausweichen hält (duck3d.js)
    page.evaluate("""() => { const s = window.duckpilot.scene; s.follow = false;
      const alle = [s.duck.root.position, ...[...(s.enten || new Map()).values()].map((e) => e.root.position)];
      const m = alle.reduce((a, v) => ({ x: a.x + v.x / alle.length, z: a.z + v.z / alle.length }), { x: 0, z: 0 });
      s.controls.target.set(m.x, 0.08, m.z); s.camera.position.set(m.x - 1.9, 1.2, m.z - 1.0);
      s._wunsch = s.camera.position.distanceTo(s.controls.target); s.controls.update(); }""")
    page.wait_for_timeout(6000)
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


def szene_training(page, base, sprache):
    A.einstellen(page, {"modul": "duckpilot", "sprache": sprache})
    A.oeffnen(page, base)
    zu(page, "cockpit")
    zu(page, "training", ms=3000)
    page.wait_for_timeout(8000)


HOCHKANT = {"handy"}


def szene_handy(page, base, sprache):
    """Am Handy: Cockpit mit Steuerkreuz und Gespräch – so sieht die Fernbedienung im Heimnetz aus."""
    _koerper(page, base, "duckpilot", sprache, "Tanz für mich" if sprache == "de" else "Dance for me")


SZENEN = {"start": szene_start, "handy": szene_handy, "cockpit": szene_cockpit, "reachy": szene_reachy, "odi": szene_odi,
          "synapsen": szene_synapsen, "charakter": szene_charakter, "tanz": szene_tanz, "team": szene_team,
          "akrobatik": szene_akrobatik, "training": szene_training}


def oeffentlich_starten(ordner: Path, port: int, physik_modell: Path | None) -> subprocess.Popen:
    """Server aus der öffentlichen Fassung, mit leerem Datenordner (kein nachgeladenes Pollen-Modell)."""
    quelle = ordner / "oeffentlich"
    if not (quelle / "duckpilot").is_dir():
        subprocess.run([sys.executable, str(ROOT / "tools" / "export_public.py"), str(quelle)], check=True,
                       stdout=subprocess.DEVNULL)
    for verboten in ("microduck.dpm", "reachy_mini.dpm"):
        if (quelle / "duckpilot" / "server" / "static" / "model" / verboten).exists():
            raise SystemExit(f"Pollens Modell {verboten} in der öffentlichen Fassung – Abbruch")
    env = dict(os.environ, DUCKPILOT_SETTINGS=str(ordner / "settings.json"), DUCKPILOT_OFFLINE="1",
               XDG_DATA_HOME=str(ordner / "daten"), LOCALAPPDATA=str(ordner / "daten"), PYTHONPATH=str(quelle))
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("DUCKPILOT_MODELL", None)
    if physik_modell and (physik_modell / "physik.xml").exists():
        nur = ordner / "nur-physik"
        if not nur.exists():
            nur.mkdir()
            shutil.copy2(physik_modell / "physik.xml", nur / "physik.xml")
            if (physik_modell / "quelle").is_dir():
                shutil.copytree(physik_modell / "quelle", nur / "quelle")
        env["DUCKPILOT_MODELL"] = str(nur)          # ohne ansicht.dpm: gezeigt wird das eigene Modell
    (ordner / "settings.json").write_text(json.dumps({"backend": "sim", "sim_physik": False, "gehirn": "claude"}),
                                          encoding="utf-8")
    log = open(ordner / "server.log", "w", encoding="utf-8")  # noqa: SIM115 – lebt so lange wie der Server
    proc = subprocess.Popen([sys.executable, "-m", "duckpilot", "--no-browser", "--port", str(port), "--memory",
                             str(ordner / "mem.json")], cwd=quelle, env=env, stdout=log, stderr=log)
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


# Handy: hochkant, doppelte Pixeldichte (ohne 3D-Last, das Cockpit am Handy zeigt die Bühne klein)
HANDY = (390, 844)


def speichern(png: bytes, name: str, sprache: str, ziel: Path) -> None:
    from PIL import Image

    roh = Image.open(io.BytesIO(png)).convert("RGB")
    ziel.mkdir(parents=True, exist_ok=True)
    if name in HOCHKANT:
        roh.save(ziel / f"{name}-{sprache}-780.webp", quality=88, method=6)
        roh.resize((390, round(390 * roh.height / roh.width)), Image.LANCZOS).save(
            ziel / f"{name}-{sprache}-390.webp", quality=86, method=6)
        return
    bild = roh.resize((BREITE, HOEHE), Image.LANCZOS)
    ziel.mkdir(parents=True, exist_ok=True)
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
    ap.add_argument("--physik-modell", type=Path, default=None,
                    help="Ordner mit Pollens physik.xml (und quelle/) – für die Akrobatik; ansicht.dpm wird nie benutzt")
    a = ap.parse_args(argv)
    ordner = Path(a.ordner).resolve()
    ordner.mkdir(parents=True, exist_ok=True)
    gedaechtnis_fuellen(ordner)
    ziel = ordner / "bilder" if a.probe else ZIEL
    namen = [n for n in a.nur.split(",") if n] or list(SZENEN)
    port = A.freier_port()
    proc = oeffentlich_starten(ordner, port, a.physik_modell)
    base = f"http://127.0.0.1:{port}"
    t0 = time.monotonic()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            for sprache in a.sprachen.split(","):
                for name in namen:
                    groesse = {"width": HANDY[0], "height": HANDY[1]} if name in HOCHKANT else {"width": BREITE, "height": HOEHE}
                    page = b.new_page(viewport=groesse, device_scale_factor=2 if name in HOCHKANT else 1,
                                      is_mobile=name in HOCHKANT, has_touch=name in HOCHKANT)
                    A.oeffnen(page, base)
                    # weitere Enten bleiben sonst aus der Team-Szene stehen und laufen durch die nächsten Bilder
                    A.einstellen(page, {"sprache": sprache, "weitere_enten": 0})
                    fn = SZENEN[name]
                    fn(page, base, sprache, ordner) if name == "tanz" else fn(page, base, sprache)
                    verbunden(page)
                    speichern(page.screenshot(timeout=180000), name, sprache, ziel)
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
