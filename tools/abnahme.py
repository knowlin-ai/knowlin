"""Abnahmetest: spielt die Testschritte aus ZWEIG.md automatisch im Browser durch (seit 0.38.10, Wunsch des Maintainers).

Startet einen eigenen Server (Simulator, ohne Netz, ohne Claude) mit frischen Einstellungen in einem Arbeitsordner,
klickt sich mit Playwright durch Startseite, Kopf-Gespräch, Verkörperungen, Charakter, Stimme, Herkunft und Reachy
und schreibt einen Bericht (Markdown) mit Bildschirmfotos. Fasst nichts außerhalb des Arbeitsordners an.

    python tools/abnahme.py <arbeitsordner> [--port 8811] [--axe <pfad zu axe.min.js>]

Braucht `pip install playwright` und einen Chromium für Playwright. Ohne axe entfällt die Barrierefreiheits-Prüfung.
Rückgabe 0 = alles bestanden, 1 = mindestens eine Prüfung fehlgeschlagen.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class Bericht:
    def __init__(self, ordner: Path):
        self.ordner = ordner
        self.zeilen: list[tuple[str, bool, str]] = []
        self.bilder: list[tuple[str, str]] = []
        self.fehler_js: list[str] = []

    def pruefe(self, name: str, ok: bool, detail: str = "") -> bool:
        self.zeilen.append((name, bool(ok), detail))
        print(("OK   " if ok else "FEHL ") + name + (f" – {detail}" if detail and not ok else ""), flush=True)
        return bool(ok)

    def foto(self, page, name: str, titel: str) -> None:
        datei = f"{name}.png"
        page.screenshot(path=str(self.ordner / datei))
        self.bilder.append((datei, titel))

    @property
    def bestanden(self) -> bool:
        return all(ok for _, ok, _ in self.zeilen) and not self.fehler_js

    def schreiben(self, version: str, dauer: float) -> Path:
        n_ok = sum(1 for _, ok, _ in self.zeilen if ok)
        z = [f"# Abnahmetest {version}", "",
             f"{'Bestanden' if self.bestanden else 'NICHT bestanden'}: {n_ok} von {len(self.zeilen)} Prüfungen, "
             f"{len(self.fehler_js)} Skriptfehler im Browser · Dauer {dauer:.0f} s · Simulator, ohne Netz, ohne Claude", "",
             "| Prüfung | Ergebnis | Hinweis |", "|---|---|---|"]
        for name, ok, detail in self.zeilen:
            z.append(f"| {name} | {'✅' if ok else '❌'} | {detail.replace('|', '/')[:160]} |")
        if self.fehler_js:
            z += ["", "## Skriptfehler im Browser", ""] + [f"- `{f[:200]}`" for f in self.fehler_js]
        z += ["", "## Bildschirmfotos", ""] + [f"- {t}: `{d}`" for d, t in self.bilder]
        datei = self.ordner / "abnahme.md"
        datei.write_text("\n".join(z) + "\n", encoding="utf-8")
        return datei


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def server_starten(ordner: Path, port: int, python: str | None = None) -> subprocess.Popen:
    """`python`: ein anderes Python mit installiertem Paket (seit 0.38.33, „--installiert“) – dann läuft der Server
    außerhalb des Quellordners, damit wirklich das installierte Paket startet wie nach dem Installer."""
    (ordner / "settings.json").write_text(json.dumps({"backend": "sim", "sim_physik": False, "gehirn": "claude"}),
                                          encoding="utf-8")
    env = dict(os.environ, DUCKPILOT_SETTINGS=str(ordner / "settings.json"), DUCKPILOT_OFFLINE="1")
    env.pop("ANTHROPIC_API_KEY", None)                     # ohne Claude: prüft die festen Regeln, nicht das Modell
    if python:
        env.pop("PYTHONPATH", None)                        # wirklich das installierte Paket, nicht den Quellordner
    log = open(ordner / "server.log", "w", encoding="utf-8")  # noqa: SIM115 – lebt so lange wie der Server
    proc = subprocess.Popen([python or sys.executable, "-m", "duckpilot", "--no-browser", "--port", str(port),
                             "--memory", str(ordner / "mem.json")], cwd=ordner if python else ROOT, env=env,
                            stdout=log, stderr=log)
    for _ in range(120):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return proc
        except OSError:
            if proc.poll() is not None:
                raise SystemExit(f"Server ist abgebrochen, siehe {ordner / 'server.log'}") from None
            time.sleep(0.5)
    proc.terminate()
    raise SystemExit("Server antwortet nicht")


def einstellen(page, werte: dict) -> None:
    page.evaluate("w => fetch('/api/settings', {method: 'POST', headers: {'Content-Type': 'application/json'},"
                  " body: JSON.stringify(w)}).then(r => r.json())", werte)


def ruhig(page) -> None:
    """3D anhalten – headless rendert langsam und verzögert sonst alle Zeitgeber."""
    page.evaluate("() => { const s = window.duckpilot && window.duckpilot.scene;"
                  " if (s) { s.paused = true; s.render = () => {}; } }")


def oeffnen(page, base: str, ansicht: str = "start") -> None:
    """Lädt die Seite neu (ein reiner Wechsel des #-Teils lädt nicht)."""
    page.goto("about:blank")
    page.goto(f"{base}/#{ansicht}")
    page.wait_for_selector("#kopf-gruss", state="attached", timeout=60000)
    page.wait_for_timeout(2500)
    ruhig(page)


def ansicht(page, name: str) -> None:
    """Wechselt die Ansicht wie ein Klick im Menü, ohne neu zu laden."""
    page.evaluate("n => window.duckpilot.showView(n)", name)
    page.wait_for_timeout(2500)
    ruhig(page)


def zum_kopf(page) -> None:
    page.click("#rail-start")
    page.wait_for_function("() => document.body.classList.contains('im-kopf')", timeout=30000)
    page.wait_for_function("() => { const o = document.getElementById('einzug'); return !o || o.hidden; }", timeout=60000)
    page.wait_for_timeout(1500)


def kopf_sagen(page, text: str, warten_auf: str, timeout: int = 30000) -> str:
    """Schreibt Knowlin und wartet auf seine neue Antwortzeile (nicht die eigene „Du …“-Zeile)."""
    letzte = "() => { const z = [...document.querySelectorAll('.kopf-zeile')].slice(-1)[0]; return z ? z.textContent : ''; }"
    vorher = page.evaluate(letzte)
    page.fill("#kopf-text", text)
    page.press("#kopf-text", "Enter")
    page.wait_for_function(
        "([vorher, t]) => { const z = [...document.querySelectorAll('.kopf-zeile')].slice(-1)[0];"
        " const s = z ? z.textContent.trim() : '';"
        " return s && s !== vorher.trim() && !/^(Du|You)\\b/.test(s) && s.includes(t); }",
        arg=[vorher, warten_auf], timeout=timeout)
    return page.evaluate(letzte)


def axe(page, b: Bericht, axe_js: str | None, wo: str, selektor: str = "body") -> None:
    if not axe_js:
        return
    page.add_script_tag(content=axe_js)
    v = page.evaluate("s => axe.run(document.querySelector(s), {runOnly: ['wcag2a', 'wcag2aa']})"
                      ".then(r => r.violations.map(v => v.id + ' (' + v.nodes.length + ')'))", selektor)
    b.pruefe(f"Barrierefreiheit (axe, WCAG 2 AA): {wo}", not v, ", ".join(v))


# ── Inhalte je Körper (Fund aus dem Test 5.11.2026: „Logische Zusammenhänge und Inhalte sollten geprüft sein!“) ──
# Enten-Wörter (deutsch und englisch) – bei Reachy verboten
ENTENWORT = re.compile(r"\b(Enten?\w*|\w+ente|quak\w*|quack\w*|Schnabel\w*|watschel\w*|Gefieder\w*|ducks?|beaks?|"
                       r"waddl\w*|feathers?)\b", re.I)
# Namen und begründete Stellen, die ein Enten-Wort enthalten dürfen (auch Wörter, die nur auf „-ente“ enden)
ENTE_ERLAUBT = re.compile(r"Open Duck|Microduck|Duck Mini|Quacki|\b(intelligente|Akzente?|Momente?|Elemente?|Prozente?|"
                          r"Argumente?|Dokumente?|Instrumente?|Segmente?|Patente?|Talente?|Experimente?|Komponente\w*|"
                          r"Rente)\b|Enten? zu Besuch|ducks? visiting|duckpilot für die Enten|duckpilot for the ducks", re.I)
# „duckpilot“ nur als Paket, Codename, Befehl, Ordner oder Datei
DUCKPILOT_ERLAUBT = re.compile(r"Python-Paket duckpilot|Python package duckpilot|Codenamen der Module: duckpilot|"
                               r"module code names: duckpilot|%LOCALAPPDATA%\\duckpilot|duckpilot\.toml|-m duckpilot")
KOERPER_ANSICHTEN = [("cockpit", None), ("tricks", "tricks"), ("tricks", "tanz"), ("tricks", "team"), ("tricks", "hub"),
                     ("tricks", "spiele"), ("tricks", "zubehoer"), ("mentor", None), ("alltag", None), ("umgebung", None), ("persoenlichkeit", None),
                     ("stimme", "stimme"), ("stimme", "gespraech"), ("memory", None), ("knowlets", None),
                     ("akrobatik", None), ("parcours", None), ("training", None), ("dashboard", None),
                     ("settings", None), ("tricks", "pakete")]
KOPF_ANSICHTEN = [("start", None), ("memory", None), ("knowlets", None), ("settings", None), ("stimme", "stimme")]
NUR_MICRODUCK = {"akrobatik", "parcours", "training", "team", "hub", "zubehoer"}   # wie static/modul.js (Zubehör: Profil)
SICHTBARER_TEXT = """() => {
  for (const d of document.querySelectorAll('details')) d.open = true;      // auch zugeklappte Erklärungen
  const zeilen = document.body.innerText.split('\\n');                       // innerText: nur, was gerendert ist
  for (const e of document.querySelectorAll('[title],[aria-label],[placeholder],[alt]')) {
    if (!(e.checkVisibility ? e.checkVisibility() : e.offsetParent)) continue;
    for (const a of ['title', 'aria-label', 'placeholder', 'alt']) if (e.getAttribute(a)) zeilen.push(e.getAttribute(a));
  }
  zeilen.push(document.title);
  // der Gesprächsverlauf ist Fremdtext (Antworten, Namen) – den prüft die Ablaufprüfung oben
  const log = document.getElementById('log');
  const ohne = new Set(log ? log.innerText.split('\\n') : []);
  return [...new Set(zeilen.map((z) => z.trim()).filter((z) => z && !ohne.has(z)))];
}"""


def _verbotene_woerter(zeilen: list[str], reachy: bool) -> list[str]:
    funde = []
    for z in zeilen:
        if "duckpilot" in z.lower() and not DUCKPILOT_ERLAUBT.search(z):
            funde.append(z)
        elif reachy and ENTENWORT.search(ENTE_ERLAUBT.sub("", z)):
            funde.append(z)
    return funde


def inhalte_je_koerper(page, base: str, b: Bericht) -> None:
    """Je Körper (und bei Knowlin) und je Sprache den sichtbaren Text aller Ansichten sammeln und prüfen:
    nirgends „duckpilot“ außer der Erlaubt-Liste, bei Reachy keine Enten-Wörter."""
    if not page.url.startswith(base):
        oeffnen(page, base)                                     # einstellen() braucht die eigene Herkunft
    for sprache in ("de", "en"):
        for modul, name in (("duckpilot", "Microduck"), ("reachy_mini", "Reachy Mini"), ("open_duck_mini", "Open Duck"),
                            ("so101", "SO-101"), ("stackchan", "Stack-chan"),
                            ("bittle", "Bittle X")):   # Arm 0.38.47, Stack-chan .58, Bittle .59
            einstellen(page, {"modul": modul, "backend": "sim", "sim_physik": False, "sprache": sprache})
            oeffnen(page, base)                                 # Startseite; showView einer Körperseite weckt den Körper
            # Charakter ganz oben rechts (seit 0.46.2, Fund des Maintainers: Stacki hieß dort „Chaos-Ente“) – danach zurück
            vorher = page.evaluate("() => fetch('/api/settings').then((r) => r.json())"
                                   ".then((s) => [s.werte.energie, s.werte.humor])")
            einstellen(page, {"energie": 0.95, "humor": 0.95})
            reihen = [("Körper", KOERPER_ANSICHTEN)] + ([("Knowlin", KOPF_ANSICHTEN)] if modul == "duckpilot" else [])
            for wo, ansichten in reihen:
                if wo == "Knowlin":
                    zum_kopf(page)
                funde: list[str] = []
                stoesse: list[str] = []
                for v, teil in ansichten:
                    if modul != "duckpilot" and (v in NUR_MICRODUCK or teil in NUR_MICRODUCK):
                        continue                                  # bei Reachy und Open Duck gar nicht erreichbar
                    if modul != "reachy_mini" and teil == "spiele":
                        continue
                    page.evaluate("([n, t]) => window.duckpilot.showView(n, t)", [v, teil])
                    page.wait_for_timeout(800)
                    ruhig(page)
                    if v == "cockpit" and wo == "Körper":
                        klasse = {"duckpilot": "microduck", "reachy_mini": "reachy", "open_duck_mini": "open-duck",
                                  "so101": "so101", "stackchan": "stackchan", "bittle": "bittle"}[modul]
                        b.pruefe(f"Inhalte: Körper {name} ist geladen ({sprache})",
                                 page.evaluate("k => document.body.classList.contains('koerper-' + k)", klasse))
                        if sprache == "de":                       # jeder Körper, nicht nur Quacki und Reachy
                            ueberdeckungen(page, b, name)
                    if sprache == "de":
                        stoesse += [f"{v}/{teil or ''}: {s}" for s in page.evaluate(ANEINANDER_JS)]
                    keine_ente = modul in ("reachy_mini", "so101", "stackchan", "bittle") and wo == "Körper"
                    funde += [f"{v}/{teil or ''}: {z[:80]}" for z in _verbotene_woerter(page.evaluate(SICHTBARER_TEXT),
                                                                                       keine_ente)]
                titel = f"Inhalte {name if wo == 'Körper' else 'Knowlin (Kopf)'} ({sprache}): kein „duckpilot“" + \
                    (", keine Enten-Wörter" if modul in ("reachy_mini", "so101", "stackchan", "bittle") and wo == "Körper" else "")
                b.pruefe(titel, not funde, " · ".join(funde[:6]) + (f" (+{len(funde) - 6})" if len(funde) > 6 else ""))
                if sprache == "de":
                    b.pruefe(f"Ansichten {name if wo == 'Körper' else 'Knowlin (Kopf)'}: keine Karten ohne Abstand",
                             not stoesse, " · ".join(stoesse[:6]))
            if vorher and None not in vorher:
                einstellen(page, {"energie": vorher[0], "humor": vorher[1]})
    einstellen(page, {"modul": "duckpilot", "backend": "sim", "sim_physik": False, "sprache": "de"})


# Karten, die ohne Luft aneinanderstoßen (seit 0.38.57, Fund des Maintainers: „bei Wissen kleben immer noch die
# UI-Kacheln aneinander … ich dachte, das ist überall behoben“) – sichtbare Geschwister mit Rahmen oder Kartenklasse,
# übereinander, Lücke unter 4 px.
ANEINANDER_JS = r"""() => {
  const sichtbar = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.height > 4 && r.width > 4 && s.display !== 'none' && s.visibility !== 'hidden'; };
  const kartig = (e) => { const s = getComputedStyle(e);
    return /\b(card|dash|set-card|al-card)\b/.test(e.className) || (parseFloat(s.borderTopWidth) > 0
      && s.borderRadius !== '0px' && s.backgroundColor !== 'rgba(0, 0, 0, 0)'); };
  const v = [...document.querySelectorAll('section.view')].find((x) => !x.hidden);
  if (!v) return [];
  const funde = [];
  for (const el of v.querySelectorAll('*')) {
    if (!sichtbar(el) || !kartig(el)) continue;
    let n = el.nextElementSibling;
    while (n && !sichtbar(n)) n = n.nextElementSibling;
    if (!n || !kartig(n)) continue;
    const a = el.getBoundingClientRect(), b = n.getBoundingClientRect();
    if (Math.min(a.right, b.right) - Math.max(a.left, b.left) < 20) continue;
    const luecke = b.top - a.bottom;
    if (luecke >= -1 && luecke < 4) funde.push(`${el.id || el.className.split(' ')[0]} → ${n.id || n.className.split(' ')[0]}`);
  }
  return funde;
}"""


# Was über der 3D-Bühne schwebt (Zustand, Werkzeuge, Anzeige, Tastenhinweis, Gespräch), darf sich nicht überdecken –
# Hinweis 7.11.: „Entenbild als kleines Bild ist hinter dem Dialogfenster … sowas sollte dir bei der UI-Prüfung
# auffallen“. Geprüft wird je Breite (PC, schmale Bühne neben dem Gespräch, Handy).
UEBERDECKUNG_JS = """() => {
  const sicht = (el) => { const s = getComputedStyle(el); if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity === 0) return false;
    if (el.closest('[hidden]')) return false; const r = el.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const view = document.querySelector('#view-cockpit');
  const kinder = [...view.querySelectorAll(':scope > *, :scope > .stage > *, :scope > .stage > * > *')].filter((el) => {
    const p = getComputedStyle(el).position;
    return (p === 'absolute' || p === 'fixed' || el.classList.contains('talk')) && sicht(el) && el.tagName !== 'CANVAS'
      && !el.closest('.finder') && !el.classList.contains('stage');
  });
  const namen = kinder.map((el) => (el.id ? '#' + el.id : el.tagName.toLowerCase()) + (el.classList.length ? '.' + [...el.classList].join('.') : ''));
  const r = kinder.map((el) => el.getBoundingClientRect());
  const ueber = [];
  for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++) {
    if (kinder[i].contains(kinder[j]) || kinder[j].contains(kinder[i])) continue;
    const w = Math.min(r[i].right, r[j].right) - Math.max(r[i].left, r[j].left), h = Math.min(r[i].bottom, r[j].bottom) - Math.max(r[i].top, r[j].top);
    if (w > 4 && h > 4) ueber.push(`${namen[i]} × ${namen[j]} (${Math.round(w)}×${Math.round(h)})`);
  }
  // eine Tafel ohne sichtbaren Inhalt (nur das „?“) ist ein leeres Glas über der Bühne (Fund 12.11., Ari am PC)
  const tafel = view.querySelector('.hud-tele');
  if (tafel && sicht(tafel) && ![...tafel.children].some((c) => !c.matches('.hud-help-btn, .hud-help') && sicht(c)))
    ueber.push('.hud-tele ist leer – nur „?“ auf einem Glas');
  return { elemente: namen, ueber };
}"""


# Abstände (seit 0.38.26, Hinweis „hier scheint der Abstand nicht zu stimmen – das sollte bei den Design-Tests
# auffallen“): Schalter, Knöpfe und Auswahlfelder, die in einer Spalte übereinander stehen, brauchen Luft dazwischen.
ABSTAND_JS = """() => {
  const sichtbar = (e) => e.offsetParent && !e.closest('[hidden]') && e.getBoundingClientRect().height > 0;
  const innen = (e) => {                      // Inhaltskasten: Innenabstand zählt als Luft, der Rahmen nicht
    const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return { left: r.left, right: r.right, top: r.top + parseFloat(s.paddingTop), bottom: r.bottom - parseFloat(s.paddingBottom) };
  };
  const name = (e) => (e.closest('[id]') ? '#' + e.closest('[id]').id + ' ' : '') + (e.textContent || '').trim().slice(0, 24);
  const funde = [];
  const gruppen = new Map();
  for (const e of document.querySelectorAll('main label.switch, main .btn, main .farbkarte, main .field, main .seg, main p.field-help')) {
    if (!sichtbar(e)) continue;
    const p = e.parentElement; if (!gruppen.has(p)) gruppen.set(p, []); gruppen.get(p).push(e);
  }
  for (const liste of gruppen.values()) {
    for (let i = 1; i < liste.length; i++) {
      const a = innen(liste[i - 1]), c = innen(liste[i]);
      const ueberein = Math.min(a.right, c.right) - Math.max(a.left, c.left) > 8;     // gleiche Spalte
      const luecke = c.top - a.bottom;
      const soll = liste[i].matches('label.switch') ? 10 : liste[i].matches('p.field-help') ? 4 : 6;   // Hinweis darf näher
      if (ueberein && luecke >= -2 && luecke < soll) funde.push(`${name(liste[i])} (${Math.round(luecke)} px)`);
    }
  }
  // seit 0.50.1 („wieder Abstandsprobleme“): Karten untereinander brauchen Luft, nichts läuft rechts über den Rand
  const karten = [...document.querySelectorAll('main .card')].filter(sichtbar);
  for (let i = 0; i < karten.length; i++) for (let j = 0; j < karten.length; j++) {
    if (i === j || karten[i].contains(karten[j]) || karten[j].contains(karten[i])) continue;
    const a = karten[i].getBoundingClientRect(), c = karten[j].getBoundingClientRect();
    const luecke = c.top - a.bottom;
    if (Math.min(a.right, c.right) - Math.max(a.left, c.left) > 8 && luecke >= -2 && luecke < 8)
      funde.push(`Karten zu dicht: ${name(karten[i])} / ${name(karten[j])} (${Math.round(luecke)} px)`);
  }
  const breite = document.documentElement.clientWidth;
  if (document.documentElement.scrollWidth > breite + 1) {
    const zu = [...document.querySelectorAll('main *')].filter((e) => sichtbar(e) && e.getBoundingClientRect().right > breite + 1
      && !e.closest('[role=tablist], .subnav, .tabs'));
    funde.push(`läuft rechts über (${document.documentElement.scrollWidth} > ${breite}): ${zu.slice(0, 3).map(name).join(', ')}`);
  }
  return funde;
}"""


def abstaende(page, b: "Bericht", wo: str, seiten: tuple = ()) -> None:
    """`seiten`: weitere Ansichten (z. B. ("tricks", "tanz")), die dabei mitgeprüft werden."""
    funde = []
    alt = page.viewport_size
    for v, teil in seiten:
        page.evaluate("([v, p]) => window.duckpilot.showView(v, p)", [v, teil])
        page.wait_for_timeout(1500)
        for breite, hoehe in ((1440, 900), (390, 844)):
            page.set_viewport_size({"width": breite, "height": hoehe})
            page.wait_for_timeout(900)
            funde += [f"{v}/{teil} {breite} px: {f}" for f in page.evaluate(ABSTAND_JS)]
        page.set_viewport_size(alt)
    for breite, hoehe in ((1440, 900), (390, 844)):
        page.set_viewport_size({"width": breite, "height": hoehe})
        page.wait_for_timeout(900)
        funde += [f"{breite} px: {f}" for f in page.evaluate(ABSTAND_JS)]
    page.set_viewport_size(alt)
    page.wait_for_timeout(500)
    b.pruefe(f"{wo}: Schalter, Knöpfe und Felder haben Luft untereinander (1440, 390 px)", not funde, "; ".join(funde[:6]))


# Kopfzeile am Handy (seit 0.38.39): „Knowlin getrennt“ lag über „Aktiv“ – geprüft mit der längsten Meldung (englisch)
KOPF_JS = """(text) => {
  const link = document.querySelector('#badge-link > span'); const alt = link.textContent; if (text) link.textContent = text;
  const els = [...document.querySelectorAll('.top .geist-pfad, .top #badge-link, .top #mode-chip, .top .persona')]
    .filter((e) => e.offsetParent && e.getBoundingClientRect().width > 0);
  const r = els.map((e) => e.getBoundingClientRect()); const ueber = [];
  for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++) {
    const w = Math.min(r[i].right, r[j].right) - Math.max(r[i].left, r[j].left);
    const h = Math.min(r[i].bottom, r[j].bottom) - Math.max(r[i].top, r[j].top);
    if (w > 1 && h > 1) ueber.push((els[i].id || els[i].className) + ' × ' + (els[j].id || els[j].className) + ' (' + Math.round(w) + ' px)');
  }
  const aus = r.filter((x) => x.right > innerWidth + 1).length;
  link.textContent = alt; return { ueber, aus };
}"""


def kopfzeile(page, b: "Bericht") -> None:
    alt = page.viewport_size
    funde = []
    for breite in (390, 360):
        page.set_viewport_size({"width": breite, "height": 844})
        page.wait_for_timeout(900)
        for text in ("", "Knowlin disconnected", "Roboter nicht erreichbar"):
            r = page.evaluate(KOPF_JS, text)
            funde += [f"{breite} px „{text or 'jetzt'}“: {u}" for u in r["ueber"]]
            if r["aus"]:
                funde.append(f"{breite} px „{text or 'jetzt'}“: ragt rechts hinaus")
    page.set_viewport_size(alt)
    page.wait_for_timeout(500)
    b.pruefe("Handy: Kopfzeile ohne Überlappung, auch mit langer Verbindungsmeldung (390, 360 px)", not funde,
             "; ".join(funde[:6]))


HANDY_JS = """() => {
  const sicht = (e) => e.offsetParent !== null && e.getBoundingClientRect().width > 0;
  const unten = [...document.querySelectorAll('.rail .rail-btn, .rail .rail-logo-btn')].filter(sicht);
  const abgeschnitten = unten.map((e) => e.querySelector('span')).filter((s) => s && s.scrollWidth > s.clientWidth + 1)
    .map((s) => s.textContent.trim());
  const log = document.getElementById('log').getBoundingClientRect();
  const say = document.getElementById('say').getBoundingClientRect();
  const rail = document.querySelector('.rail').getBoundingClientRect();
  return { anzahl: unten.length, namen: unten.map((e) => (e.querySelector('span') || e).textContent.trim()), abgeschnitten,
           verlauf: Math.round(log.height), hoehe: innerHeight, eingabeSichtbar: say.bottom <= rail.top + 1 && say.top >= 0,
           seiteRollt: document.documentElement.scrollHeight > innerHeight + 2 };
}"""


def handyansicht(page, b: "Bericht") -> None:
    """Seit 0.38.41 („Der Bereich vom Textverlauf ist immer noch zu flach“): unten höchstens fünf Bereiche mit
    vollem Namen plus Not-Aus, der Rest unter „Mehr“; im Cockpit hat der Verlauf Platz, die Eingabe steht über der Leiste."""
    alt = page.viewport_size
    page.set_viewport_size({"width": 390, "height": 760})
    page.wait_for_timeout(1200)
    r = page.evaluate(HANDY_JS)
    b.pruefe("Handy: unten höchstens fünf Bereiche mit vollem Namen, dazu der Not-Aus",
             r["anzahl"] <= 5 and not r["abgeschnitten"], f"{r['namen']} abgeschnitten: {r['abgeschnitten']}")
    b.pruefe("Handy: Verlauf im Cockpit sichtbar hoch, Eingabe über der Leiste, Seite rollt nicht",
             r["verlauf"] >= r["hoehe"] * 0.18 and r["eingabeSichtbar"] and not r["seiteRollt"],
             f"Verlauf {r['verlauf']} von {r['hoehe']} px, Eingabe sichtbar {r['eingabeSichtbar']}, rollt {r['seiteRollt']}")
    # Bühne ziehen (seit 0.38.43): Griff nach unten ziehen macht die Bühne größer, Doppeltippen setzt zurück
    griff = page.locator(".buehne-teiler")
    vorher = page.evaluate("() => document.querySelector('#view-cockpit > .stage').getBoundingClientRect().height")
    kasten = griff.bounding_box() if griff.is_visible() else None
    if kasten:
        x, y = kasten["x"] + kasten["width"] / 2, kasten["y"] + kasten["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x, y + 120, steps=6)
        page.mouse.up()
        page.wait_for_timeout(300)
    nachher = page.evaluate("() => document.querySelector('#view-cockpit > .stage').getBoundingClientRect().height")
    b.pruefe("Handy: Bühne lässt sich am Griff größer ziehen", bool(kasten) and nachher > vorher + 60,
             f"{vorher:.0f} → {nachher:.0f} px")
    if kasten:
        griff.dblclick()
        page.wait_for_timeout(300)
    mehr = page.locator("#rail-mehr")
    ok, eintraege = False, []
    if mehr.is_visible():
        mehr.click()
        page.wait_for_timeout(400)
        eintraege = [t.strip() for t in page.locator("#mehr-pop .mehr-eintrag").all_text_contents()]
        if "Charakter" in eintraege:
            page.locator("#mehr-pop .mehr-eintrag", has_text="Charakter").click()
            page.wait_for_timeout(1500)
            ok = page.evaluate("() => document.getElementById('rail-mehr').classList.contains('ist-aktiv')"
                               " && document.getElementById('mehr-pop').hidden")
    b.pruefe("Handy: „Mehr“ öffnet Charakter, System und Knowlin; die Wahl führt hin und markiert „Mehr“",
             ok and {"System", "Knowlin"} <= set(eintraege), str(eintraege))
    page.evaluate("() => window.duckpilot.showView('cockpit')")
    page.set_viewport_size(alt)
    page.wait_for_timeout(800)


def ueberdeckungen(page, b: "Bericht", wer: str) -> None:
    alt = page.viewport_size
    funde = []
    for breite, hoehe in ((1440, 900), (1100, 800), (390, 844)):
        page.set_viewport_size({"width": breite, "height": hoehe})
        page.wait_for_timeout(1200)
        r = page.evaluate(UEBERDECKUNG_JS)
        funde += [f"{breite} px: {u}" for u in r.get("ueber", [])]
    page.set_viewport_size(alt)
    page.wait_for_timeout(800)
    b.pruefe(f"Cockpit {wer}: nichts über der Bühne liegt übereinander (1440, 1100, 390 px)", not funde, "; ".join(funde[:6]))


def ablauf(page, base: str, b: Bericht, axe_js: str | None, ordner: Path) -> None:
    # 0 · Seit 0.38.24: beim ersten Öffnen lädt Knowlins Bewusstsein (statt des Startbilds), dann „Knowlin ist wach“
    page.goto(f"{base}/#start", wait_until="commit")
    page.wait_for_selector("#splash .splash-zeichen", state="attached", timeout=30000)
    start = page.evaluate("() => ({ text: document.getElementById('splash-text').textContent,"
                          " funken: document.querySelectorAll('#splash .splash-funken i').length,"
                          " startbild: !!document.querySelector('img[src*=\"splash.jpg\"]') })")
    try:
        page.wait_for_function("() => { const s = document.getElementById('splash');"
                               " if (s && s.classList.contains('is-wach')) window.__wach = s.textContent; return !s; }",
                               timeout=30000, polling=50)
        weg = True
    except Exception:  # noqa: BLE001
        weg = False
    wach = page.evaluate("() => window.__wach || ''")
    b.pruefe("Start: Knowlins Bewusstsein lädt, dann „Knowlin ist wach“, danach frei (kein Startbild)",
             "Bewusstsein lädt" in start["text"] and start["funken"] == 8 and not start["startbild"]
             and "Knowlin ist wach" in wach and weg, f"{start} wach={wach!r} weg={weg}")

    # 1 · Startseite
    oeffnen(page, base)
    b.pruefe("Startseite: Gruß „Hallo Mensch“", page.text_content("#kopf-gruss").strip() == "Hallo Mensch")
    satz = page.text_content("#kopf-satz")
    b.pruefe("Startseite: Knowlin stellt sich vor (selbstlernend)", "selbstlernende Lebensform" in satz, satz)
    b.pruefe("Startseite: Mind-Form vorhanden", page.locator("canvas#mind").count() == 1)
    chips = page.locator(".kopf-vorschlag").all_text_contents()
    b.pruefe("Startseite: kein „Tanz für mich“ unter den Vorschlägen", not any("Tanz" in c for c in chips), str(chips))
    b.foto(page, "01-startseite", "Startseite")
    axe(page, b, axe_js, "Startseite", "#view-start")

    # 2 · Gespräch mit Knowlin selbst
    antwort = kopf_sagen(page, "Wer bist du?", "Lebensform")
    b.pruefe("Kopf: „Wer bist du?“ – seriöse Antwort, keine Entenlaute", "quak" not in antwort.lower(), antwort)

    # 3 · Erst fragen, dann in den Körper – „nein“
    antwort = kopf_sagen(page, "Lauf vor", "?")
    b.pruefe("Kopf: Körperliches → schlägt einen Körper vor und fragt", "Körper" in antwort and "?" in antwort, antwort)
    antwort = kopf_sagen(page, "nein", "ohne Körper")
    b.pruefe("Kopf: „nein“ → bleibt ohne Körper", "ohne Körper" in antwort, antwort)
    b.pruefe("Kopf: bleibt auf der Startseite", page.evaluate("document.body.classList.contains('im-kopf')"))

    # 4 · Namen
    antwort = kopf_sagen(page, "Ich heiße Testperson", "Testperson")
    page.wait_for_function("() => document.getElementById('kopf-gruss').textContent.includes('Testperson')", timeout=15000)
    b.pruefe("Namen: „Ich heiße …“ ändert den Gruß", True)
    kopf_sagen(page, "Ich nenne dich Nova", "Nova")
    page.wait_for_function("() => document.getElementById('kopf-satz').textContent.includes('Nova')", timeout=15000)
    b.pruefe("Namen: „Ich nenne dich …“ benennt Knowlin", True)
    b.foto(page, "02-namen", "Startseite mit Namen")
    einstellen(page, {"kopf_name": "", "nutzer_name": ""})

    # 5 · Erst fragen, dann in den Körper – „ja“, Auftrag wird weitergegeben
    oeffnen(page, base)
    antwort = kopf_sagen(page, "Tanz für mich", "?")
    b.pruefe("Kopf: „Tanz für mich“ → fragt nach Quacki", "Quacki" in antwort, antwort)
    page.fill("#kopf-text", "ja")
    page.press("#kopf-text", "Enter")
    page.wait_for_function("() => !document.body.classList.contains('im-kopf')", timeout=60000)
    b.pruefe("Kopf: „ja“ → geht in den Körper", True)
    page.wait_for_function("() => [...document.querySelectorAll('#log .msg-user')].some(p => p.textContent.includes('Tanz'))",
                           timeout=60000)
    b.pruefe("Körper: der Wunsch kommt bei Quacki an", True)
    ruhig(page)
    page.wait_for_timeout(2000)
    wer = page.locator("#log .msg-wer").all_text_contents()
    b.pruefe("Gespräch im Körper zeigt, wer spricht", any(w.strip() for w in wer), str(wer[-3:]))
    b.foto(page, "03-cockpit", "Quacki im Cockpit mit dem Wunsch")
    ueberdeckungen(page, b, "Quacki")
    kopfzeile(page, b)
    handyansicht(page, b)
    abstaende(page, b, "Tanzen, Team, Zubehör, Ablauf, Lab, Mentor", (("tricks", "tanz"), ("tricks", "team"),
              ("tricks", "zubehoer"), ("tricks", "ablauf"), ("lab", None), ("mentor", None)))
    page.evaluate("() => window.duckpilot.showView('cockpit')")
    page.wait_for_timeout(1500)

    # 6 · Herkunft: im Körper etwas merken
    page.fill("#say-text", "Merk dir: ich trinke gern Tee")
    page.press("#say-text", "Enter")
    mem = ordner / "mem.json"
    text = ""
    for _ in range(30):                     # bis 15 s – unter Last schreibt der Server etwas später (0.38.28)
        page.wait_for_timeout(500)
        text = mem.read_text(encoding="utf-8") if mem.exists() else ""
        if "Tee" in text:
            break
    b.pruefe("Herkunft: Gemerktes trägt die Verkörperung („von“)", "Tee" in text and "duckpilot" in text,
             "kein Eintrag" if "Tee" not in text else "")

    # 7 · Ausprägung und Gestalt
    ansicht(page, "persoenlichkeit")
    auspraegung = page.text_content("#auspraegung") or ""
    b.pruefe("Persönlichkeit: Ausprägung gegenüber Knowlin", "Knowlin" in auspraegung, auspraegung)
    boxen = page.locator("#gestalt-liste input[type=checkbox]")
    b.pruefe("Persönlichkeit: Eigenschaften der Gestalt (Microduck: 4)", boxen.count() == 4, str(boxen.count()))
    if boxen.count():
        boxen.first.click()
        page.wait_for_timeout(1500)
        eig = json.loads((ordner / "settings.json").read_text(encoding="utf-8")).get("eigenschaften")
        b.pruefe("Persönlichkeit: Abwählen wird gespeichert", isinstance(eig, list) and "schnabel" not in eig, str(eig))
    b.foto(page, "04-persoenlichkeit", "Ausprägung und Gestalt")
    abstaende(page, b, "Persönlichkeit")
    axe(page, b, axe_js, "Persönlichkeit", "#view-persoenlichkeit")

    # 7b · Von sich aus beschäftigen (seit 0.38.14; seit 0.38.44 ein stufenloser Regler, Standard 0,4 = „ab und zu“)
    std = json.loads((ordner / "settings.json").read_text(encoding="utf-8")).get("eigenstaendig", 0.4)
    b.pruefe("Verhalten: „Von sich aus beschäftigen“ steht auf „ab und zu“ (0,4)", std in (0.4, "ab_und_zu"), str(std))
    regler = page.locator("#eigen-regler")
    if regler.count():
        page.evaluate("() => { const r = document.getElementById('eigen-regler'); r.value = '0.75';"
                      " r.dispatchEvent(new Event('change', {bubbles: true})); }")
        page.wait_for_timeout(1500)
        jetzt = json.loads((ordner / "settings.json").read_text(encoding="utf-8")).get("eigenstaendig")
        b.pruefe("Verhalten: Regler fein einstellbar und gespeichert", jetzt == 0.75, str(jetzt))
        page.evaluate("() => { const r = document.getElementById('eigen-regler'); r.value = '0.4';"
                      " r.dispatchEvent(new Event('change', {bubbles: true})); }")
        page.wait_for_timeout(1000)
    else:
        b.pruefe("Verhalten: Regler „Von sich aus beschäftigen“", False, "nicht gefunden")
    # 7c · Seit 0.38.44: Gedankenspur unter Persönlichkeit – Karte da, Schnittstelle antwortet, Antrieb ohne eigene Anzeige
    spur = page.evaluate("() => fetch('/api/gedankenspur').then(r => r.json())")
    karte = page.evaluate("() => !!document.getElementById('gedanken-karte')")
    b.pruefe("Gedankenspur: Karte unter Persönlichkeit, Schnittstelle mit Zeilen und Antrieb",
             karte and isinstance(spur.get("zeilen"), list) and set(spur.get("antrieb", {}).get("werte", {}))
             == {"neugier", "naehe", "ruhe", "koennen"}, f"Karte {karte} · {len(spur.get('zeilen') or [])} Zeilen")
    # 7d · Seit 0.38.45: Rückblick – Karte im Gedächtnis, „Jetzt zurückblicken“ antwortet, Liste lesbar
    blick = page.evaluate("() => fetch('/api/rueckblick/jetzt', {method: 'POST'}).then(r => r.json())")
    lehren_karte = page.evaluate("() => !!document.getElementById('lehren-karte')")
    b.pruefe("Rückblick: Karte im Gedächtnis, Rückblick am PC anstoßbar, Lehren als Liste",
             lehren_karte and blick.get("ok") is True and isinstance(blick.get("lehren"), list),
             f"Karte {lehren_karte} · {len(blick.get('lehren') or [])} Lehren")

    # 8 · Zurück zu Knowlin – kurzer Übergang
    page.evaluate("() => { window.__zurueck = ''; const ov = document.getElementById('einzug');"
                  " new MutationObserver(() => { if (ov.classList.contains('is-zurueck'))"
                  " window.__zurueck = document.getElementById('einzug-text').textContent; })"
                  ".observe(ov, {attributes: true, subtree: true, childList: true}); }")
    zum_kopf(page)
    uebergang = page.evaluate("() => window.__zurueck")
    b.pruefe("Übergang zurück zu Knowlin sichtbar („Zurück aus …“)", "Zurück aus" in (uebergang or ""), uebergang or "kein Übergang")
    page.wait_for_timeout(1000)
    b.pruefe("Startseite nach dem Körper wieder im Kopf", page.evaluate("document.body.classList.contains('im-kopf')"))

    # 9 · Grundcharakter bei Knowlin, Stimme ohne Körper
    ansicht(page, "settings")
    name = (page.text_content("#pad-knowlin .pad-name") or "").strip()
    b.pruefe("Grundcharakter als Feld mit Quadranten, anfangs „Sachlich“", name == "Sachlich", name)
    marken = page.locator("#pad-knowlin .pad-mark").all_text_contents()
    b.pruefe("Feld zeigt die Verkörperungen als Punkte", len(marken) >= 3 and "Quacki" in marken, str(marken))
    vorher = json.loads((ordner / "settings.json").read_text(encoding="utf-8"))
    page.focus("#pad-knowlin .pad-puck")
    for _ in range(4):
        page.keyboard.press("ArrowUp")                     # per Tastatur verspielter
    page.wait_for_timeout(2500)
    nachher = json.loads((ordner / "settings.json").read_text(encoding="utf-8"))
    b.pruefe("Feld per Tastatur bedienbar (Grundcharakter verspielter)",
             nachher.get("grund_humor", 0) > vorher.get("grund_humor", 0.1) + 0.1,
             f"{vorher.get('grund_humor')} → {nachher.get('grund_humor')}")
    b.pruefe("Grundcharakter verschieben lässt die Verkörperungen, wo sie sind (seit 0.38.14)",
             abs(nachher.get("humor", 0) - vorher.get("humor", 0)) < 0.01,
             f"{vorher.get('humor')} → {nachher.get('humor')}")
    # 9a · Verkörperungen einzeln im Knowlin-Feld verschieben (Wunsch des Maintainers 5.11.2026)
    figuren = ordner / "figuren.json"
    def _reachy_profil():
        try:
            return (json.loads(figuren.read_text(encoding="utf-8")).get("profile", {}).get("reachy_mini") or {})
        except (OSError, ValueError):
            return {}
    r_vorher = _reachy_profil()
    marke = page.locator('#pad-knowlin button.pad-mark[data-marke="reachy_mini"]')
    if marke.count() == 0:
        b.pruefe("Knowlin-Feld: Reachys Punkt ist ziehbar", False, "kein Knopf data-marke=reachy_mini")
    else:
        marke.focus()
        for _ in range(4):
            page.keyboard.press("ArrowRight")              # Reachy lebhafter
        page.wait_for_timeout(2500)
        r_nachher = _reachy_profil()
        grund = json.loads((ordner / "settings.json").read_text(encoding="utf-8"))
        b.pruefe("Knowlin-Feld: Reachy einzeln lebhafter, Knowlins Grund bleibt",
                 (r_nachher.get("energie") or 0) > (r_vorher.get("energie") or 0) + 0.05
                 and abs(grund.get("grund_humor", 0) - nachher.get("grund_humor", 0)) < 0.01
                 and abs(grund.get("grund_energie", 0) - nachher.get("grund_energie", 0)) < 0.01,
                 f"Reachy {r_vorher.get('energie')} → {r_nachher.get('energie')}")
    b.foto(page, "05-knowlin-einstellungen", "Einstellungen → Knowlin")
    abstaende(page, b, "Einstellungen")
    axe(page, b, axe_js, "Einstellungen → Knowlin", "#set-knowlin")
    page.click("#goto-kopf-stimme")
    page.wait_for_timeout(2000)
    b.pruefe("Knowlins Stimme ohne Körper erreichbar",
             page.evaluate("document.body.classList.contains('im-kopf') && !document.getElementById('view-stimme').hidden"))
    b.foto(page, "06-knowlins-stimme", "Knowlins Stimme")

    # 10 · Hirnaktivität mit Herkunft
    ansicht(page, "dashboard")
    optionen = page.locator("#brain-herkunft option").all_text_contents()
    b.pruefe("Hirnaktivität: Filter nach Herkunft", len(optionen) >= 2, str(optionen))

    # 10b · Synapsen bei Knowlin: leben (drehen, schweben, Impulse), Bild ändert sich von selbst
    zum_kopf(page)
    ansicht(page, "memory")
    b.pruefe("Gedächtnis bei Knowlin bleibt im Kopf (Wissen)", page.evaluate("document.body.classList.contains('im-kopf')"))
    bild = "() => { const c = document.getElementById('brain'); return c && c.width ? c.toDataURL() : ''; }"
    eins = page.evaluate(bild)
    page.wait_for_timeout(1500)
    zwei = page.evaluate(bild)
    b.pruefe("Synapsen bei Knowlin bewegen sich von selbst", bool(eins) and eins != zwei)
    b.foto(page, "09-synapsen-knowlin", "Synapsen bei Knowlin (Wissen → Gedächtnis)")

    # 11 · Reachy wecken
    zum_kopf(page)
    knopf = page.get_by_role("button", name="Reachy wecken")
    if knopf.count() == 0:
        b.pruefe("Reachy: Kachel „Reachy wecken“", False, "nicht gefunden")
    else:
        knopf.first.click()
        page.wait_for_function("() => !document.body.classList.contains('im-kopf')", timeout=60000)
        page.wait_for_function("() => document.querySelector('#log .msg-trenner')", timeout=60000)
        ruhig(page)                                        # nach dem Wecken entsteht die 3D-Ansicht neu
        trenner = page.locator("#log .msg-trenner").last.text_content() or ""
        b.pruefe("Gespräch: Trennlinie beim Körperwechsel", "Reachy" in trenner, trenner)
        page.wait_for_timeout(4000)
        page.fill("#say-text", "freu dich")
        page.press("#say-text", "Enter")
        page.wait_for_timeout(6000)
        b.foto(page, "07-reachy-freude", "Reachy freut sich (Kopf außerhalb des Körpers?)")
        ueberdeckungen(page, b, "Reachy")
        b.pruefe("Reachy: „freu dich“ ohne Fehlermeldung", page.locator("#log .msg-err").count() == 0)
        b.pruefe("Kamera-Kachel bei Reachy sichtbar (Reachys Blick)", page.evaluate(
            "() => [...document.querySelectorAll('.braucht-sicht')].some((t) => t.checkVisibility())"))
        st = page.evaluate("() => { const s = window.duckpilot.state || {};"
                           " return {z: s.stand_z, wo: s.standflaeche, modul: s.modul}; }")
        b.pruefe("Reachy steht auf dem Couchtisch", (st.get("z") or 0) > 0.1 and "tisch" in str(st.get("wo", "")).lower(),
                 str(st))
        # Pollens Apps (seit 0.38.19): im Simulator ehrlich „nur am echten Reachy“, mit Link zu Pollens Katalog
        ansicht(page, "tricks")
        try:
            page.wait_for_selector("#reachy-apps-sim:not([hidden])", timeout=15000)
            hinweis = page.text_content("#reachy-apps-sim") or ""
        except Exception:  # noqa: BLE001
            hinweis = ""
        b.pruefe("Reachy: Pollens Apps im Simulator ehrlich erklärt, Link zum Katalog",
                 "echten Reachy" in hinweis and "huggingface.co" in (page.get_attribute("#reachy-apps-seite", "href") or ""), hinweis[:100])

    # 11 · Stimme entwerfen je Körper (seit 0.38.14): Reachy bekommt Tischroboter-Vorlagen, keine Enten
    if page.evaluate("document.body.classList.contains('koerper-reachy')"):
        # (Die Vorlagen stehen im Qwen-Entwerfer; ohne Qwen zeigt die Seite ihn nicht – deshalb über die Schnittstelle.)
        q = page.evaluate("() => fetch('/api/stimme').then(r => r.json()).then(m => m.qwen || {})")
        namen = list((q.get("vorlagen") or {}).keys())
        b.pruefe("Stimme bei Reachy: Vorlage „Freundlicher Tischroboter“, keine Enten-Vorlage",
                 "Freundlicher Tischroboter" in namen and not any("Ente" in n for n in namen), str(namen))

    # 11a · Kamera-Spiele mit Reachy (seit 0.38.13): Hand folgen, Rotes Licht – grünes Licht
    if page.evaluate("document.body.classList.contains('koerper-reachy')"):
        page.evaluate("() => window.duckpilot.showView('tricks', 'spiele')")
        page.wait_for_timeout(2500)
        b.pruefe("Spiele: Bereich bei Reachy sichtbar, mit Datenschutz-Hinweis", page.locator("#ks-hinweis").is_visible())
        page.click("#ks-folgen-start")
        page.wait_for_function("() => document.getElementById('ks-folgen-start').getAttribute('aria-pressed') === 'true'")
        page.evaluate("() => { const s = window.duckpilot.scene; if (s) { s.paused = true; } }")   # headless entlasten
        page.wait_for_timeout(3000)
        status = page.evaluate("() => fetch('/api/spiele').then(r => r.json())")
        b.pruefe("Spiel im Simulator: Bühne mit Reachy daneben (Übergang)", page.evaluate(
            "() => !!document.querySelector('#ks-raster[data-spielt]') && !!document.querySelector('#ks-sim-ansicht canvas')"))
        b.pruefe("Hand folgen läuft, Webcam-Hinweis oben", status.get("laeuft") == "folgen"
                 and page.locator("#badge-spiel-cam").is_visible(), str(status))
        b.foto(page, "10-reachy-hand-folgen", "Reachy: Hand folgen (Fake-Webcam)")
        page.click("#ks-folgen-start")
        page.wait_for_timeout(2000)
        b.pruefe("Hand folgen aus: Webcam-Hinweis weg", not page.locator("#badge-spiel-cam").is_visible())
        page.click("#ks-ampel-start")
        page.wait_for_function("() => ['kalibrieren', 'gruen', 'rot'].includes(document.getElementById('ks-ampel').dataset.zustand)")
        b.pruefe("Ampel-Spiel startet (kalibriert zuerst)", True)
        page.click("#ks-ampel-stopp")
        page.wait_for_timeout(1500)
        b.pruefe("Ampel-Spiel beendet, Webcam aus", not page.locator("#badge-spiel-cam").is_visible())

    # 11b · Open Duck Mini (seit 0.38.13): nur, was sie kann – frisch geladen (headless ohne Grafikkarte wird die Seite
    # im Körper sehr träge; auf einem PC mit GPU nicht)
    oeffnen(page, base)
    knopf = page.get_by_role("button", name="Odi wecken")
    if knopf.count() == 0:
        b.pruefe("Open Duck: Kachel „Odi wecken“", False, "nicht gefunden")
    else:
        knopf.first.click()
        page.wait_for_function("() => document.body.classList.contains('koerper-open-duck') && !document.body.classList.contains('im-kopf')",
                               timeout=60000)
        page.wait_for_timeout(3000)
        ruhig(page)
        sichtbar = page.evaluate("""() => ({
            lernen: !!document.getElementById('rail-lernen')?.offsetParent,
            kollision: !!document.getElementById('kol-btn')?.offsetParent,
            pollen: [...document.querySelectorAll('#emo-pollen')].some(e => e.offsetParent),
            titel: document.getElementById('geist-koerper')?.textContent || '' })""")
        b.pruefe("Open Duck: kein Lernen, kein Kollisionsmodus, keine Pollen-Emotionen",
                 not sichtbar["lernen"] and not sichtbar["kollision"] and not sichtbar["pollen"], str(sichtbar))
        b.pruefe("Open Duck: Kopfzeile nennt den Körper", "Open Duck" in sichtbar["titel"], sichtbar["titel"])
        ansicht(page, "memory")
        kopf = page.text_content("#view-memory h2") or ""
        b.pruefe("Open Duck: Gedächtnis trägt ihren Namen (Odi)", "Odi" in kopf, kopf)
        ansicht(page, "settings")
        wahl = page.evaluate("""() => ({ odi: !!document.querySelector('#set-koerper input[value=open_duck_mini]')?.checked,
            echt: !!document.querySelector('#set-koerper input[value=robotd]')?.closest('label')?.offsetParent })""")
        b.pruefe("Open Duck: in Einstellungen → Körper gewählt, „Echter Roboter“ ausgeblendet",
                 wahl["odi"] and not wahl["echt"], str(wahl))
        b.foto(page, "11-open-duck-koerper", "Open Duck: Einstellungen → Körper")
        # Reiter nach dem Neuladen im Körper (Fund 6.11.2026: Team, Vom Hub und Spiele standen bei Odi)
        page.goto(f"{base}/#cockpit")
        page.reload()
        page.wait_for_function("() => document.body.classList.contains('koerper-open-duck')", timeout=90000)
        page.wait_for_timeout(3000)
        ruhig(page)
        reiter = page.locator("#subnav .subnav-tab").all_text_contents()
        # seit 0.44 gibt es „Spiele“ für jeden Körper (Ente sagt, Verstecken, Elfmeter) – Team und Hub bleiben Microduck
        b.pruefe("Open Duck: nach Neuladen nur ihre Reiter (kein Team, kein Hub, aber Spiele)",
                 not {"Team", "Vom Hub"} & set(reiter) and "Spiele" in reiter, str(reiter))
        # Einfache Darstellung passt zur Open Duck (seit 0.38.15: grau, höher, Antennen – nicht die Microduck)
        einstellen(page, {"model_style": "einfach"})
        # seit 0.38.40 wartet die Abnahme bis zu 20 s statt fest 2,5 s (bei langsamem Rechner fiel der Schritt sonst durch)
        eigene = ("() => { const s = window.duckpilot.scene; return !!s && !!s.einfacheOpenDuck && s.duck === s.einfacheOpenDuck "
                  "&& s.duck !== s.simpleDuck; }")
        try:
            page.wait_for_function(eigene, timeout=20000)
        except Exception:  # noqa: BLE001 – Ergebnis prüft die nächste Zeile
            pass
        b.pruefe("Open Duck: einfache Darstellung ist ihre eigene (nicht die einfache Microduck)", page.evaluate(eigene))
        einstellen(page, {"model_style": "original"})
        ansicht(page, "cockpit")
        # seit 0.38.21: Odi läuft auf „lauf zum Ball“ wirklich hin (vorher nur 40 cm geradeaus) und schießt nachgestellt
        page.fill("#say-text", "lauf zum Ball")
        page.press("#say-text", "Enter")
        # Odi ist verspielt und bockt manchmal erst kurz („trotzig“, dann schütteln) – danach läuft er hin
        try:
            page.wait_for_function("() => /ball|annäher/i.test(document.getElementById('doing')?.textContent || '')",
                                   timeout=15000)
        except Exception:  # noqa: BLE001
            pass
        tun = page.text_content("#doing") or ""
        b.pruefe("Open Duck: „lauf zum Ball“ läuft zum Ball (Annähern statt geradeaus)",
                 "ball" in str(tun).lower() or "annäher" in str(tun).lower(), str(tun)[:80])
        page.keyboard.press("Escape")
        page.wait_for_timeout(1500)

    # 12 · Weitere Enten: Standard keine
    s = json.loads((ordner / "settings.json").read_text(encoding="utf-8"))
    b.pruefe("Keine weiteren Enten als Standard", int(s.get("weitere_enten", 0) or 0) == 0, str(s.get("weitere_enten")))

    # 13 · Englisch
    einstellen(page, {"sprache": "en"})
    oeffnen(page, base)
    b.pruefe("Englisch: „Hello human“", page.text_content("#kopf-gruss").strip() == "Hello human",
             page.text_content("#kopf-gruss"))
    b.foto(page, "08-englisch", "Start page in English")
    einstellen(page, {"sprache": "de"})

    # 13b · Inhalte je Körper und Sprache
    inhalte_je_koerper(page, base, b)

    # 13c · Verbindungstest vor dem ersten Start am echten Roboter (seit 0.38.16): prüft nur, speichert nichts
    oeffnen(page, base)
    page.evaluate("() => document.getElementById('wizard-open').click()")
    page.wait_for_timeout(500)
    page.click("#wizard-next")
    page.click("[data-wiz-body=robot]")
    page.fill("#wizard-robot-addr", "tcp:127.0.0.1:7959")
    page.click("#wizard-robot-test")
    page.wait_for_selector("#wizard-robot-befund .befund--fehler", timeout=15000)
    befund = page.text_content("#wizard-robot-befund") or ""
    b.foto(page, "12-verbindungstest", "Erste Schritte: Verbindung prüfen ohne Roboter")
    backend = json.loads((ordner / "settings.json").read_text(encoding="utf-8")).get("backend", "sim")
    b.pruefe("Verbindungstest: zeigt „Erreichbar“ als Problem mit Zeichen, speichert nichts",
             "Erreichbar" in befund and "✕" in befund and "Tunnel" in befund and backend == "sim", f"{befund[:120]} · {backend}")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # 13c2 · Erster Start (seit 0.38.60): alle Körper zur Wahl, „Erst mal ohne“ zuerst, am Ende wacht der gewählte auf
    einstellen(page, {"modul": "duckpilot", "backend": "sim"})   # vorher die Microduck – Bello kommt nur über den Assistenten
    oeffnen(page, base)
    page.evaluate("() => document.getElementById('wizard-open').click()")
    page.wait_for_timeout(500)
    page.click("#wizard-next")
    page.wait_for_selector("#wizard-koerper [data-wiz-koerper]", timeout=10000)
    wahl = page.evaluate("() => [...document.querySelectorAll('#wizard-koerper [data-wiz-koerper]')].map((b) => b.dataset.wizKoerper)")
    erstes_hirn = page.evaluate("() => document.querySelector('[data-wiz-brain]').dataset.wizBrain")
    b.foto(page, "12b-erster-start", "Erste Schritte: Wen weckst du zuerst?")
    page.click("[data-wiz-koerper=bittle]")
    page.click("[data-wiz-brain=ohne]")
    try:                                                # speichert erst, dann Schritt 4
        page.wait_for_function("() => !document.querySelector('[data-wiz=\"4\"]').hidden", timeout=10000)
    except Exception:  # noqa: BLE001
        pass
    knopf = (page.text_content("#wizard-next") or "").strip()
    page.click("#wizard-next")
    try:
        page.wait_for_function("() => (window.duckpilot.state || {}).koerper === 'bittle'", timeout=30000)
        page.wait_for_function("() => !document.body.classList.contains('im-kopf')", timeout=20000)   # nach dem Übergang
        page.wait_for_timeout(500)
    except Exception:  # noqa: BLE001
        pass
    modul = json.loads((ordner / "settings.json").read_text(encoding="utf-8")).get("modul")
    im_cockpit = page.evaluate("() => !document.body.classList.contains('im-kopf')"
                            " && document.getElementById('view-cockpit').offsetParent !== null")
    b.pruefe("Erster Start: sechs Körper zur Wahl, „Erst mal ohne“ zuerst, „Bello wecken“ weckt ihn im Cockpit",
             len(wahl) >= 6 and "bittle" in wahl and erstes_hirn == "ohne" and knopf == "Bello wecken"
             and modul == "bittle" and im_cockpit, f"{wahl} · {erstes_hirn} · {knopf} · {modul} · Cockpit: {im_cockpit}")
    einstellen(page, {"modul": "duckpilot", "backend": "sim"})

    # 13c3 · Suche auf der Trickseite (seit 0.38.61): filtert alle Kacheln, zeigt „x von y“, sonst „Nichts gefunden“
    oeffnen(page, base)
    page.evaluate("() => window.duckpilot.showView('tricks', 'tricks')")
    page.wait_for_timeout(2500)
    page.fill("#tricks-suche", "freu")
    page.wait_for_function("() => /von/.test(document.getElementById('tricks-suche-info').textContent)", timeout=5000)
    info = page.text_content("#tricks-suche-info") or ""
    b.foto(page, "12c-tricks-suche", "Tricks: Suche nach „freu“")
    page.fill("#tricks-suche", "xyzqq")
    page.wait_for_function("() => /^0 von/.test(document.getElementById('tricks-suche-info').textContent)", timeout=5000)
    leer = page.evaluate("() => !document.getElementById('tricks-suche-leer').hidden")
    page.fill("#tricks-suche", "")
    page.wait_for_timeout(400)
    zurueck = page.evaluate("() => document.querySelectorAll('#view-tricks .such-aus').length")
    treffer, gesamt = (int(x) for x in re.findall(r"\d+", info)[:2]) if len(re.findall(r"\d+", info)) >= 2 else (0, 0)
    b.pruefe("Tricks: Suche filtert („freu“ findet etwas, aber nicht alles), „Nichts gefunden“, leer zeigt wieder alles",
             0 < treffer < gesamt and leer and zurueck == 0, f"{info} · leer: {leer} · ausgeblendet danach: {zurueck}")

    # 13c4 · Stacki spürt Berührung (seit 0.38.62): Knopf „Streicheln“ → froh, „Schütteln“ → schwindelig
    einstellen(page, {"modul": "stackchan", "backend": "sim"})
    # Seit 0.47 zählt auch die Antwort des Servers auf den Knopf („freut sich“ / „ist schwindelig“): Ein langsamer Rechner
    # (Software-Grafik in der Prüfkette) bekommt dank Quittung nur alle paar Sekunden einen Zustand – der 2-s-Ausdruck
    # kann dazwischen liegen, obwohl Stacki ihn gezeigt hat.
    antworten: list[str] = []

    def _horchen(ws) -> None:
        ws.on("framereceived", lambda f: antworten.append(str(f)) if '"tool": "beruehren"' in str(f) else None)
    page.on("websocket", _horchen)
    oeffnen(page, base)
    page.evaluate("() => window.duckpilot.showView('cockpit')")
    page.wait_for_function("() => (window.duckpilot.state || {}).koerper === 'stackchan'", timeout=20000)
    page.evaluate("() => document.querySelector('.quick.nur-stackchan [data-tool=power][data-args*=stand_up]').click()")
    page.wait_for_function("() => ((window.duckpilot.state || {}).gesicht || {}).wach === true", timeout=20000)
    gesehen = []
    # jeden Ausdruck mitschreiben, der im Zustand ankommt: Das Gesicht zeigt ihn nur rund 3 s – unter Last (Prüfkette,
    # Software-Grafik) verpasste das Warten auf Bildwiederholungen das Fenster manchmal (Fund 15.11., 0.38.65)
    # Seit 0.47 je Zustandsnachricht statt alle 40 ms: Unter Last kommen die Zustände gestaut und im Schwall an – ein 2-s-
    # Ausdruck lief dann zwischen zwei Abfragen durch (beide Klicks „ruhig“, obwohl Stacki sich freute).
    page.evaluate("""() => { window.__ausdruecke = new Set(); clearInterval(window.__ausdruckUhr);
        if (!window.__ausdruckHorcher) { window.__ausdruckHorcher = (ev) => { const st = ev.detail || {};
          const a = (st.gesicht || {}).ausdruck; window.__simZeit = st.t; if (a) window.__ausdruecke.add(a); };
          window.addEventListener('knowlin:state', window.__ausdruckHorcher); } }""")
    for art, erwartet in (("streicheln", "froh"), ("schuetteln", "schwindelig")):
        # Unter Last ging der erste Klick gelegentlich ins Leere (0.38.67, 0.40.0: Gesicht blieb „ruhig“): nach 20 s ein
        # zweiter Klick, wie ein Mensch es täte – im Bericht vermerkt. Scheitern beide, ist es ein echter Fehler.
        ergebnis = None
        grund = {"froh": "freut sich", "schwindelig": "ist schwindelig"}[erwartet]
        for versuch in (1, 2):
            page.evaluate("() => window.__ausdruecke.clear()")   # nur, was nach diesem Knopf kommt
            vorher = len(antworten)
            page.evaluate(f"() => document.querySelector('.quick.nur-stackchan [data-tool=beruehren][data-args*={art}]').click()")
            ende = time.monotonic() + (20 if versuch == 1 else 40)
            while time.monotonic() < ende and ergebnis is None:
                if page.evaluate(f"() => window.__ausdruecke.has('{erwartet}')"):
                    ergebnis = erwartet
                elif any(grund in a for a in antworten[vorher:]):
                    ergebnis = f"{erwartet} (Antwort des Servers)"
                else:
                    page.wait_for_timeout(250)
            if ergebnis is not None:
                ergebnis += " (erst beim 2. Klick)" if versuch == 2 else ""
                break
        if ergebnis is None:
            # Befund für den Bericht: kam überhaupt Zustand an, und was stand im Gesicht und im Verlauf?
            befund = page.evaluate("""() => [window.__simZeit, [...window.__ausdruecke].join('/'),
                [...document.querySelectorAll('#log p')].slice(-3).map((m) => m.textContent.trim().slice(0, 60))]""")
            ergebnis = f"nicht {erwartet} {befund}"
        gesehen.append(ergebnis)
    b.pruefe("Stacki: Streicheln macht froh, Schütteln schwindelig (Knöpfe im Cockpit)",
             [g.split(" ")[0] for g in gesehen] == ["froh", "schwindelig"], " · ".join(gesehen))
    page.evaluate("() => window.removeEventListener('knowlin:state', window.__ausdruckHorcher)")
    page.remove_listener("websocket", _horchen)
    einstellen(page, {"modul": "duckpilot", "backend": "sim"})

    # 13d · Seit 0.38.19: Farbe der Microduck, Trainingsfeld mit vielen Enten
    oeffnen(page, base)
    einstellen(page, {"farbe": "lavender"})
    page.wait_for_timeout(2500)
    b.pruefe("Farbe der Microduck: Lavender kommt in der 3D-Ansicht an",
             page.evaluate("() => window.duckpilot.scene && window.duckpilot.scene.farbe") == "lavender")
    einstellen(page, {"farbe": "cream"})
    ansicht(page, "training")
    try:
        page.wait_for_function("() => /von 144/.test(document.getElementById('tr-feld-zahl')?.textContent || '')", timeout=30000)
        ok, zahl = True, page.text_content("#tr-feld-zahl")
    except Exception:  # noqa: BLE001
        ok, zahl = False, page.text_content("#tr-feld-zahl")
    b.pruefe("Trainingsfeld: 144 Enten üben, Zahl darunter", ok, zahl or "")
    # seit 0.38.23: mit gewählten Originalen auch im Feld die Originale (leichte Fassung vom Server)
    if page.evaluate("() => window.duckpilot.scene && window.duckpilot.scene.modelStyle === 'original' && !!window.duckpilot.scene.realDuck"):
        try:
            # seit 0.38.24 als Bildbogen aus dem vollen Modell – in Software-Grafik dauert das Zeichnen ein paar Minuten
            page.wait_for_function("() => /^original/.test(document.getElementById('tr-feld-canvas')?.dataset.figur || '')", timeout=420000)
            ok = True
        except Exception:  # noqa: BLE001
            ok = False
        b.pruefe("Trainingsfeld: Originalmodelle, wenn sie gewählt sind", ok,
                 page.evaluate("() => document.getElementById('tr-feld-canvas')?.dataset.figur"))
    art = page.text_content("#tr-feld-art") or ""
    b.pruefe("Trainingsfeld sagt ehrlich, was es ist (Vorschau oder gemessene Quote)",
             "hier lernt nichts" in art or "Gemessene Quote" in art, art)
    page.wait_for_timeout(2500)
    axe(page, b, axe_js, "Training mit Trainingsfeld", "#view-training")
    b.foto(page, "13-trainingsfeld", "Lernen → Training: Trainingsfeld")

    # 13e · Seit 0.38.24: eine Ente beim Start, Sicherungspunkte anlegen und Bereiche zurücksetzen (zwei Klicks)
    oeffnen(page, base)
    anzahl = page.evaluate("() => fetch('/api/enten').then((r) => r.json()).then((d) => d.anzahl)")
    b.pruefe("Beim Start nur eine Ente (keine weiteren im Zimmer)", anzahl == 0, f"weitere: {anzahl}")
    # weitere Enten in Pollens Farben, die eigene behält ihre (Wunsch 7.11.)
    page.evaluate("() => fetch('/api/settings', {method: 'POST', headers: {'content-type': 'application/json'},"
                  " body: JSON.stringify({weitere_enten: 3})})")
    try:
        page.wait_for_function("() => (window.duckpilot.scene.enten?.size || 0) >= 3", timeout=60000)
        farben = page.evaluate("() => { const sc = window.duckpilot.scene; return { eigene: sc.farbe || 'cream', gaeste:"
                               " [...sc.enten.keys()].map((id) => sc._gastFarben.get(id)) }; }")
    except Exception:  # noqa: BLE001
        farben = {"eigene": None, "gaeste": []}
    page.evaluate("() => fetch('/api/settings', {method: 'POST', headers: {'content-type': 'application/json'},"
                  " body: JSON.stringify({weitere_enten: 0})})")
    alle = [farben["eigene"], *farben["gaeste"]]
    b.pruefe("Weitere Enten in Pollens Farben, alle verschieden, die eigene behält ihre",
             len(farben["gaeste"]) == 3 and len(set(alle)) == 4, str(farben))
    ansicht(page, "settings")
    page.wait_for_timeout(1500)
    page.locator("#set-sicherung").scroll_into_view_if_needed()
    page.fill("#sich-name", "Abnahme")
    page.click("#sich-anlegen")
    try:
        page.wait_for_function("() => /Abnahme/.test(document.getElementById('sich-liste')?.textContent || '')", timeout=20000)
        ok = True
    except Exception:  # noqa: BLE001
        ok = False
    page.check("#sich-bereiche input[value='taenze']")
    page.click("#sich-reset")
    scharf = page.evaluate("() => document.getElementById('sich-reset').classList.contains('armed')")
    page.click("#sich-reset")
    try:
        page.wait_for_function("() => /Zurückgesetzt/.test(document.getElementById('sich-msg')?.textContent || '')", timeout=20000)
        zurueck = True
    except Exception:  # noqa: BLE001
        zurueck = False
    vorher = page.evaluate("() => /Vor dem Zurücksetzen/.test(document.getElementById('sich-liste')?.textContent || '')")
    b.pruefe("Sicherungspunkte: anlegen, Zurücksetzen erst beim zweiten Klick, vorher automatisch gesichert",
             ok and scharf and zurueck and vorher, f"angelegt={ok} scharf={scharf} zurück={zurueck} vorher={vorher}")
    axe(page, b, axe_js, "Einstellungen: Sicherungspunkte", "#set-sicherung")
    b.foto(page, "13e-sicherungspunkte", "Einstellungen → Sicherungspunkte")

    # 13i · Seit 0.38.32: Updates – Schalter und „Jetzt nach Updates suchen“ unter Über (offline: ehrliche Meldung)
    page.evaluate("() => document.getElementById('set-ueber').scrollIntoView()")
    page.wait_for_timeout(500)
    schalter = page.evaluate("() => !!document.querySelector('#set-ueber input[data-set=updates_suchen]')")
    page.click("#update-pruefen")
    try:
        page.wait_for_function("() => /offline|aktuell|ist da/.test(document.getElementById('update-stand').textContent)",
                               timeout=20000)
    except Exception:  # noqa: BLE001
        pass
    stand = page.text_content("#update-stand") or ""
    b.pruefe("Updates: Schalter und Suche unter Über, offline ehrlich gemeldet", schalter and "offline" in stand, stand)

    # 13k · Seit 0.38.33: Tricks mit Pollens Emotionen (fehlten im Paket) und Live-Vorschau daneben – Klick bleibt hier
    einstellen(page, {"modul": "duckpilot"})
    page.wait_for_timeout(2500)
    ansicht(page, "tricks")
    try:
        page.wait_for_selector("#emo-pollen .emo", timeout=15000)
    except Exception:  # noqa: BLE001
        pass
    pollen = page.evaluate("() => document.querySelectorAll('#emo-pollen .emo').length")
    vorschau = page.evaluate("() => !!document.querySelector('#tricks-vorschau canvas')")
    if pollen and page.is_visible("#emo-pollen .emo"):
        page.click("#emo-pollen .emo")
        page.wait_for_timeout(800)
    bleibt = page.evaluate("() => location.hash.startsWith('#tricks')")
    b.pruefe("Tricks: Pollens Emotionen da, Live-Vorschau daneben, Antippen bleibt auf der Seite",
             pollen >= 10 and vorschau and bleibt, f"{pollen} Emotionen · Vorschau {vorschau} · bleibt {bleibt}")
    b.foto(page, "13k-tricks-vorschau", "Tricks mit Live-Vorschau")
    # 13k2 · Seit 0.38.37: Die Vorschau läuft beim Blättern mit (gemeldet 9.11.: „das Fenster hängt ja oben fest“)
    mit = page.evaluate("""() => { const pg = document.querySelector('#view-tricks .page');
      const s = pg.scrollHeight > pg.clientHeight + 2 ? pg : document.scrollingElement;
      const k = document.querySelector('.tricks-vorschau-karte'); s.scrollTop = s.scrollHeight;
      const r = k.getBoundingClientRect(); const ok = r.bottom > 0 && r.top < innerHeight;
      s.scrollTop = 0; return [ok, Math.round(r.top)]; }""")
    b.pruefe("Tricks: Vorschau bleibt beim Blättern im Bild", bool(mit[0]), f"Oberkante ganz unten gescrollt: {mit[1]} px")
    ansicht(page, "settings")

    # 13l · Seit 0.44: Spiele für jeden Körper – „Ente sagt“ mit Knöpfen, Verstecken und Elfmeter sichtbar bei der Microduck
    page.evaluate("() => window.duckpilot.showView('tricks', 'spiele')")
    page.wait_for_timeout(1500)
    sichtbar = page.evaluate("() => ['sp-sagt', 'sp-versteck', 'sp-elfer'].map((i) => !!document.getElementById(i)?.offsetParent)")
    b.pruefe("Spiele: „Ente sagt“, Verstecken und Elfmeter bei der Microduck", all(sichtbar), str(sichtbar))
    page.click("#sp-sagt-start")
    try:
        page.wait_for_function("() => /sagt|Zeig|Nimm/.test(document.getElementById('sp-sagt-ansage').textContent)", timeout=10000)
        ansage = page.text_content("#sp-sagt-ansage")
    except Exception:  # noqa: BLE001
        ansage = page.text_content("#sp-sagt-ansage")
    b.pruefe("Spiele: „Ente sagt“ beginnt mit einer Ansage", any(w in (ansage or "") for w in ("sagt", "Zeig", "Nimm")), ansage)
    page.click("#sp-sagt-stopp")

    # 13m · Seit 0.45: Smart Home unter Alltag – Karte da, Cloud-Adressen abgewiesen, Aufräumen sagt ehrlich, was fehlt
    page.evaluate("() => window.duckpilot.showView('alltag')")
    page.wait_for_timeout(1500)
    karte = page.evaluate("() => ['al-haus', 'haus-ha-form', 'haus-aufraeumen'].map((i) => !!document.getElementById(i)?.offsetParent)")
    cloud = page.evaluate("() => fetch('/api/haus/ha', {method: 'POST', headers: {'Content-Type': 'application/json'},"
                          " body: JSON.stringify({adresse: 'https://abcd.ui.nabu.casa', token: 'x'.repeat(40)})}).then(r => r.json())")
    b.pruefe("Smart Home: Karte unter Alltag, Adresse in der Cloud abgewiesen", all(karte) and
             "eigenen Netz" in (cloud.get("fehler") or ""), f"{karte} · {cloud.get('fehler')}")
    page.click("#haus-aufraeumen")
    try:
        page.wait_for_function("() => /Korb|aufwecken|räume/.test(document.getElementById('haus-msg').textContent)", timeout=8000)
    except Exception:  # noqa: BLE001
        pass
    meldung = page.text_content("#haus-msg") or ""
    raeume = page.evaluate("() => ['haus-raum-form', 'haus-rundgang'].map((i) => !!document.getElementById(i)?.offsetParent)")
    b.pruefe("Smart Home: Räume und Rundgang bei der Microduck (seit 0.46)", all(raeume), str(raeume))
    b.pruefe("Smart Home: „Vor dem Saugroboter aufräumen“ antwortet ehrlich", any(w in meldung for w in ("Korb", "aufwecken", "räume")),
             meldung)

    # Seit 0.48: vor Zubehör und Mentor aufwecken – Rennen und Marionette brauchen eine stehende Ente
    page.evaluate("() => window.duckpilot.send({type: 'tool', name: 'power', args: {action: 'stand_up'}})")
    try:
        page.wait_for_function("() => (window.duckpilot.state || {}).powered === true", timeout=20000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(2500)
    # 13n · Seit 0.47: Zubehör der Microduck – Rollen anklemmen, Polaroid malt einen Traum, Rennen stellt sich auf
    page.evaluate("() => window.duckpilot.showView('tricks', 'zubehoer')")
    page.wait_for_timeout(1500)
    page.click("#zb-rollen-an")
    try:
        page.wait_for_function("() => /dran/.test(document.getElementById('zb-rollen-stand').textContent)", timeout=6000)
    except Exception:  # noqa: BLE001
        pass
    rollen = page.text_content("#zb-rollen-stand") or ""
    page.click("#zb-polaroid-halten")
    try:
        page.wait_for_function("() => !document.getElementById('zb-polaroid-laden').hidden", timeout=6000)
    except Exception:  # noqa: BLE001
        pass
    traum = page.text_content("#zb-polaroid-text") or ""
    b.foto(page, "13n-zubehoer", "Steuern → Zubehör: Rollen, Arena-Rennen, NFC-Polaroid")
    b.pruefe("Zubehör: Rollen angeklemmt, Polaroid zeigt einen Traum", "dran" in rollen and "geträumt" in traum,
             f"{rollen} · {traum}")
    rennen = page.evaluate("() => fetch('/api/zubehoer/rennen', {method: 'POST', headers: {'Content-Type': 'application/json'},"
                           " body: JSON.stringify({aktion: 'start'})}).then(r => r.json())")
    page.evaluate("() => fetch('/api/zubehoer/rennen', {method: 'POST', headers: {'Content-Type': 'application/json'},"
                  " body: JSON.stringify({aktion: 'stopp'})})")
    page.evaluate("() => fetch('/api/zubehoer/rollen', {method: 'POST', headers: {'Content-Type': 'application/json'},"
                  " body: JSON.stringify({an: false})})")
    b.pruefe("Zubehör: Arena-Rennen startet oder sagt ehrlich, warum nicht",
             bool(rennen.get("ok")) or any(w in (rennen.get("fehler") or "") for w in ("aufwecken", "Not-Aus")), str(rennen))

    # 13o · Seit 0.48: Mentor als Modul – Lernziel anlegen, Kopf im Feld führen (Marionette), Ziel wieder löschen
    page.evaluate("() => window.duckpilot.showView('cockpit')")
    page.wait_for_timeout(1500)
    page.evaluate("() => window.duckpilot.showView('mentor')")
    page.wait_for_timeout(1500)
    page.fill("#mt-neu-text", "Abnahme: nicken lernen")
    page.click("#mt-neu button[type=submit]")
    try:
        page.wait_for_function("() => /Abnahme: nicken lernen/.test(document.getElementById('mt-ziele').textContent)", timeout=6000)
    except Exception:  # noqa: BLE001
        pass
    ziel = "Abnahme: nicken lernen" in (page.text_content("#mt-ziele") or "")
    box = page.locator("#mt-feld").bounding_box()
    gedreht = None
    if box:
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        for i in range(25):
            page.mouse.move(box["x"] + box["width"] * 0.12, box["y"] + box["height"] * (0.5 - 0.01 * i))
            page.wait_for_timeout(70)
        gedreht = page.evaluate("() => ((window.duckpilot.state || {}).head || {}).head_yaw")
        page.mouse.up()
    b.foto(page, "13o-mentor", "Lernen → Mentor: Lernziele, Marionette, Übungen")
    b.pruefe("Mentor: Lernziel angelegt, Kopf folgt dem Feld (Marionette)", ziel and (gedreht or 0) > 0.15,
             f"Ziel: {ziel} · Kopf drehen {gedreht}")
    page.evaluate("""() => fetch('/api/mentor').then(r => r.json()).then(d => Promise.all(d.ziele.filter(z => z.eigen)
        .map(z => fetch('/api/mentor/ziel/' + z.id, {method: 'DELETE'}))))""")

    # 13p · Seit 0.49: Ablauf-Baukasten – zwei Karten anklicken, abspielen; Duck-Cards-Leser erkennt erzeugte AprilTags
    page.evaluate("() => window.duckpilot.showView('tricks', 'ablauf')")
    page.wait_for_timeout(1500)
    page.click("#ab-leeren")
    page.locator("#ab-palette button", has_text="Links drehen").first.click()
    page.locator("#ab-palette button", has_text="Juhu").first.click()
    page.click("#ab-start")
    try:
        page.wait_for_function("() => /fertig|Übersprungen/.test(document.getElementById('ab-stand').textContent)", timeout=30000)
    except Exception:  # noqa: BLE001
        pass
    lauf = page.text_content("#ab-stand") or ""
    erkannt = page.evaluate("""async () => {
        const { AR } = await import('/static/vendor/aruco36h11.js');
        const svg = (id) => new AR.Dictionary('APRILTAG_36h11').generateSVG(id);
        const c = Object.assign(document.createElement('canvas'), { width: 640, height: 320 });
        const ctx = c.getContext('2d');
        ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 640, 320);
        for (const [i, id] of [[0, 2], [1, 84]]) {
            const img = new Image();
            img.src = 'data:image/svg+xml,' + encodeURIComponent(svg(id));
            await img.decode();
            ctx.drawImage(img, 60 + i * 300, 60, 200, 200);
        }
        const d = new AR.Detector({ dictionaryName: 'APRILTAG_36h11' });
        return d.detectImage(640, 320, ctx.getImageData(0, 0, 640, 320).data).map((m) => m.id).sort((a, b) => a - b);
    }""")
    b.foto(page, "13p-ablauf", "Steuern → Ablauf: Baukasten und Duck Cards")
    b.pruefe("Ablauf: Baukasten spielt ab, Duck-Cards-Leser erkennt die Karten", "fertig" in lauf and erkannt == [2, 84],
             f"{lauf} · erkannt {erkannt}")

    # 13q · Seit 0.50: Knowlin Lab – Lernwege da, Zimmer aus einer Messung benutzen und zurück; Aufmerksamkeit-Schalter
    page.evaluate("() => window.duckpilot.showView('lab')")
    page.wait_for_timeout(1500)
    wege = page.evaluate("() => document.querySelectorAll('#lab-wege .lab-weg').length")
    messung = {"boden": [[-1.2, -1.0], [1.2, -1.0], [1.2, 1.0], [-1.2, 1.0]],
               "flaechen": [{"art": "table", "x": 0.6, "y": 0.4, "breite": 0.5, "tiefe": 0.5, "hoehe": 0.45}]}
    page.evaluate("(m) => fetch('/api/lab/raum', {method: 'POST', headers: {'Content-Type': 'application/json'},"
                  " body: JSON.stringify(m)})", messung)
    an = page.evaluate("() => fetch('/api/lab/raum/aktiv', {method: 'POST', headers: {'Content-Type': 'application/json'},"
                       " body: JSON.stringify({aktiv: true})}).then(r => r.json())")
    page.evaluate("() => window.duckpilot.showView('lab')")
    page.wait_for_timeout(1500)
    b.foto(page, "13q-lab", "Lernen → Lab: Lernwege, Gelerntes, Raum aus der Quest")
    aus = page.evaluate("() => fetch('/api/lab/raum/aktiv', {method: 'POST', headers: {'Content-Type': 'application/json'},"
                        " body: JSON.stringify({aktiv: false})}).then(r => r.json())")
    page.evaluate("() => fetch('/api/lab/raum', {method: 'DELETE'})")
    schalter = page.evaluate("() => !!document.querySelector('input[data-set=aufmerksamkeit]')")
    b.pruefe("Knowlin Lab: Lernwege, Zimmer aus der Quest benutzen und zurück, Schalter „Aufmerksamkeit suchen“",
             wege >= 6 and an.get("ok") and an.get("raum", {}).get("aktiv") and aus.get("ok") and schalter,
             f"{wege} Lernwege · an {an.get('text') or an.get('fehler')} · aus {aus.get('text') or aus.get('fehler')}")

    # 13r · Seit 0.51: Choreografie zum Ziehen – Tanz öffnen, aus der Palette antippen, Block wählen und löschen
    tanz = {"bpm": 120, "start": 0, "schritte": [{"t": 0, "takte": 2, "art": "nicken"}, {"t": 4, "takte": 2, "art": "wippen"}]}
    page.evaluate("(c) => fetch('/api/choreo/speichern', {method: 'POST', headers: {'Content-Type': 'application/json'},"
                  " body: JSON.stringify({name: 'Abnahme-Zeitleiste', choreo: c})})", tanz)
    page.evaluate("() => window.duckpilot.showView('tricks', 'tanz')")
    page.wait_for_timeout(1500)
    page.locator("#tanz-liste li", has_text="Abnahme-Zeitleiste").locator("button", has_text="Bearbeiten").first.click()
    page.wait_for_timeout(800)
    chips = page.locator("#tanz-palette .tanz-chip").count()
    vorher = page.locator("#tanz-schritte li:not(.tanz-teil)").count()
    page.locator("#tanz-palette .tanz-chip").first.click()
    page.wait_for_timeout(300)
    nachher = page.locator("#tanz-schritte li:not(.tanz-teil)").count()
    box = page.locator("#tanz-zeitleiste").bounding_box()
    page.mouse.click(box["x"] + 6, box["y"] + 90)                       # erster Block in der oberen Spur
    page.keyboard.press("Delete")
    page.wait_for_timeout(300)
    geloescht = page.locator("#tanz-schritte li:not(.tanz-teil)").count()
    b.foto(page, "13r-zeitleiste", "Tanzen: Palette und Zeitleiste zum Ziehen")
    page.evaluate("() => fetch('/api/choreo', {method: 'DELETE', headers: {'Content-Type': 'application/json'},"
                  " body: JSON.stringify({name: 'Abnahme-Zeitleiste'})})")
    b.pruefe("Choreografie zum Ziehen: Palette, Einfügen, Block löschen", chips >= 5 and nachher == vorher + 1
             and geloescht == nachher - 1, f"{chips} Bausteine · {vorher} → {nachher} → {geloescht} Schritte")

    # 13j · Seit 0.38.33: „Anderes Modell“ unter Einstellungen bietet Anbieter an (vorher leer), LM Studio ohne Server: Hinweis
    anbieter = page.evaluate("() => [...document.querySelectorAll('#anbieter-pick option')].map(o => o.value)")
    lm = page.evaluate("() => fetch('/api/anbieter/modelle', {method: 'POST', headers: {'Content-Type': 'application/json'},"
                       " body: JSON.stringify({anbieter: 'lmstudio', adresse: 'http://127.0.0.1:9/v1'})}).then(r => r.json())")
    b.pruefe("Anderes Modell: Anbieter unter Einstellungen gelistet, LM Studio ohne Server mit klarem Hinweis",
             {"openai", "eigen"} <= set(anbieter) and "lmstudio" not in anbieter      # seit 0.38.41 unter „Lokales Modell“
             and "LM Studio antwortet nicht" in (lm.get("fehler") or ""),
             f"{len(anbieter)} Anbieter · {lm.get('fehler')}")

    # 13f · Seit 0.38.27: Policies aus Isaac Lab – Karte, falsche Datei wird abgewiesen, nichts übernommen
    ansicht(page, "training")
    page.wait_for_timeout(1500)
    page.locator("#isaaclab").scroll_into_view_if_needed()
    aufgaben = page.evaluate("() => [...document.querySelectorAll('#il-aufgabe option')].map((o) => o.value)")
    # Seit 0.38.30: Quelle Hugging Face ist vorgewählt; eine fremde Adresse wird abgewiesen, bevor etwas geladen wird
    page.fill("#il-hf", "https://example.com/besitzer/policy.onnx")
    page.click("#il-go")
    page.wait_for_function("() => /huggingface\\.co/.test(document.getElementById('il-state').textContent)", timeout=30000)
    hf_ok = page.evaluate("() => !document.getElementById('il-hf-feld').hidden && document.getElementById('il-datei-feld').hidden")
    b.pruefe("Isaac Lab: Quelle Hugging Face vorgewählt, fremde Adresse abgewiesen",
             hf_ok and "huggingface.co" in (page.text_content("#il-state") or ""), page.text_content("#il-state") or "")
    page.evaluate("() => document.querySelector('input[name=il-quelle][value=datei]').click()")
    page.set_input_files("#il-datei", {"name": "kaputt.onnx", "mimeType": "application/octet-stream",
                                       "buffer": b"das ist keine Policy"})
    page.fill("#il-name", "abnahme")
    page.click("#il-go")
    try:
        page.wait_for_function("() => { const s = document.getElementById('il-state').textContent;"
                               " return s && !/Prüfe die Datei/.test(s); }", timeout=30000)
    except Exception:  # noqa: BLE001
        pass
    meldung = page.text_content("#il-state") or ""
    liste = page.evaluate("() => fetch('/api/isaaclab').then((r) => r.json()).then((d) => d.liste.length)")
    b.pruefe("Isaac Lab: Karte mit beiden Aufgaben, falsche Datei abgewiesen, nichts übernommen",
             any("Rough" in a for a in aufgaben) and any("Flat" in a for a in aufgaben) and meldung
             and "bestanden" not in meldung and liste == 0, f"{aufgaben} · {meldung[:100]} · {liste}")
    # Seit 0.38.35 („Warum laden wir nicht die Standard-Policy von Pollen …“ – „und wie man wieder die Standard-Policy
    # aktiviert“): oben steht, was läuft; der Weg zurück steht dort, wo man ihn sucht
    aktiv = page.evaluate("() => { const a = document.getElementById('il-aktiv'), f = document.getElementById('il-form');"
                          " return {text: document.getElementById('il-aktiv-text').textContent, vorne:"
                          " !!(a.compareDocumentPosition(f) & Node.DOCUMENT_POSITION_FOLLOWING),"
                          " knopf: !!a.querySelector('#il-standard')}; }")
    b.pruefe("Isaac Lab: oben steht, dass Pollens Standard läuft; „Zurück auf Pollens Standard“ sitzt dort",
             "Pollens Standard" in aktiv["text"] and aktiv["vorne"] and aktiv["knopf"], str(aktiv))
    axe(page, b, axe_js, "Training: Policies aus Isaac Lab", "#isaaclab")
    b.foto(page, "13f-isaaclab", "Lernen → Training: Policies aus Isaac Lab übernehmen")

    # 13g · Seit 0.38.27: „Was Knowlin über deine Welt weiß“ im Gedächtnis, Legende des Netzes in Worten
    ansicht(page, "memory")
    page.wait_for_timeout(2000)
    welt = page.evaluate("() => ({ da: !document.getElementById('welt').hidden,"
                         " text: document.getElementById('welt').textContent,"
                         " legende: document.querySelector('.brain-erklaerung')?.textContent || '' })")
    b.pruefe("Gedächtnis: Themenkarten „Was Knowlin über deine Welt weiß“ und Legende in Worten",
             welt["da"] and "über deine Welt" in welt["text"] and "Leuchten" in welt["legende"], welt["text"][:120])
    axe(page, b, axe_js, "Gedächtnis: Was Knowlin über deine Welt weiß", "#welt")

    # 13h · Seit 0.38.28 (T2): „Auf Handy oder Tablet“ auf der Startseite – ein Klick schaltet ein und zeigt den Code
    oeffnen(page, base)
    page.locator("#start-handy").scroll_into_view_if_needed()
    page.click("#handy-los")
    try:
        page.wait_for_function("() => !document.getElementById('handy-qr').hidden"
                               " || /Heimnetz/.test(document.getElementById('handy-hinweis').textContent)", timeout=20000)
    except Exception:  # noqa: BLE001
        pass
    handy = page.evaluate("() => ({ qr: !document.getElementById('handy-qr').hidden,"
                          " code: document.getElementById('handy-code').textContent,"
                          " hinweis: document.getElementById('handy-hinweis').textContent,"
                          " an: /^An/.test(document.getElementById('handy-satz').textContent) })")
    ok = handy["an"] and ((handy["qr"] and re.search(r"[A-Z2-9]{3}-[A-Z2-9]{3}", handy["code"] or ""))
                          or "Heimnetz" in handy["hinweis"])      # der Testrechner hat kein WLAN – dann ehrlich gesagt
    b.pruefe("Startseite: Auf Handy oder Tablet – einschalten, QR-Code und kurzer Code (oder ehrlich: kein Heimnetz)",
             bool(ok), f"{handy['code']} · {handy['hinweis'][:90]}")
    axe(page, b, axe_js, "Startseite: Auf Handy oder Tablet", "#start-handy")
    b.foto(page, "13h-handy", "Startseite → Auf Handy oder Tablet")
    page.evaluate("() => fetch('/api/fernzugang', {method: 'POST', headers: {'content-type': 'application/json'},"
                  " body: JSON.stringify({an: false})})")

    # 14 · Not-Aus
    oeffnen(page, base)
    page.keyboard.press("Escape")
    page.wait_for_timeout(1500)
    b.pruefe("Not-Aus per Esc ohne Skriptfehler", not b.fehler_js)


FINGER_JS = """() => {
  const out = [];
  if (!matchMedia('(pointer: coarse)').matches) return ['kein Finger-Zeiger erkannt'];
  if (document.documentElement.scrollWidth > innerWidth + 1) out.push('Seite breiter als Fenster');
  for (const el of document.querySelectorAll('main button, main select, main input:not([type=hidden]), main summary, .rail button, .top button')) {
    if (el.closest('[hidden]') || el.matches('.hud-help-btn, .pad-puck, .pad-mark, .sr-only') || (el.matches('button.link, a') && el.closest('p, li'))) continue;
    let ziel = el;
    if (el.matches('input[type=radio], input[type=checkbox]')) ziel = el.closest('label') || el;
    if (el.matches('input[type=range], input[type=color], input[type=file]')) continue;
    const r = ziel.getBoundingClientRect(), cs = getComputedStyle(ziel);
    if (!r.width || !r.height || cs.visibility === 'hidden' || cs.display === 'none' || r.bottom < 0 || r.top > innerHeight) continue;
    if (r.height < 43.5) out.push((ziel.id ? '#' + ziel.id : ziel.tagName.toLowerCase() + (ziel.className ? '.' + String(ziel.className).split(' ')[0] : '')
      + ' „' + (ziel.textContent || '').trim().slice(0, 20) + '“') + ' ' + Math.round(r.height) + ' px');
  }
  return [...new Set(out)];
}"""


def tablet(browser, base: str, b: "Bericht", axe_js: str | None) -> None:
    """Seit 0.38.27 (T1): Tablet hochkant und quer, mit Finger – nichts ragt heraus, Ziele mindestens 44 px hoch.
    Kleine runde Griffe (Hilfe-Knopf, Punkte im Steuerkreuz) haben ihre 44 px als unsichtbare Fläche (::before)."""
    for breite, hoehe, lage in ((820, 1180, "hochkant"), (1180, 820, "quer")):
        page = browser.new_page(viewport={"width": breite, "height": hoehe}, has_touch=True)
        page.on("pageerror", lambda e: b.fehler_js.append(str(e)))
        page.set_default_timeout(90000)
        funde = []
        oeffnen(page, base, "cockpit")
        for v in ("cockpit", "memory", "training", "settings"):
            ansicht(page, v)
            page.wait_for_timeout(1500)
            funde += [f"{v}: {f}" for f in page.evaluate(FINGER_JS)]
        b.foto(page, f"15-tablet-{lage}", f"Tablet {lage} ({breite}×{hoehe}), Einstellungen")
        ansicht(page, "cockpit")
        page.wait_for_timeout(1500)
        b.foto(page, f"15-tablet-{lage}-cockpit", f"Tablet {lage} ({breite}×{hoehe}), Cockpit")
        b.pruefe(f"Tablet {lage} ({breite} px): nichts ragt heraus, Fingerziele mindestens 44 px",
                 not funde, "; ".join(funde[:8]))
        page.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ordner", type=Path)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--axe", type=Path, default=None)
    ap.add_argument("--installiert", default=None, metavar="PYTHON",
                    help="Python einer frischen Umgebung mit installiertem Paket ohne Zusatzpakete (wie nach dem "
                         "Installer) – prüft das Paket statt des Quellordners")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright

    from duckpilot import __version__

    ordner = a.ordner.resolve()
    ordner.mkdir(parents=True, exist_ok=True)
    port = a.port or freier_port()
    base = f"http://127.0.0.1:{port}"
    axe_js = a.axe.read_text(encoding="utf-8") if a.axe and a.axe.exists() else None
    b = Bericht(ordner)
    t0 = time.time()
    proc = server_starten(ordner, port, a.installiert)
    try:
        with sync_playwright() as pw:
            # Fake-Webcam für die Kamera-Spiele (Bilder bleiben im Browser – so auch hier)
            browser = pw.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
            page = browser.new_page(viewport={"width": 1300, "height": 820})
            page.on("pageerror", lambda e: b.fehler_js.append(str(e)))
            page.set_default_timeout(90000)
            try:
                ablauf(page, base, b, axe_js, ordner)
                tablet(browser, base, b, axe_js)
            except Exception as e:  # noqa: BLE001 – Abbruch mitten im Ablauf ist selbst ein Befund
                b.pruefe("Ablauf vollständig", False, f"{type(e).__name__}: {str(e).splitlines()[0][:150]}")
                try:
                    b.foto(page, "99-abbruch", "Stand beim Abbruch")
                except Exception:  # noqa: BLE001
                    pass
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
    datei = b.schreiben(__version__, time.time() - t0)
    print(f"\nBericht: {datei}")
    return 0 if b.bestanden else 1


if __name__ == "__main__":
    raise SystemExit(main())
