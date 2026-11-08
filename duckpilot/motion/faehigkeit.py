"""Fähigkeiten-Schnittstelle (seit 0.38, Bauprinzip aus dem Suite-Gedanken vom 1.11.).

Eine Fähigkeit ist ein Verhalten mit festem Ablauf: **Vorbedingung** (kann dieser Körper das, passt die Lage?),
**Ausführen**, **Ergebnisprüfung** (hat es wirklich geklappt?), **Plan B** (nachjustieren, neuer Versuch) und ein
ehrlicher **Bericht**. Was ein Körper nicht kann, lehnt die Fähigkeit sauber ab, statt so zu tun als ob – das ist die
Grundlage dafür, dass Reachy Mini (0.38.1) und weitere Module dieselben Befehle verstehen.

Apportieren, gezielter Schuss, Purzelbaum und Erkunden bauen darauf auf. Unterklassen setzen `faehigkeit` (Name) und
`braucht` (Körper-Eigenschaften aus `DuckBackend.eigenschaften()`), überschreiben bei Bedarf `vorbedingung(st)` und
beenden mit `erfolg()`, `fehlschlag()` oder `ablehnen()`. Plan-B-Schritte kommen mit `plan_b()` ins Protokoll.
"""

from __future__ import annotations

from typing import Any

from .engine import Behavior, Command

ERGEBNISSE = ("erfolg", "fehlschlag", "abgelehnt", "abgebrochen")


def eigenschaften(engine: Any) -> frozenset[str]:
    be = getattr(engine, "backend", None)
    fn = getattr(be, "eigenschaften", None)
    return frozenset(fn()) if callable(fn) else frozenset()


class Faehigkeit(Behavior):
    faehigkeit = ""                         # Name im Bericht und im Katalog („apportieren“, „schiessen“ …)
    braucht: frozenset[str] = frozenset()   # z. B. {"beine", "schnabel", "tiefensensor"}
    braucht_skill: tuple[str, ...] = ()     # gelernte Bewegungen des Körpers (seit 0.38.4), z. B. („roulade“,)

    def __init__(self) -> None:
        super().__init__()
        self.inner: Behavior | None = None
        self.protokoll: list[str] = []
        self.ergebnis_art = ""
        self._geprueft = False

    # ── Bausteine ────────────────────────────────────────────────────────
    def _use(self, b: Behavior) -> None:
        b.engine = self.engine
        self.inner = b

    def vorbedingung(self, st) -> str | None:
        """Grund, warum es gerade nicht geht – oder None. (Lage, nicht Körper: das prüft `braucht`.)"""
        return None

    def plan_b(self, text: str) -> None:
        self.protokoll.append(text)

    def erfolg(self, text: str) -> Command | None:
        self.ergebnis_art = "erfolg"
        return self.finish(text)

    def fehlschlag(self, text: str) -> Command | None:
        self.failed = True
        self.ergebnis_art = "fehlschlag"
        return self.finish(text)

    def ablehnen(self, text: str) -> Command | None:
        self.failed = True
        self.ergebnis_art = "abgelehnt"
        return self.finish(text)

    # ── Ablauf ───────────────────────────────────────────────────────────
    def _step(self, st, dt):
        if not self._geprueft:
            self._geprueft = True
            fehlt = sorted(self.braucht - eigenschaften(self.engine)) if self.engine is not None else []
            if fehlt:
                return self.ablehnen(f"Das kann dieser Körper nicht (fehlt: {', '.join(fehlt)})")
            be = getattr(self.engine, "backend", None)
            skills = be.skills() if be is not None and callable(getattr(be, "skills", None)) else []
            ohne = [s for s in self.braucht_skill if s not in skills]
            if skills and ohne:                                 # leere Liste = Körper sagt nichts dazu
                return self.ablehnen(f"Diese gelernte Bewegung hat der Körper nicht (fehlt: {', '.join(ohne)})")
            grund = self.vorbedingung(st)
            if grund:
                return self.ablehnen(grund)
        out = super()._step(st, dt)
        if self.done and not self.ergebnis_art:      # ältere Wege über finish()/failed
            self.ergebnis_art = "fehlschlag" if getattr(self, "failed", False) else "erfolg"
        return out

    def on_stop(self) -> None:
        if not self.done and not self.ergebnis_art:
            self.ergebnis_art = "abgebrochen"
        super().on_stop()

    def bericht(self) -> dict[str, Any]:
        """Einheitliches Ergebnis für Claude, Oberfläche und Tests."""
        out: dict[str, Any] = {"faehigkeit": self.faehigkeit or self.name, "ergebnis": self.ergebnis_art or "läuft",
                               "text": self.result, "plan_b": list(self.protokoll)}
        if hasattr(self, "versuche"):
            out["versuche"] = self.versuche
        info = getattr(self, "info", None)
        if callable(info):
            try:
                out["einzelheiten"] = info()
            except Exception:  # noqa: BLE001 – der Bericht darf nie scheitern
                pass
        return out
