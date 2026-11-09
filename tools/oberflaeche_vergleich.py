"""Oberfläche vorher/nachher vergleichen – für Umbauten ohne sichtbare Änderung (Architektur-Etappe A2, seit 0.38.38).

Beim Aufteilen von index.html und style.css in Bereiche darf sich nichts ändern, was man sieht. Dieses Werkzeug hält für
jede Ansicht (und jeden Körper) die berechneten Stile aller sichtbaren Elemente fest und vergleicht zwei Aufnahmen:

    python tools/oberflaeche_vergleich.py aufnehmen <ordner> <datei.json>
    python tools/oberflaeche_vergleich.py vergleichen <vorher.json> <nachher.json>

Aufgenommen wird im Simulator ohne Netz, wie bei der Abnahme, in zwei Breiten (PC 1440 px, Handy 390 px). Inhalte,
die sich von selbst bewegen (3D-Bild, Uhrzeiten, Zähler), sind ausgenommen; verglichen werden nur Stile, nicht Texte.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import abnahme as A  # noqa: E402

BREITEN = ((1440, 900), (390, 844))
KOERPER = (("duckpilot", A.KOERPER_ANSICHTEN), ("reachy_mini", A.KOERPER_ANSICHTEN))

# Eigenschaften, die sich ohne Umbau von selbst ändern (Animationen, Zeiger, Bildlauf)
UNRUHIG = {"transform", "opacity", "animation-name", "animation-play-state", "transition", "caret-color", "cursor",
           "will-change", "translate", "rotate", "scale", "offset-distance", "stroke-dashoffset", "background-position",
           "inset-block-start", "inset-block-end", "top", "bottom", "left", "right", "inset-inline-start",
           "inset-inline-end", "width", "height", "block-size", "inline-size", "perspective-origin",
           "transform-origin", "d", "x", "y", "r", "cx", "cy", "min-inline-size", "min-block-size"}

AUFNAHME_JS = """(unruhig) => {
  const raus = new Set(unruhig);
  const out = {};
  const view = [...document.querySelectorAll('.view')].find((v) => !v.hidden);
  if (!view) return out;
  const pfad = (el) => { const t = []; for (let e = el; e && e !== view; e = e.parentElement) {
      const geschw = e.parentElement ? [...e.parentElement.children].filter((k) => k.tagName === e.tagName) : [e];
      t.push(e.id ? '#' + e.id : e.tagName.toLowerCase() + ':' + geschw.indexOf(e)); if (e.id) break; }
    return t.reverse().join('>'); };
  for (const el of view.querySelectorAll('*')) {
    if (el.closest('canvas, svg, [aria-live], .log, time')) continue;
    if (!(el.checkVisibility ? el.checkVisibility() : el.offsetParent)) continue;
    const s = getComputedStyle(el); const w = {};
    for (let i = 0; i < s.length; i++) { const n = s[i]; if (!raus.has(n) && !n.startsWith('--')) w[n] = s.getPropertyValue(n); }
    out[pfad(el)] = w;
  }
  return out;
}"""


def aufnehmen(ordner: Path, datei: Path) -> None:
    from playwright.sync_api import sync_playwright

    ordner.mkdir(parents=True, exist_ok=True)
    port = A.freier_port()
    proc = A.server_starten(ordner, port)
    base = f"http://127.0.0.1:{port}"
    erg: dict[str, dict[str, dict[str, str]]] = {}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            for w, h in BREITEN:
                page = b.new_page(viewport={"width": w, "height": h}, reduced_motion="reduce")
                A.oeffnen(page, base)
                for modul, ansichten in KOERPER:
                    A.einstellen(page, {"modul": modul, "backend": "sim", "sim_physik": False, "sprache": "de"})
                    A.oeffnen(page, base)
                    for v, teil in ansichten:
                        if modul != "duckpilot" and (v in A.NUR_MICRODUCK or teil in A.NUR_MICRODUCK):
                            continue
                        page.evaluate("([n, t]) => window.duckpilot.showView(n, t)", [v, teil])
                        page.wait_for_timeout(1200)
                        A.ruhig(page)
                        erg[f"{w}/{modul}/{v}/{teil or ''}"] = page.evaluate(AUFNAHME_JS, sorted(UNRUHIG))
                page.close()
            b.close()
    finally:
        proc.terminate()
    datei.write_text(json.dumps(erg, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    n = sum(len(x) for x in erg.values())
    print(f"{len(erg)} Ansichten, {n} Elemente → {datei}")


def _ohne_port(w: dict[str, str]) -> dict[str, str]:
    """Adressen enthalten den zufälligen Port des Testservers – für den Vergleich weglassen."""
    return {k: re.sub(r"127\.0\.0\.1:\d+", "127.0.0.1", v) for k, v in w.items()}


def _kurz(w: dict[str, str]) -> str:
    return hashlib.sha1(json.dumps(w, sort_keys=True).encode()).hexdigest()


def vergleichen(vorher: Path, nachher: Path, zeigen: int = 40) -> int:
    a = {v: {e: _ohne_port(w) for e, w in x.items()} for v, x in json.loads(vorher.read_text(encoding="utf-8")).items()}
    b = {v: {e: _ohne_port(w) for e, w in x.items()} for v, x in json.loads(nachher.read_text(encoding="utf-8")).items()}
    funde: list[str] = []
    for ansicht in sorted(set(a) | set(b)):
        ea, eb = a.get(ansicht, {}), b.get(ansicht, {})
        for el in sorted(set(ea) | set(eb)):
            if el not in ea or el not in eb:
                funde.append(f"{ansicht} {el}: {'neu' if el not in ea else 'fehlt'}")
                continue
            if _kurz(ea[el]) != _kurz(eb[el]):
                diff = [f"{k}: {ea[el].get(k)} → {eb[el].get(k)}" for k in sorted(set(ea[el]) | set(eb[el]))
                        if ea[el].get(k) != eb[el].get(k)]
                funde.append(f"{ansicht} {el}: " + "; ".join(diff[:4]))
    for f in funde[:zeigen]:
        print(f)
    print(f"{len(funde)} Unterschiede in {len(set(a) | set(b))} Ansichten")
    return 1 if funde else 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) == 3 and argv[0] == "aufnehmen":
        aufnehmen(Path(argv[1]), Path(argv[2]))
        return 0
    if len(argv) == 3 and argv[0] == "vergleichen":
        return vergleichen(Path(argv[1]), Path(argv[2]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
