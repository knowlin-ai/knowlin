"""Auftrag: vom Ziel in einem Satz bis zur geprüften Policy – wie in NVIDIAs Microduck-Vorführung,
aber mit Claude, Pollens Training in der Cloud und der Physik auf dem eigenen PC.

Ablauf (jeder Schritt sichtbar auf der Seite „Parcours“):

1. Ziel        – z. B. „Die Ente soll Rampe und Stufen schaffen“
2. Parcours    – Claude (oder das lokale Modell) baut ihn mit `parcours_bauen`
3. Basis-Test  – Pollens Geh-Policy läuft mehrmals hindurch (`parcours_testen`)
4. Vorschlag   – scheitert sie, schlägt Claude einen Trainingslauf vor (`training_vorschlagen`)
5. Training    – startet der Mensch (kostet Geld), läuft auf Hugging Face Jobs
6. Bewertung   – ist der Lauf fertig, prüft duckpilot das Ergebnis selbst auf demselben Parcours
                 und vergleicht mit dem Basis-Test

Auf die echte Ente geht eine Policy nur, wenn der Mensch es auslöst.
Gespeichert wird in `auftraege.json` im lokalen App-Datenordner, die Aufzeichnungen der
Versuche (für die 3D-Wiederholung) in `parcours/`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .physics import course as C

log = logging.getLogger(__name__)

MAX_MISSIONS = 20
MAX_TESTS = 12
MAX_REPLAYS = 30
STEPS = ("ziel", "parcours", "basis", "vorschlag", "training", "bewertung")
STEP_LABEL = {"ziel": "Ziel", "parcours": "Parcours", "basis": "Basis-Test", "vorschlag": "Vorschlag",
              "training": "Training", "bewertung": "Bewertung"}


class MissionStore:
    def __init__(self, root: Path) -> None:
        self.path = root / "auftraege.json"
        self.replay_dir = root / "parcours"
        self._lock = threading.Lock()
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("liste"), list):
                return data
        except Exception:
            pass
        return {"aktuell": None, "liste": []}

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)

    # ── Aufträge ──────────────────────────────────────────────────────────
    def current(self) -> dict[str, Any] | None:
        mid = self.data.get("aktuell")
        return next((m for m in self.data["liste"] if m["id"] == mid), None)

    def new(self, ziel: str = "") -> dict[str, Any]:
        mid = time.strftime("%Y%m%d-%H%M%S")
        while any(m["id"] == mid for m in self.data["liste"]):
            mid += "x"
        m = {"id": mid, "ziel": _text(ziel, 200) or "Parcours schaffen", "erstellt": time.strftime("%Y-%m-%d %H:%M"),
             "parcours": None, "tests": [], "vorschlag": None, "lauf": None}
        self.data["liste"].append(m)
        del self.data["liste"][:-MAX_MISSIONS]
        self.data["aktuell"] = mid
        self.save()
        return m

    def select(self, mid: str) -> dict[str, Any]:
        m = next((x for x in self.data["liste"] if x["id"] == mid), None)
        if m is None:
            raise KeyError("Diesen Auftrag gibt es nicht.")
        self.data["aktuell"] = mid
        self.save()
        return m

    def set_course(self, spec: dict[str, Any], ziel: str | None = None) -> dict[str, Any]:
        m = self.current()
        if m is None or (ziel and _text(ziel, 200) != m["ziel"] and m.get("tests")):
            m = self.new(ziel or "")          # neues Ziel nach Tests: neuer Auftrag, der alte bleibt lesbar
        elif ziel:
            m["ziel"] = _text(ziel, 200)
        if m.get("parcours") != spec:
            m["parcours"] = spec
            m["tests"] = []                  # anderer Parcours: alte Ergebnisse, Vorschlag und Lauf passen nicht mehr
            m["vorschlag"] = None
            m["lauf"] = None
            m["laeufe"] = []
        self.save()
        return m

    def add_test(self, test: dict[str, Any], mid: str | None = None, spec: dict[str, Any] | None = None) -> bool:
        """Ergebnis an den Auftrag hängen, für den getestet wurde – nicht, wenn sich der Parcours inzwischen änderte."""
        m = next((x for x in self.data["liste"] if x["id"] == mid), None) if mid else self.current()
        if m is None or (spec is not None and m.get("parcours") != spec):
            return False
        m["tests"].append(test)
        del m["tests"][:-MAX_TESTS]
        self.save()
        return True

    def link_proposal(self, plan: dict[str, Any]) -> None:
        m = self.current()
        if m is not None and m.get("parcours"):
            if (m.get("vorschlag") or {}).get("aufgabe") != plan.get("aufgabe"):
                m["lauf"] = None             # neuer Vorschlag: die alten Läufe gehören nicht mehr dazu
                m["laeufe"] = []
            m["vorschlag"] = {k: plan.get(k) for k in ("aufgabe", "iterationen", "anpassungen", "begruendung")}
            self.save()

    def link_run(self, plan: dict[str, Any], run: dict[str, Any], mid: str | None = None) -> bool:
        """Ein gestarteter Lauf gehört zum Auftrag, wenn er dessen Vorschlag umsetzt. `mid`: der Auftrag, der beim
        Start aktuell war (Varianten starten nacheinander – inzwischen kann ein anderer Auftrag gewählt sein)."""
        m = next((x for x in self.data["liste"] if x["id"] == mid), None) if mid else self.current()
        v = (m or {}).get("vorschlag")
        if m and v and v.get("aufgabe") == plan.get("aufgabe") and run.get("id"):   # der neueste Lauf zählt
            group = run.get("gruppe")
            prev = linked(m)
            same_group = group and prev and all((self._group_of(m, r) == group) for r in prev)
            m["laeufe"] = [*prev, run["id"]] if same_group else [run["id"]]   # Varianten eines Starts gehören zusammen
            m["lauf"] = run["id"]
            m.setdefault("gruppen", {})[run["id"]] = group
            self.save()
            return True
        return False

    @staticmethod
    def _group_of(m: dict[str, Any], rid: str) -> str | None:
        return (m.get("gruppen") or {}).get(rid)

    # ── Aufzeichnungen ────────────────────────────────────────────────────
    def save_replay(self, tid: str, frames: list[list[float]] | None) -> None:
        if not frames:
            return
        self.replay_dir.mkdir(parents=True, exist_ok=True)
        (self.replay_dir / f"{tid}.json").write_text(json.dumps(frames, separators=(",", ":")), encoding="utf-8")
        old = sorted(self.replay_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)[:-MAX_REPLAYS]
        for p in old:
            try:
                p.unlink()
            except OSError:
                pass

    def replay(self, tid: str) -> list[list[float]] | None:
        if not re.fullmatch(r"[\w-]{1,60}", tid or ""):
            return None
        p = self.replay_dir / f"{tid}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _text(s: Any, n: int) -> str:
    return " ".join(str(s or "").split())[:n]


def linked(m: dict[str, Any] | None) -> list[str]:
    """Die Trainingsläufe des Auftrags (bei Varianten mehrere)."""
    if not m:
        return []
    return list(m.get("laeufe") or ([m["lauf"]] if m.get("lauf") else []))


def steps(m: dict[str, Any] | None, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fortschritt des Auftrags für die Oberfläche."""
    if m is None:
        return [{"id": s, "titel": STEP_LABEL[s], "stand": "offen", "text": ""} for s in STEPS]
    tests = m.get("tests") or []
    base = next((t for t in tests if t["quelle"] == "standard"), None)
    mine = [r for r in runs if r["id"] in linked(m)]
    run = mine[-1] if mine else None
    keys = {f"lauf:{r['id']}" for r in mine}
    trained_all = [t for t in tests if t["quelle"] in keys]
    trained = max(trained_all, key=lambda t: (t["im_ziel"], _score(t)), default=None)
    out = [{"id": "ziel", "titel": "Ziel", "stand": "fertig", "text": f"seit {m['erstellt'][-5:]} Uhr"}]
    spec = m.get("parcours")
    out.append({"id": "parcours", "titel": "Parcours", "stand": "fertig" if spec else "jetzt",
                "text": spec["name"] if spec else "Claude baut ihn – oder eine Vorlage wählen"})
    out.append({"id": "basis", "titel": "Basis-Test", "stand": "fertig" if base else ("jetzt" if spec else "offen"),
                "text": f"{base['im_ziel']} von {base['versuche']} im Ziel" if base else "Pollens Geh-Policy prüfen"})
    v = m.get("vorschlag")
    good = base and base["im_ziel"] == base["versuche"]
    out.append({"id": "vorschlag", "titel": "Vorschlag",
                "stand": "fertig" if v else ("nicht nötig" if good else ("jetzt" if base else "offen")),
                "text": (v or {}).get("aufgabe") or ("die Standard-Policy schafft es schon" if good else "Claude schlägt ein Training vor")})
    if mine:
        states = [r["status"] for r in mine]
        failed = ("fehlgeschlagen", "abgebrochen")
        if any(x not in ("fertig", *failed) for x in states):
            stand = "läuft"
        elif any(x == "fertig" for x in states):
            stand = "fertig"
        else:
            stand = "fehler"
        text = states[0] if len(mine) == 1 else f"{len(mine)} Varianten: " + ", ".join(states)
        out.append({"id": "training", "titel": "Training", "stand": stand, "text": text})
    else:
        out.append({"id": "training", "titel": "Training", "stand": "jetzt" if v else "offen",
                    "text": "unter Lernen → Training starten (zwei Klicks)" if v else ""})
    if trained and base:
        better = trained["im_ziel"] - base["im_ziel"]
        txt = f"{trained['im_ziel']} statt {base['im_ziel']} von {trained['versuche']} im Ziel"
        if len(mine) > 1:
            txt += f" – beste: {trained.get('policy', '')}"
        out.append({"id": "bewertung", "titel": "Bewertung", "stand": "fertig", "text": txt,
                    "besser": better > 0 or (better == 0 and _score(trained) > _score(base))})
    else:
        out.append({"id": "bewertung", "titel": "Bewertung",
                    "stand": "läuft" if any(r["status"] == "fertig" for r in mine) else "offen",
                    "text": "prüft das Ergebnis auf demselben Parcours" if run else ""})
    return out


def _score(t: dict[str, Any]) -> int:
    return sum(e["geschafft"] for e in t.get("elemente", []))


class CourseLab:
    """Baut Parcours, prüft Policies darauf und hält den Auftrag – für Werkzeuge, Server und Oberfläche."""

    def __init__(self, root: Path, policies: Callable[[], Any], trainer: Any = None,
                 on_change: Callable[[], None] | None = None, note: Callable[[dict[str, Any]], None] | None = None,
                 token: Callable[[], str | None] | None = None) -> None:
        self.root = root
        self.missions = MissionStore(root)
        self.policies = policies          # () -> PolicyStore
        self.trainer = trainer
        self.on_change = on_change
        self.note = note
        self.token = token
        self.job: dict[str, Any] = {}
        self._cancel = False
        self._busy = asyncio.Lock()
        self._auto_tried: set[str] = set()
        self._auto_fails: dict[str, int] = {}

    def _changed(self) -> None:
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                log.exception("Parcours: Benachrichtigung")

    def course(self) -> C.Course | None:
        m = self.missions.current()
        if not m or not m.get("parcours"):
            return None
        try:
            return C.build(m["parcours"])
        except C.CourseError:
            return None

    # ── Parcours bauen ────────────────────────────────────────────────────
    def build(self, spec: dict[str, Any], ziel: str | None = None) -> dict[str, Any]:
        course = C.build(spec)
        cur = self.missions.current()
        if not ziel and (cur is None or (cur.get("tests") and cur.get("parcours") != course.spec())):
            ziel = f"Den Parcours „{course.name}“ ohne Sturz schaffen"
        m = self.missions.set_course(course.spec(), ziel)
        self._changed()
        return {"auftrag": m["id"], "ziel": m["ziel"], **course.summary()}

    # ── Policies zum Prüfen ───────────────────────────────────────────────
    def sources(self) -> list[dict[str, Any]]:
        out = []
        try:
            if "walk" in self.policies().roles():
                out.append({"id": "standard", "name": "Pollens Geh-Policy (VelStand)"})
        except Exception:
            pass
        if self.trainer is not None:
            from .training import TASKS

            for r in self.trainer.runs()[::-1]:
                if r.get("status") == "fertig":
                    t = TASKS.get(r["plan"]["aufgabe"], {})
                    if t.get("art") == "gangart":
                        extra = f" · {r['variante']}" if r.get("variante") else ""
                        out.append({"id": f"lauf:{r['id']}", "name": f"Training {r['start']}{extra} – {t.get('name', '')}"})
        for prov in getattr(self, "providers", []):       # kostenlose Wege: Kaggle, dieser PC
            try:
                out.extend(prov.sources())
            except Exception:
                pass
        return out

    def _resolve(self, quelle: str) -> tuple[str, float, str]:
        if quelle == "standard":
            roles = self.policies().roles()
            if "walk" not in roles:
                raise ValueError("Pollens Geh-Policy fehlt – unter Einstellungen → Körper laden.")
            e = roles["walk"]["eintrag"]
            return roles["walk"]["pfad"], float(e.get("action_scale") or 1.0), "Pollens Geh-Policy"
        if quelle.startswith("lauf:") and self.trainer is not None:
            rid = quelle[5:]
            run = next((r for r in self.trainer.runs() if r["id"] == rid), None)
            if run is None:
                raise ValueError("Diesen Trainingslauf gibt es nicht.")
            if run.get("status") != "fertig":
                raise ValueError(f"Der Lauf ist noch nicht fertig ({run.get('status')}).")
            token = self.token() if self.token else None
            path = run.get("onnx")
            if not path or not Path(path).exists():
                if not token:
                    raise ValueError("Für das Ergebnis braucht es den Hugging-Face-Token (Lernen → Training).")
                path = str(self.trainer.result(token, rid))
            return path, 1.0, f"Training {run['start']}" + (f" · {run['variante']}" if run.get("variante") else "")
        for prov in getattr(self, "providers", []):
            got = prov.resolve(quelle)
            if got is not None:
                return got
        raise ValueError("Unbekannte Policy – „standard“ oder „lauf:<id>“")

    # ── Prüfen ───────────────────────────────────────────────────────────
    async def test(self, quelle: str = "standard", versuche: int = 3, auto: bool = False) -> dict[str, Any]:
        course = self.course()
        if course is None:
            raise ValueError("Es gibt noch keinen Parcours – erst bauen.")
        mission = self.missions.current()
        mid, spec = mission["id"], mission["parcours"]
        if self._busy.locked():
            raise ValueError("Es läuft schon ein Test.")
        async with self._busy:
            self._cancel = False
            self.job = {"laeuft": True, "text": "lädt die Policy …", "quelle": quelle, "fehler": None}
            self._changed()
            loop = asyncio.get_running_loop()

            def progress(text: str) -> None:
                self.job["text"] = text
                loop.call_soon_threadsafe(self._changed)

            try:
                path, scale, label = await asyncio.to_thread(self._resolve, quelle)
                self.job["text"] = f"{label} läuft durch den Parcours …"
                self._changed()
                res = await asyncio.to_thread(C.evaluate, course, path, versuche, scale, label, progress,
                                              None, None, None, lambda: self._cancel)
            except Exception as exc:
                self.job = {"laeuft": False, "text": "fehlgeschlagen", "quelle": quelle, "fehler": str(exc)[:300]}
                self._changed()
                raise
            if self._cancel:
                self.job = {"laeuft": False, "text": "abgebrochen", "quelle": quelle, "fehler": None}
                self._changed()
                raise ValueError("Test abgebrochen")
            tid = time.strftime("%Y%m%d-%H%M%S") + f"-{abs(hash(quelle)) % 1000:03d}"
            replay = res.pop("wiederholung", None)
            res.pop("bahnen", None)
            test = {"id": tid, "zeit": time.strftime("%Y-%m-%d %H:%M"), "quelle": quelle, "auto": auto,
                    "parcours": course.name, "wiederholung": bool(replay), **res}
            if not self.missions.add_test(test, mid, spec):
                self.job = {"laeuft": False, "text": "Der Parcours hat sich während des Tests geändert – Ergebnis verworfen.",
                            "quelle": quelle, "fehler": None}
                self._changed()
                return test
            self.missions.save_replay(tid, replay)
            self.job = {"laeuft": False, "text": f"{label}: {res['im_ziel']} von {res['versuche']} im Ziel",
                        "quelle": quelle, "fehler": None, "test": tid}
            if self.note:
                self.note({"type": "parcours", "message": f"Parcours-Test {label}: {res['im_ziel']}/{res['versuche']} im Ziel"})
            self._changed()
            return test

    def cancel(self) -> None:
        self._cancel = True

    # ── Training fertig? Dann selbst prüfen ──────────────────────────────
    async def check_finished_runs(self) -> list[dict[str, Any]]:
        """Fertige Läufe des Auftrags selbst auf dem Parcours prüfen (bei Varianten jeden)."""
        m = self.missions.current()
        if not m or not linked(m) or self.trainer is None or not m.get("parcours"):
            return []
        done = []
        for rid in linked(m):
            run = next((r for r in self.trainer.runs() if r["id"] == rid), None)
            if not run or run.get("status") != "fertig":
                continue
            key = f"lauf:{rid}"
            m = self.missions.current() or {}
            if any(t["quelle"] == key for t in m.get("tests", [])) or key in self._auto_tried or self._busy.locked():
                continue
            self._auto_tried.add(key)
            try:
                done.append(await self.test(key, 3, auto=True))
            except Exception as exc:          # z. B. Token fehlt: beim nächsten Mal wieder versuchen, höchstens dreimal
                self._auto_fails[key] = self._auto_fails.get(key, 0) + 1
                if self._auto_fails[key] < 3:
                    self._auto_tried.discard(key)
                log.warning("Auftrag: Ergebnis automatisch prüfen: %s", exc)
        return done

    # ── für die Oberfläche ───────────────────────────────────────────────
    def message(self, available: bool, problem: str = "") -> dict[str, Any]:
        m = self.missions.current()
        course = self.course()
        runs = self.trainer.runs() if self.trainer is not None else []
        tests = list((m or {}).get("tests", []))
        return {
            "type": "parcours", "verfuegbar": available, "problem": problem,
            "auftrag": {**{k: m.get(k) for k in ("id", "ziel", "erstellt", "vorschlag", "lauf")}, "laeufe": linked(m)} if m else None,
            "schritte": steps(m, runs), "tests": tests[::-1],
            "parcours": course.summary() if course else None, "welt": course.world() if course else None,
            "job": self.job, "quellen": self.sources() if available else [],
            "vorlagen": list(C.PRESETS), "elemente": {k: [{"name": n, "min": lo, "max": hi, "standard": d}
                                                         for n, lo, hi, d in v] for k, v in C.PARAMS.items()},
            "titel": C.LABEL,
            "verlauf": [{"id": x["id"], "ziel": x["ziel"], "erstellt": x["erstellt"]} for x in self.missions.data["liste"][::-1][:8]],
        }
