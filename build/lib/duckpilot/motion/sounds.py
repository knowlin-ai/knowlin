"""Die gerenderten Gesten-Laute (tools/render_gestures.py): welche Dateien es je Geste gibt und
wie weit der Schnabel dabei offen ist."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

INDEX = Path(__file__).resolve().parent.parent / "server" / "static" / "sounds" / "gesten" / "index.json"
PREFIX = "gesten/"


@lru_cache(maxsize=1)
def _index() -> dict[str, Any]:
    try:
        return json.loads(INDEX.read_text(encoding="utf-8")).get("gesten", {})
    except (OSError, ValueError):
        return {}


def clips(name: str) -> list[str]:
    """Alle Varianten einer Geste als Klang-Namen, z. B. ['gesten/freude_0', …]; leer, wenn nicht gerendert."""
    entry = _index().get(name)
    return [PREFIX + f for f in entry["dateien"]] if entry else []


def mouth(clip: str) -> list[float] | None:
    """Schnabelöffnung 0…1 alle 0,1 s, aus der Lautstärke des Klangs."""
    if not clip.startswith(PREFIX):
        return None
    file = clip[len(PREFIX):]
    name = file.rsplit("_", 1)[0]
    entry = _index().get(name)
    return entry["mund"].get(file) if entry else None


def with_sound(name: str, spec: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Die Geste mit ihren eigenen Lauten statt der einzelnen Stimmbank-Töne.

    Gibt es keine gerenderten Laute, bleibt alles wie es ist (Töne der Stimmbank)."""
    found = clips(name)
    if not found or not spec:
        return spec
    out = [{k: v for k, v in kf.items() if k not in ("ton", "sound")} for kf in spec]
    out[0] = {**out[0], "klang": found}
    return out
