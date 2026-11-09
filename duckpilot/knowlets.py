"""Knowlets (seit 0.38.5): Verkörperungen, Tricks und Tänze als Paket teilen und laden.

das Bild (1.11.2026): andere sollen „die Intelligenz von Knowlin bespielen“ können – ohne Code. Ein Knowlet ist
eine ZIP-Datei mit der Endung `.knowlet`:

    knowlet.json        Steckbrief: Name, Beschreibung, Urheber, Lizenz, für welchen Körper, was drin ist
    figur.json          Charakter der Verkörperung: Name, Persönlichkeit, Sprechweise, Stimme (Piper), Klang
    tricks/<name>.json  selbst gebaute Tricks (Keyframes), ohne Notizen und Bewertungen
    taenze/<name>.json  Choreografien, ohne das Musikstück

**Nie drin**: Code, Gedächtnis über Personen, Orte, Karte und Sichtungen, Gespräche, Einstellungen des Geräts,
Schlüssel, entworfene Stimmen (die gehören ihrer Verkörperung am PC), Musikstücke, Pollens Policies. Beim Laden gilt eine
Positivliste: unbekannte Dateien, zu große Pakete und Pfade außerhalb des Pakets lehnt `pruefe()` ab, bevor irgendetwas
übernommen wird. Alles Fremde ist Daten – Texte werden gekürzt und nie ausgeführt.

Sicherheit: Ein Trick aus einem Knowlet läuft am echten Roboter erst, nachdem er einmal im Simulator lief
(„erst im Zwilling zur Probe“). Gelenkgrenzen, Not-Aus und Sturzreflex gelten ohnehin für jeden Trick.
"""

from __future__ import annotations

import io
import json
import re
import time
import zipfile
from typing import Any

FORMAT = 1
ENDUNG = ".knowlet"
MAX_PAKET = 2 * 1024 * 1024          # gepackt
MAX_ENTPACKT = 6 * 1024 * 1024       # entpackt, gegen ZIP-Bomben
MAX_DATEI = 512 * 1024
MAX_TRICKS = 40
MAX_TAENZE = 20
LIZENZEN = ("CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0", "CC-BY-NC-4.0")
MODULE = ("duckpilot", "reachy_mini", "open_duck_mini")       # eingebaute Körper mit Verkörperung (Hub-Tags)
KOERPER = {"duckpilot": "Microduck", "reachy_mini": "Reachy Mini", "open_duck_mini": "Open Duck Mini v2"}


def koerper_ids() -> tuple[str, ...]:
    """Für welche Körper Knowlets gehen: alle mit Profil (Körperschnittstelle, seit 0.38.35 auch Erweiterungen)."""
    from . import koerper

    return koerper.ids()


def koerper_name(modul: str) -> str:
    from . import koerper

    try:
        return koerper.holen(modul).name
    except KeyError:
        return KOERPER.get(modul, modul)

# Was von einer Verkörperung geteilt wird – Teilmenge von figuren.FIGUR_KEYS. Nicht: tts (Gerät), stimme_motor/stimme_qwen/
# qwen_qualitaet (entworfene Stimme bleibt am PC), weitere_enten (wer im eigenen Zimmer ist), model_style (Ansicht)
FIGUR_TEILEN = ("duck_name", "wake_word", "energie", "humor", "emotions", "idle_life", "plaudern", "stimme_piper",
                "entenhaft", "entenlaute", "klang_hoehe", "klang_farbe")

_DATEI = re.compile(r"^(knowlet\.json|figur\.json|LIESMICH\.md|(tricks|taenze)/[^/\\]{1,80}\.json)$")
_STEUER = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class KnowletFehler(ValueError):
    """Paket ist kaputt, zu groß oder enthält, was nicht hineingehört."""


def text(wert: Any, laenge: int) -> str:
    """Fremder Text: ohne Steuerzeichen, auf eine Zeile bzw. Länge gekürzt."""
    t = _STEUER.sub("", str(wert or "")).strip()
    return t[:laenge]


def name(wert: Any) -> str:
    """Namen für Verkörperung, Trick, Tanz: Buchstaben, Ziffern, Leerzeichen und wenige Zeichen – kurz."""
    t = re.sub(r"[^\w äöüÄÖÜß.,!?'()+-]", "", text(wert, 60), flags=re.UNICODE)
    return " ".join(t.split())[:40]


def _dateiname(n: str) -> str:
    return re.sub(r"[^\w-]+", "_", n, flags=re.UNICODE).strip("_")[:60] or "ohne_name"


# ── Packen ────────────────────────────────────────────────────────────────
def packe(*, titel: str, beschreibung: str = "", urheber: str = "", lizenz: str = "CC-BY-4.0", modul: str,
          figur: dict[str, Any] | None = None, tricks: dict[str, dict[str, Any]] | None = None,
          taenze: dict[str, dict[str, Any]] | None = None, version: str = "") -> bytes:
    """Ein Knowlet bauen. `figur` sind Einstellungswerte der Verkörperung; es wird nur `FIGUR_TEILEN` übernommen."""
    from .choreo import pruefe as choreo_pruefe

    titel = name(titel)
    if not titel:
        raise KnowletFehler("Bitte einen Namen für das Knowlet angeben.")
    if modul not in koerper_ids():
        raise KnowletFehler(f"Unbekannter Körper: {modul}")
    if lizenz not in LIZENZEN:
        raise KnowletFehler("Bitte eine der angebotenen Lizenzen wählen.")
    dateien: dict[str, Any] = {}
    inhalt: dict[str, Any] = {"figur": False, "tricks": [], "taenze": []}
    if figur:
        dateien["figur.json"] = {k: figur[k] for k in FIGUR_TEILEN if k in figur}
        inhalt["figur"] = True
    for n, t in list((tricks or {}).items())[:MAX_TRICKS]:
        kf = t.get("keyframes") if isinstance(t, dict) else None
        if not kf:
            continue
        dateien[f"tricks/{_dateiname(n)}.json"] = {"name": name(n), "keyframes": kf[:80],
                                                   "loops": int(t.get("loops", 1) or 1),
                                                   "beschreibung": text(t.get("beschreibung"), 200)}
        inhalt["tricks"].append(name(n))
    for n, c in list((taenze or {}).items())[:MAX_TAENZE]:
        sauber = choreo_pruefe(c)
        sauber.pop("musik", None)                                 # Musikstücke bleiben am PC (Rechte)
        dateien[f"taenze/{_dateiname(n)}.json"] = {"name": name(n), **sauber}
        inhalt["taenze"].append(name(n))
    if not (inhalt["figur"] or inhalt["tricks"] or inhalt["taenze"]):
        raise KnowletFehler("Das Knowlet ist leer – Verkörperung, Tricks oder Tänze auswählen.")
    steckbrief = {"format": FORMAT, "name": titel, "beschreibung": text(beschreibung, 400),
                  "urheber": text(urheber, 80), "lizenz": lizenz, "fuer": modul,
                  "erstellt": time.strftime("%Y-%m-%d"), "knowlin": version, "inhalt": inhalt}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("knowlet.json", json.dumps(steckbrief, ensure_ascii=False, indent=1))
        for pfad, daten in dateien.items():
            z.writestr(pfad, json.dumps(daten, ensure_ascii=False, indent=1))
    out = buf.getvalue()
    if len(out) > MAX_PAKET:
        raise KnowletFehler("Das Knowlet wird zu groß – weniger Tricks oder Tänze auswählen.")
    return out


# ── Prüfen ────────────────────────────────────────────────────────────────
def pruefe(daten: bytes) -> dict[str, Any]:
    """Paket öffnen und streng prüfen. Gibt den Inhalt sauber zurück (`steckbrief`, `figur`, `tricks`, `taenze`)
    oder wirft `KnowletFehler`. Übernommen wird hier noch nichts."""
    from .choreo import pruefe as choreo_pruefe
    from .motion.behaviors import Choreography
    from .settings import validate

    if len(daten) > MAX_PAKET:
        raise KnowletFehler("Das Paket ist größer als 2 MB.")
    try:
        z = zipfile.ZipFile(io.BytesIO(daten))
    except zipfile.BadZipFile as exc:
        raise KnowletFehler("Das ist kein Knowlet (keine ZIP-Datei).") from exc
    infos = z.infolist()
    if len(infos) > 2 + MAX_TRICKS + MAX_TAENZE + 1:
        raise KnowletFehler("Zu viele Dateien im Paket.")
    gesamt = 0
    roh: dict[str, Any] = {}
    for i in infos:
        if i.is_dir():
            continue
        if not _DATEI.match(i.filename) or ".." in i.filename:
            raise KnowletFehler(f"Datei gehört nicht in ein Knowlet: {text(i.filename, 80)}")
        if i.file_size > MAX_DATEI:
            raise KnowletFehler(f"Datei zu groß: {text(i.filename, 80)}")
        gesamt += i.file_size
        if gesamt > MAX_ENTPACKT:
            raise KnowletFehler("Das Paket ist entpackt zu groß.")
        with z.open(i) as f:
            inhalt = f.read(MAX_DATEI + 1)
        if len(inhalt) > MAX_DATEI:
            raise KnowletFehler(f"Datei zu groß: {text(i.filename, 80)}")
        if i.filename.endswith(".md"):
            roh[i.filename] = text(inhalt.decode("utf-8", "replace"), 4000)
            continue
        try:
            roh[i.filename] = json.loads(inhalt.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise KnowletFehler(f"Kaputte Datei: {text(i.filename, 80)}") from exc
    s = roh.get("knowlet.json")
    if not isinstance(s, dict) or s.get("format") != FORMAT:
        raise KnowletFehler("Steckbrief fehlt oder hat ein unbekanntes Format.")
    fuer = s.get("fuer") if s.get("fuer") in koerper_ids() else None
    if fuer is None:
        raise KnowletFehler("Für welchen Körper das Knowlet ist, fehlt.")
    steckbrief = {"name": name(s.get("name")) or "Knowlet", "beschreibung": text(s.get("beschreibung"), 400),
                  "urheber": text(s.get("urheber"), 80), "lizenz": text(s.get("lizenz"), 20),
                  "fuer": fuer, "koerper": koerper_name(fuer), "erstellt": text(s.get("erstellt"), 10),
                  "knowlin": text(s.get("knowlin"), 12)}
    figur = None
    if isinstance(roh.get("figur.json"), dict):
        werte = {k: v for k, v in roh["figur.json"].items() if k in FIGUR_TEILEN}
        if "duck_name" in werte:
            werte["duck_name"] = name(werte["duck_name"])[:24] or "Verkörperung"
        if "wake_word" in werte:
            werte["wake_word"] = name(werte["wake_word"]).lower()[:20]
        try:
            figur = validate(werte)
        except ValueError as exc:
            raise KnowletFehler(f"Verkörperung: {exc}") from exc
    tricks: dict[str, dict[str, Any]] = {}
    taenze: dict[str, dict[str, Any]] = {}
    for pfad, d in sorted(roh.items()):
        if pfad.startswith("tricks/"):
            if not isinstance(d, dict) or not isinstance(d.get("keyframes"), list) or not d["keyframes"]:
                raise KnowletFehler(f"Trick ohne Keyframes: {text(pfad, 80)}")
            n = name(d.get("name")) or name(pfad[7:-5])
            loops = max(1, min(20, int(d.get("loops", 1) or 1)))
            try:
                Choreography.from_spec(list(d["keyframes"])[:80], loops, n)   # Formprüfung wie bei eigenen Tricks
            except Exception as exc:
                raise KnowletFehler(f"Trick „{n}“ ist ungültig: {exc}") from exc
            tricks[n] = {"keyframes": list(d["keyframes"])[:80], "loops": loops,
                         "beschreibung": text(d.get("beschreibung"), 200)}
        elif pfad.startswith("taenze/"):
            if not isinstance(d, dict):
                raise KnowletFehler(f"Kaputter Tanz: {text(pfad, 80)}")
            n = name(d.get("name")) or name(pfad[7:-5])
            sauber = choreo_pruefe(d)
            sauber.pop("musik", None)
            if not sauber.get("schritte"):
                raise KnowletFehler(f"Tanz „{n}“ hat keine Schritte.")
            taenze[n] = sauber
    if not (figur or tricks or taenze):
        raise KnowletFehler("Das Knowlet ist leer.")
    return {"steckbrief": steckbrief, "figur": figur, "tricks": tricks, "taenze": taenze,
            "liesmich": roh.get("LIESMICH.md", "")}


def vorschau(paket: dict[str, Any], vorhanden_tricks: set[str], vorhanden_taenze: set[str]) -> dict[str, Any]:
    """Was das Knowlet mitbringt – für den Dialog vor dem Übernehmen (ohne die Keyframes selbst)."""
    f = paket["figur"]
    return {"steckbrief": paket["steckbrief"],
            "figur": {"name": f.get("duck_name"), "energie": f.get("energie"), "humor": f.get("humor"),
                      "entenhaft": f.get("entenhaft"), "stimme": f.get("stimme_piper")} if f else None,
            "tricks": [{"name": n, "keyframes": len(t["keyframes"]), "beschreibung": t["beschreibung"],
                        "gibt_es": n in vorhanden_tricks} for n, t in paket["tricks"].items()],
            "taenze": [{"name": n, "schritte": len(c["schritte"]), "bpm": c.get("bpm"), "gibt_es": n in vorhanden_taenze}
                       for n, c in paket["taenze"].items()],
            "liesmich": paket.get("liesmich", "")}


def freier_name(n: str, belegt: set[str]) -> str:
    """„Winken“ gibt es schon → „Winken 2“."""
    if n not in belegt:
        return n
    k = 2
    while f"{n} {k}" in belegt:
        k += 1
    return f"{n} {k}"
