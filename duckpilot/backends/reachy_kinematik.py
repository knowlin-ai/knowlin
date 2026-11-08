"""Reachy Mini: Welche Kopflagen gehen wirklich? (seit 0.38.10)

Der Kopf von Reachy Mini sitzt auf einer Stewart-Plattform: sechs Motoren mit 4 cm langen Armen, an jedem Arm eine
8,5 cm lange Stange zum Kopf. Jede Achse für sich (Nicken ±40°, Neigen ±40° …) ist kein ausreichender Maßstab – erst
die **ganze** Lage (x, y, z, roll, pitch, yaw relativ zum Körper) entscheidet, ob alle sechs Stangen sie erreichen und
ob der Kopf dabei über der Körperschale bleibt. Kombiniert (z. B. Nicken + Neigen + etwas tiefer) tauchte der Kopf
im Simulator sichtbar in den Körper (Beobachtung aus dem Test bei „freu dich“).

Hier steht die eine Prüfung, die Simulator (`ReachyMiniSim`) und echter Reachy (`ReachyMiniDaemon`, `set_target`)
beide nutzen:

- `erreichbar(lage)` – gehen alle sechs Stangen hin, und hält der Kopf Abstand zum Körper?
- `begrenzen(lage)` – nimmt eine unerreichbare Lage Richtung Neutral zurück (Bisektion über einen Faktor 0…1), bis
  sie passt; vorher wird versucht, die Kopfdrehung (yaw) zu behalten, damit der Blick stimmt.

**Geometrie.** Kommt aus Pollens 3D-Modell, das duckpilot ohnehin für die Ansicht backt (`modell/reachy.py`,
Abschnitt `kinematik` + Teile von Kopf und Körper). Diese Dateien sind CC BY-NC-SA (© Pollen Robotics) und liegen nur
im Datenordner bzw. in der privaten Fassung – hier im Quelltext steht **keine** Zahl daraus. Zur Laufzeit liest
`Geometrie.aus_modell()` die Datei einmal (Stangen-Anker, Längen, Motorlage und -bereich, Kopfhöhe; daraus eine
Höhenkarte der Körperschale und eine Punktwolke der Kopfschale).

**Ohne Pollens Modell** (öffentliche Fassung, noch nicht geladen, offline) greift `ersatz_erreichbar()`: vorsichtige
Grenzen für Kombinationen (Kippen insgesamt, Kippen gegen Absenken, Drehen gegen Kippen), an Pollens Modell geprüft
(Test `tests/test_reachy_kinematik.py`): Was die Ersatzprüfung durchlässt, ist auch mit Modell erreichbar.

Winkel in rad, Wege in m. Euler wie Pollen: R = Rz(yaw)·Ry(pitch)·Rx(roll).
"""

from __future__ import annotations

import logging
import math
import struct
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ACHSEN = ("x", "y", "z", "roll", "pitch", "yaw")
NEUTRAL = {k: 0.0 for k in ACHSEN}
# Je Achse für sich (Pollens Doku: Nicken/Neigen ±40°, Kopf gegen Körper höchstens 65° gedreht)
GRENZE = {"x": 0.03, "y": 0.03, "z": 0.045, "roll": math.radians(40), "pitch": math.radians(40),
          "yaw": math.radians(65)}
ABSTAND_M = 0.001          # Mindestabstand Kopfschale über Körperschale (senkrecht; Pollens Schalen liegen bei 60° Drehung nur ~2 mm auseinander)
WINKEL_LUFT = 0.02         # rad Abstand zum Ende des Motorbereichs
STRECK_LUFT = 0.995        # Stange nie ganz gestreckt (Singularität)
SCHRITTE = 12              # Bisektion: 1/4096 genau
LUFT = 0.995               # zurückgenommene Lagen ein halbes Prozent weiter innen – Runden (Anzeige, set_target) bleibt drin

# ── Ersatzprüfung ohne Pollens Modell (vorsichtig; am Modell geprüft, siehe Test) ─────────────────────────────────
# Höhe z (mm) muss zwischen unterer und oberer Grenze liegen; beide hängen am Kippen t (Grad, roll und pitch
# zusammen) und an der Drehung (Grad): Kippen und Drehen bringen die Kopfkante an den Rand der Körperschale (tiefer
# verboten), Hochfahren und Kippen brauchen zusammen mehr Stangenlänge (höher verboten).
ERSATZ = {
    "xy_mm": 5.0,                      # seitlich/vor/zurück je höchstens 5 mm
    "kipp_grad": 25.0,
    "dreh_grad": 50.0,
    "unten": (-15.0, 1.0, 0.4),        # z ≥ −15 mm + 1,0 mm je Grad Kippen + 0,4 mm je Grad Drehen
    "oben": (18.0, -0.5, -0.15),       # z ≤ 18 mm − 0,5 mm je Grad Kippen − 0,15 mm je Grad Drehen
}


def _klemmen(lage: dict[str, float]) -> dict[str, float]:
    return {k: max(-g, min(g, float(lage.get(k, 0.0) or 0.0))) for k, g in GRENZE.items()}


def ersatz_erreichbar(lage: dict[str, float]) -> bool:
    """Vorsichtige Prüfung ohne Pollens Geometrie: Kippen und Drehen begrenzt, und je mehr davon, desto enger die Höhe."""
    e = ERSATZ
    if max(abs(lage.get("x", 0.0)), abs(lage.get("y", 0.0))) * 1000 > e["xy_mm"] + 1e-6:
        return False
    t = math.degrees(math.hypot(lage.get("roll", 0.0), lage.get("pitch", 0.0)))
    d = abs(math.degrees(lage.get("yaw", 0.0)))
    if t > e["kipp_grad"] + 1e-6 or d > e["dreh_grad"] + 1e-6:
        return False
    z = lage.get("z", 0.0) * 1000
    u, o = e["unten"], e["oben"]
    return u[0] + u[1] * t + u[2] * d - 1e-6 <= z <= o[0] + o[1] * t + o[2] * d + 1e-6


# ── Kleine Vektorrechnung (ohne numpy, die Prüfung läuft im Takt) ─────────────────────────────────────────────────
def _rot(roll: float, pitch: float, yaw: float) -> tuple[tuple[float, float, float], ...]:
    cr, sr, cp, sp, cy, sy = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw)
    return ((cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
            (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
            (-sp, cp * sr, cp * cr))


def _quat_mat(pos: list[float], quat: list[float]) -> list[list[float]]:
    w, x, y, z = quat
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    w, x, y, z = w / n, x / n, y / n, z / n
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), pos[0]],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), pos[1]],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), pos[2]],
            [0.0, 0.0, 0.0, 1.0]]


@dataclass
class Bein:
    """Eine Stange: Ihr Ende am Motorarm läuft auf einem Kreis (Mitte, Ebene X/Y, Radius), das andere Ende sitzt am
    Kopf (`anker`, im Rahmen der Kopflage). Erreichbar, wenn ein Motorwinkel im Bereich die Länge genau trifft."""
    mitte: tuple[float, float, float]
    ex: tuple[float, float, float]
    ey: tuple[float, float, float]
    radius: float
    phase: float
    lo: float
    hi: float
    anker: tuple[float, float, float]
    laenge: float
    zweig: int = 1                     # welche der beiden Lösungen (wie Pollens „solution“) – aus der Grundstellung

    def winkel(self, p: tuple[float, float, float]) -> float | None:
        """Motorwinkel für den Ankerpunkt p (Körperrahmen) – None, wenn die Stange nicht hinreicht."""
        d = (p[0] - self.mitte[0], p[1] - self.mitte[1], p[2] - self.mitte[2])
        a = d[0] * self.ex[0] + d[1] * self.ex[1] + d[2] * self.ex[2]
        b = d[0] * self.ey[0] + d[1] * self.ey[1] + d[2] * self.ey[2]
        m = math.hypot(a, b)
        if m < 1e-9:
            return None
        k = (self.radius ** 2 + d[0] ** 2 + d[1] ** 2 + d[2] ** 2 - self.laenge ** 2) / (2 * self.radius)
        c = k / m
        if abs(c) > STRECK_LUFT:
            return None
        th = math.atan2(b, a) + self.zweig * math.acos(c) - self.phase
        return math.atan2(math.sin(th), math.cos(th))


class Geometrie:
    """Stewart-Plattform und Schalen aus Pollens Modell (nur zur Laufzeit gelesen, nicht im Quelltext)."""

    def __init__(self, beine: list[Bein], kopf_z: float, punkte: Any, hoehen: Any, zelle: float, rand: float) -> None:
        self.beine = beine
        self.kopf_z = kopf_z
        self.punkte = punkte          # numpy (n, 3): Kopfschale im Rahmen der Kopflage
        self.hoehen = hoehen          # numpy (m, m): höchster Punkt der Körperschale je Zelle (Körperrahmen)
        self.zelle = zelle
        self.rand = rand

    # Kopflage → Ankerpunkt im Körperrahmen
    def _welt(self, lage: dict[str, float], p: tuple[float, float, float]) -> tuple[float, float, float]:
        r = _rot(lage.get("roll", 0.0), lage.get("pitch", 0.0), lage.get("yaw", 0.0))
        t = (lage.get("x", 0.0), lage.get("y", 0.0), lage.get("z", 0.0) + self.kopf_z)
        return tuple(r[i][0] * p[0] + r[i][1] * p[1] + r[i][2] * p[2] + t[i] for i in range(3))  # type: ignore[return-value]

    def motorwinkel(self, lage: dict[str, float]) -> list[float | None]:
        return [b.winkel(self._welt(lage, b.anker)) for b in self.beine]

    def stangen_ok(self, lage: dict[str, float]) -> bool:
        for b in self.beine:
            w = b.winkel(self._welt(lage, b.anker))
            if w is None or not b.lo + WINKEL_LUFT <= w <= b.hi - WINKEL_LUFT:
                return False
        return True

    def abstand(self, lage: dict[str, float]) -> float:
        """Kleinster senkrechter Abstand Kopfschale über Körperschale (m); negativ = der Kopf steckt im Körper."""
        import numpy as np

        r = np.array(_rot(lage.get("roll", 0.0), lage.get("pitch", 0.0), lage.get("yaw", 0.0)))
        t = np.array([lage.get("x", 0.0), lage.get("y", 0.0), lage.get("z", 0.0) + self.kopf_z])
        w = self.punkte @ r.T + t
        n = self.hoehen.shape[0]
        ij = np.floor((w[:, :2] + self.rand) / self.zelle).astype(int)
        drin = (ij >= 0).all(axis=1) & (ij < n).all(axis=1)
        if not drin.any():
            return float(w[:, 2].min())
        return float((w[drin, 2] - self.hoehen[ij[drin, 0], ij[drin, 1]]).min())

    def erreichbar(self, lage: dict[str, float]) -> bool:
        return self.stangen_ok(lage) and self.abstand(lage) >= ABSTAND_M

    # ── Laden ─────────────────────────────────────────────────────────────
    @classmethod
    def aus_datei(cls, pfad: Path) -> "Geometrie":
        """Pollens gebackenes Modell (DPM2 aus `modell/reachy.py`) lesen und die Prüfgeometrie daraus ableiten."""
        import json

        import numpy as np

        daten = pfad.read_bytes()
        if daten[:4] != b"DPM2":
            raise ValueError("kein DPM2")
        n = struct.unpack("<I", daten[4:8])[0]
        kopf = json.loads(daten[8:8 + n])
        if kopf.get("art") != "reachy_mini" or "kinematik" not in kopf:
            raise ValueError("kein Reachy-Mini-Modell mit Kinematik")
        off = 8 + n
        off += -off % 4
        nv = sum(m["v"][1] for m in kopf["meshes"])
        ni = sum(m["i"][1] for m in kopf["meshes"])
        pos = np.frombuffer(daten, dtype="<u2", count=nv * 3, offset=off).reshape(-1, 3)
        off += nv * 6
        off += -off % 4
        off += nv * 3                                     # Normalen überspringen
        off += -off % 4
        idx = np.frombuffer(daten, dtype="<u2", count=ni, offset=off)
        K, bodies = kopf["kinematik"], kopf["bodies"]
        M = lambda b: np.array(_quat_mat(b["pos"], b["quat"]))          # noqa: E731
        welt: list[Any] = []
        for b in bodies:                                   # Lage aller Körper bei Gelenken = 0
            welt.append((welt[b["parent"]] if b["parent"] >= 0 else np.eye(4)) @ M(b))
        site = np.array(_quat_mat(K["kopf_site"]["pos"], K["kopf_site"]["quat"]))
        site_inv = np.linalg.inv(site)
        koerper = K["koerper"]

        beine = []
        for s in K["stangen"]:
            w0 = welt[s["horn"]]
            r = np.array(bodies[s["stange"]]["pos"])            # Stangenansatz am Arm (im Rahmen des Arms)
            rho, phase = math.hypot(r[0], r[1]), math.atan2(r[1], r[0])
            mitte = w0[:3, 3] + w0[:3, 2] * r[2]
            anker = site_inv[:3, :3] @ np.array(s["anker"]) + site_inv[:3, 3]
            lo, hi = bodies[s["horn"]].get("range") or (-math.pi, math.pi)
            beine.append(Bein(tuple(map(float, mitte)), tuple(map(float, w0[:3, 0])), tuple(map(float, w0[:3, 1])),
                              float(rho), float(phase), float(lo), float(hi), tuple(map(float, anker)),
                              float(s["laenge"])))
        geo = cls(beine, float(K["kopf_z"]), None, None, 0.002, 0.096)
        for b in beine:                                    # Zweig wie in der Grundstellung (nächster an 0)
            p = geo._welt(NEUTRAL, b.anker)
            kandidaten = [(abs(w), z) for z in (1, -1) for w in [Bein(**{**vars(b), "zweig": z}).winkel(p)] if w is not None]
            if not kandidaten:
                raise ValueError("Grundstellung nicht erreichbar – Modell passt nicht")
            b.zweig = min(kandidaten)[1]

        def verts(mi: int) -> Any:
            m = kopf["meshes"][mi]
            q = pos[m["v"][0]:m["v"][0] + m["v"][1]].astype(float)
            return np.array(m["min"]) + q * np.array(m["step"])

        def dicht(teil: dict[str, Any], rahmen: Any, schritt: float) -> Any:
            """Ecken plus Punkte auf großen Dreiecken – damit die Höhenkarte keine Lücken hat."""
            mat = rahmen @ M(teil)
            m = kopf["meshes"][teil["mesh"]]
            v = verts(teil["mesh"]) @ mat[:3, :3].T + mat[:3, 3]
            f = idx[m["i"][0]:m["i"][0] + m["i"][1]].reshape(-1, 3).astype(int)
            a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
            lang = np.maximum(np.maximum(np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1)),
                              np.linalg.norm(a - c, axis=1))
            k = np.clip(np.ceil(lang / schritt), 1, 24).astype(int)
            out = [v]
            for kk in np.unique(k):
                if kk < 2:
                    continue
                sel = k == kk
                uu, vv = np.meshgrid(np.arange(kk + 1), np.arange(kk + 1))
                m2 = (uu + vv) <= kk
                u, w = uu[m2] / kk, vv[m2] / kk
                A, B, C = a[sel], b[sel], c[sel]
                out.append((A[:, None, :] + (B - A)[:, None, :] * u[None, :, None]
                            + (C - A)[:, None, :] * w[None, :, None]).reshape(-1, 3))
            return np.vstack(out)

        schale = np.vstack([dicht(t, welt[koerper], 0.0015) for t in kopf["parts"] if t["body"] == koerper])
        m = int(round(2 * geo.rand / geo.zelle))
        ij = np.floor((schale[:, :2] + geo.rand) / geo.zelle).astype(int)
        ok = (ij >= 0).all(axis=1) & (ij < m).all(axis=1)
        hoehen = np.zeros((m, m))
        np.maximum.at(hoehen, (ij[ok, 0], ij[ok, 1]), schale[ok, 2])
        teile = [t for t in kopf["parts"] if t["body"] == K["kopf"] and not t["name"].startswith("stewart_link")]
        kopfpunkte = np.vstack([dicht(t, site_inv, 0.004) for t in teile])
        kopfpunkte = kopfpunkte[kopfpunkte[:, 2] < 0.06]          # nur die untere Hälfte kommt dem Körper nahe
        _, einmal = np.unique(np.round(kopfpunkte / 0.004), axis=0, return_index=True)
        geo.punkte, geo.hoehen = kopfpunkte[np.sort(einmal)], hoehen
        if not geo.erreichbar(NEUTRAL):
            raise ValueError("Grundstellung laut Modell nicht frei – Modell passt nicht")
        return geo

    @classmethod
    def aus_modell(cls) -> "Geometrie | None":
        """Pollens Modell auf diesem PC (Datenordner oder private Fassung) – sonst None (dann gilt die Ersatzprüfung)."""
        try:
            from ..modell.reachy import PACKAGED_VIEW, store

            try:
                pfad = store().view_path()
            except Exception:  # noqa: BLE001 – ohne Einstellungen (Tests, Werkzeuge): nur die mitgelieferte Datei
                pfad = PACKAGED_VIEW if PACKAGED_VIEW.exists() else None
            if pfad is None:
                return None
            return cls.aus_datei(pfad)
        except Exception as exc:  # noqa: BLE001 – ohne Geometrie bleibt die Ersatzprüfung, nie ein Absturz
            log.info("Reachy-Geometrie nicht verfügbar (%s) – vorsichtige Ersatzprüfung", exc)
            return None


# ── Eine Stelle für Simulator und echten Reachy ──────────────────────────────────────────────────────────────────
_geo: Geometrie | None = None
_geladen = False
_sperre = threading.Lock()


def geometrie() -> Geometrie | None:
    """Einmal je Prozess laden (dauert gut eine halbe Sekunde); None = keine Geometrie, Ersatzprüfung."""
    global _geo, _geladen
    if not _geladen:
        with _sperre:
            if not _geladen:
                _geo, _geladen = Geometrie.aus_modell(), True
    return _geo


def geometrie_setzen(geo: Geometrie | None) -> None:
    """Für Tests und nach dem Nachladen von Pollens Modell: Geometrie austauschen (None = Ersatzprüfung)."""
    global _geo, _geladen
    with _sperre:
        _geo, _geladen = geo, True


def geometrie_neu_laden() -> None:
    global _geladen
    with _sperre:
        _geladen = False


_AUTO: Any = object()


def erreichbar(lage: dict[str, float], geo: Any = _AUTO) -> bool:
    """Ganze Kopflage (relativ zum Körper) erreichbar? Mit Pollens Geometrie genau, sonst vorsichtig."""
    g = geometrie() if geo is _AUTO else geo
    voll = {k: float(lage.get(k, 0.0) or 0.0) for k in ACHSEN}
    if any(abs(voll[k]) > GRENZE[k] + 1e-9 for k in ACHSEN):
        return False
    return g.erreichbar(voll) if g is not None else ersatz_erreichbar(voll)


def _mal(lage: dict[str, float], s: float, behalten: tuple[str, ...] = ()) -> dict[str, float]:
    return {k: v if k in behalten else v * s for k, v in lage.items()}


def _bisektion(lage: dict[str, float], ok: Any, behalten: tuple[str, ...]) -> dict[str, float]:
    lo, hi = 0.0, 1.0
    for _ in range(SCHRITTE):
        mitte = (lo + hi) / 2
        if ok(_mal(lage, mitte, behalten)):
            lo = mitte
        else:
            hi = mitte
    innen = _mal(lage, lo * LUFT, behalten)
    return innen if ok(innen) else _mal(lage, lo, behalten)


_letzte: tuple[tuple[float, ...], int, dict[str, float]] | None = None


def begrenzen(lage: dict[str, float], geo: Any = _AUTO) -> dict[str, float]:
    """Kopflage auf das Erreichbare zurücknehmen – so wenig wie möglich, immer Richtung Neutral.

    Erst je Achse in Pollens Grenzen; reicht das nicht, die Lage mit einem Faktor 0…1 verkleinern (Bisektion), dabei
    zuerst die Kopfdrehung behalten. Neutral ist immer erreichbar, also kommt immer eine gültige Lage heraus."""
    global _letzte
    g = geometrie() if geo is _AUTO else geo
    voll = _klemmen(lage)
    schluessel = tuple(round(voll[k], 6) for k in ACHSEN)
    if _letzte is not None and _letzte[0] == schluessel and _letzte[1] == id(g):
        return dict(_letzte[2])

    def ok(x: dict[str, float]) -> bool:
        return erreichbar(x, g)

    if ok(voll):
        out = voll
    elif voll["yaw"] and ok({**NEUTRAL, "yaw": voll["yaw"]}):
        out = _bisektion(voll, ok, ("yaw",))
    else:
        out = _bisektion(voll, ok, ())
    _letzte = (schluessel, id(g), dict(out))
    return out


def gerundet(lage: dict[str, float], stellen: int = 4, geo: Any = _AUTO) -> dict[str, float]:
    """Für Anzeige und set_target runden – aber nie über die Grenze: Liegt die Lage auf dem Rand des Erreichbaren
    und schöbe das Runden sie hinaus, bleibt sie ungerundet."""
    r = {k: round(float(v), stellen) for k, v in lage.items()}
    if r == lage or erreichbar(r, geo):
        return r
    return {k: float(v) for k, v in lage.items()}
