"""Ari übt selbst (seit 0.41, Stufe B; Maintainer: „A, dann B“, Prinzip HIL-SERL).

Nach dem Lernen durch Vormachen (Stufe A, `arm_lernen.py`) kann Ari mit eigenen Versuchen besser werden – im
Simulator, ohne dass jemand daneben sitzt:

- **Üben in Runden.** Je Runde probiert Ari es mehrmals bei zufälliger Lage, mit etwas Zufall in den Bewegungen
  (Erkunden; der Zufall wird von Runde zu Runde kleiner). Was gelingt, wird Lernstoff („aus eigenen Erfolgen lernen“,
  Self-Imitation Learning – eine einfache Form des bestärkenden Lernens: Belohnung = Würfel liegt in der Kiste).
- **Nachlernen.** Mit den alten Beispielen und den eigenen Erfolgen lernt eine Kopie des Netzes weiter. Danach prüft
  Ari in zehn unsichtbaren Versuchen (immer dieselben Lagen, damit die Zahlen vergleichbar sind). Behalten wird die
  Kopie nur, wenn sie mindestens so gut ist wie vorher – Üben macht Ari nie schlechter.
- **Mensch im Kreis (HIL).** Greift der Mensch beim Ausprobieren mit der Hand ein, werden diese Korrekturen als
  Beispiele gespeichert (`arm_schule.py`) und fließen ins nächste Üben ein – wie bei HIL-SERL.

Alles läuft in eigenen, unsichtbaren Simulatoren auf dem Prozessor (NumPy), nie am echten Arm.
"""

from __future__ import annotations

import copy
import random
from typing import Any, Callable

import numpy as np

from . import arm_lernen as L

RUNDEN = 4
JE_RUNDE = 8                 # Versuche je Runde
PRUEF_N = 10                 # unsichtbare Prüfversuche (feste Lagen)
PRUEF_SEED = 1000            # dieselben Lagen wie beim Lernen (`arm_schule`), damit „vorher“ und „nachher“ passen
RAUSCHEN = 0.35              # Zufall in den Schritten zu Beginn (Anteil des größten Schritts)
EPOCHEN = 120


def mit_rauschen(netz: L.Netz, staerke: float, rng: np.random.Generator) -> Callable[[np.ndarray], dict[str, float]]:
    """Steuerung: das Netz plus etwas Zufall in den Schritten (Erkunden); der Greifer bleibt, wie das Netz will."""
    def steuern(obs: np.ndarray) -> dict[str, float]:
        akt = netz(obs).copy()
        akt[:3] = np.clip(akt[:3] + rng.normal(0.0, staerke, 3), -1, 1)
        return L.aktion_zu_ziel(obs, akt)
    return steuern


def ueben(netz: L.Netz, a: dict[str, str], beispiele: list[dict[str, Any]], runden: int = RUNDEN,
          je_runde: int = JE_RUNDE, seed: int = 7, bescheid: Callable[[str], None] | None = None,
          weiter: Callable[[], bool] | None = None) -> tuple[L.Netz, dict[str, Any]]:
    """Übt `runden` Runden und gibt das beste Netz zurück (nie schlechter als `netz`) – mit Verlauf je Runde."""
    bescheid = bescheid or (lambda _t: None)
    weiter = weiter or (lambda: True)
    rng, nrng = random.Random(seed), np.random.default_rng(seed)
    bestes, beste_quote = netz, L.pruefen(netz, a, n=PRUEF_N, seed=PRUEF_SEED)
    vorher = beste_quote
    eigene: list[dict[str, Any]] = []
    verlauf: list[dict[str, Any]] = []
    sim = L._simulator(seed)
    for r in range(runden):
        if not weiter():
            break
        staerke = RAUSCHEN * (1 - r / max(1, runden))
        gelungen = 0
        for i in range(je_runde):
            if not weiter():
                break
            bescheid(f"Runde {r + 1} von {runden}: Versuch {i + 1} von {je_runde} …")
            L.neu_starten(sim)
            L.zufaellige_lage(sim, a, rng)
            ok, schritte = L.durchgang(sim, a, mit_rauschen(bestes, staerke, nrng))
            if ok:
                gelungen += 1
                eigene.append({"von": "geuebt", "schritte": schritte})
        if not eigene:
            verlauf.append({"runde": r + 1, "gelungen": gelungen, "versuche": je_runde, "quote": beste_quote,
                            "behalten": False})
            continue
        bescheid(f"Runde {r + 1} von {runden}: Ari lernt aus {len(eigene)} eigenen Erfolgen …")
        kandidat = copy.deepcopy(bestes)
        X, Y = L.daten([*beispiele, *eigene])
        kandidat.lernen(X, Y, epochen=EPOCHEN, seed=r)
        quote = L.pruefen(kandidat, a, n=PRUEF_N, seed=PRUEF_SEED)
        behalten = quote >= beste_quote
        if behalten:
            bestes, beste_quote = kandidat, quote
        verlauf.append({"runde": r + 1, "gelungen": gelungen, "versuche": je_runde, "quote": quote, "behalten": behalten})
    return bestes, {"vorher": vorher, "nachher": beste_quote, "versuche": PRUEF_N, "runden": verlauf,
                    "eigene_erfolge": len(eigene)}
