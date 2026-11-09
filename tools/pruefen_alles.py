"""Eine Prüfkette für alles – vor jedem Push (seit 0.38.35, Architektur-Etappe A4).

Auftrag: „damit Fix-Schleifen nicht immer so riesig sind“. Bisher lagen die Prüfungen auf acht Werkzeuge verteilt,
und wer eines ausließ (z. B. die Abnahme gegen das installierte Paket), fand Fehler erst beim Nutzer. Diese Kette lässt
alle nacheinander laufen und schreibt einen Bericht:

    python tools/pruefen_alles.py <ordner> [--axe axe.min.js] [--eslint <ordner mit node_modules/.bin/eslint>]
                                           [--schnell] [--ohne website]

1. ruff                      – Stil und Fehler (duckpilot, tests, tools)
2. eslint                    – Oberfläche (wenn --eslint angegeben)
3. Sprachkatalog             – keine fehlenden englischen Texte
4. pytest                    – alle Tests
5. öffentliche Fassung       – Export mit Geheimnis-Scan, dort alle Tests (ohne und mit MuJoCo)
6. Paket                     – Rad bauen, in eigene Umgebung installieren, Rauchtest außerhalb des Quellordners
7. Abnahme (installiert)     – Browser-Abnahme gegen das installierte Paket (nicht mit --schnell)
8. Website                   – Bau und Prüfung von knowlin.de (nicht mit --schnell)

Rückgabewert 0 nur, wenn alles bestanden ist. Bericht: `<ordner>/pruefkette.md`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Kette:
    def __init__(self, ordner: Path) -> None:
        self.ordner = ordner
        self.zeilen: list[tuple[str, bool, float, str]] = []

    def schritt(self, name: str, befehl: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None,
                ok_wenn: str | None = None, timeout: int = 3600) -> bool:
        print(f"── {name} …", flush=True)
        t0 = time.monotonic()
        try:
            r = subprocess.run(befehl, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
            ausgabe = (r.stdout or "") + (r.stderr or "")
            ok = r.returncode == 0 and (ok_wenn is None or ok_wenn in ausgabe)
        except subprocess.TimeoutExpired:
            ausgabe, ok = f"nach {timeout} s abgebrochen", False
        dauer = time.monotonic() - t0
        log = self.ordner / f"{len(self.zeilen) + 1:02d}-{name.split()[0].lower()}.log"
        log.write_text(ausgabe, encoding="utf-8")
        letzte = next((z for z in reversed(ausgabe.strip().splitlines()) if z.strip()), "")[:160]
        self.zeilen.append((name, ok, dauer, letzte))
        print(f"   {'OK  ' if ok else 'FEHL'} {dauer:5.0f} s  {letzte}", flush=True)
        return ok

    def uebersprungen(self, name: str, grund: str) -> None:
        self.zeilen.append((name, True, 0.0, f"übersprungen – {grund}"))
        print(f"── {name}: übersprungen – {grund}", flush=True)

    def bericht(self) -> bool:
        alles = all(ok for _, ok, _, _ in self.zeilen)
        z = [f"# Prüfkette – {'bestanden' if alles else 'NICHT bestanden'}", "",
             "| Schritt | Ergebnis | Dauer | Letzte Zeile |", "|---|---|---|---|"]
        z += [f"| {n} | {'✅' if ok else '❌'} | {d:.0f} s | {letzte.replace('|', '/')} |" for n, ok, d, letzte in self.zeilen]
        (self.ordner / "pruefkette.md").write_text("\n".join(z) + "\n", encoding="utf-8")
        print(f"\n{'Bestanden' if alles else 'NICHT bestanden'} – Bericht: {self.ordner / 'pruefkette.md'}")
        return alles


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ordner")
    ap.add_argument("--axe", help="axe.min.js für Abnahme und Website")
    ap.add_argument("--eslint", help="Ordner mit node_modules/.bin/eslint und eslint.config.mjs")
    ap.add_argument("--schnell", action="store_true", help="ohne Browser-Abnahme und Website")
    ap.add_argument("--ohne", action="append", default=[], help="Schritt auslassen (website, abnahme, paket, oeffentlich)")
    a = ap.parse_args(argv)
    ordner = Path(a.ordner).resolve()
    if ordner.exists():
        shutil.rmtree(ordner)
    ordner.mkdir(parents=True)
    k = Kette(ordner)
    py = sys.executable
    axe = ["--axe", a.axe] if a.axe else []

    ruff = shutil.which("ruff")
    k.schritt("ruff", [ruff, "check", "duckpilot", "tests", "tools"] if ruff else
              [py, "-m", "ruff", "check", "duckpilot", "tests", "tools"])
    if a.eslint:
        e = Path(a.eslint)
        static = ROOT / "duckpilot" / "server" / "static"
        k.schritt("eslint", [str(e / "node_modules" / ".bin" / "eslint"), "-c", str(e / "eslint.config.mjs"),
                             *sorted(str(p) for p in static.glob("*.js"))], cwd=static)
    else:
        k.uebersprungen("eslint", "ohne --eslint")
    k.schritt("Sprachkatalog", [py, "tools/i18n_texte.py"], ok_wenn=" 0 fehlen")
    k.schritt("pytest", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider"])

    oeffentlich = ordner / "oeffentlich"
    if "oeffentlich" in a.ohne:
        k.uebersprungen("öffentliche Fassung", "--ohne oeffentlich")
    elif k.schritt("öffentliche Fassung: Export", [py, "tools/export_public.py", str(oeffentlich)], ok_wenn="Geheimnis-Scan: sauber"):
        # wie die Prüfung bei GitHub: eigene Umgebung ohne Physik-Zusätze (dort gibt es kein MuJoCo, Physik-Tests
        # überspringen sich), Pollens Modell von GitHub in einen eigenen Datenordner. Mit MuJoCo und dem nachgeladenen
        # Modell im normalen Datenordner änderten sich sonst die privaten Tests (erster Lauf der Kette, 9.11.).
        venv_ci = Path.home() / ".cache" / "knowlin-pruefkette" / "venv"
        py_ci = str(venv_ci / ("Scripts" if os.name == "nt" else "bin") / "python")
        if not Path(py_ci).exists():
            k.schritt("öffentliche Fassung: Umgebung anlegen", [py, "-m", "venv", str(venv_ci)])
        k.schritt("öffentliche Fassung: Pakete", [py_ci, "-m", "pip", "install", "-q", "-r", "requirements.txt", "pytest"],
                  cwd=oeffentlich, timeout=1200)
        daten = dict(os.environ, XDG_DATA_HOME=str(ordner / "daten"), LOCALAPPDATA=str(ordner / "daten"))
        daten.pop("DUCKPILOT_SETTINGS", None)
        k.schritt("öffentliche Fassung: Modell laden", [py_ci, "-m", "duckpilot.modell"], cwd=oeffentlich, env=daten,
                  timeout=900)
        k.schritt("öffentliche Fassung: Tests", [py_ci, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=oeffentlich,
                  env=daten)
        # und einmal mit echter Physik (MuJoCo aus dieser Umgebung) gegen Pollens nachgeladenes Modell – wie der Lauf
        # „physik“ bei GitHub. Mit dem eingebauten privaten Modell gelang „Auf einem Bein“, mit Pollens nie (9.11.).
        # das Physik-Modell baut `duckpilot.modell` nur, wenn MuJoCo da ist – in der Umgebung oben fehlt es
        k.schritt("öffentliche Fassung: Physik-Modell", [py, "-m", "duckpilot.modell"], cwd=oeffentlich, env=daten,
                  ok_wenn="physik", timeout=900)
        k.schritt("öffentliche Fassung: Physik", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=oeffentlich,
                  env=daten)

    venv_py = None
    if "paket" in a.ohne or not oeffentlich.exists():
        k.uebersprungen("Paket", "--ohne paket oder ohne Export")
    else:
        rad = ordner / "rad"
        venv = ordner / "venv"
        if (k.schritt("Paket: Rad bauen", [py, "-m", "pip", "wheel", "-q", "--no-deps", "-w", str(rad), "."], cwd=oeffentlich)
                and k.schritt("Paket: Umgebung", [py, "-m", "venv", "--system-site-packages", str(venv)])):
            venv_py = str(venv / ("Scripts" if os.name == "nt" else "bin") / "python")
            raeder = sorted(rad.glob("*.whl"))
            if k.schritt("Paket: installieren", [venv_py, "-m", "pip", "install", "-q", "--no-deps", str(raeder[-1])]):
                k.schritt("Paket: Rauchtest", [venv_py, str(oeffentlich / "tools" / "paket_rauchtest.py")], cwd=ordner,
                          ok_wenn="in Ordnung")
        for weg in ("build",):
            shutil.rmtree(oeffentlich / weg, ignore_errors=True)

    if a.schnell or "abnahme" in a.ohne:
        k.uebersprungen("Abnahme (installiert)", "--schnell" if a.schnell else "--ohne abnahme")
    elif venv_py is None:
        k.uebersprungen("Abnahme (installiert)", "kein installiertes Paket")
    else:
        k.schritt("Abnahme (installiert)", [py, "tools/abnahme.py", str(ordner / "abnahme"), *axe,
                                            "--installiert", venv_py], timeout=5400)
    if a.schnell or "website" in a.ohne:
        k.uebersprungen("Website", "--schnell" if a.schnell else "--ohne website")
    else:
        k.schritt("Website", [py, "tools/website_pruefen.py", str(ordner / "website"), *axe], timeout=2400)
    return 0 if k.bericht() else 1


if __name__ == "__main__":
    raise SystemExit(main())
