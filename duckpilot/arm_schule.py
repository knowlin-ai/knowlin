"""Ari lernt durch Vormachen – der Ablauf in der laufenden App (seit 0.38.64, Stufe A; Maintainer: „A, dann B“).

Die Rechnung steckt in `arm_lernen.py`, das Paket für LeRobot in `arm_export.py`. Hier:

- **Aufnehmen** (A1): Solange die Aufnahme läuft, wird alle `SCHRITT_S` festgehalten, was Ari sieht und wohin deine
  Hand ihn gerade führt (`Runtime._mentor_ziel`, gesetzt beim Vormachen). Landet der Würfel in der Kiste, ist das
  Beispiel fertig und wird gespeichert; abgebrochene Versuche zählen nicht.
- **Lernen** (A2): deine Beispiele, auf Wunsch ergänzt um Beispiele vom Lehrer, in einem Hintergrund-Thread; danach
  prüft Ari in zehn unsichtbaren Versuchen, wie oft er es schafft.
- **Ausprobieren** (A3): das gelernte Netz steuert Ari im Simulator, Takt für Takt über `nachmachen` – dieselbe
  Wegprüfung wie beim Vormachen. Jeder Stopp und der Not-Aus beenden es sofort (`engine.stopped_at`/`estop_at`).
- **Export** (A4): ZIP für LeRobot.

Nur im Simulator: Am echten Arm kennt Knowlin die Lage der Würfel nicht (dafür bräuchte es Kamerabilder).
Gespeichert wird unter `data_dir()/ari_lernen/` – nur Zahlen aus dem Simulator, keine Bilder, nichts über Personen.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from . import arm_lernen as L
from . import settings as S
from .aio import spawn

if TYPE_CHECKING:  # pragma: no cover
    from .server.runtime import Runtime

log = logging.getLogger(__name__)

NUR_SIM = "Ari lernt im Simulator – am echten Arm kennt Knowlin die Lage der Würfel nicht."
AUFNAHME_MAX_S = 180.0              # länger zählt eine Aufnahme nicht
MIN_TAKTE = 5                       # kürzere Beispiele sind keine
LEHRER_N = 30                       # so viele Beispiele steuert der Lehrer bei
VERSUCHE = 10                       # so oft probiert Ari nach dem Lernen unsichtbar


def _aufgabe_von(zeile: str) -> str | None:
    try:
        return json.loads(zeile).get("aufgabe")
    except (ValueError, AttributeError):
        return None


def _stamm(name: str, endung: str) -> tuple[str, str]:
    adj, _, nomen = name.partition(" ")
    return (adj[: -len(endung)] if adj.endswith(endung) else adj), nomen


def wuerfel_nom(name: str) -> str:
    """„roter Würfel“ → „der rote Würfel“."""
    s, n = _stamm(name, "er")
    return f"der {s}e {n}" if n else name


def wuerfel_akk(name: str) -> str:
    """„roter Würfel“ → „den roten Würfel“."""
    s, n = _stamm(name, "er")
    return f"den {s}en {n}" if n else name


def kiste_dativ(name: str) -> str:
    """„linke Kiste“ → „der linken Kiste“."""
    s, n = _stamm(name, "e")
    return f"der {s}en {n}" if n else name


def _datei_name(text: str) -> str:
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    return "".join(c for c in text.lower() if c.isascii() and (c.isalnum() or c == "-"))


class ArmSchule:
    def __init__(self, rt: "Runtime") -> None:
        self.rt = rt
        self.aufgabe = L.aufgabe("roter Würfel", "linke Kiste")
        self.taetigkeit: str | None = None          # "aufnahme" | "lernen" | "ausprobieren"
        self.meldung = ""
        self.fortschritt = ""
        self._netz: L.Netz | None = None
        self._meta: dict[str, Any] | None = None
        self._laden()

    # ── Ablage ───────────────────────────────────────────────────────────
    @property
    def ordner(self):
        return S.data_dir() / "ari_lernen"

    def _laden(self) -> None:
        pfad = self.ordner / "netz.npz"
        if pfad.exists():
            try:
                self._netz, self._meta = L.Netz.laden(pfad)
            except Exception as exc:  # noqa: BLE001 – kaputte Datei: neu lernen
                log.warning("gelerntes Netz nicht lesbar: %s", exc)

    def _lesen(self, datei: str) -> list[dict[str, Any]]:
        pfad = self.ordner / datei
        if not pfad.exists():
            return []
        out = []
        for zeile in pfad.read_text(encoding="utf-8").splitlines():
            try:
                b = json.loads(zeile)
            except ValueError:
                continue
            if b.get("aufgabe") == self.aufgabe["name"]:
                out.append(b)
        return out

    def _anhaengen(self, datei: str, beispiele: list[dict[str, Any]], ersetzen: bool = False) -> None:
        self.ordner.mkdir(parents=True, exist_ok=True)
        pfad = self.ordner / datei
        alt = [] if not pfad.exists() else [z for z in pfad.read_text(encoding="utf-8").splitlines() if z.strip()]
        if ersetzen:      # die Beispiele dieser Aufgabe ersetzen, andere behalten
            alt = [z for z in alt if _aufgabe_von(z) != self.aufgabe["name"]]
        neu = [json.dumps(b, ensure_ascii=False) for b in beispiele]
        pfad.write_text("\n".join([*alt, *neu]) + "\n", encoding="utf-8")

    # ── was geht ─────────────────────────────────────────────────────────
    @property
    def body(self) -> Any:
        return self.rt.backend

    def grund(self) -> str | None:
        if not (hasattr(self.body, "werkbank") and hasattr(self.body, "nachmachen")):
            return NUR_SIM
        return None

    def _wahl(self) -> dict[str, list[str]]:
        wb = getattr(self.body, "werkbank", None)
        if wb is None:
            return {"wuerfel": [], "kisten": []}
        return {"wuerfel": [d["name"] for d in wb.dinge if not d.get("feld")], "kisten": [k["name"] for k in wb.kisten]}

    def status(self) -> dict[str, Any]:
        gelernt = self._meta if self._meta and self._meta.get("aufgabe") == self.aufgabe["name"] else None
        return {"grund": self.grund(), "aufgabe": {"wuerfel": self.aufgabe["wuerfel"], "kiste": self.aufgabe["kiste"]},
                "wahl": self._wahl(), "beispiele": len(self._lesen("beispiele.jsonl")), "taetigkeit": self.taetigkeit,
                "meldung": self.meldung, "fortschritt": self.fortschritt, "gelernt": gelernt}

    def _frei(self) -> dict[str, Any] | None:
        if (g := self.grund()) is not None:
            return {"ok": False, "fehler": g}
        if self.taetigkeit is not None:
            return {"ok": False, "fehler": "Ari ist gerade beschäftigt – erst beenden"}
        return None

    # ── Aufgabe ──────────────────────────────────────────────────────────
    def aufgabe_setzen(self, wuerfel: str, kiste: str) -> dict[str, Any]:
        if (f := self._frei()) is not None:
            return f
        wahl = self._wahl()
        if wuerfel not in wahl["wuerfel"] or kiste not in wahl["kisten"]:
            return {"ok": False, "fehler": "Diesen Würfel oder diese Kiste gibt es auf der Werkbank nicht"}
        self.aufgabe = L.aufgabe(wuerfel, kiste)
        self.meldung = ""
        return {"ok": True, **self.status()}

    def neu_legen(self) -> dict[str, Any]:
        """Würfel an ihre Plätze, den Ziel-Würfel an eine zufällige freie Stelle – für das nächste Beispiel."""
        if (f := self._frei()) is not None:
            return f
        wb = self.body.werkbank
        wb.zuruecksetzen()
        L.zufaellige_lage(self.body, self.aufgabe, random.Random())
        wer = wuerfel_nom(self.aufgabe["wuerfel"])
        self.meldung = f"{wer[:1].upper()}{wer[1:]} liegt neu."
        return {"ok": True, **self.status()}

    # ── Aufnehmen (A1) ───────────────────────────────────────────────────
    def aufnehmen(self) -> dict[str, Any]:
        if (f := self._frei()) is not None:
            return f
        self.taetigkeit = "aufnahme"
        self.meldung = (f"Aufnahme läuft – führe Ari mit deiner Hand: {wuerfel_akk(self.aufgabe['wuerfel'])} greifen, "
                        f"in die {self.aufgabe['kiste']} legen.")
        spawn(self._aufnahme())
        return {"ok": True, **self.status()}

    def _stopp_marke(self) -> tuple[float, float]:
        eng = self.rt.engine
        return float(getattr(eng, "estop_at", 0.0)), float(getattr(eng, "stopped_at", 0.0))

    async def _aufnahme(self) -> None:
        a, be = dict(self.aufgabe), self.body
        start, marke, takte = time.monotonic(), self._stopp_marke(), []
        try:
            while self.taetigkeit == "aufnahme":
                await asyncio.sleep(L.SCHRITT_S)
                if self._stopp_marke()[0] != marke[0]:
                    self.meldung = "Not-Aus – die Aufnahme ist verworfen."
                    return
                m = getattr(self.rt, "_mentor_ziel", None)
                if m and time.monotonic() - m[0] < 0.5:
                    takte.append(L.schritt_daten(L.beobachtung(be.gelenke, be.werkbank, a), m[1], be.gelenke))
                if L.geschafft(be.werkbank, a):
                    if len(takte) < MIN_TAKTE:
                        self.meldung = "Zu kurz – das zählt nicht. „Neu legen“ und noch einmal."
                        return
                    self._anhaengen("beispiele.jsonl", [{"aufgabe": a["name"], "von": "mensch", "schritte": takte,
                                                          "wann": datetime.now().isoformat(timespec="seconds")}])
                    self.meldung = (f"Beispiel gespeichert ({len(self._lesen('beispiele.jsonl'))}). "
                                    "„Neu legen“ für das nächste oder „Lernen“.")
                    return
                if time.monotonic() - start > AUFNAHME_MAX_S:
                    self.meldung = "Zu lange – die Aufnahme ist verworfen."
                    return
            self.meldung = "Aufnahme beendet – ohne Würfel in der Kiste zählt sie nicht."
        finally:
            if self.taetigkeit == "aufnahme":
                self.taetigkeit = None

    def abbrechen(self) -> dict[str, Any]:
        if self.taetigkeit in ("aufnahme", "ausprobieren"):
            self.taetigkeit = None
        return {"ok": True, **self.status()}

    # ── Lernen (A2) ──────────────────────────────────────────────────────
    def lernen(self, mit_lehrer: bool = True) -> dict[str, Any]:
        if (f := self._frei()) is not None:
            return f
        eigene = self._lesen("beispiele.jsonl")
        if not eigene and not mit_lehrer:
            return {"ok": False, "fehler": "Noch keine Beispiele – erst vormachen oder den Lehrer helfen lassen"}
        self.taetigkeit = "lernen"
        self.meldung, self.fortschritt = "Ari lernt …", ""
        spawn(self._lernen(eigene, mit_lehrer))
        return {"ok": True, **self.status()}

    async def _lernen(self, eigene: list[dict[str, Any]], mit_lehrer: bool) -> None:
        a = dict(self.aufgabe)
        try:
            netz, meta, lehrer = await asyncio.to_thread(self._rechnen, a, eigene, mit_lehrer)
            netz.speichern(self.ordner / "netz.npz", meta)
            if lehrer:
                self._anhaengen("lehrer.jsonl", lehrer, ersetzen=True)
            self._netz, self._meta = netz, meta
            self.meldung = f"Gelernt – im Test schafft Ari es {meta['geschafft']} von {meta['versuche']} Mal."
        except Exception as exc:  # noqa: BLE001
            log.exception("Lernen fehlgeschlagen")
            self.meldung = f"Lernen fehlgeschlagen: {exc}"
        finally:
            self.taetigkeit, self.fortschritt = None, ""

    def _rechnen(self, a: dict[str, str], eigene: list[dict[str, Any]], mit_lehrer: bool):
        from . import __version__

        lehrer: list[dict[str, Any]] = []
        if mit_lehrer:
            self.fortschritt = "Der Lehrer macht Beispiele vor …"
            lehrer = [{**b, "aufgabe": a["name"]} for b in L.lehrer_beispiele(a, n=LEHRER_N, seed=1)]
        X, Y = L.daten([*eigene, *lehrer])
        if len(X) < MIN_TAKTE:
            raise ValueError("zu wenige Takte")
        netz = L.Netz(0)
        netz.lernen(X, Y, epochen=400, bescheid=lambda ep, v: setattr(self, "fortschritt", f"Runde {ep + 1} von 400"))
        self.fortschritt = "Ari probiert es zehnmal aus …"
        ok = L.pruefen(netz, a, n=VERSUCHE)
        meta = {"aufgabe": a["name"], "wuerfel": a["wuerfel"], "kiste": a["kiste"], "geschafft": ok,
                "versuche": VERSUCHE, "mensch": len(eigene), "lehrer": len(lehrer), "takte": int(len(X)),
                "wann": datetime.now().isoformat(timespec="seconds"), "version": __version__}
        return netz, meta, lehrer

    # ── Ausprobieren (A3) ────────────────────────────────────────────────
    def ausprobieren(self) -> dict[str, Any]:
        if (f := self._frei()) is not None:
            return f
        if self._netz is None or not self._meta or self._meta.get("aufgabe") != self.aufgabe["name"]:
            return {"ok": False, "fehler": "Für diese Aufgabe hat Ari noch nichts gelernt"}
        if not getattr(self.body, "powered", True):
            return {"ok": False, "fehler": "Motoren sind aus – erst aufwecken"}
        self.taetigkeit = "ausprobieren"
        self.meldung = "Ari probiert es selbst …"
        spawn(self._ausprobieren(self._netz))
        return {"ok": True, **self.status()}

    async def _ausprobieren(self, netz: L.Netz) -> None:
        a, be, marke = dict(self.aufgabe), self.body, self._stopp_marke()
        try:
            for _ in range(int(L.DAUER_S / L.SCHRITT_S)):
                if self.taetigkeit != "ausprobieren":
                    self.meldung = "Abgebrochen."
                    return
                if self._stopp_marke() != marke:          # Stopp oder Not-Aus: sofort aufhören
                    self.meldung = "Angehalten."
                    return
                obs = L.beobachtung(be.gelenke, be.werkbank, a)
                r = await be.nachmachen(L.aktion_zu_ziel(obs, netz(obs)))
                if not r.accepted and not getattr(be, "powered", True):
                    self.meldung = r.reason
                    return
                self.rt.engine.kontakt("Lernen")
                if (alltag := getattr(self.rt, "alltag", None)) is not None:
                    alltag.touch()
                await asyncio.sleep(L.SCHRITT_S)
                if L.geschafft(be.werkbank, a):
                    self.meldung = f"Geschafft – {wuerfel_nom(a['wuerfel'])} liegt in {kiste_dativ(a['kiste'])}."
                    return
            self.meldung = "Nicht geschafft – mehr Beispiele vormachen und neu lernen."
        finally:
            if self.taetigkeit == "ausprobieren":
                self.taetigkeit = None

    # ── Export (A4) ──────────────────────────────────────────────────────
    def export(self) -> tuple[bytes, str] | None:
        from . import __version__
        from .arm_export import paket

        beispiele = [*self._lesen("beispiele.jsonl"), *self._lesen("lehrer.jsonl")]
        if not beispiele:
            return None
        name = "ari-" + "-".join(_datei_name(w.split()[0]) for w in (self.aufgabe["wuerfel"], self.aufgabe["kiste"]))
        return paket(beispiele, self.aufgabe, __version__), f"{name}-lerobot.zip"
