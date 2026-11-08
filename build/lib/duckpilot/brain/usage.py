"""Tokenzähler: was die Gespräche mit Claude verbrauchen – pro Tag, mit Cache-Anteil.

Liest die `usage`-Felder jeder Antwort (Eingabe, Cache schreiben/lesen, Ausgabe) und legt Tagessummen in
`verbrauch.json` neben den Einstellungen ab. Keine Inhalte, nur Zahlen. Die Oberfläche zeigt daraus, wie viel
gecacht gelesen wurde und wie viele Befehle ohne Claude erledigt wurden.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

FIELDS = ("anfragen", "eingabe", "cache_schreiben", "cache_lesen", "ausgabe", "ohne_claude")
KEEP_DAYS = 60


def _get(usage: Any, name: str) -> int:
    v = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
    return int(v or 0)


class UsageMeter:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.days: dict[str, dict[str, int]] = {}
        self._dirty = False
        self._saved_at = 0.0
        if path and path.exists():
            try:
                self.days = {k: {f: int(v.get(f, 0)) for f in FIELDS} for k, v in json.loads(path.read_text("utf-8")).items()}
            except (OSError, ValueError, AttributeError):
                log.warning("Verbrauchsdatei unlesbar – fange neu an")

    def _today(self) -> dict[str, int]:
        key = time.strftime("%Y-%m-%d")
        if key not in self.days:
            self.days[key] = dict.fromkeys(FIELDS, 0)
            for old in sorted(self.days)[:-KEEP_DAYS]:
                del self.days[old]
        return self.days[key]

    def add(self, usage: Any) -> None:
        """Eine Antwort von Claude zählen (usage aus der API, Objekt oder dict)."""
        d = self._today()
        d["anfragen"] += 1
        d["eingabe"] += _get(usage, "input_tokens")
        d["cache_schreiben"] += _get(usage, "cache_creation_input_tokens")
        d["cache_lesen"] += _get(usage, "cache_read_input_tokens")
        d["ausgabe"] += _get(usage, "output_tokens")
        self._changed()

    def local(self) -> None:
        """Ein Befehl, der ohne Claude erledigt wurde (Schnellbefehl)."""
        self._today()["ohne_claude"] += 1
        self._changed()

    def _changed(self) -> None:
        self._dirty = True
        if time.monotonic() - self._saved_at > 30:     # nicht bei jeder Antwort auf die Platte
            self.save()

    def save(self) -> None:
        if not (self.path and self._dirty):
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.days, indent=1), "utf-8")
            tmp.replace(self.path)
            self._dirty = False
            self._saved_at = time.monotonic()
        except OSError as exc:
            log.warning("Verbrauch nicht gespeichert: %s", exc)

    def summary(self, days: int = 7) -> dict[str, Any]:
        keys = sorted(self.days)[-days:]
        total = dict.fromkeys(FIELDS, 0)
        for k in keys:
            for f in FIELDS:
                total[f] += self.days[k][f]
        prompt = total["eingabe"] + total["cache_schreiben"] + total["cache_lesen"]
        return {
            "heute": dict(self._today()),
            "tage": days,
            "summe": total,
            "cache_anteil": round(total["cache_lesen"] / prompt, 3) if prompt else None,
            "pro_anfrage": round((prompt + total["ausgabe"]) / total["anfragen"]) if total["anfragen"] else None,
        }
