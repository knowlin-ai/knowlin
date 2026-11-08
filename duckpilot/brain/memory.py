"""Das Gedächtnis der Ente: eine JSON-Datei auf dem PC.

Claude selbst lernt nichts dazu. Stattdessen merkt sich duckpilot, was der
Mensch der Ente beibringt, und gibt Claude bei jeder Nachricht den passenden
Ausschnitt mit:

* **Tricks** – gelungene Choreografien unter einem Namen („Verbeugung“).
* **Orte** – Positionen mit Namen („Küche“). Getrennt nach Körper: Simulator-
  Koordinaten sind auf dem echten Roboter wertlos und umgekehrt.
* **Vorlieben** – kurze Sätze („lauf langsamer“, „quak nicht so oft“).
* **Wissen** – was der Mensch der Ente erzählt und was sie behalten soll („ich heiße
  Alex“, „unsere Katze heißt Momo“). Nur auf Wunsch, nie Gesundheits-, Bank- oder
  Zugangsdaten.
* **Übung** – gespeicherte Tricks werden besser: jede Verbesserung legt die alte Fassung
  als Version ab, Lob und Kritik („zu wild“, „super!“) stehen als Notizen am Trick.
* **Protokoll** – was schiefging (Stürze, abgelehnte Befehle), zum Nachjustieren.

Die Datei liegt standardmäßig *nicht* im Projektordner, sondern im lokalen
App-Datenordner (Windows: %LOCALAPPDATA%\\duckpilot\\memory.json), damit sie
nicht ungefragt per OneDrive in die Cloud wandert. Sie ist lesbar, in der
Oberfläche einsehbar und dort einzeln oder komplett löschbar.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
import tempfile
import time
import unicodedata
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# Herkunft (seit 0.38.10, Wunsch des Maintainers): wo etwas gelernt wurde – „kopf“ (Knowlin ohne Körper) oder
# „<modul>:sim|echt“. Der Kopf setzt sie für seine Antworten; sonst gilt die Verkörperung im Körper (`Memory.herkunft`).
HERKUNFT: ContextVar[str | None] = ContextVar("herkunft", default=None)

log = logging.getLogger(__name__)

VERSION = 1
MAX_TRICKS = 50
MAX_PLACES = 30
MAX_PREFS = 40
MAX_FACTS = 60
MAX_VERSIONS = 5
MAX_NOTES = 8
MAX_LOG = 200
MAX_NAME = 40
MAX_TEXT = 200
KINDS = ("trick", "ort", "vorliebe", "wissen", "protokoll")
# Was nicht ins Gedächtnis gehört (Datenschutz) – grob, aber verlässlich
SENSITIVE = re.compile(
    r"\b(passw\w*|kennw\w*|pins?|tans?|iban|bic|kontonummer\w*|kontostand\w*|kreditkart\w*|ausweis\w*|"
    r"reisepass\w*|steuer-?id|sozialversicherung\w*|versichertennummer\w*|diagnos\w*|krankheit\w*|"
    r"medikament\w*)\b", re.I)


def default_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "duckpilot" / "memory.json"


def norm(text: str) -> str:
    """Für Vergleiche: klein, ohne Akzente, Umlaute ausgeschrieben, nur Buchstaben/Ziffern."""
    t = text.lower().strip()
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", str(name or "")).strip(" .,!?\"'„“")
    return name[:MAX_NAME]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _stem_match(word: str, target: str) -> bool:
    """„verbeug“ trifft „verbeugung“, „kueche“ trifft „kuechen“ – gemeinsamer Anfang reicht."""
    if not word or not target:
        return False
    if word == target:
        return True
    n = min(len(word), len(target))
    need = max(4, min(6, n))
    return n >= 4 and word[:need] == target[:need]


def mentions(text: str, name: str) -> bool:
    """Kommt `name` (ein oder mehrere Wörter) in `text` vor – tolerant gegenüber Endungen?"""
    words = norm(text).split()
    parts = norm(name).split()
    if not parts:
        return False
    return all(any(_stem_match(w, p) for w in words) for p in parts)


class Memory:
    def __init__(self, path: str | os.PathLike | None = None) -> None:
        self.path = Path(path) if path else default_path()
        self.data: dict[str, Any] = self._empty()
        self.listeners: list[Callable[[dict[str, Any]], None]] = []
        self.error: str | None = None
        self.load()

    # ── Datei ─────────────────────────────────────────────────────────────
    @staticmethod
    def _empty() -> dict[str, Any]:
        # „tricks“ gehören der Verkörperung, die gerade einen Körper hat; die der anderen liegen unter „tricks_je_figur“
        # (seit 0.38.3). Orte, Vorlieben, Wissen und Protokoll teilen alle Verkörperungen.
        return {"version": VERSION, "figur": "duckpilot", "tricks": {}, "tricks_je_figur": {}, "orte": {},
                "vorlieben": [], "wissen": [], "protokoll": []}

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            data = self._empty()
            for key in data:
                if key in raw and isinstance(raw[key], type(data[key])):
                    data[key] = raw[key]
            self.data = data
        except Exception as exc:
            # Kaputte Datei nicht überschreiben – zur Seite legen und leer starten.
            backup = self.path.with_suffix(f".kaputt-{int(time.time())}.json")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            self.error = f"Gedächtnisdatei war nicht lesbar ({exc}); gesichert als {backup.name}"
            log.error(self.error)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".memory-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)  # atomar: nie eine halb geschriebene Datei
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        for fn in list(self.listeners):
            try:
                fn(self.snapshot())
            except Exception:
                log.exception("Gedächtnis-Listener")

    def snapshot(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.data))

    @property
    def figur(self) -> str:
        return str(self.data.get("figur") or "duckpilot")

    def set_figur(self, modul: str) -> None:
        """Andere Verkörperung bekommt den Körper: eigene Tricks tauschen, alles Gemeinsame bleibt."""
        if modul == self.figur:
            return
        je = self.data.setdefault("tricks_je_figur", {})
        je[self.figur] = self.data.get("tricks", {})
        self.data["tricks"] = je.pop(modul, {})
        self.data["figur"] = modul
        self.save()

    # ── Tricks ────────────────────────────────────────────────────────────
    def remember_trick(self, name: str, keyframes: list[dict[str, Any]], loops: int = 1,
                       description: str = "") -> str:
        name = clean_name(name)
        if not name:
            raise ValueError("Ein Trick braucht einen Namen")
        if not keyframes:
            raise ValueError("Ein Trick braucht Keyframes")
        key = self._existing_key(self.data["tricks"], name) or name
        if key not in self.data["tricks"] and len(self.data["tricks"]) >= MAX_TRICKS:
            raise ValueError(f"Schon {MAX_TRICKS} Tricks gespeichert – erst einen vergessen")
        old = self.data["tricks"].get(key, {})
        versions = list(old.get("versionen", []))
        if old.get("keyframes"):
            versions.append({"keyframes": old["keyframes"], "loops": old.get("loops", 1),
                             "geaendert": old.get("geaendert", old.get("erstellt", _now()))})
        self.data["tricks"][key] = {
            "keyframes": keyframes[:80],
            "loops": max(1, min(20, int(loops or 1))),
            "beschreibung": str(description or old.get("beschreibung", ""))[:MAX_TEXT],
            "erstellt": old.get("erstellt", _now()),
            "geaendert": _now(),
            "benutzt": old.get("benutzt", 0),
            "version": old.get("version", 0) + 1,
            "versionen": versions[-MAX_VERSIONS:],
            "gut": old.get("gut", 0),
            "schlecht": old.get("schlecht", 0),
            "notizen": old.get("notizen", []),
        }
        for k in ("herkunft", "probe"):              # Trick aus einem Knowlet bleibt einer, auch nachbearbeitet (0.38.6)
            if k in old:
                self.data["tricks"][key][k] = old[k]
        self.save()
        return key

    def rate_trick(self, name: str, verdict: str, note: str = "") -> tuple[str, dict[str, Any]]:
        """Lob, Kritik oder „zurück zur vorigen Fassung“ – damit die Ente mit jeder Übung besser wird."""
        key = self.trick_name(name)
        if not key:
            raise KeyError(f"Keinen Trick namens '{name}'")
        t = self.data["tricks"][key]
        if verdict == "zurueck":
            versions = t.get("versionen") or []
            if not versions:
                raise ValueError(f"„{key}“ hat keine ältere Fassung")
            prev = versions.pop()
            t.update(keyframes=prev["keyframes"], loops=prev.get("loops", 1), geaendert=_now(),
                     version=max(1, t.get("version", 1) - 1))
        elif verdict in ("gut", "schlecht"):
            t[verdict] = t.get(verdict, 0) + 1
        else:
            raise ValueError("urteil: gut, schlecht oder zurueck")
        note = re.sub(r"\s+", " ", str(note or "")).strip()[:120]
        if note:
            notes = t.setdefault("notizen", [])
            notes.append(f"{'👍' if verdict == 'gut' else '👎' if verdict == 'schlecht' else '↩'} {note}")
            del notes[:-MAX_NOTES]
        self.save()
        return key, t

    def find_trick(self, text: str) -> str | None:
        """Welcher gespeicherte Trick ist in `text` gemeint? Längster Treffer gewinnt."""
        hits = [n for n in self.data["tricks"] if mentions(text, n)]
        return max(hits, key=len) if hits else None

    def get_trick(self, name: str) -> dict[str, Any] | None:
        key = self._existing_key(self.data["tricks"], name) or self.find_trick(name)
        return self.data["tricks"].get(key) if key else None

    def trick_name(self, name: str) -> str | None:
        return self._existing_key(self.data["tricks"], name) or self.find_trick(name)

    def used_trick(self, name: str) -> None:
        t = self.data["tricks"].get(name)
        if t:
            t["benutzt"] = t.get("benutzt", 0) + 1
            t["zuletzt"] = _now()
            self.save()

    # ── Orte ──────────────────────────────────────────────────────────────
    def remember_place(self, name: str, body: str, x: float, y: float, yaw: float, note: str = "") -> str:
        name = clean_name(name)
        if not name:
            raise ValueError("Ein Ort braucht einen Namen")
        places = self.data["orte"]
        key = self._existing_key(places, name, body=body) or name
        if key in places and places[key].get("koerper") != body:
            key = f"{name} ({body})"
        if key not in places and len(places) >= MAX_PLACES:
            raise ValueError(f"Schon {MAX_PLACES} Orte gespeichert – erst einen vergessen")
        places[key] = {
            "koerper": body,
            "x": round(float(x), 3),
            "y": round(float(y), 3),
            "blick_grad": round(math.degrees(yaw)),
            "notiz": str(note or "")[:MAX_TEXT],
            "erstellt": _now(),
        }
        self.save()
        return key

    def places_for(self, body: str) -> dict[str, dict[str, Any]]:
        return {n: p for n, p in self.data["orte"].items() if p.get("koerper") == body}

    def find_place(self, text: str, body: str) -> str | None:
        places = self.places_for(body)
        exact = self._existing_key(places, text)
        if exact:
            return exact
        hits = [n for n in places if mentions(text, n)]
        return max(hits, key=len) if hits else None

    # ── Vorlieben ─────────────────────────────────────────────────────────
    def remember_preference(self, text: str) -> str:
        text = re.sub(r"\s+", " ", str(text or "")).strip()[:MAX_TEXT]
        if not text:
            raise ValueError("Leere Vorliebe")
        prefs = self.data["vorlieben"]
        for p in prefs:
            if norm(p["text"]) == norm(text):
                return p["id"]
        pid = f"v{int(time.time() * 1000) % 10**10}"
        prefs.append({"id": pid, "text": text, "erstellt": _now(), **self._von()})
        del prefs[:-MAX_PREFS]
        self.save()
        return pid

    def _von(self) -> dict[str, str]:
        """Herkunft eines neuen Eintrags – leer, wenn unbekannt (alte Einträge haben keine)."""
        von = HERKUNFT.get()
        if von is None and callable(getattr(self, "herkunft", None)):
            von = self.herkunft()
        return {"von": von} if von else {}

    # ── Wissen ────────────────────────────────────────────────────────────
    def remember_fact(self, text: str) -> str:
        text = re.sub(r"\s+", " ", str(text or "")).strip()[:MAX_TEXT]
        if not text:
            raise ValueError("Leerer Eintrag")
        if SENSITIVE.search(text):
            raise ValueError("Das merke ich mir lieber nicht – Zugangs-, Bank-, Ausweis- und Gesundheitsdaten "
                             "gehören nicht ins Gedächtnis einer Ente.")
        facts = self.data["wissen"]
        for f in facts:
            if norm(f["text"]) == norm(text):
                return f["id"]
        fid = f"w{int(time.time() * 1000) % 10**10}"
        facts.append({"id": fid, "text": text, "erstellt": _now(), **self._von()})
        del facts[:-MAX_FACTS]
        self.save()
        return fid

    def relevant_facts(self, text: str, limit: int = 12) -> list[str]:
        facts = self.data["wissen"]
        words = {w for w in norm(text).split() if len(w) >= 4}
        hits = [f for f in facts if words & {w for w in norm(f["text"]).split() if len(w) >= 4}]
        rest = [f for f in reversed(facts) if f not in hits]
        return [f["text"] for f in (hits + rest)[:limit]]

    # ── Protokoll ─────────────────────────────────────────────────────────
    def log_event(self, kind: str, text: str, save: bool = True) -> None:
        entries = self.data["protokoll"]
        text = str(text)[:MAX_TEXT]
        if entries and entries[-1]["text"] == text and entries[-1]["art"] == kind:
            entries[-1]["anzahl"] = entries[-1].get("anzahl", 1) + 1
            entries[-1]["zeit"] = _now()
        else:
            entries.append({"zeit": _now(), "art": kind, "text": text})
            del entries[:-MAX_LOG]
        if save:
            self.save()

    # ── Vergessen ─────────────────────────────────────────────────────────
    def forget(self, kind: str, name: str | None = None) -> str:
        kind = {"tricks": "trick", "orte": "ort", "vorlieben": "vorliebe"}.get(kind, kind)
        if kind == "wissen":
            facts = self.data["wissen"]
            match = next((f for f in facts if f["id"] == name), None)
            if match is None and name:
                match = next((f for f in facts if norm(name) in norm(f["text"])), None)
            if match is None:
                raise KeyError(f"Nichts gemerkt zu '{name}'")
            facts.remove(match)
            self.save()
            return match["text"]
        if kind == "trick":
            key = self.trick_name(name or "")
            if not key:
                raise KeyError(f"Keinen Trick namens '{name}'")
            del self.data["tricks"][key]
        elif kind == "ort":
            places = self.data["orte"]
            key = self._existing_key(places, name or "") or next((n for n in places if mentions(name or "", n)), None)
            if not key:
                raise KeyError(f"Keinen Ort namens '{name}'")
            del places[key]
        elif kind == "vorliebe":
            prefs = self.data["vorlieben"]
            match = next((p for p in prefs if p["id"] == name), None)
            if match is None and name:
                match = next((p for p in prefs if norm(name) in norm(p["text"])), None)
            if match is None:
                raise KeyError(f"Keine Vorliebe passend zu '{name}'")
            prefs.remove(match)
            key = match["text"]
        elif kind == "protokoll":
            self.data["protokoll"] = []
            key = "Protokoll"
        else:
            raise ValueError(f"Unbekannte Art '{kind}' – {', '.join(KINDS)}")
        self.save()
        return key

    def forget_all(self) -> None:
        self.data = self._empty()
        self.save()

    # ── Für Claude: nur, was zur Lage passt ───────────────────────────────
    def context(self, body: str, text: str = "", x: float = 0.0, y: float = 0.0) -> dict[str, Any]:
        out: dict[str, Any] = {}
        prefs = self.data["vorlieben"]
        if prefs:
            out["vorlieben"] = [p["text"] for p in prefs[-15:]]
        tricks = self.data["tricks"]
        if tricks:
            ranked = sorted(tricks, key=lambda n: (not mentions(text, n), -tricks[n].get("benutzt", 0)))
            out["tricks"] = ranked[:20]
        places = self.places_for(body)
        if places:
            def score(n: str) -> tuple[bool, float]:
                p = places[n]
                return (not mentions(text, n), math.hypot(p["x"] - x, p["y"] - y))
            out["orte"] = [
                {"name": n, "entfernung_m": round(math.hypot(places[n]["x"] - x, places[n]["y"] - y), 2)}
                for n in sorted(places, key=score)[:10]
            ]
        facts = self.relevant_facts(text)
        if facts:
            out["wissen"] = facts
        notes = {}
        for n in tricks:
            t = tricks[n]
            if mentions(text, n) and (t.get("notizen") or t.get("gut") or t.get("schlecht")):
                notes[n] = {"version": t.get("version", 1), "gut": t.get("gut", 0), "schlecht": t.get("schlecht", 0),
                            "notizen": t.get("notizen", [])[-4:]}
        if notes:
            out["trick_uebung"] = notes
        recent = self.data["protokoll"][-4:]
        if recent:
            out["zuletzt_schiefgegangen"] = [e["text"] for e in recent]
        return out

    def summary(self, body: str) -> dict[str, Any]:
        """Alles, für das Werkzeug `recall` – Tricks ohne Keyframes, damit es kurz bleibt."""
        return {
            "tricks": {n: {"beschreibung": t.get("beschreibung", ""), "keyframes": len(t["keyframes"]),
                           "benutzt": t.get("benutzt", 0), "version": t.get("version", 1),
                           "gut": t.get("gut", 0), "schlecht": t.get("schlecht", 0),
                           "notizen": t.get("notizen", [])} for n, t in self.data["tricks"].items()},
            "wissen": [f["text"] for f in self.data["wissen"]],
            "orte": self.places_for(body),
            "orte_anderer_koerper": sorted(n for n, p in self.data["orte"].items() if p.get("koerper") != body),
            "vorlieben": [p["text"] for p in self.data["vorlieben"]],
            "protokoll": self.data["protokoll"][-10:],
            "datei": str(self.path),
        }

    # ── intern ────────────────────────────────────────────────────────────
    @staticmethod
    def _existing_key(table: dict[str, Any], name: str, body: str | None = None) -> str | None:
        n = norm(name)
        for key, value in table.items():
            if norm(key) == n and (body is None or value.get("koerper") == body):
                return key
        return None
