#!/usr/bin/env python3
"""Website knowlin.de automatisch prüfen – im echten Browser (Playwright, Chromium).

    python tools/website_pruefen.py <ordner> [--axe pfad/zu/axe.min.js]

Baut die Seite (tools/website.py), liefert sie lokal aus und prüft:
* Barrierefreiheit mit axe-core (WCAG 2.0–2.2 A/AA und Best Practice) in Deutsch/Englisch, hell/dunkel, Handy/Desktop
* keine waagerechte Scrollleiste von 320 bis 1920 px, auch mit erhöhten Textabständen (WCAG 1.4.12)
* Tastatur: alles erreichbar, Fokus sichtbar, Pfeiltasten im Umschalter, Sprung zum Inhalt
* keine Skriptfehler, keine fehlenden Dateien, keine Anfragen an fremde Server
* ohne JavaScript: deutscher Text, Bilder da, nichts doppelt
* „Bewegung reduzieren“: keine Bewegung über 1 px
* Bildnachweis: jedes Bild mit Pollens 3D-Modellen nennt Urheber und Lizenz (CC BY-NC-SA 4.0), auch unter der Bühne

Ergebnis: `<ordner>/bericht.md` mit Bildern. Rückgabewert 0, wenn alles bestanden ist.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from website import MIT_AUSPROBIEREN, POLLEN_BILDER, bauen  # noqa: E402

BREITEN = (320, 390, 768, 1280, 1920)
TEXTABSTAENDE = """* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; }
p { margin-bottom: 2em !important; }"""


class Bericht:
    def __init__(self) -> None:
        self.zeilen: list[tuple[str, bool, str]] = []

    def pruefe(self, was: str, ok: bool, detail: str = "") -> None:
        self.zeilen.append((was, bool(ok), detail))
        print(("OK   " if ok else "FEHL ") + was + (f" – {detail}" if detail and not ok else ""))

    @property
    def bestanden(self) -> bool:
        return all(ok for _, ok, _ in self.zeilen)


def ausliefern(ordner: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    class Leise(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a) -> None:
            pass

    handler = functools.partial(Leise, directory=str(ordner))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}/"


def seite(browser, url, *, breite=1280, hoehe=900, thema="light", sprache="de", js=True, bewegung="no-preference",
          zusatz_css=None, beobachten=None):
    ctx = browser.new_context(viewport={"width": breite, "height": hoehe}, color_scheme=thema, java_script_enabled=js,
                              reduced_motion=bewegung)
    if js:
        ctx.add_init_script(f"try {{ localStorage.setItem('knowlin.sprache', '{sprache}') }} catch (e) {{}}")
    p = ctx.new_page()
    if beobachten is not None:
        p.on("console", lambda m: beobachten["fehler"].append(m.text) if m.type == "error" else None)
        p.on("pageerror", lambda e: beobachten["fehler"].append(str(e)))
        p.on("request", lambda r: beobachten["anfragen"].append(r.url))
        p.on("response", lambda r: beobachten["fehlend"].append(r.url) if r.status >= 400 else None)
    p.goto(url, wait_until="networkidle")
    if zusatz_css:
        p.add_style_tag(content=zusatz_css)
    p.wait_for_timeout(300)
    return ctx, p


def axe(p, quelle: str) -> list[str]:
    p.add_script_tag(content=quelle)
    r = p.evaluate("""async () => (await axe.run(document, { runOnly: { type: 'tag', values:
        ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] } })).violations
        .map(v => `${v.id}: ${v.nodes.map(n => n.target.join(' ')).slice(0, 3).join(', ')}`)""")
    return r


def ueberlauf(p) -> int:
    return p.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ordner")
    ap.add_argument("--axe", required=True, help="Pfad zu axe.min.js (npm-Paket axe-core)")
    a = ap.parse_args()
    out = Path(a.ordner)
    out.mkdir(parents=True, exist_ok=True)
    site = bauen(out / "seite")
    srv, url = ausliefern(site)
    axe_js = Path(a.axe).read_text(encoding="utf-8")
    b = Bericht()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        br = pw.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        # 1 · Skriptfehler, fehlende Dateien, fremde Server
        obs = {"fehler": [], "anfragen": [], "fehlend": []}
        ctx, p = seite(br, url, beobachten=obs)
        for name in ("reachy", "odi", "microduck"):
            p.click(f"[data-koerper={name}]")
            p.wait_for_timeout(400)
        p.click("#sprache-en"); p.wait_for_timeout(400); p.click("#sprache-de"); p.wait_for_timeout(300)
        p.evaluate("window.scrollTo(0, document.body.scrollHeight)"); p.wait_for_timeout(600)
        ctx.close()
        b.pruefe("Keine Skriptfehler", not obs["fehler"], "; ".join(obs["fehler"][:3]))
        b.pruefe("Keine fehlenden Dateien", not obs["fehlend"], ", ".join(obs["fehlend"][:3]))
        fremd = sorted({u for u in obs["anfragen"] if not u.startswith(url) and not u.startswith(("data:", "blob:"))})
        b.pruefe("Keine Anfragen an fremde Server", not fremd, ", ".join(fremd[:3]))

        # 2 · Barrierefreiheit (axe) und Bilder je Sprache, Thema, Breite
        for sprache in ("de", "en"):
            for thema in ("light", "dark"):
                for breite in (390, 1280):
                    ctx, p = seite(br, url, breite=breite, thema=thema, sprache=sprache)
                    v = axe(p, axe_js)
                    b.pruefe(f"axe ohne Verstöße ({sprache}, {thema}, {breite} px)", not v, "; ".join(v[:4]))
                    if breite == 1280 and thema == "light":
                        p.screenshot(path=str(out / f"seite-{sprache}.png"), full_page=True)
                    if breite == 390 and thema == "dark":
                        p.screenshot(path=str(out / f"handy-{sprache}-dunkel.png"), full_page=True)
                        # Fund 12.11.: „Microduck“ ragte am Handy über den Rand seines Ankers
                        ueber = p.evaluate("""() => [...document.querySelectorAll('.anker')].filter((a) => {
                            const k = a.getBoundingClientRect(), r = document.createRange(); r.selectNodeContents(a.firstChild);
                            const q = r.getBoundingClientRect(); return q.left < k.left + 2 || q.right > k.right - 2;
                          }).map((a) => a.firstChild.textContent.trim())""")
                        b.pruefe(f"Handy: Körpernamen bleiben in ihren Ankern ({sprache})", not ueber, str(ueber))
                    ctx.close()

        # 2b · Impressum und Datenschutz (seit 0.38.27): aus der Fußzeile erreichbar, barrierefrei, nichts Fremdes
        ctx, p = seite(br, url)
        links = p.evaluate("() => [...document.querySelectorAll('footer .rechtliches a')].map(a => a.getAttribute('href'))")
        ctx.close()
        b.pruefe("Fußzeile verlinkt Impressum und Datenschutz", links == ["impressum.html", "datenschutz.html"], str(links))
        for name in ("impressum", "datenschutz"):
            obs = {"fehler": [], "anfragen": [], "fehlend": []}
            funde, breit = [], 0
            for sprache, thema, breite in (("de", "light", 1280), ("en", "dark", 390), ("de", "dark", 320)):
                ctx, p = seite(br, url + f"{name}.html", breite=breite, thema=thema, sprache=sprache, beobachten=obs)
                funde += [f"{sprache}/{thema}/{breite}: {v}" for v in axe(p, axe_js)]
                breit = max(breit, ueberlauf(p))
                if thema == "light":
                    p.screenshot(path=str(out / f"{name}.png"), full_page=True)
                ctx.close()
            fremd = sorted({u for u in obs["anfragen"] if not u.startswith(url) and not u.startswith(("data:", "blob:"))})
            b.pruefe(f"{name.capitalize()}: axe ohne Verstöße, keine Scrollleiste, nichts Fremdes",
                     not funde and breit <= 0 and not fremd and not obs["fehler"] and not obs["fehlend"],
                     "; ".join((funde + fremd + obs["fehler"] + obs["fehlend"])[:4]) + (f" · {breit} px zu breit" if breit > 0 else ""))

        # 2c · Odi ausprobieren (seit 0.38.29): verlinkt, barrierefrei, Odi lädt erst auf Klick, läuft, nichts Fremdes – vorerst aus (website.MIT_AUSPROBIEREN)
        ctx, p = seite(br, url)
        verlinkt = p.evaluate("() => [...document.querySelectorAll('a[href=\"ausprobieren.html\"]')].length")
        ctx.close()
        if not MIT_AUSPROBIEREN:
            b.pruefe("Keine Links auf die (vorerst abgeschaltete) Seite „Odi ausprobieren“",
                     verlinkt == 0 and not (site / "ausprobieren.html").exists() and not (site / "demo").exists(), str(verlinkt))
        else:
            b.pruefe("Startseite verlinkt „Odi ausprobieren“ (Navigation und Startbereich)", verlinkt >= 2, str(verlinkt))
            obs = {"fehler": [], "anfragen": [], "fehlend": []}
            funde, breit = [], 0
            for sprache, thema, breite in (("de", "light", 1280), ("en", "dark", 390), ("de", "dark", 320)):
                ctx, p = seite(br, url + "ausprobieren.html", breite=breite, thema=thema, sprache=sprache, beobachten=obs)
                funde += [f"{sprache}/{thema}/{breite}: {v}" for v in axe(p, axe_js)]
                breit = max(breit, ueberlauf(p))
                ctx.close()
            vorab = [u for u in obs["anfragen"] if "odi-modell" in u]
            b.pruefe("Ausprobieren: axe ohne Verstöße, keine Scrollleiste, Modell erst auf Klick",
                     not funde and breit <= 0 and not vorab, "; ".join(funde[:4]) + (f" · {breit} px zu breit" if breit > 0 else "")
                     + (" · Modell vorab geladen" if vorab else ""))
            ctx, p = seite(br, url + "ausprobieren.html", beobachten=obs)
            p.set_default_timeout(180000)
            p.click("#odi-start")
            p.wait_for_selector("#vorhang", state="hidden")
            p.wait_for_timeout(1000)
            p.click("[data-trick=tanzen]")
            p.fill("#sagen-text", "geh zum Ball")
            p.press("#sagen-text", "Enter")
            p.wait_for_timeout(1500)
            antwort = p.text_content("#antwort") or ""
            laeuft = p.evaluate("() => !document.getElementById('odi-bild').hidden")
            v = axe(p, axe_js)
            p.screenshot(path=str(out / "ausprobieren.png"))
            ctx.close()
            fremd = sorted({u for u in obs["anfragen"] if not u.startswith(url) and not u.startswith(("data:", "blob:"))})
            b.pruefe("Ausprobieren: Odi startet, versteht „geh zum Ball“, axe auch im Betrieb, nichts Fremdes, keine Fehler",
                     laeuft and "Ball" in antwort and not v and not fremd and not obs["fehler"] and not obs["fehlend"],
                     "; ".join([antwort[:40], *v[:2], *fremd[:2], *obs["fehler"][:2], *obs["fehlend"][:2]]))

        # 3 · Breiten und Textabstände (WCAG 1.4.10, 1.4.12)
        for breite in BREITEN:
            ctx, p = seite(br, url, breite=breite, hoehe=800)
            b.pruefe(f"Keine waagerechte Scrollleiste bei {breite} px", ueberlauf(p) <= 0, f"{ueberlauf(p)} px zu breit")
            ctx.close()
        for breite in (320, 1280):
            ctx, p = seite(br, url, breite=breite, zusatz_css=TEXTABSTAENDE)
            b.pruefe(f"Textabstände erhöht, nichts ragt heraus ({breite} px)", ueberlauf(p) <= 0, f"{ueberlauf(p)} px")
            ctx.close()

        # 4 · Tastatur
        ctx, p = seite(br, url)
        p.keyboard.press("Tab")
        erster = p.evaluate("document.activeElement.textContent.trim()")
        b.pruefe("Erster Tab: „Zum Inhalt springen“", "Inhalt" in erster, erster[:40])
        reihe, ohne_rahmen = [], []
        for _ in range(40):
            p.keyboard.press("Tab")
            info = p.evaluate("""() => { const e = document.activeElement; if (e === document.body) return { id: null };
                const s = getComputedStyle(e);
                return { id: e.id || e.textContent.trim().replace(/\\s+/g, ' ').slice(0, 30), fv: e.matches(':focus-visible'),
                         sichtbar: s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0 } }""")
            if info["id"] is None:          # Fokus hat die Seite verlassen (Ende der Tab-Reihe)
                continue
            reihe.append(info["id"])
            if not info["sichtbar"]:
                ohne_rahmen.append(info["id"])
        b.pruefe("Fokus überall sichtbar", not ohne_rahmen, ", ".join(ohne_rahmen[:5]))
        b.pruefe("Umschalter und Kopierknopf per Tab erreichbar", "tab-microduck" in reihe and "kopieren" in reihe,
                 " / ".join(reihe[:12]))
        # Seit 0.38.35 (Foto: „die Schrift beim Button ist nicht mittig“): Text im Kopierknopf links und rechts gleich weit
        rand = p.evaluate("""() => { const b = document.getElementById('kopieren');
            const t = [...b.querySelectorAll('.t')].find((s) => s.offsetWidth > 0);
            const bb = b.getBoundingClientRect(), tb = t.getBoundingClientRect();
            return [tb.left - bb.left, bb.right - tb.right]; }""")
        b.pruefe("Kopierknopf: Text mittig", abs(rand[0] - rand[1]) <= 2, f"links {rand[0]:.1f} px, rechts {rand[1]:.1f} px")
        p.focus("#tab-microduck")
        p.keyboard.press("ArrowRight"); p.wait_for_timeout(400)
        gewaehlt = p.evaluate("document.querySelector('[role=tab][aria-selected=true]').id")
        fokus = p.evaluate("document.activeElement.id")
        b.pruefe("Pfeiltaste wählt den nächsten Körper (Fokus folgt)", gewaehlt == "tab-reachy" and fokus == "tab-reachy",
                 f"{gewaehlt}/{fokus}")
        p.keyboard.press("End"); p.wait_for_timeout(400)
        b.pruefe("Ende springt zum letzten Körper (Bittle X, seit 0.38.59)",
                 p.evaluate("document.querySelector('[role=tab][aria-selected=true]').id") == "tab-bittle")
        bittle_nachweis = p.evaluate("document.getElementById('buehne-nachweis').dataset.nachweis")
        p.keyboard.press("ArrowLeft"); p.wait_for_timeout(400)                   # zu Stack-chan
        stack_nachweis = p.evaluate("document.getElementById('buehne-nachweis').dataset.nachweis")
        p.keyboard.press("ArrowLeft"); p.wait_for_timeout(400)                   # zu Ari
        ari_steck = p.text_content(".steckbrief") or ""
        ari_nachweis = p.evaluate("document.getElementById('buehne-nachweis').dataset.nachweis")
        # Fund 12.11.: Mit fest drei Spalten rutschte der vierte Reiter unter Microduck, der Schieber lag daneben
        reihe = p.evaluate("""() => { const t = [...document.querySelectorAll('.wahl [role=tab]')];
            const s = document.querySelector('.wahl .schieber').getBoundingClientRect();
            const a = document.querySelector('.wahl [aria-selected=true]').getBoundingClientRect();
            return { zeilen: new Set(t.map((x) => Math.round(x.getBoundingClientRect().top))).size,
                     versatz: Math.round(Math.abs(s.left - a.left) + Math.abs(s.width - a.width)) }; }""")
        b.pruefe("Alle Körper-Reiter in einer Zeile, Schieber unter dem gewählten",
                 reihe["zeilen"] == 1 and reihe["versatz"] <= 4, str(reihe))
        p.keyboard.press("ArrowLeft"); p.wait_for_timeout(400)                   # zurück zu Odi
        steck = p.text_content(".steckbrief") or ""
        b.pruefe("Steckbrief passt zum gewählten Körper", "Open Duck Mini v2" in steck and "SO-101" in ari_steck,
                 f"{steck[:40]} / {ari_steck[:40]}")
        odi_nachweis = p.evaluate("document.getElementById('buehne-nachweis').dataset.nachweis")
        p.keyboard.press("Home"); p.wait_for_timeout(400)
        # Bildnachweis (seit 0.38.40): jedes sichtbare Bild mit Pollens Modell hat im selben Abschnitt einen Nachweis
        # mit Urheber, Lizenz und Link – die Bühne zeigt ihn je nach Körper (Odi: offenes Modell, ohne Pollen-Hinweis)
        ohne = p.evaluate("""(namen) => [...document.querySelectorAll('img[data-bild]')].filter((img) => {
            if (!namen.includes(img.dataset.bild)) return false;
            const bereich = img.closest('.bildspalte, section');
            const n = bereich && bereich.querySelector('.bildnachweis[data-nachweis=pollen]');
            const ok = n && n.offsetParent && /Pollen Robotics/.test(n.textContent) && /CC BY-NC-SA 4\\.0/.test(n.textContent)
              && n.querySelector('a[href*="creativecommons.org/licenses/by-nc-sa/4.0"]');
            return !ok; }).map((img) => img.dataset.bild)""", list(POLLEN_BILDER))
        b.pruefe("Bildnachweis: jedes Bild mit Pollens Modell nennt Urheber und Lizenz (Odi, Ari, Stack-chan, Bittle ohne)",
                 not ohne and odi_nachweis == ari_nachweis == stack_nachweis == bittle_nachweis == "offen",
                 f"ohne Nachweis: {ohne} · Odi: {odi_nachweis} · Ari: {ari_nachweis} · Stack-chan: {stack_nachweis}"
                 f" · Bittle: {bittle_nachweis}")
        ctx.close()

        # 5 · Ohne JavaScript
        ctx, p = seite(br, url, js=False)
        sichtbar = p.evaluate("""() => [...document.querySelectorAll('.t')].filter(e => e.offsetParent !== null)
            .map(e => e.lang)""")
        b.pruefe("Ohne JavaScript: nur Deutsch sichtbar", sichtbar and set(sichtbar) == {"de"}, str(set(sichtbar)))
        bilder = p.evaluate("[...document.images].filter(i => i.loading !== 'lazy').every(i => i.complete && i.naturalWidth > 0)")
        b.pruefe("Ohne JavaScript: Bilder geladen", bilder)
        ctx.close()

        # 6 · Bewegung reduzieren
        ctx, p = seite(br, url, bewegung="reduce")
        dauer = p.evaluate("""() => { const e = document.querySelector('.wahl .schieber'); return getComputedStyle(e).transitionDuration }""")
        b.pruefe("Bewegung reduzieren: Umschalter springt ohne Gleiten", dauer in ("0s", "0s, 0s"), dauer)
        ctx.close()
        br.close()
    srv.shutdown()

    zeilen = ["# Prüfbericht Website knowlin.de", "",
              f"**{sum(ok for _, ok, _ in b.zeilen)} von {len(b.zeilen)} Prüfungen bestanden** (Chromium, Playwright, axe-core)", "",
              "| Prüfung | Ergebnis | Hinweis |", "|---|---|---|"]
    zeilen += [f"| {w} | {'✅' if ok else '❌'} | {d if not ok else ''} |" for w, ok, d in b.zeilen]
    (out / "bericht.md").write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    (out / "ergebnis.json").write_text(json.dumps({"bestanden": b.bestanden, "pruefungen": len(b.zeilen)}), encoding="utf-8")
    print(f"\n{sum(ok for _, ok, _ in b.zeilen)} von {len(b.zeilen)} bestanden – Bericht: {out / 'bericht.md'}")
    return 0 if b.bestanden else 1


if __name__ == "__main__":
    raise SystemExit(main())
