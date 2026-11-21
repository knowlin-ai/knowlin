"""Im Netz nachschlagen (seit 0.51, „Websuche und Routinen in Knowlets“): kurze Antworten aus der Wikipedia.

Maintainer (Plan 0.51): „Knowlets dürfen im Netz nachschlagen und feste Abläufe zu einer Uhrzeit starten.“

* Nur wenn eingeschaltet (`websuche`, Standard aus – System → Einstellungen → Knowlin). Abgefragt wird nur, wenn
  jemand fragt („Schlag Ada Lovelace nach“) oder eine Routine den Schritt „Wissen“ hat.
* An die Wikipedia geht nur der Suchbegriff – nichts über Personen, nichts aus dem Gedächtnis. Kein Konto, kein
  Schlüssel. Ergebnisse bleiben einen Tag im Speicher (nicht auf der Platte). Offline-Modus: nichts.
* Die Antwort sind die ersten zwei Sätze der Zusammenfassung mit Quelle – nichts dazuerfunden, auch ohne Sprachmodell.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
from typing import Any, Callable

SUCHE_URL = "https://{sprache}.wikipedia.org/w/rest.php/v1/search/title"
ZUSAMMENFASSUNG_URL = "https://{sprache}.wikipedia.org/api/rest_v1/page/summary/{titel}"
GUELTIG_S = 24 * 3600
MAX_BEGRIFF = 80
MAX_SATZ = 420


def offline() -> bool:
    return os.environ.get("DUCKPILOT_OFFLINE", "") not in ("", "0")


def begriff_pruefen(roh: Any) -> str:
    b = " ".join(str(roh or "").split()).strip(" ?!.„“\"'")
    if not b:
        raise ValueError("Wonach soll ich schauen?")
    if len(b) > MAX_BEGRIFF or any(ord(c) < 32 for c in b):
        raise ValueError(f"Suchbegriff: höchstens {MAX_BEGRIFF} Zeichen, eine Zeile")
    return b


def kurz(text: str, saetze: int = 2) -> str:
    """Die ersten Sätze – höchstens MAX_SATZ Zeichen, ohne Klammer-Aussprache am Anfang."""
    t = re.sub(r"\s*\([^()]{0,120}\)", "", " ".join(str(text or "").split()), count=1)
    teile = re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ0-9])", t)
    out = " ".join(teile[:saetze]).strip()
    if len(out) > MAX_SATZ:
        out = out[:MAX_SATZ].rsplit(" ", 1)[0] + " …"
    return out


def _hole(url: str) -> dict[str, Any]:
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "Knowlin duckpilot (Nachschlagen; https://knowlin.de)"})
    with urllib.request.urlopen(req, timeout=8) as res:          # noqa: S310 – feste https-Adressen oben
        return json.loads(res.read(256 * 1024).decode("utf-8"))


class Nachschlagen:
    def __init__(self, fetch: Callable[[str], dict[str, Any]] | None = None) -> None:
        self.fetch = fetch or _hole
        self._speicher: dict[str, tuple[float, dict[str, Any]]] = {}

    def frage(self, roh: Any, an: bool, en: bool = False) -> dict[str, Any]:
        if not an:
            return {"ok": False, "aus": True,
                    "fehler": "Looking things up online is off – switch it on under System → Settings → Knowlin." if en
                    else "Nachschlagen im Netz ist aus – einschalten unter System → Einstellungen → Knowlin."}
        if offline():
            return {"ok": False, "fehler": "Offline mode – I don't look anything up." if en else
                    "Offline-Modus – ich schlage nichts nach."}
        try:
            begriff = begriff_pruefen(roh)
        except ValueError as exc:
            return {"ok": False, "fehler": str(exc)}
        sprache = "en" if en else "de"
        schluessel = f"{sprache}:{begriff.lower()}"
        jetzt = time.time()
        if schluessel in self._speicher and jetzt - self._speicher[schluessel][0] < GUELTIG_S:
            return self._speicher[schluessel][1]
        try:
            q = urllib.parse.urlencode({"q": begriff, "limit": 1})
            seiten = (self.fetch(f"{SUCHE_URL.format(sprache=sprache)}?{q}").get("pages") or [])
            if not seiten:
                r = {"ok": False, "fehler": f"I found nothing about “{begriff}”." if en
                     else f"Zu „{begriff}“ finde ich nichts."}
            else:
                titel = str(seiten[0].get("key") or seiten[0].get("title") or begriff)
                d = self.fetch(ZUSAMMENFASSUNG_URL.format(sprache=sprache, titel=urllib.parse.quote(titel, safe="")))
                text = kurz(d.get("extract") or "")
                if not text or d.get("type") == "disambiguation":
                    r = {"ok": False, "fehler": f"“{begriff}” is ambiguous – say a bit more." if en
                         else f"„{begriff}“ ist mehrdeutig – sag etwas genauer, was du meinst."}
                else:
                    url = ((d.get("content_urls") or {}).get("desktop") or {}).get("page") or ""
                    r = {"ok": True, "titel": str(d.get("title") or titel), "text": text, "quelle": "Wikipedia",
                         "url": url if str(url).startswith("https://") else ""}
        except Exception as exc:  # noqa: BLE001 – Netz, Proxy, Dienst: ehrlich sagen, nie raten
            return {"ok": False, "fehler": f"Wikipedia is not reachable right now ({type(exc).__name__})." if en
                    else f"Die Wikipedia ist gerade nicht erreichbar ({type(exc).__name__})."}
        self._speicher[schluessel] = (jetzt, r)
        return r
