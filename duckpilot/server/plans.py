"""Trainingspläne aus einer Anfrage der Oberfläche (ein Plan plus bis zu zwei Varianten)."""

from __future__ import annotations

from typing import Any


def _plans_from(body: dict[str, Any], check_plan, measured: dict[str, float] | None = None) -> list[dict[str, Any]]:
    """Ein Plan plus bis zu zwei weitere Varianten (nur andere Anpassungen)."""
    base = dict(aufgabe=str(body.get("aufgabe", "")), iterations=body.get("iterationen"),
                flavor=str(body.get("grafikkarte") or "l4x1"), start_von=body.get("start_von") or None,
                max_stunden=body.get("max_stunden"), bei_stillstand=str(body.get("bei_stillstand") or "weiter"))
    variants = body.get("varianten") or []
    if not isinstance(variants, list) or len(variants) > 2:
        raise ValueError("höchstens zwei weitere Varianten")
    sets = [body.get("anpassungen") or {}] + list(variants)
    out = []
    for adj in sets:
        if not isinstance(adj, dict):
            raise ValueError("Varianten sind Anpassungen in der Form schlüssel = Zahl")
        out.append(check_plan(base["aufgabe"], base["iterations"], adj, base["flavor"], base["start_von"],
                              base["max_stunden"], base["bei_stillstand"], measured))
    return out
