"""Eine Prüfkette für alles – vor jedem Push (seit 0.38.35, Architektur-Etappe A4).

Auftrag: „damit Fix-Schleifen nicht immer so riesig sind“. Bisher lagen die Prüfungen auf acht Werkzeuge verteilt,
und wer eines ausließ (z. B. die Abnahme gegen das installierte Paket), fand Fehler erst beim Nutzer. Diese Kette lässt
alle nacheinander laufen und schreibt einen Bericht:

    python tools/pruefen_alles.py <ordner> [--axe axe.min.js] [--eslint <ordner mit node_modules/.bin/eslint>]
                                           [--schnell] [--ohne website]

1. ruff, eslint, Sprachkatalog
2. Wächter                   – keine privaten Namen, Schlüssel oder Dateien im Repo (tools/waechter.py)
3. pytest                    – Pollens Modell in einen eigenen Datenordner laden, dann alle Tests mit echter Physik
4. Paket                     – Rad bauen, in eigene Umgebung installieren, Rauchtest außerhalb des Quellordners
5. Abnahme (installiert)     – Browser-Abnahme gegen das installierte Paket (nicht mit --schnell)
6. Website                   – Bau und Prüfung von knowlin.de (nicht mit --schnell)

Rückgabewert 0 nur, wenn alles bestanden ist. Bericht: `<ordner>/pruefkette.md`.

Seit 0.38.41 („Durchlaufzeiten … verbrauchen extrem viele Tokens und dauern sehr lange“): Die teuren Teile
merken sich, mit welchem Stand ihrer Dateien sie zuletzt bestanden haben (`~/.cache/knowlin-pruefkette/stand.json`).
Ist ihr Bereich unverändert, werden sie übersprungen – „Code“ (pytest, öffentliche Fassung, Paket, Abnahme) und
„Website“ (Bau und Prüfung, dazu ihr Test) getrennt. `--alles` lässt alles laufen (vor jedem Release Pflicht).
Die öffentliche Fassung läuft nur noch einmal (mit MuJoCo und Pollens Modell); die Fassung ohne Physik prüft GitHub
bei jedem Push ohnehin („Prüfen“).
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
STAND = Path.home() / ".cache" / "knowlin-pruefkette" / "stand.json"
# private Notizen ändern nichts an Code oder Website
NOTIZEN = {"Gespraechsnotizen.md", "Releaseplan.md", "Microduck-Notizen.md", "Konzept-Geist.md", "ZWEIG.md", "CLAUDE.md"}
WEBSITE = ("website/", "docs/bilder/", "tools/website", "tests/test_website_seo.py")


def _dateien() -> list[str]:
    r = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True,
                       check=True)
    return sorted(d for d in r.stdout.splitlines()
                  if d not in NOTIZEN and not d.startswith("Archiv/") and "__pycache__" not in d and not d.endswith(".pyc") and (ROOT / d).is_file())


def fingerabdruck(bereich: str) -> str:
    """Prüfsumme über die Dateien eines Bereichs: „website“ (Website, ihre Bilder, Werkzeuge und Test, die Demo-Dateien
    aus der App und die Version) oder „code“ (alles andere ohne private Notizen)."""
    import hashlib
    h = hashlib.sha256()
    for d in _dateien():
        web = d.startswith(WEBSITE)
        if bereich == "website":
            if not (web or d in ("pyproject.toml", "README.md", "README.en.md", "NOTICE", "LICENSE")
                    or d.startswith("duckpilot/server/static/vendor/") or d.endswith((".dpm", "3d.js", "duckmodel.js"))):
                continue
        elif web:
            continue
        h.update(d.encode() + b"\0" + hashlib.sha256((ROOT / d).read_bytes()).digest())
    return h.hexdigest()


def stand_lesen() -> dict[str, str]:
    try:
        import json
        return json.loads(STAND.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def stand_merken(bereich: str, wert: str) -> None:
    import json
    s = stand_lesen()
    s[bereich] = wert
    STAND.parent.mkdir(parents=True, exist_ok=True)
    STAND.write_text(json.dumps(s, indent=1), encoding="utf-8")


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
    ap.add_argument("--alles", action="store_true", help="auch unveränderte Bereiche prüfen (vor jedem Release)")
    ap.add_argument("--ohne", action="append", default=[], help="Schritt auslassen (website, abnahme, paket, oeffentlich)")
    a = ap.parse_args(argv)
    ordner = Path(a.ordner).resolve()
    if ordner.exists():
        shutil.rmtree(ordner)
    ordner.mkdir(parents=True)
    k = Kette(ordner)
    py = sys.executable
    axe = ["--axe", a.axe] if a.axe else []
    # pytest auf allen Kernen, wenn pytest-xdist da ist (seit 0.38.41: 5 min → 2,5 min mit zwei Kernen)
    import importlib.util
    par = ["-n", "auto"] if importlib.util.find_spec("xdist") else []

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

    k.schritt("Wächter (Namen, Schlüssel, private Dateien)", [py, "tools/waechter.py"], ok_wenn="sauber")

    stand = stand_lesen()
    code, web = fingerabdruck("code"), fingerabdruck("website")
    code_neu = a.alles or stand.get("code") != code
    web_neu = a.alles or stand.get("website") != web
    unveraendert = not code_neu
    venv_py = None
    if unveraendert:
        k.uebersprungen("pytest, Paket, Abnahme", "Code unverändert seit dem letzten Bestehen")
    else:
        # wie der Lauf „physik“ bei GitHub: Pollens Modell von seiner Quelle in einen eigenen Datenordner, dann alle
        # Tests mit echter Physik (seit 0.38.42 gibt es keinen privaten Stand mehr mit eingebautem Modell)
        daten = dict(os.environ, XDG_DATA_HOME=str(ordner / "daten"), LOCALAPPDATA=str(ordner / "daten"))
        daten.pop("DUCKPILOT_SETTINGS", None)
        k.schritt("Modell laden", [py, "-m", "duckpilot.modell"], env=daten, ok_wenn="physik", timeout=900)
        k.schritt("pytest", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", *par], env=daten)
        if "paket" in a.ohne:
            k.uebersprungen("Paket", "--ohne paket")
        else:
            rad, venv = ordner / "rad", ordner / "venv"
            if (k.schritt("Paket: Rad bauen", [py, "-m", "pip", "wheel", "-q", "--no-deps", "-w", str(rad), "."])
                    and k.schritt("Paket: Umgebung", [py, "-m", "venv", "--system-site-packages", str(venv)])):
                venv_py = str(venv / ("Scripts" if os.name == "nt" else "bin") / "python")
                raeder = sorted(rad.glob("*.whl"))
                if k.schritt("Paket: installieren", [venv_py, "-m", "pip", "install", "-q", "--no-deps", str(raeder[-1])]):
                    k.schritt("Paket: Rauchtest", [venv_py, str(ROOT / "tools" / "paket_rauchtest.py")], cwd=ordner,
                              ok_wenn="in Ordnung")
            for weg in ("build", "knowlin.egg-info"):
                shutil.rmtree(ROOT / weg, ignore_errors=True)

    if unveraendert:
        pass
    elif a.schnell or "abnahme" in a.ohne:
        k.uebersprungen("Abnahme (installiert)", "--schnell" if a.schnell else "--ohne abnahme")
    elif venv_py is None:
        k.uebersprungen("Abnahme (installiert)", "kein installiertes Paket")
    else:
        k.schritt("Abnahme (installiert)", [py, "tools/abnahme.py", str(ordner / "abnahme"), *axe,
                                            "--installiert", venv_py], timeout=5400)
    code_ok = all(ok for _, ok, _, _ in k.zeilen)       # einschließlich ruff, eslint und Sprachkatalog
    if a.schnell or "website" in a.ohne:
        k.uebersprungen("Website", "--schnell" if a.schnell else "--ohne website")
    elif not web_neu:
        k.uebersprungen("Website", "Website unverändert seit dem letzten Bestehen")
    else:
        w0 = len(k.zeilen)
        if not code_neu:     # sonst lief der Test schon mit pytest
            k.schritt("Website-Test", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_website_seo.py"])
        k.schritt("Website", [py, "tools/website_pruefen.py", str(ordner / "website"), *axe], timeout=2400)
        if all(ok for _, ok, _, _ in k.zeilen[w0:]) and code_ok:
            stand_merken("website", web)
    # nur ein vollständiger Code-Durchgang zählt (nicht --schnell, nicht --ohne)
    if code_neu and code_ok and not a.schnell and not a.ohne and a.eslint and a.axe:
        stand_merken("code", code)
    return 0 if k.bericht() else 1


if __name__ == "__main__":
    raise SystemExit(main())
