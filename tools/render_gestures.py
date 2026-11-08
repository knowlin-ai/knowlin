#!/usr/bin/env python3
"""Rendert die Laute zu duckpilots eigenen Gesten – im Stil von Pollens Emotions-Tönen.

    python tools/render_gestures.py <pfad>/microduck_emotions

Pollens Sound-Design für die 14 Emotionen (Tag `workshop-2026-10-07` in
pollen-robotics/microduck_emotions, Apache-2.0) folgt ein paar Regeln, die hier übernommen sind:

- dieselbe Ente: `quack.py` mit der Persönlichkeit des Roboters (Seed 4145077059, Tonhöhe um 238 Hz),
- je Gefühl eine eigene Stimmfärbung (HAPPY, ASK, COO, YES, NO, HA, ANG, MUFFLED – Werte aus Pollens
  `make_*.py`),
- Gleittöne statt harter Sprünge, Laute genau auf den Takten der Bewegung, der Schnabel öffnet mit dem Ton,
- lieber leiser als zu laut.

Jede Geste bekommt mehrere Varianten (Tonhöhe, Länge, Phrasierung), damit sie nicht jedes Mal gleich
klingt. Ausgabe: duckpilot/server/static/sounds/gesten/<geste>_<n>.ogg und index.json mit Dauer und
Schnabel-Hüllkurve (10 Hz) je Datei. Braucht numpy, scipy und ffmpeg – nur beim Rendern.
"""

from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

import numpy as np

VARIANTS = 4
OUT = Path(__file__).resolve().parent.parent / "duckpilot" / "server" / "static" / "sounds" / "gesten"


def load_quack(folder: Path):
    spec = importlib.util.spec_from_file_location("quack", folder / "quack.py")
    q = importlib.util.module_from_spec(spec)
    sys.modules["quack"] = q
    spec.loader.exec_module(q)
    return q


class Voice:
    """Pollens Stimmfärbungen als kleine Bausteine, je Variante leicht verstimmt."""

    def __init__(self, q, name: str, variant: int) -> None:
        from scipy.signal import butter, lfilter

        self.q = q
        self._butter, self._lfilter = butter, lfilter
        self.p = q.Personality(q.ROBOT_SEED)
        self.name, self.v = name, variant
        self.rng = np.random.default_rng(zlib.crc32(f"{name}/{variant}".encode()))
        self.k = 2 ** (self.rng.uniform(-1.6, 1.6) / 12)          # Tonhöhe der Variante
        self.d = self.rng.uniform(0.9, 1.12)                      # Länge der Silben
        self.n = 0
        p = self.p
        ST = 2 ** (1 / 12)
        self.ST = ST
        # Pollens Färbungen (make_excited / make_curious / make_yes / make_no / make_laugh / make_angry /
        # make_closed / make_synced_v6_sad)
        self.HAPPY = dict(quackiness=0.75, breath=0.03, vibrato_depth=0.12, attack_sharpness=0.65, brightness=0.35)
        self.ASK = dict(quackiness=0.7, breath=0.04, vibrato_depth=0.15, attack_sharpness=0.5)
        self.YES = dict(quackiness=0.75, breath=0.03, vibrato_depth=0.12, attack_sharpness=0.6)
        self.NO = dict(quackiness=0.7, breath=0.04, vibrato_depth=0.15, attack_sharpness=0.5)
        self.NASAL = dict(quackiness=0.95, breath=0.02, vibrato_depth=0.2, attack_sharpness=0.3, nasal=1.0, am_depth=0.5, tilt=1.6)
        self.HA = dict(quackiness=0.95, breath=0.02, vibrato_depth=0.05, attack_sharpness=0.9, brightness=0.4, am_depth=0.45)
        self.ANG = dict(tilt=1.25, brightness=0.55, vibrato_rate_hz=0.0, vibrato_depth=0.0, attack_sharpness=1.0,
                        breath=0.03, quackiness=1.0, am_depth=0.8, am_rate_hz=28.0, jitter_depth=0.12)
        self.COO = dict(breath=max(p.breath, 0.12) + 0.10, quackiness=p.quackiness * 0.25, am_rate_hz=p.am_rate_hz * 0.30,
                        vibrato_rate_hz=p.vibrato_rate_hz * 0.45, vibrato_depth=p.vibrato_depth * 0.7)
        self.MUFFLED = dict(brightness=0.05, nasal=1.0, quackiness=0.6, breath=0.02, vibrato_depth=0.25,
                            attack_sharpness=0.2, tilt=2.6, am_depth=0.35)
        self.GRUMBLE = dict(self.MUFFLED, quackiness=0.95, am_depth=0.55, am_rate_hz=19.0, vibrato_depth=0.3, vibrato_rate_hz=4.5)
        self.DREAMY = dict(self.COO, vibrato_depth=max(p.vibrato_depth, 0.3) * 0.9, vibrato_rate_hz=5.0, breath=0.18)

    # ── Grundbausteine ────────────────────────────────────────────────────
    def _rng(self):
        self.n += 1
        return self.p.variant_rng(f"g/{self.name}", self.v * 1000 + self.n)

    def chance(self, x: float) -> bool:
        return bool(self.rng.random() < x)

    def pick(self, *options):
        return options[int(self.rng.integers(0, len(options)))]

    def raw(self, dur, contour, env, mods, level, **kw):
        q = self.q
        sig = q.quack(self.p, dur, contour, env, mods=mods, rng=self._rng(), **kw)
        return q.normalise(sig, level)

    def lowpass(self, x, fc=900.0):
        b, a = self._butter(2, fc / (self.q.SR / 2))
        return self._lfilter(b, a, x)

    # ── Laute (f in Hz bei der Roboterstimme; die Variante verschiebt alles um k) ──
    def happy(self, f0, rise, dur=0.2, level=-4.0):
        f0, dur = f0 * self.k, dur * self.d
        return self.raw(dur, [(0.0, f0 * 0.93), (0.03, f0), (dur, f0 * self.ST ** rise)], ("expdecay", 0.008, dur * 0.55),
                        self.HAPPY, level)

    def ask(self, f0, rise, dur=0.22, level=-4.0):
        f0, dur = f0 * self.k, dur * self.d
        return self.raw(dur, [(0.0, f0 * 0.95), (0.05, f0), (dur, f0 * self.ST ** rise)], ("expdecay", 0.015, dur * 0.6),
                        self.ASK, level)

    def yes(self, f0, fall, dur=0.26, level=-4.0, snappy=False):
        f0, dur = f0 * self.k, dur * self.d
        mods = dict(self.YES, attack_sharpness=0.9, quackiness=0.9) if snappy else self.YES
        return self.raw(dur, [(0.0, f0 * 0.97), (0.04, f0 * 1.03), (0.12, f0), (dur, f0 * self.ST ** -fall)],
                        ("expdecay", 0.012, dur * (0.4 if snappy else 0.55)), mods, level)

    def syl(self, f0, f1, dur, mods=None, level=-4.0, decay=0.5, attack=0.012):
        f0, f1, dur = f0 * self.k, f1 * self.k, dur * self.d
        return self.raw(dur, [(0.0, f0 * 0.97), (0.03, f0), (dur, f1)], ("expdecay", attack, dur * decay),
                        mods or self.NO, level)

    def ha(self, f0, fall=1.5, dur=0.12, level=-4.0):
        f0 = f0 * self.k
        return self.raw(dur, [(0.0, f0 * 1.04), (0.02, f0), (dur, f0 / self.ST ** fall)], ("expdecay", 0.006, dur * 0.45),
                        self.HA, level, click_gain=0.25)

    def coo(self, dur, f_start, f_end, level=-7.0, mods=None, rise_first=0.0):
        """Pollens Coo-Stimme (make_synced_v6_sad) auf einem weichen Gleitton beliebiger Länge."""
        q = self.q
        dur = dur * self.d
        t = q.t_axis(dur)
        x = t / dur
        down = 0.5 - 0.5 * np.cos(np.pi * x)                       # halbe Kosinus-Rampe wie der Kopf
        semis = 12 * math.log2(f_end / f_start)
        lift = 1 + rise_first * np.sin(np.pi * np.clip(x, 0, 0.5) * 2) ** 2
        freq = f_start * self.k * 2 ** (semis * down / 12) * lift
        env = q.bell(t, 0.26 * dur, 0.30 * dur)
        return q.normalise(q.quack(self.p, dur, freq, env, mods=mods or self.COO, rng=self._rng()), level)

    def glide(self, dur, points, mods, level=-5.0, env=None):
        """Freier Gleitton über (Zeitanteil, Hz)-Punkte mit weicher Hülle."""
        dur = dur * self.d
        pts = [(a * dur, f * self.k) for a, f in points]
        return self.raw(dur, pts, env or ("bell", 0.18 * dur, 0.32 * dur), mods, level)

    def bark(self, hz, dur=0.16, level=-5.0, fall=0.9):
        hz = hz * self.k
        return self.raw(dur, [(0.0, hz), (0.03, hz * 1.04), (dur, hz * fall)], ("expdecay", 0.004, dur * 0.55),
                        self.ANG, level, click_gain=0.4, crackle=0.08)

    def muffled(self, dur, points, mods=None, level=-7.0, fc=950.0, attack=0.03, decay=0.65):
        q = self.q
        dur = dur * self.d
        pts = [(a * dur, f * self.k) for a, f in points]
        sig = q.quack(self.p, dur, pts, ("expdecay", attack, dur * decay), mods=mods or self.MUFFLED, rng=self._rng())
        return q.normalise(self.lowpass(sig, fc), level)

    def nibble(self, level=-14.0):
        """Ein leises Knabbern am Gefieder: Pollens Peck, kurz und dumpf."""
        q = self.q
        dur = 0.07 + 0.03 * self.rng.random()
        t = q.t_axis(dur)
        f0 = self.p.pitch_center_hz * 0.5 * self.k
        rng = self._rng()
        body = q.voice(self.p, t, q.lerp(t, [(0.0, f0 * 1.4), (0.02, f0), (dur, f0 * 0.8)]), rng, 0.3, 0.5) * q.expdecay(t, 0.002, dur * 0.3)
        body += 0.6 * q.click(len(t), rng.numpy(), int(0.004 * q.SR))
        return q.normalise(self.lowpass(body, 2200.0), level)

    def breath(self, dur, level=-18.0, fc=1800.0, rise=False):
        """Ein Hauch – zum Seufzen, Gähnen, Niesen."""
        q = self.q
        t = q.t_axis(dur)
        noise = q.pink_noise(len(t), self.rng)
        env = q.bell(t, (0.7 if rise else 0.2) * dur, (0.25 if rise else 0.6) * dur)
        return q.normalise(self.lowpass(noise * env, fc), level)


# ── Partituren: (Zeit, Laut) auf den Takten der Gesten in duckpilot/motion/behaviors.py ──
# Laute setzen ~0,06 s vor dem Keyframe ein, an dem der Schnabel am weitesten offen ist.
def freude(V):
    out = [(0.04, V.happy(228, 3, 0.16, -6))]
    out += [(0.24, V.happy(240, 5)), (0.84, V.happy(262, 7, 0.19))]
    if V.chance(0.6):
        out.append((1.14, V.happy(300, 4, 0.12, -7)))
    return out


def traurig(V):
    a, b = V.pick((228, 150), (214, 148), (240, 158), (205, 140))
    return [(0.15, V.coo(1.5, a, b, -8))]


def neugierig(V):
    style = V.v % 3
    if style == 0:
        return [(0.44, V.ask(230, 5)), (1.74, V.ask(252, 7))]
    if style == 1:
        return [(0.44, V.ask(222, 1.5, 0.16)), (1.74, V.ask(238, 9, 0.3))]
    return [(0.44, V.ask(226, 8, 0.32)), (1.80, V.ask(262, 4, 0.14, -8))]


def ueberrascht(V):
    out = [(0.08, V.glide(0.34, [(0, 250), (0.25, 420), (1, 340)], V.HAPPY, -4, ("expdecay", 0.006, 0.2)))]
    out.append((0.92, V.glide(0.28, [(0, 300), (0.4, 330), (1, 250)], V.ASK, -9)))
    return out


def muede(V):
    yawn = V.glide(1.1, [(0, 185), (0.35, 255), (1, 150)], dict(V.COO, breath=0.3), -8, ("bell", 0.35, 0.4))
    out = [(0.82, yawn), (0.86, V.breath(1.0, -20))]
    out.append((2.55, V.coo(1.2, 190, 150, -12)))
    return out


def wuetend(V):
    out = []
    if V.chance(0.5):
        out.append((0.0, V.muffled(0.28, [(0, 150), (1, 200)], V.GRUMBLE, -12)))
    out += [(0.24, V.bark(240, 0.16)), (0.64, V.bark(225, 0.2, -6, 0.86))]
    return out


def ja(V):
    if V.chance(0.5):
        return [(0.18, V.yes(250, 3.0, 0.28))]
    return [(0.18, V.yes(255, 5.0, 0.18, snappy=True)), (0.68, V.yes(245, 2.0, 0.14, -8, snappy=True))]


def nein(V):
    semis = V.pick(-3, -5, -5, -7)
    f0 = 250
    nasal = V.chance(0.3)
    mods = V.NASAL if nasal else V.NO
    return [(0.2, V.syl(f0, f0 * 2 ** (-0.5 / 12), 0.2, mods)),
            (0.52, V.syl(f0 * 2 ** (semis / 12), f0 * 2 ** ((semis - 3) / 12), 0.32, mods, -5))]


def begruessen(V):
    out = [(0.30, V.glide(0.36, [(0, 220), (0.35, 290), (1, 250)], V.HAPPY, -4, ("expdecay", 0.01, 0.22)))]
    if V.chance(0.6):
        out.append((0.70, V.happy(250, -2, 0.18, -6)))
    out.append((1.55, V.coo(0.6, 230, 205, -11)))
    return out


def begeistert(V):
    beats = [0.1, 0.57, 1.0]
    out = [(t, V.happy(225 * V.ST ** (2 * i), 5 + i, 0.2 - 0.02 * i)) for i, t in enumerate(beats)]
    out.append((0.34, V.happy(250, 4, 0.11, -9)))
    out.append((0.79, V.happy(270, 5, 0.11, -9)))
    return out


def frustriert(V):
    out = [(0.25, V.glide(0.9, [(0, 300), (0.15, 310), (1, 230)], V.NO, -6, ("expdecay", 0.02, 0.6)))]
    out.append((1.36, V.muffled(0.3, [(0, 190), (0.2, 200), (1, 165)], V.GRUMBLE, -7)))
    return out


def erleichtert(V):
    out = [(0.45, V.breath(0.5, -22, rise=True))]
    out.append((1.0, V.coo(0.8, 270, 190, -8)))
    out.append((1.74, V.happy(255, 4, 0.13, -8)))
    return out


def stolz(V):
    out = [(0.34, V.glide(0.36, [(0, 230), (0.3, 245), (1, 300)], V.HAPPY, -4, ("expdecay", 0.01, 0.25)))]
    out.append((1.64, V.yes(265, 4.0, 0.24)))
    return out


def einfuehlsam(V):
    out = [(0.8, V.coo(1.0, 205, 192, -11, rise_first=0.06))]
    if V.chance(0.5):
        out.append((2.9, V.coo(0.6, 215, 200, -14)))
    return out


def schuetteln(V):
    beats = [0.05, 0.29, 0.53, 0.75, 0.87, 1.0]
    out = []
    for i, t in enumerate(beats):
        f = (300 - 9 * i) * (1.06 if i >= 3 else 1.0)
        out.append((t, V.ha(f, V.pick(1.0, 1.5, 2.0), 0.1 + 0.02 * V.rng.random(), -4.5 - 0.4 * i)))
    out.insert(0, (0.0, V.breath(0.6, -24, fc=3500)))      # Federrascheln
    return out


def trotzig(V):
    out = [(0.30, V.muffled(0.26, [(0, 210), (0.3, 220), (1, 180)], V.NASAL, -6))]
    out.append((1.24, V.syl(255, 240, 0.18, V.NASAL, -5)))
    out.append((2.34, V.ask(220, 4, 0.24, -9)))
    return out


def stolpern(V):
    out = [(0.06, V.glide(0.42, [(0, 260), (0.25, 380), (1, 220)], V.HAPPY, -4, ("expdecay", 0.006, 0.28)))]
    out.append((0.5, V.ha(270, 2.0, 0.12, -9)))
    return out


def verlegen(V):
    out = [(0.45, V.muffled(0.4, [(0, 205), (0.5, 215), (1, 195)], V.MUFFLED, -12, fc=1100))]
    out.append((1.84, V.ask(240, 3, 0.15, -10)))
    return out


def staunen(V):
    out = [(0.18, V.glide(0.75, [(0, 215), (1, 320)], V.ASK, -5, ("bell", 0.12, 0.3)))]
    out.append((1.72, V.glide(0.6, [(0, 280), (0.4, 360), (1, 270)], V.HAPPY, -6, ("bell", 0.08, 0.3))))
    return out


# ── Albernheiten im Leerlauf ───────────────────────────────────────────────
def schwanz_jagen(V):
    out = [(0.0, V.ask(230, 6, 0.24, -6))]
    out += [(1.45, V.happy(270, 5, 0.13, -6)), (2.95, V.happy(285, 6, 0.13, -6)), (4.6, V.happy(300, 4, 0.12, -7))]
    out.append((6.55, V.glide(0.5, [(0, 300), (0.5, 230), (1, 290)], V.ASK, -6)))      # schwindelig: „hä?“
    return out


def boden_picken(V):
    out = [(t, V.nibble(-9)) for t in (0.27, 0.67, 1.07)]
    out.append((2.05, V.ask(228, 5, 0.2, -8)))
    return out


def selbstgespraech(V):
    out, t = [], 0.26
    for _ in range(V.pick(5, 6, 7)):
        f = V.rng.uniform(205, 290)
        d = V.rng.uniform(0.07, 0.14)
        out.append((t, V.syl(f, f * 2 ** (V.rng.uniform(-3, 3) / 12), d, V.pick(V.NO, V.HAPPY, V.ASK), -8)))
        t += d + V.rng.uniform(0.04, 0.12)
        if t > 1.6:
            break
    out.append((min(t + 0.05, 1.75), V.coo(0.35, 230, 200, -12)))
    return out


def wackeln(V):
    out = [(0.36, V.happy(255, 3, 0.12, -7)), (0.76, V.happy(270, 3, 0.12, -7))]
    out.append((1.2, V.glide(0.45, [(0, 260), (0.6, 360), (1, 330)], V.HAPPY, -6, ("bell", 0.05, 0.2))))
    return out


# ── Charakter-Gesten (duckpilot/motion/character.py) ─────────────────────
def gaehnen(V):
    yawn = V.glide(1.3, [(0, 180), (0.3, 270), (0.8, 200), (1, 150)], dict(V.COO, breath=0.35), -8, ("bell", 0.4, 0.45))
    return [(0.45, V.breath(0.5, -24, rise=True)), (0.75, yawn)]


def doesen(V):
    out = [(0.8, V.breath(1.6, -26, fc=900)), (2.0, V.coo(0.9, 175, 150, -16))]
    out.append((3.15, V.glide(0.22, [(0, 240), (0.4, 330), (1, 300)], V.ASK, -7, ("expdecay", 0.005, 0.15))))   # huch!
    return out


def seufzen(V):
    return [(0.3, V.breath(0.6, -22, rise=True)), (0.75, V.coo(1.0, 240, 180, -10))]


def himmel_gucken(V):
    return [(0.6, V.coo(1.4, 210, 245, -12, mods=V.DREAMY, rise_first=0.04))]


def gefieder_putzen(V):
    out = []
    for t in (0.9, 1.15, 1.45, 1.7, 2.9, 3.15, 3.4):
        if V.chance(0.85):
            out.append((t + V.rng.uniform(-0.03, 0.03), V.nibble(-16)))
    out.append((4.25, V.muffled(0.35, [(0, 215), (0.5, 225), (1, 205)], V.MUFFLED, -14, fc=1100)))   # „mm“
    return out


def wippen(V):
    out = []
    for i, t in enumerate((0.15, 0.65, 1.15, 1.65)):
        if i % 2 == 0 or V.chance(0.5):
            out.append((t, V.happy(250 + 12 * i, 3, 0.11, -9)))
    return out


def aufhorchen(V):
    return [(0.18, V.ask(235, 6, 0.2, -6)), (1.2, V.muffled(0.3, [(0, 215), (1, 270)], V.MUFFLED, -11, fc=1100))]


def umherspaehen(V):
    return [(0.25, V.happy(260, 3, 0.1, -10)), (1.0, V.ask(245, 4, 0.16, -9))]


def traellern(V):
    """Eine kleine Melodie: Dur-Dreiklang auf und ab, im Takt der Kopfbewegung."""
    steps = V.pick([0, 4, 7, 12, 7], [0, 4, 7, 4, 0], [7, 4, 0, 4, 7, 12], [0, 2, 4, 7, 4])
    base = 230
    out, t = [], 0.2
    for s in steps:
        d = V.pick(0.16, 0.2, 0.24)
        f = base * 2 ** (s / 12)
        out.append((t, V.glide(d, [(0, f * 0.98), (0.3, f), (1, f * 1.01)], dict(V.COO, quackiness=0.35, breath=0.06), -9,
                               ("bell", 0.25 * d, 0.3 * d))))
        t += d + 0.06
    return out


def hibbeln(V):
    out = [(t, V.happy(V.rng.uniform(250, 310), V.pick(2, 4, 6), 0.09, -11)) for t in (0.2, 0.45, 0.95, 1.2)]
    return out


def mustern(V):
    return [(2.6, V.syl(230, 215, 0.2, V.MUFFLED, -12))]      # „hm.“


def haltung(V):
    return [(0.5, V.breath(0.4, -26, rise=True)), (1.0, V.yes(240, 1.5, 0.16, -11))]


def nicken(V):
    return [(0.26, V.yes(248, 2.5, 0.2, -8))]


def niesen(V):
    build = [(0.05, V.ask(230, 2, 0.16, -10)), (0.35, V.ask(245, 3, 0.18, -9)), (0.62, V.ask(262, 4, 0.2, -8))]
    burst = V.breath(0.25, -8, fc=5000)
    tschiu = V.glide(0.22, [(0, 380), (0.2, 330), (1, 240)], V.HA, -4, ("expdecay", 0.003, 0.12))
    return build + [(0.96, burst), (0.98, tschiu)]


def schluckauf(V):
    out = []
    for i, t in enumerate((0.25, 1.15, 2.0)):
        out.append((t, V.raw(0.09, [(0, 330 * V.k), (0.09, 380 * V.k)], ("expdecay", 0.003, 0.05), V.HA, -6 - i, click_gain=0.3)))
    out.append((2.6, V.ask(230, 3, 0.2, -10)))
    return out


def erschrecken(V):
    out = [(0.12, V.glide(0.3, [(0, 260), (0.2, 400), (1, 330)], V.HAPPY, -5, ("expdecay", 0.005, 0.2)))]
    out.append((1.6, V.muffled(0.4, [(0, 210), (0.5, 220), (1, 190)], V.MUFFLED, -11, fc=1100)))
    return out


SCORES = {fn.__name__: fn for fn in (
    freude, traurig, neugierig, ueberrascht, muede, wuetend, ja, nein, begruessen, begeistert, frustriert,
    erleichtert, stolz, einfuehlsam, schuetteln, trotzig, stolpern, verlegen, staunen,
    schwanz_jagen, boden_picken, selbstgespraech, wackeln,
    gaehnen, doesen, seufzen, himmel_gucken, gefieder_putzen, wippen, aufhorchen, umherspaehen, traellern, hibbeln,
    mustern, haltung, nicken, niesen, schluckauf, erschrecken,
)}


def mixdown(q, parts) -> np.ndarray:
    end = max(t + len(s) / q.SR for t, s in parts) + 0.05
    out = np.zeros(int(end * q.SR) + 1)
    for t, s in parts:
        i = int(round(max(0.0, t) * q.SR))
        n = min(len(s), len(out) - i)
        out[i:i + n] += s[:n]
    peak = float(np.max(np.abs(out))) or 1.0
    ceiling = 10 ** (-3.0 / 20)                 # nie lauter als Pollens Emotionen (-3 dBFS)
    if peak > ceiling:
        out *= ceiling / peak
    return out


def mouth_track(q, sig: np.ndarray) -> list[float]:
    """Schnabel aus der Lautstärke (10 Hz), wie Pollen den Schnabel an den Ton koppelt."""
    hop = int(0.1 * q.SR)
    rms = np.array([math.sqrt(float(np.mean(sig[i:i + hop] ** 2)) + 1e-12) for i in range(0, len(sig), hop)])
    db = 20 * np.log10(rms + 1e-9)
    m = np.clip((db + 38.0) / 26.0, 0.0, 1.0)            # -38 dB zu, -12 dB weit offen
    m = np.maximum(m, np.concatenate([[0.0], m[:-1]]) * 0.6)   # kurz nachklingen lassen
    return [round(float(x), 2) for x in m]


def decoded_peak(path: Path) -> float:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "48000", "-"],
                         capture_output=True, check=True).stdout
    return float(np.max(np.abs(np.frombuffer(raw, np.float32)))) if raw else 0.0


def to_ogg(q, sig: np.ndarray, dest: Path) -> None:
    """Opus mit Kontrolle: Der Encoder erzeugt bei manchen hohen Gleittönen einen Knack-Ausreißer.
    Dann mit höherer Bitrate neu – bis der dekodierte Ton nicht lauter ist als das Original."""
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "x.wav"
        q.write_wav(wav, sig, peak_dbfs=None)
        limit = float(np.max(np.abs(sig))) * 1.25 + 0.02
        for rate in ("64k", "96k", "128k"):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-c:a", "libopus", "-b:a", rate,
                            "-ar", "48000", str(dest)], check=True)
            if decoded_peak(dest) <= limit:
                return
        raise RuntimeError(f"{dest.name}: Opus-Ausreißer lässt sich nicht vermeiden")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    q = load_quack(Path(sys.argv[1]).expanduser())
    only = set(sys.argv[2:])
    OUT.mkdir(parents=True, exist_ok=True)
    index_path = OUT / "index.json"
    index = json.loads(index_path.read_text()) if (only and index_path.exists()) else {
        "quelle": "pollen-robotics/microduck_emotions quack.py, Stimmfärbungen aus dem Tag workshop-2026-10-07 (Apache-2.0)",
        "gesten": {}}
    for name, fn in SCORES.items():
        if only and name not in only:
            continue
        for old in OUT.glob(f"{name}_*.ogg"):
            old.unlink()
        entry = {"dateien": [], "dauer": {}, "mund": {}}
        for v in range(VARIANTS):
            V = Voice(q, name, v)
            sig = mixdown(q, fn(V))
            fname = f"{name}_{v}"
            to_ogg(q, sig, OUT / f"{fname}.ogg")
            entry["dateien"].append(fname)
            entry["dauer"][fname] = round(len(sig) / q.SR, 2)
            entry["mund"][fname] = mouth_track(q, sig)
        index["gesten"][name] = entry
        print(f"{name:16s} {VARIANTS} Varianten, {max(entry['dauer'].values()):.1f} s")
    index_path.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")))
    total = sum(f.stat().st_size for f in OUT.glob("*.ogg"))
    print(f"{OUT}: {len(list(OUT.glob('*.ogg')))} Dateien, {total / 1024:.0f} KB")


if __name__ == "__main__":
    main()
