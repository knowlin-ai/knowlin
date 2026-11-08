"""Aufbau eines Musikstücks aus Klang und Lautstärke je Takt (seit 0.38.23).

Hinweis: „die Erkennung der Passagen, Refrain etc., ist noch nicht perfekt, und die Moves passen noch nicht
immer gut zum Song“. Bis 0.38.22 kannte der Tanzplan nur die Lautstärke: laut = Refrain, mittel = Strophe. Ein lauter
Strophenschluss wurde so zum Refrain, ein leiser Refrain zur Strophe, und zwei Refrains mussten nicht gleich heißen.

Jetzt wie in der Musikforschung (Foote 2000, „Novelty“; Wiederholungen in der Selbstähnlichkeitsmatrix):
1. Je Takt ein Klangbild aus dem Browser: zwölf Tonklassen (Chroma – Harmonie, Melodie) und sechs Frequenzbänder
   (Klangfarbe, Schlagzeug), dazu die Lautstärke.
2. Grenzen: Wo sich das Klangbild der vier Takte davor deutlich von den vier Takten danach unterscheidet (Schachbrett
   über die Selbstähnlichkeit), beginnt ein neuer Teil – bevorzugt auf Phrasengrenzen (alle vier Takte), höchstens
   alle vier Takte.
3. Wiederholung: Teile mit ähnlichem Klangbild bekommen dieselbe Gruppe (A, B, C …).
4. Namen: Die Gruppe, die sich wiederholt und am lautesten ist, ist der Refrain; andere Wiederholungen sind Strophen;
   ein einmaliger Teil mittendrin ist die Bridge, ein leiser der Breakdown; ein lauter Teil gleich nach einem leisen
   der Drop; Intro und Outro am Rand, wenn sie leiser sind oder kein Refrain.

Ohne Klangbild (alte Analysen, Claude, Knowlets) bleibt die Einteilung nach Lautstärke (`choreo.teile`).
"""

from __future__ import annotations

from typing import Any

import numpy as np

PHRASE = 4
KERN = 4                       # Takte je Seite für den Schachbrett-Vergleich
AEHNLICH = 0.9                 # Kosinus-Ähnlichkeit der mittleren Klangbilder: gleiche Gruppe


def _merkmale(energie: list[float], klang: list[list[float]]) -> np.ndarray:
    """Je Takt ein Vektor: Tonklassen (normiert), Bänder (normiert) und Lautstärke, jeweils gewichtet."""
    k = np.asarray(klang, dtype=float)
    if k.ndim != 2 or k.shape[0] != len(energie) or k.shape[1] < 12:
        raise ValueError("Klangbild passt nicht zur Lautstärke")
    # Tonklassen mit Kontrast: Schlagzeug verteilt Energie über alle zwölf – erst den Boden abziehen, dann quadrieren,
    # damit die Akkordtöne zählen
    chroma = k[:, :12] - k[:, :12].min(axis=1, keepdims=True)
    chroma = chroma ** 2
    baender = k[:, 12:]
    def norm(m: np.ndarray) -> np.ndarray:
        return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)
    teile_ = [norm(chroma) * 1.2]
    if baender.shape[1]:
        teile_.append(norm(baender) * 0.6)
    teile_.append(np.asarray(energie, dtype=float)[:, None] * 0.9)
    return np.hstack(teile_)


def _neuheit(f: np.ndarray, kern: int = KERN) -> np.ndarray:
    """Neuheit an jeder Taktgrenze b (zwischen Takt b-1 und b): wie anders die `kern` Takte danach klingen als die
    davor (mittlere Ähnlichkeit innerhalb minus über die Grenze hinweg)."""
    n = len(f)
    fn = f / np.maximum(np.linalg.norm(f, axis=1, keepdims=True), 1e-9)
    s = fn @ fn.T
    nov = np.zeros(n + 1)
    for b in range(1, n):
        k = min(kern, b, n - b)
        if k < 1:
            continue
        a, c = s[b - k:b, b - k:b], s[b:b + k, b:b + k]
        x = s[b - k:b, b:b + k]
        nov[b] = (a.mean() + c.mean()) / 2 - x.mean()
    return nov


def _grenzen(f: np.ndarray, energie: np.ndarray) -> list[int]:
    n = len(f)
    nov = _neuheit(f)
    # Lautstärkesprung zählt mit: ein Refrain, der genauso klingt, aber deutlich lauter ist, ist trotzdem ein neuer Teil
    sprung = np.zeros(n + 1)
    for b in range(1, n):
        k = min(KERN, b, n - b)
        sprung[b] = abs(energie[b:b + k].mean() - energie[b - k:b].mean())
    wert = nov + 0.5 * sprung
    # Phrasenraster: Stücke mit Auftakt oder abgeschnittenem ersten Takt verschieben es – die Lage (0–3 Takte), an der
    # die Grenzen am deutlichsten sind
    lage = max(range(PHRASE), key=lambda o: float(np.mean([wert[b] for b in range(o or PHRASE, n, PHRASE)] or [0])))
    kandidaten = [b for b in range(lage or PHRASE, n - 1, PHRASE) if 2 <= b <= n - 2]
    if not kandidaten:
        return [0, n]
    werte = np.array([wert[b] for b in kandidaten])
    # Schwelle relativ zur deutlichsten Grenze im Stück (Median scheiterte, wenn die meisten Phrasen Grenzen sind)
    schwelle = max(0.06, 0.35 * float(werte.max()))
    gewaehlt = [b for i, b in enumerate(kandidaten) if werte[i] >= schwelle]
    # sehr lange Teile ohne Grenze (über 16 Takte) an der stärksten Phrasengrenze darin teilen
    grenzen = [0, *gewaehlt, n]
    neu = [0]
    for a, b in zip(grenzen, grenzen[1:]):
        while b - a > 16:
            innen = [c for c in kandidaten if a + 8 <= c <= b - 8]
            if not innen:
                break
            c = max(innen, key=lambda x: wert[x])
            neu.append(c)
            a = c
        neu.append(b)
    return sorted(set(neu))


def struktur(energie: list[float], klang: list[list[float]]) -> list[dict[str, Any]]:
    """Teile eines Stücks: [{takt, takte, name, stufe, gruppe}] (Namen wie `choreo.TEILE`)."""
    e = np.clip(np.asarray(energie, dtype=float), 0, 1)
    f = _merkmale(energie, klang)
    n = len(e)
    if n < 2 * PHRASE:
        return [{"takt": 0, "takte": n, "name": "Refrain", "stufe": 2, "gruppe": "A"}]
    g = _grenzen(f, e)
    teile_ = [{"takt": a, "takte": b - a} for a, b in zip(g, g[1:]) if b > a]
    # Gruppen: mittleres Klangbild je Teil, Ähnliche zusammen (wiederholte Teile)
    mittel = []
    for t in teile_:
        m = f[t["takt"]:t["takt"] + t["takte"]].mean(axis=0)
        mittel.append(m / max(np.linalg.norm(m), 1e-9))
        t["e"] = float(e[t["takt"]:t["takt"] + t["takte"]].mean())
    vertreter: list[np.ndarray] = []
    for t, m in zip(teile_, mittel):
        best, wert = -1, AEHNLICH
        for i, v in enumerate(vertreter):
            w = float(m @ v)
            if w >= wert:
                best, wert = i, w
        if best < 0:
            vertreter.append(m)
            best = len(vertreter) - 1
        t["gruppe"] = chr(ord("A") + min(best, 25))
    # Stufen wie bisher (ruhig, mittel, laut) – aus der Lautstärke des Teils
    for t in teile_:
        t["stufe"] = 0 if t["e"] < 0.35 else 1 if t["e"] < 0.68 else 2
    gruppen: dict[str, list[dict[str, Any]]] = {}
    for t in teile_:
        gruppen.setdefault(t["gruppe"], []).append(t)
    def laut(gr: str) -> float:
        return float(np.mean([t["e"] for t in gruppen[gr]]))
    wiederholt = [gr for gr, ts in gruppen.items() if len(ts) >= 2]
    kandidaten = [gr for gr in wiederholt if laut(gr) >= 0.45] or wiederholt or list(gruppen)
    refrain = max(kandidaten, key=lambda gr: (laut(gr), len(gruppen[gr])))
    lautester = max(t["e"] for t in teile_)
    erstes = {}
    for i, t in enumerate(teile_):
        erstes.setdefault(t["gruppe"], i)
    erster_refrain = erstes[refrain]
    for i, t in enumerate(teile_):
        rand = i == 0 or i == len(teile_) - 1
        if t["gruppe"] == refrain and t["e"] >= 0.45:
            t["name"] = "Refrain"
        elif t["e"] >= max(0.68, lautester - 0.08) and i > 0 and teile_[i - 1]["e"] < 0.35:
            t["name"] = "Drop"
        elif i == 0 and (t["e"] < lautester - 0.15 or t["takte"] <= 8):
            t["name"] = "Intro"
        elif i == len(teile_) - 1 and (t["e"] < lautester - 0.15 or t["takte"] <= 8):
            t["name"] = "Outro"
        elif len(gruppen[t["gruppe"]]) >= 2 and erstes[t["gruppe"]] < erster_refrain:
            t["name"] = "Strophe"                 # wiederholt und schon vor dem ersten Refrain: Strophe, auch wenn leise
        elif t["e"] < 0.35 and not rand:
            t["name"] = "Breakdown"
        elif len(gruppen[t["gruppe"]]) >= 2:
            t["name"] = "Strophe"
        elif not rand and t["e"] >= 0.68:
            t["name"] = "Refrain"                 # einmalig, aber laut: wie ein Refrain tanzen
        elif not rand:
            t["name"] = "Bridge"
        else:
            t["name"] = "Strophe"
        # Ein Drop nach einer leisen Stelle bleibt Drop, auch wenn er zur Refrain-Gruppe gehört (EDM)
        if t["name"] == "Refrain" and i > 0 and teile_[i - 1]["e"] < 0.3 and t["e"] >= 0.8:
            t["name"] = "Drop"
    # Nachbarn mit gleichem Namen und gleicher Gruppe zusammenlegen
    out: list[dict[str, Any]] = []
    for t in teile_:
        if out and out[-1]["name"] == t["name"] and out[-1]["gruppe"] == t["gruppe"]:
            out[-1]["takte"] += t["takte"]
            continue
        out.append({"takt": t["takt"], "takte": t["takte"], "name": t["name"], "stufe": t["stufe"], "gruppe": t["gruppe"]})
    return out
