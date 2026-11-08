"""Gerüst für mehrere Sprachen (seit 0.33; Englisch folgt in 0.34).

Texte stehen in Katalogen je Sprache (`de.json`, `en.json`) unter festen Schlüsseln wie „ausweichen.weicht_aus“.
Deutsch ist die Grundsprache: Jeder Schlüssel muss dort stehen. Fehlt er in einer anderen Sprache, gilt der deutsche
Text – so kann die Übersetzung Bereich für Bereich wachsen, ohne dass irgendwo ein leerer Text erscheint.

- Python: `t("ausweichen.weicht_aus", seite="links", m=0.31)` – Platzhalter im `str.format`-Stil.
- Oberfläche: `GET /api/i18n/{sprache}` liefert den fertig gemischten Katalog, `static/i18n.js` setzt ihn ein
  (`data-i18n="schlüssel"` an Elementen, `t()` in Skripten).
- Neue Texte bekommen ab jetzt einen Schlüssel, alte werden mit 0.34 Bereich für Bereich umgezogen.
- Seit 0.34 übersetzt `static/i18n.js` die Oberfläche zusätzlich über `ui_en.json` (deutscher Text → Englisch),
  ohne dass jeder Text einen Schlüssel braucht; `tools/i18n_texte.py` zeigt, was fehlt.
- Gesprochenes und Claudes Anweisungen: Die Ente spricht und denkt in `config.sprache` (`brain/agent.py`).
"""

from __future__ import annotations

import json
import re
import string
from functools import cache
from pathlib import Path
from typing import Any

STANDARD = "de"
SPRACHEN = ("de", "en")
_DIR = Path(__file__).resolve().parent
_aktuell = STANDARD


@cache
def _roh(sprache: str) -> dict[str, str]:
    pfad = _DIR / f"{sprache}.json"
    if not pfad.exists():
        return {}
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    return {k: v for k, v in daten.items() if not k.startswith("_") and isinstance(v, str)}


def katalog(sprache: str | None = None) -> dict[str, str]:
    """Alle Texte einer Sprache, Lücken mit Deutsch gefüllt."""
    s = sprache if sprache in SPRACHEN else STANDARD
    return {**_roh(STANDARD), **_roh(s)}


def setze_sprache(sprache: str) -> str:
    global _aktuell
    _aktuell = sprache if sprache in SPRACHEN else STANDARD
    return _aktuell


def sprache() -> str:
    return _aktuell


def t(schluessel: str, sprache: str | None = None, **werte: Any) -> str:
    """Text zu `schluessel` in der aktuellen (oder angegebenen) Sprache. Unbekannter Schlüssel → der Schlüssel selbst,
    damit eine Lücke auffällt statt still zu verschwinden."""
    text = _roh(sprache or _aktuell).get(schluessel) or _roh(STANDARD).get(schluessel)
    if text is None:
        return schluessel
    try:
        return text.format(**werte) if werte else text
    except (KeyError, IndexError, ValueError):
        return text


@cache
def ui_katalog(sprache: str) -> dict[str, str]:
    """Oberflächentexte für den Übersetzer in `static/i18n.js` (seit 0.34): Schlüssel ist der deutsche Text, wie er auf
    der Seite steht; `#` steht für eine Zahl. Für Deutsch leer – dort bleibt der Text, wie er ist."""
    if sprache == STANDARD:
        return {}
    pfad = _DIR / f"ui_{sprache}.json"
    if not pfad.exists():
        return {}
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    return {k: v for k, v in daten.items() if not k.startswith("_") and isinstance(v, str)}


def platzhalter(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


# ── Oberflächentext auf dem Server übersetzen (seit 0.36) ──────────────────────────────────────────────────────────
# Dieselbe Regel wie `static/i18n.js`: exakt, sonst über eine Vorlage (`#` Zahl, `*` beliebiger Text, rekursiv
# übersetzt). Gebraucht für Sätze, die die Ente selbst sagt (Reflexe, Alltag, Beschwerden, Systemmeldungen): Sie
# werden nicht nur angezeigt, sondern auch gesprochen – das kann der Übersetzer im Browser nicht.
@cache
def _vorlagen(sprache: str) -> list[tuple[re.Pattern[str], str]]:
    out = []
    for k, v in ui_katalog(sprache).items():
        if "#" in k or "*" in k:
            muster = re.escape(k).replace("\\#", "#").replace("\\*", "*")
            muster = muster.replace("#", r"([-−+]?\d+(?:[.,]\d+)?)").replace("*", "(.+?)")
            out.append((re.compile(f"^{muster}$"), v))
    return out


def ui_text(text: str, sprache: str | None = None, _tiefe: int = 0) -> str:
    """Einen deutschen Oberflächentext in `sprache` – unbekannt bleibt er, wie er ist."""
    spr = sprache or _aktuell
    if spr == STANDARD or not text:
        return text
    kat = ui_katalog(spr)
    s = " ".join(text.split())
    if s in kat:
        return kat[s]
    if _tiefe < 2 and re.search(r"[A-Za-zÄÖÜäöüß]{2}", s):
        for muster, ziel in _vorlagen(spr):
            m = muster.match(s)
            if not m:
                continue
            teile = iter(m.groups())

            def ein(z: re.Match[str], teile=teile) -> str:
                v = next(teile, "") or ""
                return v.replace(",", ".") if z.group(0) == "#" else ui_text(v, spr, _tiefe + 1)
            return re.sub(r"[#*]", ein, ziel)
    return text
