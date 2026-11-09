"""Inhalte auf Sinn und Konsistenz (Audit 0.38.14, Hinweis aus dem Test vom 5.11.: „Logische Zusammenhänge und Inhalte
sollten geprüft sein!“).

Statisch, ohne Browser:
- Für Nutzer heißt die App **Knowlin** – „duckpilot“ nur, wo wirklich das Enten-Modul, das Python-Paket oder ein
  Befehl/Ordner gemeint ist (kleine, begründete Erlaubt-Liste).
- Enten-Wörter (Ente, quaken, Schnabel, watscheln, Gefieder) nur in Bereichen, die Reachy Mini nie sieht.
- Bedienelemente mit Körperbezug (Tiefensensor, Laufen, Schnabel …) tragen eine Körper-Klasse.
- Progressive Offenlegung: Zusatzfelder nur bei passender Wahl (auch per node mit kleinem Ersatz-DOM geprüft).
Der Browser-Teil (sichtbarer Text je Körper) steht als Vorschlag für `tools/abnahme.py` in der Rückmeldung des Audits.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser

import pytest

from duckpilot.server.app import STATIC
from duckpilot.server.oberflaeche import seite, stil

INDEX = seite()
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
ATTRS = ("title", "aria-label", "placeholder", "alt")

# „duckpilot“ darf stehen, wo das Paket, der Codename, ein Befehl, ein Ordner oder eine Datei gemeint ist
DUCKPILOT_ERLAUBT = re.compile(
    r"Python-Paket duckpilot|Codenamen der Module: duckpilot|duckpilot für die Enten|%LOCALAPPDATA%\\+duckpilot|"
    r"duckpilot\.toml|-m duckpilot|duckpilot\.log")

ENTE = re.compile(r"\b(Enten?\w*|\w+ente\b|quak\w*|Schnabel\w*|watschel\w*|Gefieder\w*)", re.I)
# Wörter, die nur zufällig auf „-ente“ enden
KEINE_ENTE = re.compile(r"\b(intelligente|Akzente?|Momente?|Elemente?|Argumente?|Dokumente?|Prozente?|Instrumente?|"
                        r"Segmente?|Patente?|Rente|Komponente\w*|Talente?|Experimente?)\b", re.I)
# Bereiche, die Reachy nie sieht: Klassen am Element oder darüber, ids, Unterseiten
OHNE_REACHY_KLASSEN = {"nur-ente", "nur-microduck", "nur-open-duck", "braucht-beine", "braucht-schnabel",
                       "braucht-tiefensensor"}
OHNE_REACHY_IDS = {
    "view-akrobatik", "view-parcours", "view-training",    # Lernen gibt es nur bei der Microduck (modul.js)
    "view-design",                                          # Werkstattseite Designsystem
    "ctl",                                                  # Handy-Controller: nur über den Knopf mit braucht-beine
    "stimme-sub",                                           # Platzhalter, stimme.js setzt ihn je Verkörperung
}
OHNE_REACHY_TEILE = {"team", "hub"}                          # tricks/team, tricks/hub: NUR_MICRODUCK in modul.js
# Begründete Ausnahmen: Gäste im Simulator sind echte Enten, die Microduck-Einrichtung, die Codenamen unter „Über“
ENTE_ERLAUBT = re.compile(r"Enten? zu Besuch|duckpilot für die Enten|Meine echte Ente|Ente auf den Ständer")


class _Texte(HTMLParser):
    """Alle Texte und Attribute (title, aria-label, placeholder, alt) mit den Elementen darüber."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stapel: list[tuple[str, dict]] = []
        self.funde: list[tuple[str, list[tuple[str, dict]], int]] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = {k: v or "" for k, v in attrs}
        if tag in ("script", "style"):
            self._skip += 1
        kette = [*self.stapel, (tag, a)]
        if tag not in VOID:
            self.stapel.append((tag, a))
        if not self._skip:
            for k in ATTRS:
                if a.get(k):
                    self.funde.append((a[k], kette, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1
        for i in range(len(self.stapel) - 1, -1, -1):
            if self.stapel[i][0] == tag:
                del self.stapel[i:]
                break

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.funde.append((" ".join(data.split()), list(self.stapel), self.getpos()[0]))


def _texte() -> list[tuple[str, list[tuple[str, dict]], int]]:
    p = _Texte()
    p.feed(INDEX)
    return p.funde


def _klassen(kette) -> set[str]:
    return {c for _, a in kette for c in (a.get("class") or "").split()}


def _code(kette) -> bool:
    return any(t in ("code", "pre", "kbd") for t, _ in kette)


def test_index_sagt_knowlin_statt_duckpilot():
    falsch = [f"Zeile {z}: {t[:90]}" for t, kette, z in _texte()
              if "duckpilot" in t.lower() and not _code(kette) and not DUCKPILOT_ERLAUBT.search(t)]
    assert not falsch, falsch
    assert "<title>Knowlin</title>" in INDEX


# Funde in Dateien, an denen gerade andere Helfer arbeiten (Audit 0.38.14) – dort nachziehen, dann hier streichen
OFFEN_FREMD = {
}
_LITERAL = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"|`((?:[^`\\]|\\.)*)`")


def _js_meldungen(datei) -> list[str]:
    """Zeichenketten eines Skripts ohne Kommentare (grob, reicht für Meldungen)."""
    code = []
    for zeile in datei.read_text("utf-8").splitlines():
        s = zeile.strip()
        if s.startswith(("//", "*", "/*")):
            continue
        code.append(re.sub(r"\s//\s.*$", "", zeile))
    return [next(g for g in m.groups() if g is not None) for m in _LITERAL.finditer("\n".join(code))]


def test_js_meldungen_sagen_knowlin_statt_duckpilot():
    falsch = []
    for datei in sorted(STATIC.glob("*.js")):
        for s in _js_meldungen(datei):
            if "duckpilot" not in s.lower() or (datei.name, s) in OFFEN_FREMD:
                continue
            # Kennungen statt Text: Modulname, Speicher-Schlüssel, window.duckpilot, Dateien, Ordner
            if re.fullmatch(r"duckpilot(\.[\w.${}-]+)?|[\w./-]*duckpilot[\w./-]*", s) or DUCKPILOT_ERLAUBT.search(s):
                continue
            falsch.append(f"{datei.name}: {s[:90]}")
    assert not falsch, falsch


def test_keine_entenwoerter_wo_reachy_hinschaut():
    """Enten-Wörter nur in Bereichen, die Reachy nie sieht (Körper-Klassen, Microduck-Seiten) – bei Reachy heißt es
    „Verkörperung“, „Roboter“ oder sein Name."""
    falsch = []
    for t, kette, z in _texte():
        if not ENTE.search(KEINE_ENTE.sub("", t)) or ENTE_ERLAUBT.search(t):
            continue
        if _klassen(kette) & OHNE_REACHY_KLASSEN or any(a.get("translate") == "no" for _, a in kette):
            continue
        if {a.get("id") for _, a in kette} & OHNE_REACHY_IDS or {a.get("data-part") for _, a in kette} & OHNE_REACHY_TEILE:
            continue
        falsch.append(f"Zeile {z}: {t[:90]}")
    assert not falsch, falsch


def test_nur_reachy_ohne_entenwoerter():
    falsch = [f"Zeile {z}: {t[:90]}" for t, kette, z in _texte()
              if "nur-reachy" in _klassen(kette) and ENTE.search(KEINE_ENTE.sub("", t))]
    assert not falsch, falsch


# Bedienelemente mit Körperbezug → Körper-Klasse am Element oder darüber (Fund aus dem Test: „Optionen, die beim Körper
# nichts bewirken“). Kopf-Seiten (nur-im-kopf) beschreiben die Verkörperungen nur.
KOERPERBEZUG = [
    (re.compile(r"Tiefensensor|Punktwolke"), {"braucht-tiefensensor", "nur-microduck", "nur-im-kopf", "braucht-sicht"}),
    (re.compile(r"\b(Laser|Folg mir|Spur|Kollision|Purzelbaum|Gelaufen|Raum erkunden|Kamera folgt)\b"),
     {"braucht-beine", "nur-microduck", "nur-ente", "nur-im-kopf"}),
    (re.compile(r"Schnabel"), {"braucht-schnabel", "nur-microduck", "nur-ente"}),
    (re.compile(r"Antennen"), {"braucht-antennen", "nur-reachy", "nur-open-duck", "ohne-microduck"}),
]
BEDIENELEMENT = {"button", "label", "option", "summary", "dt"}


def test_bedienelemente_mit_koerperbezug_haben_koerperklasse():
    falsch = []
    for t, kette, z in _texte():
        if not any(tag in BEDIENELEMENT for tag, _ in kette[-3:]):
            continue
        if {a.get("id") for _, a in kette} & OHNE_REACHY_IDS or {a.get("data-part") for _, a in kette} & OHNE_REACHY_TEILE:
            continue
        for muster, klassen in KOERPERBEZUG:
            if muster.search(t) and not _klassen(kette) & klassen:
                falsch.append(f"Zeile {z}: {t[:80]}")
    assert not falsch, falsch


def test_ansicht_menue_je_koerper():
    """Fund aus dem Test 6: im Ansicht-Menü nur, was der Körper kann; Blick heißt bei Reachy „Reachys Blick“."""
    menue = INDEX[INDEX.index('id="view-menu" hidden'):INDEX.index('id="szene-reset"')]
    for oid, klasse in (("opt-follow", "braucht-beine"), ("opt-trail", "braucht-beine"), ("opt-sensor", "braucht-tiefensensor"),
                        ("opt-cloud", "braucht-tiefensensor"), ("opt-raum", "braucht-tiefensensor")):
        label = menue[menue.rindex("<label", 0, menue.index(f'id="{oid}"')):menue.index(f'id="{oid}"')]
        assert klasse in label, oid
    assert "kleines Bild" not in menue and 'id="opt-pov"' not in menue   # seit 0.38.24: kein Bild hinter dem Gespräch
    assert '<span class="nur-reachy">Reachys Blick</span>' in INDEX


def test_blick_aktiv_auch_mit_zweitem_text():
    """Fund aus dem Test 8: Der gewählte Blick war bei Reachy nicht zu sehen – `+ span` traf den ausgeblendeten Enten-Text."""
    css = stil()
    assert ".stage-mode input:checked ~ span" in css and ".stage-mode input:checked + span" not in css


def test_sicht_kachel_bei_kamera_ohne_tiefensensor():
    """Fund aus dem Test 7: Reachy (Kamera, kein Tiefensensor) bekommt die kleine Kachel mit dem Kamerabild."""
    css = stil()
    app = (STATIC / "app.js").read_text("utf-8")
    kachel = (STATIC / "kachel.js").read_text("utf-8")                    # seit 0.38.17 eigenes Modul
    assert 'class="hud-sensor braucht-sicht"' in INDEX
    assert "body:not(.im-kopf).ohne-tiefensensor.ohne-kamera .braucht-sicht" in css
    assert "nurKamera()" in kachel and "$('sensor-tile').disabled = nurKamera();" in kachel
    # erst nach den Körperklassen festlegen, sonst gilt der Körper davor
    init = app[app.index("function onInit"):]
    assert init.index("setzeModul(config") < init.index("kachel.setTile(kachel.modus)")


def test_beenden_bei_knowlin_rechts():
    """Fund aus dem Test 5: Im Kopf fehlen Persönlichkeit und Aktiv/Ruht, die den Beenden-Knopf sonst nach rechts schieben."""
    css = stil()
    assert "body.im-kopf .quit-btn { margin-left: auto; }" in css


def test_3d_darstellung_je_koerper():
    """Fund aus dem Test 1: „Einfache Ente“ passt nicht zu Reachy – dort „Einfaches Modell“, Hilfe je Körper."""
    karte = INDEX[INDEX.index('id="set-darstellung"'):INDEX.index('name="quality3d"')]
    assert '<span class="nur-ente">Einfache Ente</span><span class="nur-reachy">Einfaches Modell</span>' in karte
    for k in ("nur-microduck", "nur-reachy", "nur-open-duck"):
        assert f'<p class="field-help {k}">Originalmodell' in karte


def test_koerperwahl_bleibt_beim_koerper():
    """Oben „Was gesteuert wird“: nur Optionen des eigenen Körpers; die Open Duck bleibt beim Simulator Open Duck."""
    pop = INDEX[INDEX.index('id="koerper-pop"'):INDEX.index('id="koerper-mehr"')]
    for k, klasse in (("sim", "nur-ente"), ("physik", "nur-microduck"), ("reachy_sim", "nur-reachy"), ("robotd", "ohne-open-duck")):
        assert re.search(rf'class="[^"]*{klasse}[^"]*" type="button" data-koerper="{k}"', pop), k
    js = (STATIC / "koerperwahl.js").read_text("utf-8")
    assert "modul: modul === 'open_duck_mini' ? modul : 'duckpilot'" in js


def test_progressive_offenlegung_im_html():
    """Fund aus dem Test 3: Zusatzfelder erst, wenn die zugehörige Wahl aktiv ist."""
    for ziel, bedingung in (('id="anbieter-card"', "gehirn=anbieter"), ('id="local-card"', "gehirn=lokal"),
                            ('id="fern-details"', "#fern-an"), ('id="stopp-fenster-feld"', "auto_recover=true"),
                            ('id="weckwort-feld"', "stt!=aus"), ('id="plaudern-feld"', "stt!=aus")):
        tag = INDEX[INDEX.rindex("<", 0, INDEX.index(ziel)):INDEX.index(">", INDEX.index(ziel))]
        assert f'data-zeige-wenn="{bedingung}"' in tag, ziel
    fern = INDEX[INDEX.index('id="fern-details"'):INDEX.index('id="fern-auto-row"')]
    assert 'id="fern-code"' in fern and 'id="fern-ts-an"' in fern
    app = (STATIC / "app.js").read_text("utf-8")
    einst = (STATIC / "einstellungen_ui.js").read_text("utf-8")          # seit 0.38.17 eigenes Modul
    assert "initOffenlegung();" in app and "offenlegen()" in einst


def test_progressive_offenlegung_logik():
    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    code = r"""
const el = (attrs) => ({ ...attrs, attrs: {}, dataset: attrs.dataset || {}, hidden: false, fokus: false,
  setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k] ?? null; },
  contains(x) { return x === this || (this.kinder || []).includes(x); }, focus() { globalThis.document.activeElement = this; } });
const claude = el({ type: 'radio', name: 'gehirn', value: 'claude', checked: true });
const lokal = el({ type: 'radio', name: 'gehirn', value: 'lokal', checked: false });
const schalter = el({ type: 'checkbox', id: 'fern-an', checked: false });
const feld = el({ type: 'text' });
const karte = el({ id: 'local-card', dataset: { zeigeWenn: 'gehirn=lokal' }, kinder: [feld] });
const fern = el({ id: 'fern-details', dataset: { zeigeWenn: '#fern-an' } });
const stt = el({ type: 'radio', name: 'stt', value: 'aus', checked: true });
const wort = el({ id: 'weckwort-feld', dataset: { zeigeWenn: 'stt!=aus' } });
globalThis.document = {
  activeElement: null,
  getElementById: (id) => ({ 'fern-an': schalter })[id] || null,
  querySelectorAll(sel) {
    if (sel === '[data-zeige-wenn]') return [karte, fern, wort];
    if (sel.includes('name="gehirn"')) return [claude, lokal];
    if (sel.includes('name="stt"')) return [stt];
    return [];
  },
};
const { offenlegen } = await import('MODUL');
const z = () => [karte.hidden, fern.hidden, wort.hidden];
offenlegen(); const a = z();
lokal.checked = true; claude.checked = false; schalter.checked = true; stt.checked = false; stt.value = 'browser'; stt.checked = true;
offenlegen(); const b = z();
document.activeElement = feld; lokal.checked = false; claude.checked = true;
offenlegen();
console.log(JSON.stringify({ a, b, fokus: document.activeElement === claude, expanded: schalter.attrs['aria-expanded'],
  controls: lokal.attrs['aria-controls'] }));
""".replace("MODUL", (STATIC / "offenlegung.js").as_uri())
    out = json.loads(subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True,
                                    check=True).stdout)
    assert out["a"] == [True, True, True]          # Claude, Fernbedienung aus, keine Spracherkennung: alles zu
    assert out["b"] == [False, False, False]       # eigenes Modell, Fernbedienung an, Online-Erkennung: alles da
    assert out["fokus"]                            # Fokus im verschwundenen Feld → zurück auf die Wahl
    assert out["expanded"] == "true" and out["controls"] == "local-card"


def test_sperre_nicht_fest_zwei_minuten():
    """Die Not-Aus-Sperre ist seit 0.38.13 einstellbar (2, 5, 10 min) – Meldungen nennen nicht fest „zwei Minuten“."""
    from pathlib import Path

    import duckpilot
    paket = Path(duckpilot.__file__).parent
    assert "zwei Minuten lang nicht von selbst" not in (paket / "brain" / "tools.py").read_text("utf-8")
    assert "Not-Aus vor weniger als zwei Minuten" not in (paket / "protest.py").read_text("utf-8")


def test_reiter_werden_nach_der_koerperwahl_neu_gezeichnet():
    """Fund 6.11.2026: Nach Neuladen im Körper standen bei Odi „Team“, „Vom Hub“ und „Spiele“ – die Reiterleiste war vor
    der Körperwahl gezeichnet und danach nicht erneuert."""
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    i = app.index("setzeModul(config, { $, hiddenTabs });")
    assert "renderSubnav(" in app[i:i + 200]


def test_einfache_darstellung_passt_zur_open_duck():
    """Fund aus dem Test 5.11.2026: „3D-Darstellung ‚Einfache Ente‘ sollte auch je Roboter passen“ – Odi bekam die einfache
    Microduck. Seit 0.38.15 hat die Open Duck eine eigene einfache Gestalt (grau, höher, Antennen)."""
    js = (STATIC / "duck3d.js").read_text(encoding="utf-8")
    ente = (STATIC / "ente3d.js").read_text(encoding="utf-8")       # die einfachen Gestalten (seit 0.38.18 eigenes Modul)
    assert "new Duck('open_duck')" in js and "art === 'open_duck'" in ente
    i = js.index("if (this.koerper === 'open_duck_mini')")
    assert "this.simpleDuck" not in js[i:i + 400]
