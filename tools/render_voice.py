#!/usr/bin/env python3
"""Rendert die Stimmbank der Ente (die sieben Ton-Tags) mit Pollens Stimm-Synthesizer.

    python tools/render_voice.py <pfad>/microduck_emotions [seed]

`quack.py` aus pollen-robotics/microduck_emotions (Apache-2.0) ist die Python-Portierung
der Roboter-Stimme mit derselben Persönlichkeit pro Seed. Dort sind nur `alarm` und
`peck` portiert; `greet`, `inquire`, `chirp`, `coo` und `wheee` sind hier aus
`sounds/src/voices.rs` (pollen-robotics/microduck, Apache-2.0) nachgebaut – gleiche
Rezepte, gleicher Zufallsstrom pro Variante, Rauschen nicht bitgenau.

Ausgabe: duckpilot/server/static/sounds/voice/<tag>_<n>.ogg (Opus) und index.json.
Braucht numpy, scipy und ffmpeg – nur beim Rendern, nie zur Laufzeit.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np

# Wie Pollen (sounds/src/lib.rs, variant_count): greet und chirp hört man am meisten → 12, sonst 10.
# „wheee“ nur kurz (0,85 s) – lang klang es wie eine Sirene; duckpilot nutzt es kaum noch.
VARIANTS = {"greet": 12, "chirp": 12, "alarm": 10, "inquire": 10, "peck": 10, "coo": 10, "wheee": 2}
WHEEE_MAX_S = 0.85


def load_quack(folder: Path):
    spec = importlib.util.spec_from_file_location("quack", folder / "quack.py")
    q = importlib.util.module_from_spec(spec)
    sys.modules["quack"] = q
    spec.loader.exec_module(q)
    return q


def recipes(q):
    s_ = q

    def attack(p, dur, snappy):
        return s_.attack_time(p, dur, snappy)

    def greet_syllable(p, rng, dur_scale, f0_scale):
        dur = (0.32 + 0.25 * rng.random()) * dur_scale / p.speed
        t = s_.t_axis(dur)
        f0 = p.pitch_center_hz * (0.9 + 0.15 * rng.random()) * f0_scale
        bias, bend = p.glide_bias, 0.10 + 0.15 * p.pitch_spread
        start = f0 * (1.0 - bias * bend * 0.5)
        mid = f0 * (1.0 + bias * bend)
        end = f0 * (1.0 - bias * bend * 0.3) * (0.92 + 0.08 * rng.random())
        freq = s_.lerp(t, [(0.0, start), (0.18 * dur, mid), (dur, end)])
        env = s_.expdecay(t, attack(p, dur, 0.5), dur * 0.7)
        return s_.voice(p, t, freq, rng, 1.0, 1.0) * env

    def greet(p, v):
        rng = p.variant_rng("greet", v)
        sig = greet_syllable(p, rng, 1.0, 1.0)
        if rng.random() < 0.4:
            gap = s_.silence((0.05 + 0.06 * rng.random()) / p.speed)
            f0_scale = 0.95 + 0.06 * rng.random()
            sig = np.concatenate([sig, gap, greet_syllable(p, rng, 0.8, f0_scale)])
        return s_.normalise(sig, -3.0)

    def inquire(p, v):
        rng = p.variant_rng("inquire", v)
        dur = (0.42 + 0.25 * rng.random()) / p.speed
        t = s_.t_axis(dur)
        f0 = p.pitch_center_hz * (0.88 + 0.10 * rng.random())
        rise = 1.15 + 0.50 * p.pitch_spread + 0.20 * max(p.glide_bias, 0.0) + 0.10 * rng.random()
        freq = s_.lerp(t, [(0.0, f0 * 0.92), (0.30 * dur, f0 * 0.95), (dur, f0 * rise)])
        env = s_.bell(t, dur * (0.06 + 0.10 * (1.0 - p.attack_sharpness)), dur * 0.32)
        return s_.normalise(s_.voice(p, t, freq, rng, 0.6, 1.0) * env, -3.0)

    def chirp_syllable(p, rng, f0, dur, contour):
        t = s_.t_axis(dur)
        warble = s_.vibrato(t, p.warble_hz, p.warble_depth, rng.uniform(0.0, s_.TAU))
        freq = f0 * s_.lerp(t, contour) * warble
        env = s_.expdecay(t, attack(p, dur, 0.7), dur * 0.55)
        soft = replace(p, quackiness=p.quackiness * 0.2, brightness=p.brightness * 0.5,
                       formant_gain=p.formant_gain * 0.5)
        return s_.voice(soft, t, freq, rng, 1.0, 0.4) * env

    def chirp(p, v):
        rng = p.variant_rng("chirp", v)
        shape = v % 4
        f0 = p.pitch_center_hz * (0.95 + 0.75 * rng.random())
        if shape == 0:
            dur = (0.10 + 0.10 * rng.random()) / p.speed
            peak = 1.12 + 0.10 * rng.random()
            sig = chirp_syllable(p, rng, f0, dur, [(0.0, 0.88), (0.5 * dur, peak), (dur, 1.05)])
        elif shape == 1:
            dur = (0.10 + 0.10 * rng.random()) / p.speed
            start = 1.12 + 0.10 * rng.random()
            sig = chirp_syllable(p, rng, f0, dur, [(0.0, start), (0.3 * dur, 1.0), (dur, 0.78)])
        elif shape == 2:
            dur = (0.22 + 0.14 * rng.random()) / p.speed
            trill = replace(p, warble_depth=max(p.warble_depth, 0.7) * 1.6)
            sig = chirp_syllable(trill, rng, f0, dur, [(0.0, 1.0), (0.5 * dur, 1.06), (dur, 0.94)])
        else:
            dur = (0.08 + 0.05 * rng.random()) / p.speed
            a = chirp_syllable(p, rng, f0, dur, [(0.0, 0.95), (0.4 * dur, 1.10), (dur, 0.88)])
            gap = s_.silence((0.03 + 0.03 * rng.random()) / p.speed)
            db = dur * 0.9
            f0b = f0 * (0.92 + 0.10 * rng.random())
            b = chirp_syllable(p, rng, f0b, db, [(0.0, 0.95), (0.4 * db, 1.10), (db, 0.88)])
            sig = np.concatenate([a, gap, b])
        return s_.normalise(sig, -6.0)

    def coo(p, v):
        rng = p.variant_rng("coo", v)
        dur = (0.85 + 0.55 * rng.random()) / p.speed
        t = s_.t_axis(dur)
        f0 = p.pitch_center_hz * (0.42 + 0.15 * (1.0 - p.attack_sharpness)) * (0.94 + 0.12 * rng.random())
        drift = 1.0 + 0.05 * rng.random() + 0.04 * p.glide_bias
        freq = s_.lerp(t, [(0.0, f0 * 0.94), (dur * 0.5, f0 * drift), (dur, f0 * 0.90)])
        env = s_.bell(t, dur * (0.18 + 0.10 * (1.0 - p.attack_sharpness)), dur * 0.30)
        soft = replace(p, breath=max(p.breath, 0.12) + 0.10, quackiness=p.quackiness * 0.25,
                       am_rate_hz=p.am_rate_hz * 0.30, vibrato_rate_hz=p.vibrato_rate_hz * 0.45,
                       vibrato_depth=p.vibrato_depth * 0.7)
        return s_.normalise(s_.voice(soft, t, freq, rng, 1.0, 1.0) * env, -5.0)

    def wheee(p, v):
        rng = p.variant_rng("wheee", v)
        d_start = (0.80 + 0.30 * rng.random()) / p.speed
        d_loop = (1.60 + 0.60 * rng.random()) / p.speed
        d_end = (0.55 + 0.25 * rng.random()) / p.speed
        d_loop *= 0.5      # für den PC eine kürzere Fahrt: ein halber Loop statt zwei ganzer
        total = d_start + d_loop + d_end
        t = s_.t_axis(total)
        t1, t2 = d_start, d_start + d_loop
        f0 = p.pitch_center_hz * (0.95 + 0.10 * rng.random())
        top = 1.6 + 0.5 * p.pitch_spread + 0.25 * rng.random()
        base = s_.lerp(t, [(0.0, f0 * 0.85), (0.15 * d_start, f0), (t1, f0 * top), (t2, f0 * top),
                           (t2 + 0.25 * d_end, f0 * top * 1.04), (total, f0 * 0.60)])
        wob_hz = 4.5 + 3.0 * rng.random()
        swell = s_.lerp(t, [(0.0, 0.15), (t1, 1.0), (total, 1.0)])
        freq = base * 2.0 ** (0.5 * swell * np.sin(s_.TAU * wob_hz * t) / 12.0)
        env = s_.lerp(t, [(0.0, 0.0), (min(0.06, 0.5 * d_start), 1.0), (t2 + 0.40 * d_end, 1.0), (total, 0.0)])
        joy = replace(p, vibrato_depth=p.vibrato_depth * 0.5, quackiness=p.quackiness * 0.5)
        return s_.normalise(s_.voice(joy, t, freq, rng, 0.5, 0.5) * env, -4.0)

    return {"greet": greet, "inquire": inquire, "chirp": chirp, "coo": coo, "wheee": wheee,
            "alarm": q.alarm, "peck": q.peck}


def to_ogg(sig: np.ndarray, sr: int, dest: Path, q) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "x.wav"
        q.write_wav(wav, sig, peak_dbfs=None)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-c:a", "libopus", "-b:a", "48k",
                        "-ar", "48000", str(dest)], check=True)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    q = load_quack(Path(sys.argv[1]).expanduser())
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else q.ROBOT_SEED
    p = q.Personality(seed)
    out = Path(__file__).resolve().parent.parent / "duckpilot" / "server" / "static" / "sounds" / "voice"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.ogg"):
        old.unlink()
    index = {"seed": seed, "source": "pollen-robotics/microduck_emotions quack.py + microduck sounds/voices.rs (Apache-2.0)",
             "tags": {}}
    for tag, fn in recipes(q).items():
        files = []
        for v in range(VARIANTS[tag]):
            sig = np.asarray(fn(p, v), dtype=np.float64)
            if tag == "wheee" and len(sig) > WHEEE_MAX_S * q.SR:
                sig = sig[: int(WHEEE_MAX_S * q.SR)].copy()
                fade = int(0.08 * q.SR)
                sig[-fade:] *= np.linspace(1.0, 0.0, fade)
            name = f"{tag}_{v}.ogg"
            to_ogg(sig, q.SR, out / name, q)
            files.append(name)
        index["tags"][tag] = files
    (out / "index.json").write_text(json.dumps(index, indent=1))
    total = sum(f.stat().st_size for f in out.glob("*.ogg"))
    print(f"{out}: {sum(len(v) for v in index['tags'].values())} Töne, {total / 1024:.0f} KB, Seed {seed}")


if __name__ == "__main__":
    main()
