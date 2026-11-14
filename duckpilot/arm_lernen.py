"""Ari lernt durch Vormachen (seit 0.38.64, Stufe A; Maintainer: „Ari zuerst“, „A, dann B“).

Ari soll eine Aufgabe an der Werkbank – „leg den roten Würfel in die linke Kiste“ – nicht nach festem Plan ausführen,
sondern aus Beispielen lernen: wie bei LeRobot (Lernen durch Vormachen, „Behavior Cloning“), nur klein und am PC.

Alle steuern Ari über dieselbe Schnittstelle wie das Vormachen mit der Hand (`So101Sim.nachmachen`): die Spitze nach
x, y, z (m im Rahmen des Sockels) und den Greifer auf oder zu – etwa sieben Schritte je Sekunde (`SCHRITT_S`).

- **Beispiele** kommen vom Menschen (Vormachen per Webcam, aufgezeichnet in der Laufzeit) oder vom **Lehrer**: einem
  einfachen Ablauf, der nur aus dem sieht, was auch das Netz sieht (`Lehrer`). Er macht vor bei zufällig gelegtem Würfel,
  so lernt das Netz nicht nur eine Lage auswendig.
- **Beobachtung** (`beobachtung`, 11 Werte): Spitze (x, y, z), Greifer offen (0…1), hält den Würfel (0/1), Würfel und
  Kiste relativ zur Spitze. **Aktion** (4 Werte): Schritt der Spitze (je Achse bis `MAX_SCHRITT`, auf −1…1 geteilt) und
  Greifer (0 = zu, 1 = auf).
- **Netz** (`Netz`): zwei verdeckte Schichten, NumPy, Adam – lernt in Sekunden auf dem Prozessor, braucht kein PyTorch.
- **Prüfen** (`pruefen`): Ari versucht es in eigenen, unsichtbaren Simulatoren mit zufälliger Lage; gezählt wird, wie
  oft der Würfel in der Kiste landet.

Alles läuft im Simulator; den echten Arm steuert das gelernte Netz nicht (dafür braucht es Kamerabilder – Stufe A4,
Export im LeRobot-Format). Not-Aus: Die Laufzeit führt ein gelerntes Netz über dieselben Wege aus wie jede Bewegung;
`nachmachen` lehnt stromlos ab.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
from pathlib import Path
from typing import Any, Callable

import numpy as np

from . import arm_kinematik as K

SCHRITT_S = 0.15            # Regeltakt (wie das Vormachen: etwa 7 Ziele je Sekunde)
MAX_SCHRITT = 0.02          # m je Takt und Achse
DAUER_S = 30.0              # so lange darf ein Durchgang dauern
TRAGEN = 0.075              # Höhe beim Tragen und Anfahren – reicht auch nah am Sockel (wie TRAGEN_FLACH)
GREIFER_AUF, GREIFER_ZU = 55.0, 8.0
EIN, AUS = 11, 4
GELENKE = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
BEOBACHTUNG = ("spitze_x", "spitze_y", "spitze_z", "greifer_offen", "haelt", "wuerfel_dx", "wuerfel_dy", "wuerfel_dz",
               "kiste_dx", "kiste_dy", "eins")
ABSTAND = 0.085            # so weit liegen die anderen Würfel mindestens vom Ziel-Würfel weg


def aufgabe(wuerfel: str, kiste: str) -> dict[str, str]:
    return {"wuerfel": wuerfel, "kiste": kiste, "name": f"{wuerfel} → {kiste}"}


def _ding(wb: Any, name: str) -> dict[str, Any] | None:
    return next((d for d in wb.dinge if d["name"] == name), None)


def _kiste(wb: Any, name: str) -> dict[str, Any] | None:
    return next((k for k in wb.kisten if k["name"] == name), None)


def spitze(gelenke: dict[str, float]) -> tuple[float, float, float]:
    p, _ = K.spitze(gelenke)
    return float(p[0]), float(p[1]), float(p[2])


def beobachtung(gelenke: dict[str, float], wb: Any, a: dict[str, str]) -> np.ndarray:
    """Was Lehrer, Mensch und Netz gleich sehen (11 Werte, grob auf −1…1)."""
    x, y, z = spitze(gelenke)
    d, k = _ding(wb, a["wuerfel"]), _kiste(wb, a["kiste"])
    haelt = 1.0 if wb.haelt == a["wuerfel"] else 0.0
    cx, cy, cz = (x, y, z) if (d is None or haelt) else (d["x"], d["y"], d["z"])
    bx, by = (k["x"], k["y"]) if k else (x, y)
    return np.array([x * 4, y * 4, z * 8, gelenke.get("gripper", 0.0) / GREIFER_AUF, haelt,
                     (cx - x) * 8, (cy - y) * 8, (cz - z) * 8, (bx - x) * 8, (by - y) * 8, 1.0], dtype=np.float32)


def aktion_zu_ziel(obs: np.ndarray, akt: np.ndarray) -> dict[str, float]:
    """Aktion (−1…1, Greifer 0…1) → Ziel für `nachmachen`."""
    x, y, z = obs[0] / 4, obs[1] / 4, obs[2] / 8
    d = np.clip(akt[:3], -1, 1) * MAX_SCHRITT
    return {"x": round(float(x + d[0]), 4), "y": round(float(y + d[1]), 4), "z": round(float(max(0.012, z + d[2])), 4),
            "greifer": GREIFER_AUF if akt[3] >= 0.5 else GREIFER_ZU}


def ziel_zu_aktion(obs: np.ndarray, ziel: dict[str, float]) -> np.ndarray:
    x, y, z = obs[0] / 4, obs[1] / 4, obs[2] / 8
    d = np.clip(np.array([ziel["x"] - x, ziel["y"] - y, ziel["z"] - z]) / MAX_SCHRITT, -1, 1)
    return np.array([*d, 1.0 if ziel["greifer"] > (GREIFER_AUF + GREIFER_ZU) / 2 else 0.0], dtype=np.float32)


class Lehrer:
    """Macht vor – nur aus der Beobachtung, damit das Netz dasselbe lernen kann: über den Würfel, hinab, greifen, hoch,
    über die Kiste, loslassen."""

    def __call__(self, obs: np.ndarray) -> dict[str, float]:
        x, y, z, auf, haelt = obs[0] / 4, obs[1] / 4, obs[2] / 8, obs[3] > 0.5, obs[4] > 0.5
        cx, cy, cz = x + obs[5] / 8, y + obs[6] / 8, z + obs[7] / 8
        bx, by = x + obs[8] / 8, y + obs[9] / 8
        if not haelt:
            weit = math.hypot(cx - x, cy - y)
            if weit > 0.006:                                     # erst darüber (offen, in Tragehöhe)
                ziel = (cx, cy, max(cz + 0.05, min(z, TRAGEN)) if weit > 0.03 else cz + 0.05)
                return self._schritt(x, y, z, ziel, GREIFER_AUF)
            if not auf:                                          # zu, ohne zu halten: erst öffnen
                return {"x": x, "y": y, "z": z, "greifer": GREIFER_AUF}
            if z > cz + 0.006:                                   # senkrecht hinab
                return self._schritt(x, y, z, (cx, cy, cz), GREIFER_AUF)
            return {"x": cx, "y": cy, "z": cz, "greifer": GREIFER_ZU}  # greifen
        weit = math.hypot(bx - x, by - y)
        if weit > 0.012:
            if z < TRAGEN - 0.012:                               # erst hoch
                return self._schritt(x, y, z, (x, y, TRAGEN), GREIFER_ZU)
            return self._schritt(x, y, z, (bx, by, TRAGEN), GREIFER_ZU)
        return {"x": x, "y": y, "z": z, "greifer": GREIFER_AUF}       # über der Kiste: loslassen

    @staticmethod
    def _schritt(x: float, y: float, z: float, ziel: tuple[float, float, float], greifer: float) -> dict[str, float]:
        """Ein Schritt im Bogen um den Sockel (Winkel und Abstand getrennt) – ein gerader Weg quer vor dem Sockel
        käme ihm zu nah, dort reicht die Spitze nicht hoch genug."""
        r, w = math.hypot(x, y), math.atan2(y, x)
        rz, wz = math.hypot(ziel[0], ziel[1]), math.atan2(ziel[1], ziel[0])
        dw = max(-MAX_SCHRITT / max(r, 0.1), min(MAX_SCHRITT / max(r, 0.1), wz - w))
        r2 = r + max(-MAX_SCHRITT, min(MAX_SCHRITT, rz - r))
        nx, ny = r2 * math.cos(w + dw), r2 * math.sin(w + dw)
        nx, ny = x + max(-MAX_SCHRITT, min(MAX_SCHRITT, nx - x)), y + max(-MAX_SCHRITT, min(MAX_SCHRITT, ny - y))
        nz = z + max(-MAX_SCHRITT, min(MAX_SCHRITT, ziel[2] - z))
        return {"x": round(nx, 4), "y": round(ny, 4), "z": round(nz, 4), "greifer": greifer}


class Netz:
    """Kleines Netz (EIN → 64 → 64 → AUS), tanh; Schritt gerade, Greifer über eine Sigmoid-Ausgabe."""

    def __init__(self, seed: int = 0, breite: int = 64) -> None:
        r = np.random.default_rng(seed)
        groessen = [EIN, breite, breite, AUS]
        self.W = [r.normal(0, 1 / math.sqrt(a), (a, b)).astype(np.float32) for a, b in zip(groessen, groessen[1:])]
        self.b = [np.zeros(b, np.float32) for b in groessen[1:]]

    def _vor(self, x: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
        h = [x]
        for i, (w, b) in enumerate(zip(self.W, self.b)):
            z = h[-1] @ w + b
            h.append(np.tanh(z) if i < len(self.W) - 1 else z)
        return h[-1], h

    def __call__(self, obs: np.ndarray) -> np.ndarray:
        y, _ = self._vor(obs[None, :].astype(np.float32))
        y = y[0]
        return np.array([*np.tanh(y[:3]), 1 / (1 + math.exp(-float(y[3])))], dtype=np.float32)

    def lernen(self, X: np.ndarray, Y: np.ndarray, epochen: int = 300, lr: float = 3e-3, seed: int = 0,
               bescheid: Callable[[int, float], None] | None = None) -> float:
        """Adam auf Mittelwert der Fehler: Schritt (tanh, quadratisch), Greifer (Sigmoid, Kreuzentropie)."""
        r = np.random.default_rng(seed)
        m = [np.zeros_like(p) for p in (*self.W, *self.b)]
        v = [np.zeros_like(p) for p in (*self.W, *self.b)]
        t, verlust = 0, float("nan")
        for ep in range(epochen):
            idx = r.permutation(len(X))
            summe = 0.0
            for s in range(0, len(X), 128):
                xb, yb = X[idx[s:s + 128]], Y[idx[s:s + 128]]
                out, h = self._vor(xb)
                schritt = np.tanh(out[:, :3])
                p = 1 / (1 + np.exp(-out[:, 3]))
                summe += float(np.mean((schritt - yb[:, :3]) ** 2) * len(xb))
                g = np.zeros_like(out)
                g[:, :3] = 2 * (schritt - yb[:, :3]) * (1 - schritt ** 2) / (3 * len(xb))
                g[:, 3] = (p - yb[:, 3]) / len(xb)
                grads_w, grads_b = [], []
                for i in range(len(self.W) - 1, -1, -1):
                    grads_w.insert(0, h[i].T @ g)
                    grads_b.insert(0, g.sum(0))
                    if i:
                        g = (g @ self.W[i].T) * (1 - h[i] ** 2)
                t += 1
                for j, (par, gr) in enumerate(zip((*self.W, *self.b), (*grads_w, *grads_b))):
                    m[j] = 0.9 * m[j] + 0.1 * gr
                    v[j] = 0.999 * v[j] + 0.001 * gr * gr
                    par -= lr * (m[j] / (1 - 0.9 ** t)) / (np.sqrt(v[j] / (1 - 0.999 ** t)) + 1e-8)
            verlust = summe / max(1, len(X))
            if bescheid and (ep % 25 == 0 or ep == epochen - 1):
                bescheid(ep, verlust)
        return verlust

    def speichern(self, pfad: Path, meta: dict[str, Any]) -> None:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        np.savez(pfad, **{f"W{i}": w for i, w in enumerate(self.W)}, **{f"b{i}": b for i, b in enumerate(self.b)},
                 meta=np.array(json.dumps(meta, ensure_ascii=False)))

    @classmethod
    def laden(cls, pfad: Path) -> tuple[Netz, dict[str, Any]]:
        d = np.load(pfad, allow_pickle=False)
        n = cls.__new__(cls)
        k = sum(1 for key in d.files if key.startswith("W"))
        n.W = [d[f"W{i}"] for i in range(k)]
        n.b = [d[f"b{i}"] for i in range(k)]
        return n, json.loads(str(d["meta"]))


# ── Durchgänge im unsichtbaren Simulator ─────────────────────────────────────────────────────────────────────────
def _simulator(seed: int) -> Any:
    from .backends.so101 import So101Sim

    sim = So101Sim(realtime=False, seed=seed)

    async def wach() -> None:
        await sim.connect()
        await sim.init()
    asyncio.run(wach())
    for _ in range(80):
        sim.step(0.05)
    return sim


def zufaellige_lage(sim: Any, a: dict[str, str], rng: random.Random) -> None:
    """Den Ziel-Würfel an eine freie, erreichbare Stelle vor Ari legen (andere bleiben, wo sie sind)."""
    wb = sim.werkbank
    d = _ding(wb, a["wuerfel"])
    if d is None:
        return
    for _ in range(60):
        r, w = rng.uniform(0.17, 0.27), math.radians(rng.uniform(-45, 45))
        x, y = r * math.cos(w), r * math.sin(w)
        # Abstand zu den anderen Würfeln: die Beobachtung kennt nur den Ziel-Würfel, die offenen Finger brauchen Platz
        frei = all(math.hypot(x - o["x"], y - o["y"]) >= ABSTAND for o in wb.dinge
                   if o["name"] != d["name"] and not o.get("in"))
        if frei and wb.stelle_frei(x, y, ohne=d["name"]) and K.greifhaltung(x, y, d["z"], GREIFER_AUF) is not None:
            d["x"], d["y"], d["in"], d["auf"] = round(x, 4), round(y, 4), None, None
            return


def gelenkwerte(gelenke: dict[str, float]) -> list[float]:
    """Die sechs Gelenke in der Reihenfolge von LeRobot (`so101_follower`), in Grad."""
    return [round(float(gelenke.get(n, 0.0)), 3) for n in GELENKE]


def schritt_daten(obs: np.ndarray, ziel: dict[str, float], gelenke: dict[str, float]) -> list[list[float]]:
    """Ein aufgezeichneter Takt: Beobachtung, Aktion, Gelenke jetzt und Ziel-Gelenke (für den LeRobot-Export)."""
    g = K.greifhaltung(round(ziel["x"], 3), round(ziel["y"], 3), round(ziel["z"], 3), ziel["greifer"])
    return [[round(float(v), 5) for v in obs], [round(float(v), 5) for v in ziel_zu_aktion(obs, ziel)],
            gelenkwerte(gelenke), gelenkwerte(g) if g else gelenkwerte(gelenke)]


def geschafft(wb: Any, a: dict[str, str]) -> bool:
    d = _ding(wb, a["wuerfel"])
    return d is not None and d.get("in") == a["kiste"] and wb.haelt is None


def durchgang(sim: Any, a: dict[str, str], steuerung: Callable[[np.ndarray], dict[str, float]],
              aufnehmen: bool = True) -> tuple[bool, list[list[list[float]]]]:
    """Ein Versuch: bis der Würfel in der Kiste ist oder die Zeit abläuft. Liefert (geschafft, Takte – siehe
    `schritt_daten`)."""
    schritte: list[list[list[float]]] = []
    takte = int(DAUER_S / SCHRITT_S)
    for _ in range(takte):
        obs = beobachtung(sim.gelenke, sim.werkbank, a)
        ziel = steuerung(obs)
        if aufnehmen:
            schritte.append(schritt_daten(obs, ziel, sim.gelenke))
        asyncio.run(sim.nachmachen(ziel))
        for _ in range(3):
            sim.step(SCHRITT_S / 3)
        if geschafft(sim.werkbank, a):
            return True, schritte
    return False, schritte


def neu_starten(sim: Any) -> None:
    """Würfel an ihre Plätze, Arm in die Bereitschaft – wie vor jedem neuen Versuch."""
    from .arm import POSEN

    sim.werkbank.zuruecksetzen()
    asyncio.run(sim.haltung(dict(POSEN["bereit"]), 0.6))
    for _ in range(20):
        sim.step(0.05)


def lehrer_beispiele(a: dict[str, str], n: int = 20, seed: int = 0) -> list[dict[str, Any]]:
    """`n` Beispiele vom Lehrer bei zufälliger Lage; nur gelungene zählen."""
    rng = random.Random(seed)
    sim = _simulator(seed)
    out = []
    for i in range(n):
        neu_starten(sim)
        zufaellige_lage(sim, a, rng)
        ok, schritte = durchgang(sim, a, Lehrer())
        if ok:
            out.append({"von": "lehrer", "nr": i, "schritte": schritte})
    return out


def daten(beispiele: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    """Beobachtungen und Aktionen aller Takte als Lernstoff."""
    X = np.array([s[0] for b in beispiele for s in b["schritte"]], dtype=np.float32).reshape(-1, EIN)
    Y = np.array([s[1] for b in beispiele for s in b["schritte"]], dtype=np.float32).reshape(-1, AUS)
    return X, Y


def pruefen(netz: Netz, a: dict[str, str], n: int = 10, seed: int = 1000) -> int:
    """So oft schafft es das Netz bei `n` zufälligen Lagen (eigene Simulatoren, andere Lagen als beim Lernen)."""
    rng = random.Random(seed)
    sim = _simulator(seed)
    geschafft = 0
    for _ in range(n):
        neu_starten(sim)
        zufaellige_lage(sim, a, rng)
        ok, _ = durchgang(sim, a, lambda o: aktion_zu_ziel(o, netz(o)), aufnehmen=False)
        geschafft += ok
    return geschafft
