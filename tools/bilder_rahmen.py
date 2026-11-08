#!/usr/bin/env python3
"""Bildschirmfotos auf ein einheitliches Format bringen (seit 0.38.31, Hinweis: „die Screenshots sind immer unterschiedlich
groß auf Website und GitHub – das sieht vom Layout komisch aus“).

Alle Fotos der README und der Website haben das Format 1600 × 965 (wie die Fenster-Aufnahmen von Startseite und Cockpit).
Ausschnitte mit anderem Seitenverhältnis (Hirnaktivität, Charakterfeld) werden nicht beschnitten, sondern mittig auf
eine Fläche gesetzt, die ihren eigenen Rand nahtlos fortsetzt – mit gleichem Abstand ringsum. So stehen alle Bilder gleich groß
nebeneinander, wie bei Produktseiten üblich.

    python tools/bilder_rahmen.py            # README- und Website-Bilder vereinheitlichen
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BREITE, HOEHE = 1600, 965
RAND = 72                      # Mindestabstand ringsum, in Pixeln des Zielbilds
KANTE = 10                     # so viel vom Ausschnitt-Rand weg: abgerundete Kartenecken und Rahmenlinie


def einpassen(bild: Image.Image) -> Image.Image:
    """Ausschnitt mittig auf 1600 × 965 setzen; schon passende Fenster-Aufnahmen bleiben, wie sie sind."""
    if bild.size == (BREITE, HOEHE):
        return bild.convert("RGB")
    innen = bild.convert("RGB").crop((KANTE, KANTE, bild.width - KANTE, bild.height - KANTE))
    massstab = min((BREITE - 2 * RAND) / innen.width, (HOEHE - 2 * RAND) / innen.height, 1.0)
    neu = np.asarray(innen.resize((round(innen.width * massstab), round(innen.height * massstab)), Image.LANCZOS))
    # Rand nach außen fortsetzen: Die Karten haben einen sanften Verlauf von oben nach unten – so bleibt er nahtlos
    oben, links = (HOEHE - neu.shape[0]) // 2, (BREITE - neu.shape[1]) // 2
    flaeche = np.pad(neu, ((oben, HOEHE - neu.shape[0] - oben), (links, BREITE - neu.shape[1] - links), (0, 0)), mode="edge")
    return Image.fromarray(flaeche)


def main() -> None:
    for name in ("synapsen", "synapsen-en", "charakter", "charakter-en"):
        p = ROOT / "docs" / "bilder" / f"{name}.png"
        einpassen(Image.open(p)).save(p, optimize=True)
        print("README:", p.name)
    for name in ("synapsen", "charakter"):
        for sprache in ("de", "en"):
            gross = ROOT / "website" / "bilder" / f"{name}-{sprache}-1600.webp"
            bild = einpassen(Image.open(gross))
            bild.save(gross, quality=86, method=6)
            bild.resize((900, round(900 * HOEHE / BREITE)), Image.LANCZOS).save(
                ROOT / "website" / "bilder" / f"{name}-{sprache}-900.webp", quality=84, method=6)
            print("Website:", gross.name)


if __name__ == "__main__":
    sys.exit(main())
