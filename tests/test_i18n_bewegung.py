"""Englische Oberfläche: Was die Figur gerade tut, steht auf Englisch (seit 0.38.16).

Beim Fotografieren der englischen README-Bilder fiel auf: „umschauen“, „einfache Befehle“ und die Reachy-Hinweise
„hindrehen“/„drehen“ blieben deutsch. Der Test bildet die Suche aus `static/i18n.js` nach (fester Text, sonst die
erste passende Vorlage mit # = Zahl und * = Text) und prüft die Beschreibungen der Bewegungen.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI = json.loads((ROOT / "duckpilot" / "i18n" / "ui_en.json").read_text(encoding="utf-8"))


def _vorlage(k: str) -> re.Pattern[str]:
    re_ = re.sub(r"[.+?^${}()|\[\]\\]", lambda m: "\\" + m.group(0), k)
    re_ = re_.replace("#", r"([-−+]?\d+(?:[.,]\d+)?)").replace("*", "(.+?)")
    return re.compile(f"^{re_}$")


VORLAGEN = [(_vorlage(k), v) for k, v in UI.items() if re.search(r"[#*]", k)]


def uebersetze(roh: str, tiefe: int = 0) -> str | None:
    s = re.sub(r"\s+", " ", roh).strip()
    if s in UI:
        return UI[s]
    if re.search(r"[A-Za-zÄÖÜäöüß]{2}", s) and tiefe < 2:
        for muster, ziel in VORLAGEN:
            m = muster.match(s)
            if not m:
                continue
            teile = iter(m.groups())

            def ein(z: re.Match[str]) -> str:
                v = next(teile, "") or ""
                return v.replace(",", ".") if z.group(0) == "#" else (uebersetze(v, tiefe + 1) or v)

            return re.sub(r"[#*]", ein, ziel)
    return None


@pytest.mark.parametrize("de, en", [
    ("umschauen", "looking around"),
    ("umschauen, hält Ball", "looking around, holding Ball"),
    ("hält den roten Würfel", "holding the red cube"),                 # Ari an der Werkbank (Fund 12.11.)
    ("erkunden (60 s)", "explore (60 s)"),
    ("apportieren: Ball (hin)", "fetching: Ball (on the way)"),
    ("begrüßen: Odi", "greeting: Odi"),
    ("choreo (Tanz, Reachy, 100 bpm, 20s)", "choreo (Dance, Reachy, 100 bpm, 20s)"),
    ("choreo (Tanz, 100 bpm, 20s)", "choreo (Dance, 100 bpm, 20s)"),
    ("mitwippen (Reachy, 100 bpm)", "bobbing along (Reachy, 100 bpm)"),
    ("Purzelbaum (mit Platzprüfung)", "somersault (with space check)"),
    ("einfache Befehle", "simple commands"),
    ("hindrehen ·", "turn there ·"),
    ("drehen ·", "turn ·"),
])
def test_bewegungen_auf_englisch(de, en):
    assert uebersetze(de) == en


def test_herkunft_der_antwort_wird_uebersetzt():
    js = (ROOT / "duckpilot" / "server" / "static" / "app.js").read_text(encoding="utf-8")
    assert "addLine('duck', m.text, uebersetzeText(meta) || meta" in js


def test_erfahrungsnetz_zeigt_eigene_namen_auf_englisch():
    """Knoten, die Knowlin selbst benennt (Tageszeit, Gefühle, Erlebnisse), stehen im Katalog – die Hirn-Ansicht
    zeigt sie übersetzt; Namen von Menschen und Dingen bleiben unverändert."""
    quelle = (ROOT / "duckpilot" / "erfahrung_service.py").read_text(encoding="utf-8")
    namen = set(re.findall(r'"[a-z_]+:[a-zäöüß_]+": "([^"]+)"', quelle))
    namen |= {"morgens", "mittags", "nachmittags", "abends", "nachts", "Werktag", "Wochenende", "Lob", "Kritik",
              "Stimme gehört", "ausruhen"}
    assert namen and not [n for n in namen if uebersetze(n) is None]
    assert uebersetze("Tag Küche") == "tag Küche"
    js = (ROOT / "duckpilot" / "server" / "static" / "hirn.js").read_text(encoding="utf-8")
    assert "ctx.fillText(zeigName(k.name)" in js
