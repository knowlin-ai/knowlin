"""Tagesrückblick (seit 0.39, Erfahrungsnetz 2): was Knowlin an einem Tag erlebt hat – und abends in Worten.

Jedes Erlebnis, das ins Erfahrungsnetz geht (`Erfahrungsnetz.erleben`), landet hier mit Uhrzeit, Knoten und Anlass im
Tagebuch des Tages. Daraus entsteht ohne Sprachmodell ein kurzer Rückblick: wie viel los war, worum es am meisten ging,
was neu dazukam, Lob und Kritik, ob es eher ein froher oder ein schwieriger Tag war, und die stärksten Momente.

* **Korrigierbar:** Jeder Moment lässt sich aus dem Tagebuch löschen (Maintainer zu G4: „nicht erzählen, aber
  dokumentieren – so dass man ggf. korrigieren oder löschen kann“). Das Netz bleibt davon unberührt; dort gibt es
  „Vergessen“ je Knoten.
* **Erzählt wird nur auf Frage** („Wie war dein Tag?“, Werkzeug `tagesrueckblick`) oder in der Karte im Gedächtnis.
* **Personen** stehen im Tagebuch wie im Netz nur am PC: Für das Handy fallen Personen-Knoten und Momente, an denen
  eine Person beteiligt war, weg.
* Lokal in `tagebuch.json` neben `erfahrung.json`, höchstens 14 Tage, je Tag höchstens 400 Momente.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

TAGE = 14
JE_TAG = 400
POSITIV = ("gefuehl:freude", "gefuehl:begeistert", "gefuehl:stolz", "gefuehl:zufrieden", "gefuehl:lachen",
           "gefuehl:aufgeregt", "gefuehl:erleichtert", "rueckmeldung:lob")
NEGATIV = ("gefuehl:schreck", "gefuehl:erschrocken", "gefuehl:frustriert", "gefuehl:frust", "gefuehl:traurig",
           "gefuehl:grummelig", "rueckmeldung:kritik", "sinn:sturz", "sinn:anstossen")
OHNE_RAHMEN = ("zeit",)            # Tageszeiten zählen nicht als „worum es ging“


def tag_von(ts: float) -> str:
    return datetime.fromtimestamp(ts).date().isoformat()


def _aufzaehlung(namen: list[str], en: bool) -> str:
    if len(namen) <= 1:
        return "".join(namen)
    return f"{', '.join(namen[:-1])} {'and' if en else 'und'} {namen[-1]}"


def _mal(n: int) -> str:
    """1 → „einmal“, 2 → „zweimal“ … 12 → „zwölfmal“, sonst „13-mal“."""
    worte = ("ein", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwölf")
    return f"{worte[n - 1]}mal" if 1 <= n <= len(worte) else f"{n}-mal"


class Tagebuch:
    def __init__(self, pfad: Path | None = None) -> None:
        self.pfad = pfad
        self.tage: dict[str, list[dict[str, Any]]] = {}
        self.geaendert = False
        if pfad and pfad.exists():
            try:
                roh = json.loads(pfad.read_text(encoding="utf-8"))
                self.tage = {str(d): list(v)[:JE_TAG] for d, v in (roh.get("tage") or {}).items()}
            except (OSError, ValueError, AttributeError):
                self.tage = {}

    # ── Schreiben ─────────────────────────────────────────────────────────
    def notieren(self, ids: dict[str, str], warum: str = "", salienz: float = 1.0, herkunft: str | None = None,
                 jetzt: float | None = None) -> None:
        if not ids:
            return
        ts = time.time() if jetzt is None else jetzt
        tag = self.tage.setdefault(tag_von(ts), [])
        if len(tag) >= JE_TAG:
            # voll: den schwächsten Moment ersetzen, nie einfach abschneiden
            i = min(range(len(tag)), key=lambda j: tag[j].get("s", 1.0))
            if tag[i].get("s", 1.0) >= salienz:
                return
            tag.pop(i)
        tag.append({"t": round(ts, 1), "ids": {k: str(v)[:60] for k, v in ids.items()}, "warum": str(warum)[:120],
                    "s": round(float(salienz), 2), **({"h": herkunft} if herkunft else {})})
        self._aufraeumen()
        self.geaendert = True

    def _aufraeumen(self) -> None:
        if len(self.tage) > TAGE:
            for d in sorted(self.tage)[:-TAGE]:
                del self.tage[d]

    def loeschen(self, tag: str, t: float) -> bool:
        """Einen Moment löschen (Tag und Zeitstempel bestimmen ihn eindeutig genug)."""
        eintraege = self.tage.get(tag) or []
        vorher = len(eintraege)
        self.tage[tag] = [e for e in eintraege if abs(float(e.get("t", 0)) - float(t)) > 0.05]
        if len(self.tage[tag]) != vorher:
            self.geaendert = True
            return True
        return False

    def tag_loeschen(self, tag: str) -> bool:
        if self.tage.pop(tag, None) is None:
            return False
        self.geaendert = True
        return True

    def speichern(self) -> None:
        if not self.pfad or not self.geaendert:
            return
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.pfad.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"tage": self.tage}, f, ensure_ascii=False)
        os.replace(tmp, self.pfad)
        self.geaendert = False

    # ── Lesen ─────────────────────────────────────────────────────────────
    def tage_liste(self) -> list[str]:
        return sorted(self.tage, reverse=True)

    def rueckblick(self, tag: str | None = None, en: bool = False, ohne_personen: bool = False,
                   erst: dict[str, float] | None = None, heute: date | None = None) -> dict[str, Any]:
        """Der Rückblick eines Tages (Standard: heute). `erst`: wann ein Knoten zuerst erlebt wurde (aus dem Netz) –
        daraus „neu kennengelernt“."""
        heute = heute or date.today()
        tag = tag or heute.isoformat()
        eintraege = [e for e in self.tage.get(tag, [])
                     if not (ohne_personen and any(k.startswith("person:") for k in e.get("ids", {})))]
        zaehler: Counter[str] = Counter()
        namen: dict[str, str] = {}
        for e in eintraege:
            for k, label in e.get("ids", {}).items():
                if k.split(":", 1)[0] in OHNE_RAHMEN:
                    continue
                zaehler[k] += 1
                namen[k] = label
        froh = sum(1 for e in eintraege for k in e.get("ids", {}) if k in POSITIV)
        schwer = sum(1 for e in eintraege for k in e.get("ids", {}) if k in NEGATIV)
        lob = sum(1 for e in eintraege if "rueckmeldung:lob" in e.get("ids", {}))
        kritik = sum(1 for e in eintraege if "rueckmeldung:kritik" in e.get("ids", {}))
        neu = []
        if erst:
            beginn = datetime.fromisoformat(tag).timestamp()
            for k in zaehler:
                if beginn <= erst.get(k, 0) < beginn + 86400 and not k.startswith(("gefuehl:", "rueckmeldung:")):
                    neu.append(namen[k])
        haeufig = [{"id": k, "name": namen[k], "art": k.split(":", 1)[0], "n": n} for k, n in zaehler.most_common(6)]
        momente = sorted(eintraege, key=lambda e: (-float(e.get("s", 1.0)), float(e.get("t", 0))))[:5]
        momente = sorted(momente, key=lambda e: float(e.get("t", 0)))
        stimmung = "froh" if froh > schwer * 1.5 and froh else "schwer" if schwer > froh * 1.5 and schwer else \
            ("gemischt" if froh or schwer else "ruhig")
        return {
            "tag": tag, "anzahl": len(eintraege), "haeufig": haeufig, "neu": neu[:6], "lob": lob, "kritik": kritik,
            "stimmung": stimmung, "tage": self.tage_liste(), "ids": sorted(zaehler),   # für „In der Galaxie zeigen“
            "momente": [{"t": e["t"], "zeit": datetime.fromtimestamp(float(e["t"])).strftime("%H:%M"),
                         "warum": e.get("warum") or ", ".join(e.get("ids", {}).values()),
                         "dinge": [v for k, v in e.get("ids", {}).items() if not k.startswith("zeit:")]} for e in momente],
            "text": self.text(tag, len(eintraege), haeufig, neu, lob, kritik, stimmung, en, heute),
        }

    @staticmethod
    def text(tag: str, anzahl: int, haeufig: list[dict[str, Any]], neu: list[str], lob: int, kritik: int,
             stimmung: str, en: bool, heute: date) -> str:
        """Der Rückblick in ein paar Sätzen – ohne Sprachmodell, damit er immer da ist und nichts erfindet."""
        d = date.fromisoformat(tag)
        if d == heute:
            wann = "Today" if en else "Heute"
        elif d == heute - timedelta(days=1):
            wann = "Yesterday" if en else "Gestern"
        else:
            wann = (f"On {d.strftime('%d %B')}" if en else f"Am {d.day}.{d.month}.")
        if not anzahl:
            return f"{wann} nothing much happened yet." if en else f"{wann} ist noch nicht viel passiert."
        if en:
            saetze = [f"{wann} I experienced {'one thing' if anzahl == 1 else f'{anzahl} things'}."]
        else:
            saetze = [f"{wann} habe ich {'eine Sache' if anzahl == 1 else f'{anzahl} Dinge'} erlebt."]
        oben = [f"{h['name']} ({h['n']}×)" for h in haeufig[:3] if h["n"] > 1]
        if oben:
            saetze.append(f"It was mostly about {_aufzaehlung(oben, en)}." if en
                          else f"Am meisten ging es um {_aufzaehlung(oben, en)}.")
        if neu:
            saetze.append(f"New to me: {_aufzaehlung(neu[:3], en)}." if en else f"Neu kennengelernt: {_aufzaehlung(neu[:3], en)}.")
        if lob:
            saetze.append(f"I was praised {lob} {'time' if lob == 1 else 'times'}." if en
                           else f"Gelobt wurde ich {_mal(lob)}.")
        if kritik:
            saetze.append(f"I was criticised {kritik} {'time' if kritik == 1 else 'times'} – I'll keep it in mind." if en
                           else f"Kritik gab es {_mal(kritik)} – das merke ich mir.")
        stimmungen = ({"froh": "All in all, a happy day.", "schwer": "All in all, a bumpy day.",
                       "gemischt": "Ups and downs.", "ruhig": "A calm day."} if en else
                      {"froh": "Alles in allem ein froher Tag.", "schwer": "Alles in allem ein holpriger Tag.",
                       "gemischt": "Mal so, mal so.", "ruhig": "Ein ruhiger Tag."})
        saetze.append(stimmungen[stimmung])
        return " ".join(saetze)
