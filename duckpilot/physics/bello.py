"""Bello lernt laufen (seit 0.43, Fahrplan „Bello lernt“): Gangart mit einer Evolutionsstrategie im MuJoCo-Modell.

Bello (Petois Bittle X) läuft im einfachen Simulator gezeichnet, ohne Physik. Hier bekommt er ein MuJoCo-Modell aus
den Zahlen von Petois offenem Simulationsmodell (bittle_simple.xml, MIT – nur die Maße, keine Datei): Rumpfplatte,
vier Beine mit Schulter und Knie, Servos mit dem Drehmoment der P1S (≈ 0,27 N·m).

**Was gelernt wird:** keine neuronale Policy, sondern die Parameter seiner Gangart – Takt, Schrittlänge, Fußhub,
Anteil in der Luft, Ducken und wo die Füße stehen. Die Füße laufen wie in der 3D-Ansicht (`static/bittle3d.js`
`gangBeine`) auf Bahnen, die Beinwinkel kommen aus der Kinematik. Start ist die Handgangart (Traben).

**Wie:** Augmented Random Search (Mania, Guy & Recht 2018) – je Runde ein paar zufällige Richtungen im
Parameterraum, beide Vorzeichen ausprobiert, die besten Richtungen zählen. Jede Probe läuft mit etwas
Zufall (Reibung, Masse, Servo-Stärke, Startdrehung), damit die Gangart nicht nur auf genau einen Boden passt. Reine
NumPy, ein Rechenkern, ein paar Minuten.

**Nie schlechter:** Am Ende laufen Handgangart und Ergebnis auf neuen Prüfläufen (andere Zufallszahlen). Übernommen
wird nur, was insgesamt besser abschneidet, nicht öfter stürzt, nicht stärker wackelt und nicht langsamer ist. Sonst
bleibt alles, wie es war. Schneller als Petois Trab (≈ 1,8 Körperlängen je Sekunde, `TEMPO_GRENZE`) zählt nicht mehr,
und die Servos folgen höchstens so schnell wie echte (`SERVO_RAD_S`) – damit kein Modell-Wunder herauskommt.

Ehrlich: Das ist Simulation. Am echten Bittle X läuft weiter Petois eigene Gangart; die gelernte zeigt der einfache
Simulator (Gangart „Gelernt“), bis ein echter Hund sie prüfen kann.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

# Maße nach Petois Modell (wie bittle3d.js MASSE): Hüften ±7,35 cm vorn/hinten, ±4,85 cm seitlich, Oberschenkel 4,6 cm,
# Unterschenkel 5,5 cm, Rumpfplatte 12,7 × 9 × 3,4 cm. Gewicht und Servos nach Petois Angaben (≈ 290 g, P1S).
HUEFT_X, HUEFT_Y, HUEFT_Z = 0.0735, 0.0485, -0.006
OBEN, UNTEN, FUSS_R = 0.046, 0.055, 0.007
LAENGE, BREITE, DICKE = 0.127, 0.09, 0.034
RUMPF_KG, OBEN_KG, UNTEN_KG = 0.23, 0.008, 0.007
SERVO_NM, SERVO_KP, SERVO_KV = 0.27, 1.6, 0.025
SERVO_RAD_S = 10.0             # so schnell folgt ein P1S-Servo unter Last höchstens (0,07 s je 60° ohne Last)
STAND_S, STAND_K = 0.45, -0.85
BEINE = (("vl", HUEFT_X, HUEFT_Y, True), ("vr", HUEFT_X, -HUEFT_Y, True),
         ("hl", -HUEFT_X, HUEFT_Y, False), ("hr", -HUEFT_X, -HUEFT_Y, False))
VERSATZ = (0.0, math.pi, math.pi, 0.0)            # Traben: diagonale Paare
DT, TAKT_HZ = 0.002, 50
# Petoi: Traben höchstens etwa 1,8 Körperlängen je Sekunde (Bittle X ≈ 20 cm lang), schneller nur im Versuchsmodus.
# Schneller zählt deshalb nicht mehr – darüber gewinnt nur noch, wer ruhiger läuft.
TEMPO_GRENZE = 0.36

# Gangart-Parameter: Name → (Handgangart, kleinster, größter Wert)
PARAMETER: dict[str, tuple[float, float, float]] = {
    "takt_hz": (2.0, 1.0, 4.0),          # Schrittzyklen je Sekunde
    "schritt": (0.024, 0.008, 0.04),     # halbe Schrittlänge (m)
    "hub": (0.022, 0.008, 0.035),        # wie hoch der Fuß in der Luft geht (m)
    "luft": (0.45, 0.25, 0.6),           # Anteil des Zyklus in der Luft
    "ducken": (0.0, 0.0, 0.8),           # Beine stärker eingeknickt
    "vorn_x": (0.0, -0.02, 0.02),        # Standort der Vorderfüße (m, + = weiter vorn)
    "hinten_x": (0.0, -0.02, 0.02),      # Standort der Hinterfüße
}
HAND = {k: v[0] for k, v in PARAMETER.items()}


def mjcf() -> str:
    """Das MuJoCo-Modell als Text – Rumpf frei beweglich, je Bein Schulter und Knie mit Positions-Servo."""
    beine, servos = [], []
    for name, x, y, _vorn in BEINE:
        beine.append(f"""
      <body name="{name}_oben" pos="{x} {y} {HUEFT_Z}">
        <joint name="{name}_schulter" axis="0 -1 0" range="-1.6 1.6" damping="0.002" armature="0.00002"/>
        <geom type="capsule" fromto="0 0 0 0 0 {-OBEN}" size="0.006" mass="{OBEN_KG}"/>
        <body name="{name}_unten" pos="0 0 {-OBEN}">
          <joint name="{name}_knie" axis="0 -1 0" range="-2.4 2.4" damping="0.002" armature="0.00002"/>
          <geom type="capsule" fromto="0 0 0 0 0 {-UNTEN}" size="0.005" mass="{UNTEN_KG}"/>
          <geom name="{name}_fuss" type="sphere" pos="0 0 {-UNTEN}" size="{FUSS_R}" mass="0.001" friction="1.0 0.02 0.001"/>
        </body>
      </body>""")
        for gelenk in ("schulter", "knie"):
            servos.append(f'<position name="{name}_{gelenk}" joint="{name}_{gelenk}" kp="{SERVO_KP}" kv="{SERVO_KV}" '
                          f'forcerange="{-SERVO_NM} {SERVO_NM}" forcelimited="true"/>')
    return f"""<mujoco model="bello">
  <compiler angle="radian"/>
  <option timestep="{DT}" integrator="implicitfast"/>
  <worldbody>
    <geom name="boden" type="plane" size="5 5 0.1" friction="1.0 0.02 0.001"/>
    <body name="rumpf" pos="0 0 0.12">
      <freejoint/>
      <geom type="box" size="{LAENGE / 2} {BREITE / 2 * 0.82} {DICKE / 2}" mass="{RUMPF_KG}"/>
      {"".join(beine)}
    </body>
  </worldbody>
  <actuator>
    {"".join(servos)}
  </actuator>
</mujoco>"""


def bein(x: float, z: float, vorn: bool) -> tuple[float, float]:
    """Schulter und Knie für einen Fußpunkt relativ zur Hüfte (x vorn, z oben) – Knie zur Körpermitte."""
    d2 = x * x + z * z
    c = max(-1.0, min(1.0, (d2 - OBEN * OBEN - UNTEN * UNTEN) / (2 * OBEN * UNTEN)))
    k = (-1.0 if vorn else 1.0) * math.acos(c)
    s = math.atan2(x, -z) - math.atan2(UNTEN * math.sin(k), OBEN + UNTEN * math.cos(k))
    return s, k


def fuss(s: float, k: float) -> tuple[float, float]:
    return OBEN * math.sin(s) + UNTEN * math.sin(s + k), -OBEN * math.cos(s) - UNTEN * math.cos(s + k)


def _schritt(p: float, luft: float) -> tuple[float, float]:
    """Ein Bein im Schritt: (vor −1 … +1, Hub 0 … 1) – in der Luft im Bogen nach vorn, am Boden gleichmäßig zurück."""
    u = ((p % (2 * math.pi)) + 3 * math.pi) % (2 * math.pi) - math.pi
    a = math.pi * luft
    if abs(u) < a:
        q = (u + a) / (2 * a)
        return -math.cos(math.pi * q), math.sin(math.pi * q)
    t = (((u - a) % (2 * math.pi)) + 2 * math.pi) % (2 * math.pi) / (2 * math.pi - 2 * a)
    return 1 - 2 * t, 0.0


def gelenke(p: dict[str, float], phase: float) -> np.ndarray:
    """Zielwinkel aller acht Servos (vl, vr, hl, hr je Schulter, Knie) beim Zyklus-Winkel `phase`."""
    out = []
    for i, (_, _, _, vorn) in enumerate(BEINE):
        seite = 1.0 if vorn else -1.0
        x0, z0 = fuss((STAND_S + 0.25 * p["ducken"]) * seite, (STAND_K - 0.5 * p["ducken"]) * seite)
        x0 += p["vorn_x"] if vorn else p["hinten_x"]
        vor, hub = _schritt(phase + VERSATZ[i], p["luft"])
        out += bein(x0 + p["schritt"] * vor, z0 + p["hub"] * hub, vorn)
    return np.array(out)


@dataclass
class Lauf:
    tempo: float          # m/s vorwärts
    seitlich: float       # m/s quer
    neigung: float        # mittlere Neigung (rad)
    gestuerzt: bool

    def punkte(self) -> float:
        return (min(self.tempo, TEMPO_GRENZE) - 0.5 * abs(self.seitlich) - 0.3 * self.neigung
                - (0.3 if self.gestuerzt else 0.0))


class Welt:
    """Ein MuJoCo-Modell, wiederverwendet für viele Läufe."""

    def __init__(self) -> None:
        import mujoco

        self.mj = mujoco
        self.model = mujoco.MjModel.from_xml_string(mjcf())
        self.data = mujoco.MjData(self.model)
        self._reibung = self.model.geom_friction[:, 0].copy()
        self._masse = self.model.body_mass.copy()
        self._kp = self.model.actuator_gainprm[:, 0].copy()

    def lauf(self, p: dict[str, float], seed: int, sekunden: float = 5.0) -> Lauf:
        mj, m, d = self.mj, self.model, self.data
        rng = np.random.default_rng(seed)
        m.geom_friction[:, 0] = self._reibung * rng.uniform(0.7, 1.2)
        m.body_mass[:] = self._masse * rng.uniform(0.9, 1.1)
        kp = self._kp * rng.uniform(0.85, 1.1)
        m.actuator_gainprm[:, 0] = kp
        m.actuator_biasprm[:, 1] = -kp
        mj.mj_resetData(m, d)
        stand = gelenke({**p, "schritt": 0.0, "hub": 0.0}, 0.0)
        d.qpos[7:] = stand
        gier = rng.uniform(-0.1, 0.1)
        d.qpos[3:7] = [math.cos(gier / 2), 0.0, 0.0, math.sin(gier / 2)]
        d.qpos[2] = 0.11
        d.ctrl[:] = stand
        for _ in range(int(0.6 / DT)):                  # hinstellen
            mj.mj_step(m, d)
        start = d.qpos[:2].copy()
        richtung = np.array([math.cos(gier), math.sin(gier)])
        schritte, je = int(sekunden * TAKT_HZ), int(1 / (TAKT_HZ * DT))
        neigung, gestuerzt, t = 0.0, False, 0.0
        for n in range(schritte):
            # sanft anlaufen: Schrittlänge in der ersten halben Sekunde hochziehen
            weich = min(1.0, n / (0.5 * TAKT_HZ))
            ziel = gelenke({**p, "schritt": p["schritt"] * weich}, 2 * math.pi * p["takt_hz"] * t)
            d.ctrl[:] += np.clip(ziel - d.ctrl, -SERVO_RAD_S / TAKT_HZ, SERVO_RAD_S / TAKT_HZ)   # Servo-Tempo
            for _ in range(je):
                mj.mj_step(m, d)
            t += 1 / TAKT_HZ
            w, x, y, z = d.qpos[3:7]
            oben = 1 - 2 * (x * x + y * y)               # z-Anteil der Rumpf-Hochachse
            neigung += math.acos(max(-1.0, min(1.0, oben)))
            if oben < 0.6 or d.qpos[2] < 0.03:
                gestuerzt = True
                break
        weg = d.qpos[:2] - start
        dauer = max(1e-3, t)
        quer = np.array([-richtung[1], richtung[0]])
        return Lauf(float(weg @ richtung / dauer), float(weg @ quer / dauer), neigung / max(1, n + 1), gestuerzt)


def _aus(v: np.ndarray) -> dict[str, float]:
    return {k: lo + (hi - lo) * float(np.clip(x, 0.0, 1.0)) for (k, (_, lo, hi)), x in zip(PARAMETER.items(), v)}


def _ein(p: dict[str, float]) -> np.ndarray:
    return np.array([(p[k] - lo) / (hi - lo) for k, (_, lo, hi) in PARAMETER.items()])


def pruefen(welt: Welt, p: dict[str, float], seeds: range) -> dict[str, float]:
    laeufe = [welt.lauf(p, s) for s in seeds]
    return {"tempo": round(float(np.mean([x.tempo for x in laeufe])), 4),
            "stuerze": sum(x.gestuerzt for x in laeufe),
            "neigung": round(float(np.mean([x.neigung for x in laeufe])), 4),
            "punkte": round(float(np.mean([x.punkte() for x in laeufe])), 4), "laeufe": len(laeufe)}


PRUEF_SEED = 10_000


def lernen(runden: int = 30, richtungen: int = 6, beste: int = 3, schritt: float = 0.05, rauschen: float = 0.06,
           seeds_je_probe: int = 2, pruef_laeufe: int = 8, seed: int = 0, start: dict[str, float] | None = None,
           melden: Callable[[dict[str, Any]], None] | None = None,
           abbrechen: Callable[[], bool] | None = None) -> dict[str, Any]:
    """ARS über die Gangart-Parameter. Gibt Bericht und Ergebnis zurück; `gelernt` nur, wenn es auf neuen Prüfläufen
    in allem mindestens so gut und schneller ist als der Start."""
    t0 = time.monotonic()
    welt = Welt()
    rng = np.random.default_rng(seed)
    start = {**HAND, **(start or {})}
    theta = _ein(start)
    probe = 0

    def wert(v: np.ndarray) -> float:
        return float(np.mean([welt.lauf(_aus(v), probe * 100 + i).punkte() for i in range(seeds_je_probe)]))

    verlauf = []
    for runde in range(runden):
        if abbrechen and abbrechen():
            break
        probe += 1
        deltas = rng.standard_normal((richtungen, len(theta)))
        plus = np.array([wert(theta + rauschen * dlt) for dlt in deltas])
        minus = np.array([wert(theta - rauschen * dlt) for dlt in deltas])
        oben = np.argsort(-np.maximum(plus, minus))[:beste]
        streu = float(np.std(np.concatenate([plus[oben], minus[oben]]))) or 1.0
        theta = np.clip(theta + schritt / (beste * streu) * ((plus[oben] - minus[oben]) @ deltas[oben]), 0.0, 1.0)
        verlauf.append(round(float(np.mean(np.maximum(plus, minus))), 4))
        if melden:
            melden({"runde": runde + 1, "runden": runden, "punkte": verlauf[-1]})
    ergebnis = _aus(theta)
    seeds = range(PRUEF_SEED, PRUEF_SEED + pruef_laeufe)
    vorher, nachher = pruefen(welt, start, seeds), pruefen(welt, ergebnis, seeds)
    besser = (nachher["punkte"] > vorher["punkte"] + 0.01 and nachher["stuerze"] <= vorher["stuerze"]
              and nachher["neigung"] <= vorher["neigung"] * 1.1 + 0.005
              and min(nachher["tempo"], TEMPO_GRENZE) >= min(vorher["tempo"], TEMPO_GRENZE) * 0.95)
    return {"gelernt": besser, "parameter": {k: round(v, 4) for k, v in (ergebnis if besser else start).items()},
            "vorher": vorher, "nachher": nachher, "runden": len(verlauf), "verlauf": verlauf,
            "dauer_s": round(time.monotonic() - t0, 1)}
