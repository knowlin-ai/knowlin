"""Bello lernt laufen – der Dienst dazu (seit 0.43): lernt im Hintergrund, merkt sich das Ergebnis, gibt es dem Körper.

Das Lernen selbst steckt in `physics/bello.py` (MuJoCo-Modell, Evolutionsstrategie, Prüfung „nie schlechter“). Hier:

- `starten()` lernt in einem eigenen Faden (ein Rechenkern, etwa eine halbe Minute), `abbrechen()` hält ihn an.
- Ist das Ergebnis besser, landet es in `bello_gang.json` im Datenordner – Bello hat dann die Gangart „Gelernt“.
  Ist es nicht besser, bleibt alles, wie es war; der Bericht sagt es trotzdem.
- `vergessen()` löscht die gelernte Gangart wieder.

Nur Zahlen (Parameter der Gangart, Tempo, Neigung) – nichts über Personen, nichts geht ins Netz.
"""

from __future__ import annotations

import importlib.util
import json
import threading
import time
from pathlib import Path
from typing import Any

DATEI = "bello_gang.json"


def physik_da() -> bool:
    return importlib.util.find_spec("mujoco") is not None and importlib.util.find_spec("numpy") is not None


def laden(root: Path) -> dict[str, Any] | None:
    """Die gelernte Gangart aus dem Datenordner – oder None (keine, kaputt)."""
    try:
        d = json.loads((Path(root) / DATEI).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get("parameter"), dict) or not isinstance(d.get("tempo"), (int, float)):
        return None
    return d


class BelloSchule:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._lock = threading.Lock()
        self._faden: threading.Thread | None = None
        self._stopp = threading.Event()
        self._stand: dict[str, Any] = {"laeuft": False}
        self.bericht: dict[str, Any] | None = None

    # ── Abfragen ─────────────────────────────────────────────────────────
    def gangart(self) -> dict[str, Any] | None:
        return laden(self.root)

    def stand(self) -> dict[str, Any]:
        with self._lock:
            out = dict(self._stand)
        g = self.gangart()
        out |= {"physik": physik_da(), "gelernt": g is not None, "bericht": self.bericht or (g or {}).get("bericht")}
        if g:
            out["tempo"] = g["tempo"]
        return out

    # ── Lernen ───────────────────────────────────────────────────────────
    def starten(self, runden: int = 30, bei_fertig: Any = None) -> dict[str, Any]:
        if not physik_da():
            return {"ok": False, "fehler": "Dafür braucht es die Physik (MuJoCo) – unter Lernen → Training einrichten."}
        with self._lock:
            if self._stand.get("laeuft"):
                return {"ok": False, "fehler": "Bello lernt gerade schon."}
            self._stand = {"laeuft": True, "runde": 0, "runden": int(runden), "ab": time.time()}
        self._stopp.clear()
        start = (self.gangart() or {}).get("parameter")      # weiter ab dem, was er schon kann
        self._faden = threading.Thread(target=self._lernen, args=(int(runden), start, bei_fertig), daemon=True,
                                       name="bello-lernt")
        self._faden.start()
        return {"ok": True}

    def abbrechen(self) -> bool:
        self._stopp.set()
        return bool(self._stand.get("laeuft"))

    def vergessen(self) -> bool:
        try:
            (self.root / DATEI).unlink()
            self.bericht = None
            return True
        except OSError:
            return False

    def _melden(self, m: dict[str, Any]) -> None:
        with self._lock:
            self._stand |= {"runde": m["runde"], "punkte": m["punkte"]}

    def _lernen(self, runden: int, start: dict[str, float] | None, bei_fertig: Any) -> None:
        from .physics import bello as B

        try:
            r = B.lernen(runden=runden, start=start, melden=self._melden, abbrechen=self._stopp.is_set,
                         seed=int(time.time()) % 10_000)
            r["abgebrochen"] = self._stopp.is_set()
            self.bericht = {k: r[k] for k in ("gelernt", "vorher", "nachher", "runden", "dauer_s", "abgebrochen")}
            if r["gelernt"] and not r["abgebrochen"]:
                self.root.mkdir(parents=True, exist_ok=True)
                tmp = self.root / (DATEI + ".tmp")
                tmp.write_text(json.dumps({"parameter": r["parameter"], "tempo": min(r["nachher"]["tempo"], B.TEMPO_GRENZE),
                                           "bericht": self.bericht, "wann": time.strftime("%Y-%m-%dT%H:%M")},
                                          ensure_ascii=False, indent=1), encoding="utf-8")
                tmp.replace(self.root / DATEI)
        except Exception as exc:  # noqa: BLE001 – ehrlich melden statt still abbrechen
            self.bericht = {"gelernt": False, "fehler": f"{type(exc).__name__}: {exc}"}
        finally:
            with self._lock:
                self._stand = {"laeuft": False}
            if callable(bei_fertig):
                bei_fertig(self.gangart())
