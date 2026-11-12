"""Akrobatik-Dienst: Gliederpuppe prüfen, üben lassen, Fähigkeit je Übung merken.

Die Rechnung steckt in physics/acrobatics.py (MuJoCo). Hier: ein Prüf-Exemplar für schnelle Antworten beim
Ziehen, ein eigenes Exemplar je Übungslauf (Hintergrund-Thread), und das Fähigkeitsheft `akrobatik.json` im
Datenordner (beste Fähigkeit je Übung, Verlauf, gespeicherte Haltungen).
"""
from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path
from typing import Any

from .api import JOINT_NAMES
from .joints import LABELS

MAX_POSES = 30
MAX_HISTORY = 60
NAME_MAX = 40


def available() -> tuple[bool, str]:
    import importlib.util

    if importlib.util.find_spec("mujoco") is None or importlib.util.find_spec("numpy") is None:
        return False, "MuJoCo ist nicht installiert – unter Einstellungen → Körper „Echte Physik“ einrichten."
    return True, ""


def _clean_pose(raw: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    if isinstance(raw, dict):
        for n in JOINT_NAMES:
            v = raw.get(n)
            if isinstance(v, (int, float)) and math.isfinite(v) and abs(v) < 4:
                out[n] = float(v)
    return out


def sichere_pose(acro: Any, pose: dict[str, float], mindest: float = 0.35) -> dict[str, float] | None:
    """Die stärkste Fassung einer Haltung, die sicher steht: zwischen Grundstellung (0) und Haltung (1) wird der größte
    Anteil gesucht, bei dem der Schwerpunkt grün über der Stützfläche liegt und die Halteprobe nicht kippt."""
    # „grün“ entscheidet die Physik selbst (Ampel aus `place`) – so braucht diese Funktion kein MuJoCo zum Importieren
    # (Fund 12.11.: die Prüfung bei GitHub läuft ohne MuJoCo und schlug seit 0.38.42 fehl)
    q0, q1 = acro.pose_from({}), acro.pose_from(_clean_pose(pose))

    def steht(a: float) -> bool:
        q = q0 + a * (q1 - q0)
        lage = acro.place(q)
        return lage["ampel"] == "gruen" and not lage["nicht_nur_fuesse"] and acro.hold(q, 1.0)["steht"]

    if steht(1.0):
        return dict(pose)
    lo, hi = 0.0, 1.0
    for _ in range(6):
        mitte = (lo + hi) / 2
        lo, hi = (mitte, hi) if steht(mitte) else (lo, mitte)
    return acro.as_dict(q0 + lo * (q1 - q0)) if lo >= mindest else None


class AcrobaticsService:
    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "akrobatik.json"
        self._lock = threading.Lock()
        self._book_lock = threading.Lock()      # Heft: Übungs-Thread und Server schreiben beide
        self._acro = None
        self.job: dict[str, Any] = {}
        self._cancel = threading.Event()
        self.book = self._load()

    # ── Heft ─────────────────────────────────────────────────────────────
    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("uebungen", {})
                data.setdefault("posen", {})
                return data
        except (OSError, ValueError):
            pass
        return {"uebungen": {}, "posen": {}}

    def _save(self) -> None:
        """Nur mit self._book_lock aufrufen."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.stem}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(self.book, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def save_pose(self, name: str, pose: Any) -> dict[str, Any]:
        name = " ".join(str(name or "").replace("/", " ").replace("\\", " ").split())[:NAME_MAX]
        if not name:
            raise ValueError("Bitte einen Namen für die Haltung angeben.")
        clean = _clean_pose(pose)
        if not clean:
            raise ValueError("Die Haltung ist leer.")
        with self._book_lock:
            poses = self.book["posen"]
            if name not in poses and len(poses) >= MAX_POSES:
                raise ValueError(f"Höchstens {MAX_POSES} Haltungen – erst eine löschen.")
            poses[name] = clean
            self._save()
        return {"name": name}

    def delete_pose(self, name: str) -> bool:
        with self._book_lock:
            if self.book["posen"].pop(name, None) is None:
                return False
            self._save()
        return True

    # ── Prüfen ───────────────────────────────────────────────────────────
    def _live(self):
        if self._acro is None:
            from .physics.acrobatics import Acrobat

            self._acro = Acrobat()
        return self._acro

    def overview(self) -> dict[str, Any]:
        ok, why = available()
        with self._book_lock:
            book = json.loads(json.dumps(self.book))
        res: dict[str, Any] = {"verfuegbar": ok, "grund": why, "posen": book["posen"], "job": self.job}
        if not ok:
            return res
        from .physics.acrobatics import ACTUATORS, EXERCISES

        with self._lock:
            acro = self._live()
            res["gelenke"] = [{"name": n, "label": LABELS.get(n, n), "min": round(float(acro.lo[i]), 3),
                               "max": round(float(acro.hi[i]), 3)} for i, n in enumerate(ACTUATORS)]
            res["grundstellung"] = acro.as_dict(acro.pose_from({}))
        res["uebungen"] = []
        for ex in EXERCISES.values():
            mine = book["uebungen"].get(ex.id, {})
            res["uebungen"].append({"id": ex.id, "name": ex.name, "beschreibung": ex.beschreibung,
                                    "beste": mine.get("beste"), "start": mine.get("start"),
                                    "verlauf": mine.get("verlauf", []),
                                    "pose": mine.get("pose")})
        return res

    def tanzposen(self) -> dict[str, dict[str, float]]:
        """Haltungen für den Tanz (seit 0.38.42, Maintainer: „bei Tanz nimmt Microduck teilweise Posen, die in der Physik
        noch zum Umfallen führen“). Jede gespeicherte Haltung wird in der unsichtbaren Physik-Welt geprüft: Steht sie
        nicht sicher (Reserve unter der grünen Grenze oder sie kippt in der Halteprobe), wird sie Richtung Grundstellung
        abgeschwächt, bis sie steht. Geht das nur fast bis zur Grundstellung, fällt sie aus dem Tanz – dort deutet die
        Ente sie dann nur an. Ohne MuJoCo bleiben die Haltungen, wie sie sind (dort kann nichts umfallen)."""
        with self._book_lock:
            posen = {k: dict(v) for k, v in self.book["posen"].items()}
        if not posen or not available()[0]:
            return posen
        cache = getattr(self, "_tanz_cache", None)
        if cache is None:
            cache = self._tanz_cache = {}
        out: dict[str, dict[str, float]] = {}
        with self._lock:
            acro = self._live()
            for name, pose in posen.items():
                schluessel = json.dumps(pose, sort_keys=True)
                if schluessel not in cache:
                    cache[schluessel] = sichere_pose(acro, pose)
                if cache[schluessel] is not None:
                    out[name] = cache[schluessel]
        return out

    def check(self, pose: Any) -> dict[str, Any]:
        with self._lock:
            acro = self._live()
            return acro.place(acro.pose_from(_clean_pose(pose)))

    def probe(self, pose: Any) -> dict[str, Any]:
        with self._lock:
            acro = self._live()
            return acro.hold(acro.pose_from(_clean_pose(pose)))

    # ── Üben (Hintergrund) ───────────────────────────────────────────────
    def start_practice(self, pose: Any, exercise: str) -> dict[str, Any]:
        from .physics.acrobatics import EXERCISES

        if exercise not in EXERCISES:
            raise ValueError("Unbekannte Übung.")
        if self.job.get("laeuft"):
            raise RuntimeError("Sie übt schon.")
        clean = _clean_pose(pose)
        self._cancel.clear()
        self.job = {"laeuft": True, "uebung": exercise, "generation": 0, "von": 0, "faehigkeit": None,
                    "pose": None, "verlauf": [], "ergebnis": None, "fehler": None, "start": time.time()}
        threading.Thread(target=self._run, args=(clean, exercise), daemon=True, name="akrobatik").start()
        return self.job

    def cancel(self) -> None:
        self._cancel.set()

    def _run(self, pose: dict[str, float], exercise: str) -> None:
        from .physics.acrobatics import EXERCISES, Acrobat

        try:
            acro = Acrobat()                  # eigene Welt – Prüfen beim Ziehen bleibt flüssig

            def step(p: dict[str, Any]) -> None:
                self.job.update(generation=p["generation"], von=p["von"], faehigkeit=p["faehigkeit"], pose=p["pose"])
                self.job["verlauf"] = self.job["verlauf"] + [p["faehigkeit"]]

            res = acro.practice(acro.pose_from(pose), EXERCISES[exercise], on_step=step,
                                stop=self._cancel.is_set)
            cancelled = self._cancel.is_set()
            if not cancelled:                  # abgebrochene Runden zählen nicht als Fähigkeit
                self._remember(exercise, res)
            self.job.update(laeuft=False, ergebnis=res, abgebrochen=cancelled)
        except Exception as exc:
            self.job.update(laeuft=False, fehler=f"{type(exc).__name__}: {exc}")

    def _remember(self, exercise: str, res: dict[str, Any]) -> None:
        with self._book_lock:
            self._remember_locked(exercise, res)

    def _remember_locked(self, exercise: str, res: dict[str, Any]) -> None:
        entry = self.book["uebungen"].setdefault(exercise, {"beste": None, "verlauf": []})
        score = res["faehigkeit"]
        if entry.get("start") is None and res.get("verlauf"):
            entry["start"] = res["verlauf"][0]["faehigkeit"]      # so gut war sie vor dem allerersten Üben
        entry["verlauf"] = (entry.get("verlauf", []) + [{"zeit": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                                          "faehigkeit": score}])[-MAX_HISTORY:]
        if entry.get("beste") is None or score > entry["beste"]:
            entry["beste"] = score
            entry["pose"] = res["pose"]
        self._save()
