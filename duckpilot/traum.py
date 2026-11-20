"""Das NFC-Polaroid (seit 0.47, Zubehör der Microduck): „wovon träumt sie?“ – aus dem Tag, ohne Sprachmodell.

Pollens Polaroid ist eine 1,54-Zoll-Farb-E-Ink-Karte, die über NFC Strom bekommt: an den Kopf halten, und sie zeigt,
wovon der Roboter träumt. Bis die Karte da ist, malt Knowlin das Bild im Browser (200 × 200 Punkte, wenige Farben wie
E-Ink) und man kann es herunterladen.

Woraus der Traum wird: aus dem Tagesrückblick (`Tagebuch.rueckblick`) – was heute am häufigsten vorkam (Dinge, Orte,
Tricks, Spiele), dazu die Stimmung des Tages. Nichts wird erfunden: Ist der Tag leer, träumt sie „von einem ruhigen
Tag“. Personen kommen nur am PC vor (der Rückblick lässt sie fürs Handy schon weg) und nie mit Gesicht – nur der Name.
"""

from __future__ import annotations

from typing import Any

MOTIVE_MAX = 3
# Stichwort im Namen → Zeichen fürs Bild (das erste passende gewinnt)
ZEICHEN: tuple[tuple[tuple[str, ...], str], ...] = (
    (("ball", "fußball", "tor", "elfmeter"), "⚽"),
    (("rollen", "rollschuh", "rennen", "arena"), "🛼"),
    (("sofa", "couch"), "🛋️"),
    (("pflanze", "blume"), "🪴"),
    (("kiste", "karton", "paket"), "📦"),
    (("socke",), "🧦"),
    (("klötzchen", "klemmbau", "baustein", "lego"), "🧱"),
    (("licht", "lampe"), "💡"),
    (("musik", "lied", "tanz", "choreo"), "🎵"),
    (("sauger", "saugroboter", "aufräumen"), "🧹"),
    (("verstecken", "versteck"), "🙈"),
    (("schere", "stein", "papier", "handzeichen"), "✌️"),
    (("laser", "punkt"), "🔴"),
    (("wetter", "regen", "sonne"), "🌦️"),
    (("schach",), "♟️"),
    (("akku", "laden", "schlafen", "ruhe"), "💤"),
)
STIMMUNG = {"froh": ("sonnig", "sunny"), "schwer": ("unruhig", "restless"), "gemischt": ("bunt", "colourful"),
            "ruhig": ("ruhig", "calm")}
OHNE = ("zeit", "gefuehl", "rueckmeldung")          # Arten, die kein Motiv sind


def zeichen(name: str, art: str = "") -> str:
    n = name.lower()
    for woerter, z in ZEICHEN:
        if any(w in n for w in woerter):
            return z
    return {"person": "🙂", "ort": "📍", "trick": "✨", "spiel": "🎲"}.get(art, "✨")


def traum(rueckblick: dict[str, Any] | None, en: bool = False) -> dict[str, Any]:
    """Motive (Zeichen + Wort), ein Satz und die Stimmung – fürs Bild im Browser und für den Satz, den sie sagt."""
    r = rueckblick or {}
    motive: list[dict[str, str]] = []
    for h in r.get("haeufig") or []:
        art, name = str(h.get("art") or ""), str(h.get("name") or "").strip()
        if not name or art in OHNE or any(m["wort"] == name for m in motive):
            continue
        motive.append({"zeichen": zeichen(name, art), "wort": name})
        if len(motive) >= MOTIVE_MAX:
            break
    stimmung = str(r.get("stimmung") or "ruhig")
    wort = STIMMUNG.get(stimmung, STIMMUNG["ruhig"])[1 if en else 0]
    if not motive:
        text = "I dreamt of a quiet day." if en else "Ich habe von einem ruhigen Tag geträumt."
        return {"motive": [{"zeichen": "💤", "wort": "quiet" if en else "ruhig"}], "text": text, "stimmung": stimmung,
                "titel": "Dream" if en else "Traum", "leer": True}
    worte = [m["wort"] for m in motive]
    und = " and " if en else " und "
    liste = (", ".join(worte[:-1]) + und + worte[-1]) if len(worte) > 1 else worte[0]
    text = (f"I dreamt of {liste} – a {wort} dream." if en else f"Ich habe von {liste} geträumt – ein {wort}er Traum.")
    return {"motive": motive, "text": text, "stimmung": stimmung, "titel": "Dream" if en else "Traum", "leer": False}
