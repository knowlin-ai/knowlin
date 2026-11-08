"""Das Erfahrungsnetz: was die Ente zusammen erlebt, verknüpft sich – und prägt, was ihr einfällt und wie sie ist.

Ein kleines assoziatives Netz nach Hebb („was zusammen feuert, verdrahtet sich“):

* **Knoten** sind Dinge aus ihrer Welt: Personen (nur angelernte, mit Einverständnis), Orte, Dinge, Tageszeiten,
  Tätigkeiten, Gefühle, Sinneseindrücke und Rückmeldungen (Lob, Kritik).
* **Aktivierung:** Was gerade passiert, regt Knoten an. Der Rahmen (Tageszeit, Ort, wer da ist) bleibt leise aktiv.
  Aktivierung breitet sich über starke Verbindungen aus und klingt in Sekunden ab – das ist die „Hirnaktivität“.
* **Lernen:** Sind zwei Knoten gleichzeitig aktiv, wird ihre Verbindung stärker (Δw = η · s · aᵢ · aⱼ · (1 − w)).
  Starke Erlebnisse (Sturz, Lob, Neues) prägen sich tiefer ein (Salienz s).
* **Vergessen:** Ungenutzte Verbindungen verblassen (Halbwertszeit zwei Wochen), schwache verschwinden ganz.
  Im Ruhemodus wird nachts gefestigt und aufgeräumt (`consolidate`).
* **Erinnern:** Aus der aktuellen Lage breitet sich Aktivierung aus; was am stärksten mitschwingt, „fällt ihr ein“ –
  als kleiner Ausschnitt für Claude (`recall`).
* **Prägung:** Aus den Erfahrungen der letzten Zeit verschiebt sich ihr Temperament leicht (± 0,1) – die
  eingestellte Persönlichkeit bleibt der Anker (`praegung`).

Ehrlich: Das ist ein lernendes Gewichtsnetz, kein Deep Learning und kein Bewusstsein. Das Sprachmodell selbst
lernt nichts. Alles liegt lokal in `erfahrung.json`; Personen-Knoten verlassen nie den PC (nicht ans Handy).
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any

ARTEN = ("person", "ort", "ding", "zeit", "taetigkeit", "gefuehl", "sinn", "rueckmeldung")
LERNRATE = 0.08
HALBWERTSZEIT_TAGE = 14.0
W_MIN = 0.02                 # schwächere Verbindungen werden vergessen
AKT_TAU = 6.0                # s: so schnell klingt Aktivierung ab
RAHMEN = 0.35                # leise Grundaktivierung für Tageszeit, Ort, Anwesende
MAX_KNOTEN = 400
MAX_KANTEN = 2500
MAX_AKTIV = 12               # so viele Knoten lernen höchstens gemeinsam
PRAEGUNG_MAX = 0.1
# Gefühlston eines Themas (G1, 0.38.27): Verbindungen zu diesen Knoten zählen als schön bzw. heikel
POSITIV = frozenset({"gefuehl:freude", "gefuehl:begeistert", "gefuehl:stolz", "gefuehl:erleichtert", "gefuehl:zufrieden",
                     "gefuehl:aufgeregt", "gefuehl:lachen", "rueckmeldung:lob"})
NEGATIV = frozenset({"gefuehl:schreck", "gefuehl:erschrocken", "gefuehl:frustriert", "gefuehl:frust", "gefuehl:traurig",
                     "gefuehl:ungeduldig", "gefuehl:grummelig", "rueckmeldung:kritik", "sinn:sturz", "sinn:anstossen"})
THEMEN = (("person", "Menschen"), ("ort", "Orte"), ("ding", "Dinge"), ("taetigkeit", "Tätigkeiten"))


def key(art: str, name: str) -> str:
    return f"{art}:{name.strip().lower()[:40]}"


def _pair(a: str, b: str) -> str:
    return f"{a}|{b}" if a < b else f"{b}|{a}"


class Erfahrungsnetz:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.knoten: dict[str, dict[str, Any]] = {}
        self.kanten: dict[str, dict[str, Any]] = {}
        self.akt: dict[str, float] = {}         # flüchtig: die aktuelle Aktivierung
        self.rahmen: dict[str, float] = {}      # flüchtig: der leise Rahmen (Zeit, Ort, Anwesende)
        self.neu: list[tuple[str, float]] = []  # flüchtig: frisch gestärkte Verbindungen (für die Anzeige)
        self.gelernt_bis = time.time()
        self._dirty = False
        self.load()

    # ── Speicher ──────────────────────────────────────────────────────────
    def load(self) -> None:
        if not self.path:
            return
        try:
            data = json.loads(self.path.read_text("utf-8"))
            self.knoten = {k: v for k, v in data.get("knoten", {}).items() if isinstance(v, dict)}
            self.kanten = {k: v for k, v in data.get("kanten", {}).items() if isinstance(v, dict) and "w" in v}
            self.gelernt_bis = float(data.get("gefestigt", time.time()))
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def save(self) -> None:
        if not self.path or not self._dirty:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"knoten": self.knoten, "kanten": self.kanten, "gefestigt": self.gelernt_bis}, f, ensure_ascii=False)
            os.replace(tmp, self.path)
            self._dirty = False
        except OSError:
            pass

    def reset(self) -> None:
        self.knoten.clear()
        self.kanten.clear()
        self.akt.clear()
        self.neu.clear()
        self._dirty = True
        self.save()

    # ── Knoten ────────────────────────────────────────────────────────────
    def _knoten(self, kid: str, label: str | None = None) -> dict[str, Any]:
        k = self.knoten.get(kid)
        if k is None:
            art, _, name = kid.partition(":")
            k = {"art": art if art in ARTEN else "ding", "name": label or name, "n": 0, "zuletzt": 0.0}
            self.knoten[kid] = k
            self._trim()
        if label:
            k["name"] = label
        return k

    def set_rahmen(self, ids: dict[str, str]) -> None:
        """Der leise Rahmen: {knoten-id: anzeigename} für Tageszeit, Ort, Anwesende."""
        for kid, label in ids.items():
            self._knoten(kid, label)
        self.rahmen = {kid: RAHMEN for kid in ids}

    # ── Erleben und Lernen ────────────────────────────────────────────────
    def erleben(self, ids: dict[str, str], salienz: float = 1.0, warum: str = "", herkunft: str | None = None) -> None:
        """Etwas ist passiert: diese Knoten feuern (voll), und alles gerade Aktive lernt mit. `herkunft` (seit 0.38.10):
        wo es passiert ist – „kopf“ oder „<modul>:sim|echt“; wird je Knoten und Verbindung mitgezählt."""
        now = time.time()
        for kid, label in ids.items():
            k = self._knoten(kid, label)
            k["n"] += 1
            if herkunft:
                h = k.setdefault("herkunft", {})
                h[herkunft] = h.get(herkunft, 0) + 1
            k["zuletzt"] = now
            self.akt[kid] = 1.0
        aktiv = self._aktiv()
        top = sorted(aktiv.items(), key=lambda x: -x[1])[:MAX_AKTIV]
        s = max(0.3, min(2.0, salienz))
        for i, (a, aa) in enumerate(top):
            for b, ab in top[i + 1:]:
                if a not in ids and b not in ids:
                    continue                      # nur, was jetzt passiert, knüpft neu an
                self._staerken(a, b, LERNRATE * s * aa * ab, warum, now, herkunft)
        self._dirty = True

    def _staerken(self, a: str, b: str, dw: float, warum: str, now: float, herkunft: str | None = None) -> None:
        p = _pair(a, b)
        e = self.kanten.get(p)
        if e is None:
            e = {"w": 0.0, "n": 0, "zuletzt": now, "warum": []}
            self.kanten[p] = e
        e["w"] = round(e["w"] + dw * (1.0 - e["w"]), 4)
        e["n"] += 1
        e["zuletzt"] = now
        if herkunft:
            h = e.setdefault("herkunft", {})
            h[herkunft] = h.get(herkunft, 0) + 1
        if warum and (not e["warum"] or e["warum"][-1] != warum):
            e["warum"] = [*e["warum"], warum[:80]][-3:]
        self.neu = [*[(x, t) for x, t in self.neu if now - t < 3.0 and x != p], (p, now)][-12:]
        if len(self.kanten) > MAX_KANTEN:
            weakest = sorted(self.kanten.items(), key=lambda kv: kv[1]["w"])[: len(self.kanten) - MAX_KANTEN]
            for k, _ in weakest:
                self.kanten.pop(k, None)

    def _trim(self) -> None:
        if len(self.knoten) <= MAX_KNOTEN:
            return
        degree: dict[str, float] = {}
        for p, e in self.kanten.items():
            for kid in p.split("|"):
                degree[kid] = degree.get(kid, 0.0) + e["w"]
        victims = sorted(self.knoten, key=lambda kid: (degree.get(kid, 0.0), self.knoten[kid]["zuletzt"]))
        for kid in victims[: len(self.knoten) - MAX_KNOTEN]:
            self.vergessen(kid)

    # ── Aktivierung ───────────────────────────────────────────────────────
    def _aktiv(self) -> dict[str, float]:
        out = dict(self.rahmen)
        for kid, a in self.akt.items():
            out[kid] = max(out.get(kid, 0.0), a)
        return {k: v for k, v in out.items() if v > 0.05 and k in self.knoten}

    def _nachbarn(self) -> dict[str, list[tuple[str, float]]]:
        nb: dict[str, list[tuple[str, float]]] = {}
        for p, e in self.kanten.items():
            a, b = p.split("|")
            nb.setdefault(a, []).append((b, e["w"]))
            nb.setdefault(b, []).append((a, e["w"]))
        return nb

    def tick(self, dt: float) -> None:
        """Aktivierung klingt ab und breitet sich ein wenig über starke Verbindungen aus."""
        if not self.akt:
            return
        f = math.exp(-dt / AKT_TAU)
        nb = self._nachbarn()
        nxt: dict[str, float] = {}
        for kid, a in self.akt.items():
            nxt[kid] = max(nxt.get(kid, 0.0), a * f)
            for other, w in nb.get(kid, []):
                if w > 0.15:
                    nxt[other] = max(nxt.get(other, 0.0), min(0.6, a * w * 0.5) * f)
        self.akt = {k: round(v, 3) for k, v in nxt.items() if v > 0.04}

    # ── Erinnern ──────────────────────────────────────────────────────────
    def recall(self, cue: dict[str, float] | None = None, k: int = 5, ohne: tuple[str, ...] = (),
               skip: set[str] | None = None) -> list[dict[str, Any]]:
        """Was schwingt bei der aktuellen Lage am stärksten mit? Zwei Schritte Ausbreitung von den Anregern aus.

        `skip`: was gar nicht „einfallen“ soll, weil es ohnehin gerade da ist (Standard: alle Anreger)."""
        start = cue if cue is not None else self._aktiv()
        skip = set(start) if skip is None else skip
        if not start:
            return []
        nb = self._nachbarn()
        score: dict[str, float] = {}
        for kid, a in start.items():
            for other, w in nb.get(kid, []):
                score[other] = score.get(other, 0.0) + a * w
                for third, w2 in nb.get(other, []):
                    if third != kid:
                        score[third] = score.get(third, 0.0) + 0.4 * a * w * w2
        out = []
        for kid, sc in sorted(score.items(), key=lambda x: -x[1]):
            if kid in skip or kid.split(":", 1)[0] in ohne or sc < 0.05:
                continue
            kn = self.knoten.get(kid)
            if kn:
                out.append({"id": kid, "art": kn["art"], "name": kn["name"], "staerke": round(min(1.0, sc), 2)})
            if len(out) >= k:
                break
        return out

    def warum(self, a: str, b: str) -> list[str]:
        e = self.kanten.get(_pair(a, b))
        return list(e["warum"]) if e else []

    # ── Festigen und Vergessen ────────────────────────────────────────────
    def consolidate(self, now: float | None = None) -> dict[str, int]:
        """Verblassen nach der vergangenen Zeit, Schwaches vergessen, verwaiste Knoten entfernen."""
        now = now or time.time()
        tage = max(0.0, (now - self.gelernt_bis) / 86400.0)
        self.gelernt_bis = now
        f = 0.5 ** (tage / HALBWERTSZEIT_TAGE)
        vergessen = 0
        for p in list(self.kanten):
            e = self.kanten[p]
            e["w"] = round(e["w"] * f, 4)
            if e["w"] < W_MIN:
                self.kanten.pop(p)
                vergessen += 1
        verbunden = {kid for p in self.kanten for kid in p.split("|")}
        weg = [kid for kid in self.knoten if kid not in verbunden and now - self.knoten[kid]["zuletzt"] > 7 * 86400]
        for kid in weg:
            self.knoten.pop(kid, None)
        self._dirty = True
        self.save()
        return {"verbindungen_vergessen": vergessen, "knoten_vergessen": len(weg)}

    def vergessen(self, kid: str) -> bool:
        if kid not in self.knoten:
            return False
        self.knoten.pop(kid, None)
        self.akt.pop(kid, None)
        for p in [p for p in self.kanten if kid in p.split("|")]:
            self.kanten.pop(p, None)
        self._dirty = True
        return True

    def verbindung_vergessen(self, a: str, b: str) -> bool:
        ok = self.kanten.pop(_pair(a, b), None) is not None
        self._dirty = self._dirty or ok
        return ok

    # ── Prägung ───────────────────────────────────────────────────────────
    def praegung(self) -> dict[str, Any]:
        """Leichte Verschiebung des Temperaments aus dem Erlebten: Freude/Spiel/Lob → lebhafter, Schreck/Kritik → ruhiger."""
        def stark(*ids: str) -> float:
            return sum(self.knoten.get(k, {}).get("n", 0) for k in ids)
        hoch = stark("gefuehl:freude", "gefuehl:begeistert", "gefuehl:stolz", "rueckmeldung:lob", "taetigkeit:spielen")
        tief = stark("gefuehl:schreck", "gefuehl:frustriert", "rueckmeldung:kritik", "sinn:sturz")
        gesamt = hoch + tief
        if gesamt < 40:                           # zu wenig erlebt, um daraus etwas zu schließen – Prägung braucht Zeit
            return {"energie": 0.0, "grund": "noch zu wenig erlebt"}
        x = (hoch - tief) / gesamt                # −1 … 1
        reife = min(1.0, gesamt / 200.0)          # erst nach vielen Erlebnissen volle Wirkung
        e = round(PRAEGUNG_MAX * reife * math.tanh(1.5 * x), 3)
        grund = "viel Spiel und Lob" if e > 0.02 else "einige Schrecken und Pannen" if e < -0.02 else "ausgeglichen"
        return {"energie": e, "grund": grund}

    # ── Was sie über die Welt weiß (G1) ───────────────────────────────────
    def thema(self, kid: str, now: float | None = None) -> dict[str, Any]:
        """Ein Thema in Worten: wie viel sie darüber weiß, wie es sich anfühlt, wie frisch und wie sicher es ist."""
        now = time.time() if now is None else now
        k = self.knoten[kid]
        pos = neg = 0.0
        nachbarn: list[tuple[float, str]] = []
        for p, e in self.kanten.items():
            a, b = p.split("|")
            if kid not in (a, b):
                continue
            other = b if a == kid else a
            pos += e["w"] if other in POSITIV else 0.0
            neg += e["w"] if other in NEGATIV else 0.0
            if other not in POSITIV and other not in NEGATIV:
                nachbarn.append((e["w"], other))
        if pos + neg < 0.05:
            ton = {"wert": None, "zeichen": "·", "wort": "noch ohne Gefühl"}
        else:
            x = (pos - neg) / (pos + neg)
            ton = ({"zeichen": "+", "wort": "eher schön"} if x > 0.3 else {"zeichen": "−", "wort": "eher heikel"} if x < -0.3
                   else {"zeichen": "±", "wort": "gemischt"})
            ton["wert"] = round(x, 2)
        tage = (now - float(k.get("zuletzt") or 0)) / 86400
        frische = ("heute" if tage < 1 else "gestern" if tage < 2 else "diese Woche" if tage < 7
                   else "vor einer Woche" if tage < 14 else f"vor {int(tage // 7)} Wochen" if tage < 31
                   else "vor über einem Monat")
        n = int(k.get("n", 0))
        sicher = "oft bestätigt" if n >= 10 else "ein paar Mal erlebt" if n >= 3 else "erst einmal erlebt" if n <= 1 else "zweimal erlebt"
        mit = [self.knoten[o]["name"] for _, o in sorted(nachbarn, reverse=True)[:3] if o in self.knoten]
        return {"id": kid, "name": k["name"], "art": k["art"], "erlebnisse": n,
                "verbindungen": sum(1 for p in self.kanten if kid in p.split("|")), "ton": ton,
                "zuletzt": {"tage": round(tage, 1), "wort": frische}, "sicherheit": sicher, "mit": mit}

    def themen(self, ohne_personen: bool = False, je: int = 5) -> dict[str, Any]:
        """Themenkarten: je Art (Menschen, Orte, Dinge, Tätigkeiten) die, über die sie am meisten weiß."""
        now = time.time()
        gruppen = []
        for art, titel in THEMEN:
            if ohne_personen and art == "person":
                continue
            ids = sorted((kid for kid, k in self.knoten.items() if k.get("art") == art),
                         key=lambda kid: -self.knoten[kid].get("n", 0))
            gruppen.append({"art": art, "titel": titel, "anzahl": len(ids), "eintraege": [self.thema(kid, now) for kid in ids[:je]]})
        return {"gruppen": gruppen}

    # ── Anzeige ───────────────────────────────────────────────────────────
    def message(self, ohne_personen: bool = False, max_knoten: int = 60, max_kanten: int = 120) -> dict[str, Any]:
        """Für die Oberfläche: die stärksten Knoten und Verbindungen, aktuelle Aktivierung, frische Verknüpfungen."""
        aktiv = self._aktiv()
        kanten = sorted(self.kanten.items(), key=lambda kv: -kv[1]["w"])
        def erlaubt(kid: str) -> bool:
            return not (ohne_personen and kid.startswith("person:"))
        gew: dict[str, float] = {}
        for p, e in kanten:
            for kid in p.split("|"):
                gew[kid] = gew.get(kid, 0.0) + e["w"]
        wahl = sorted((k for k in self.knoten if erlaubt(k)), key=lambda k: (-(aktiv.get(k, 0.0) > 0.1), -gew.get(k, 0.0), -self.knoten[k]["n"]))[:max_knoten]
        ids = set(wahl)
        now = time.time()
        frisch = {p for p, t in self.neu if now - t < 3.0}
        return {
            "type": "erfahrung",
            "knoten": [{"id": k, "art": self.knoten[k]["art"], "name": self.knoten[k]["name"], "n": self.knoten[k]["n"],
                        "akt": round(aktiv.get(k, 0.0), 2), "herkunft": self.knoten[k].get("herkunft") or {}} for k in wahl],
            "kanten": [{"a": p.split("|")[0], "b": p.split("|")[1], "w": e["w"], "neu": p in frisch}
                       for p, e in kanten if all(x in ids for x in p.split("|"))][:max_kanten],
            "zahlen": {"knoten": len(self.knoten), "verbindungen": len(self.kanten)},
            "praegung": self.praegung(),
        }
