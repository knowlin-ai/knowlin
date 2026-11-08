"""Aufbau eines Musikstücks (0.38.23, Hinweis: „die Erkennung der Passagen, Refrain etc., ist noch nicht
perfekt, und die Moves passen noch nicht immer gut zum Song“): Klangbild je Takt, Wiederholungen, Namen; der Tanzplan
folgt Tempo und Energie; im Editor lassen sich Teile umbenennen und neu planen."""
import json
import shutil
import subprocess

import numpy as np
import pytest

from duckpilot import choreo as C
from duckpilot.musik_struktur import struktur
from duckpilot.server.app import STATIC

AKKORDE = {"A": (0, 4, 7), "B": (9, 0, 4), "C": (5, 9, 0, 2), "D": (2, 6, 9)}
SONG = [("Intro", "A", 0.2, 8), ("Strophe", "B", 0.5, 16), ("Refrain", "C", 0.9, 8), ("Strophe", "B", 0.5, 16),
        ("Refrain", "C", 0.9, 8), ("Bridge", "D", 0.55, 8), ("Refrain", "C", 0.95, 8), ("Outro", "A", 0.25, 4)]


def _merkmale(seed=1):
    rng = np.random.default_rng(seed)
    energie, klang = [], []
    for _, akk, e, n in SONG:
        for _ in range(n):
            c = np.zeros(12)
            for k, ton in enumerate(AKKORDE[akk]):
                c[ton] = 1 - 0.15 * k
            c += rng.random(12) * 0.15
            b = np.array([0.3, 0.5, 0.4, 0.3, 0.2, 0.1]) * (0.5 + e) + rng.random(6) * 0.05
            energie.append(float(np.clip(e + rng.normal(0, 0.06), 0, 1)))
            klang.append([round(float(x), 2) for x in [*c, *b]])
    return energie, klang


def test_teile_aus_klang_und_wiederholung():
    energie, klang = _merkmale()
    teile = struktur(energie, klang)
    assert [t["name"] for t in teile] == [s[0] for s in SONG]
    assert [t["takte"] for t in teile] == [s[3] for s in SONG]
    refrains = [t["gruppe"] for t in teile if t["name"] == "Refrain"]
    assert len(set(refrains)) == 1                                     # alle Refrains eine Gruppe
    assert C.teile(energie, klang) == teile                            # choreo nutzt das Klangbild
    # unbrauchbares Klangbild: wie bisher nach Lautstärke
    assert [t["name"] for t in C.teile(energie, [[1, 2]] * len(energie))] == [t["name"] for t in C.teile(energie)]
    assert C.teile(energie, [["x"] * 18] * len(energie))


def test_leiser_refrain_wird_trotzdem_refrain():
    """Nach Lautstärke allein wäre der zweite (leisere) Refrain eine Strophe gewesen."""
    energie, klang = _merkmale(2)
    for i in range(48, 56):
        energie[i] = 0.62
    namen = [t["name"] for t in struktur(energie, klang)]
    assert namen[4] == "Refrain"
    alt = [t["name"] for t in C.teile(energie)]
    assert "Refrain" not in [n for t, n in zip(C.teile(energie), alt) if t["takt"] == 48]


def test_plan_folgt_teilen_tempo_und_energie():
    energie, klang = _merkmale()
    c = C.plane({"bpm": 124, "start": 0.0, "energie": energie, "klang": klang})
    assert [a["name"] for a in c["abschnitte"]] == [s[0] for s in SONG]
    assert len(c["energie"]) == len(energie)
    tl = C.takt_s(124)
    for a in c["abschnitte"]:
        if a["name"] in ("Refrain", "Drop"):                           # jeder Refrain beginnt mit dem Höhepunkt
            erster = next(s for s in c["schritte"] if abs(s["t"] - a["t"]) < 1e-3)
            assert erster["art"] in ("gefuehl", "pose"), erster
    # Ballade: keine Schritte und Drehungen, gewiegt wird
    langsam = C.plane({"bpm": 76, "start": 0.0, "energie": energie, "klang": klang})
    assert not [s for s in langsam["schritte"] if s["art"] in ("schritt", "drehen")]
    # Leise Phrase in einem lauten Teil: kleiner getanzt
    leise = [0.9] * 4 + [0.1] * 4 + [0.9] * 8
    c2 = C.plane({"bpm": 128, "start": 0.0, "energie": leise})
    mitte = [s for s in c2["schritte"] if 4 * C.takt_s(128) - 1e-3 <= s["t"] < 8 * C.takt_s(128) - 1e-3]
    assert mitte and not [s for s in mitte if s["art"] in ("schritt", "drehen")]
    assert tl > 0


def test_eigene_teile_aus_dem_editor():
    energie, _ = _merkmale()
    teile = [{"takt": 0, "takte": 24, "name": "Strophe"}, {"takt": 24, "takte": 52, "name": "Refrain", "gruppe": "c"}]
    c = C.plane({"bpm": 120, "start": 0.5, "energie": energie, "teile": teile})
    assert [(a["name"], a["takte"]) for a in c["abschnitte"]] == [("Strophe", 24), ("Refrain", 52)]
    assert c["abschnitte"][1]["gruppe"] == "C"
    # Lücken, falsche Namen, zu wenig Takte: Vorgabe gilt nicht, die Erkennung entscheidet
    for kaputt in ([{"takt": 0, "takte": 10, "name": "Strophe"}], [{"takt": 0, "takte": 76, "name": "Chorus"}],
                   [{"takt": 4, "takte": 72, "name": "Strophe"}], "Refrain", [None]):
        assert C.plane({"bpm": 120, "energie": energie, "teile": kaputt})["abschnitte"][0]["takte"] != 76 or kaputt == "Refrain"
    gesp = C.pruefe(c)
    assert gesp["energie"] == c["energie"] and gesp["abschnitte"][1]["gruppe"] == "C"
    assert "energie" not in C.pruefe({"bpm": 100, "energie": ["x"], "schritte": []})


def test_klangbild_im_browser():
    """Die Analyse im Browser liefert je Takt zwölf Tonklassen und sechs Bänder; ein Ton A landet in Klasse 9."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    code = ("import { klangbild } from '" + (STATIC / "tanz.js").as_uri() + "';"
            "const rate = 44100, n = rate * 2; const s = new Float32Array(n);"
            "for (let i = 0; i < n; i++) s[i] = Math.sin(2 * Math.PI * 440 * i / rate);"
            "console.log(JSON.stringify(klangbild(s, rate, 0, n)));")
    r = subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True)
    if r.returncode:
        pytest.skip("tanz.js lässt sich ohne Browser nicht laden: " + r.stderr[:200])
    k = json.loads(r.stdout)
    assert len(k) == 18 and int(np.argmax(k[:12])) == 9
    assert int(np.argmax(k[12:])) == 2                                  # 440 Hz liegt im Band 300–800 Hz


def test_editor_zeigt_und_bearbeitet_teile():
    js = (STATIC / "tanz.js").read_text(encoding="utf-8")
    assert "function teilKopf(" in js and "function teilNeu(" in js and "function wieDerErste(" in js
    assert "Bridge" in js and "teilTitel()" in js
    assert "klang" in js and "export function klangbild" in js


def _song(sr=22050):
    """Kleines Stück mit Akkorden und Schlagzeug: Intro, Strophe, Refrain, Strophe, Refrain, Bridge, Refrain, Outro."""
    rng = np.random.default_rng(0)
    beat = 0.5
    akk = {"A": (60, 64, 67), "B": (57, 60, 64), "C": (65, 69, 72, 74), "D": (62, 66, 69)}
    plan = [("A", .25, 4, False), ("B", .5, 8, True), ("C", 1.0, 8, True), ("B", .5, 8, True), ("C", 1.0, 8, True),
            ("D", .55, 4, True), ("C", 1.0, 8, True), ("A", .3, 4, False)]
    teile = []
    for a, e, n, drums in plan:
        for _ in range(n):
            t = np.arange(int(sr * 4 * beat)) / sr
            x = sum(np.sin(2 * np.pi * 440 * 2 ** ((m - 69) / 12) * t) * (0.6 if i == 0 else 0.35) for i, m in enumerate(akk[a]))
            x = (x + 0.4 * np.sin(2 * np.pi * 440 * 2 ** ((akk[a][0] - 24 - 69) / 12) * t)) * 0.18 * e
            if drums:
                for k in range(4):
                    i0, L = int(k * beat * sr), int(0.12 * sr)
                    x[i0:i0 + L] += np.sin(2 * np.pi * 60 * np.arange(L) / sr) * np.exp(-np.arange(L) / (0.03 * sr)) * 0.5 * e
                    if k % 2 or e > 0.8:
                        x[i0:i0 + L] += rng.normal(0, 1, L) * np.exp(-np.arange(L) / (0.02 * sr)) * 0.25 * e
            teile.append(x)
    y = np.concatenate(teile)
    return (y / np.abs(y).max() * 0.9).astype("<f4"), sr


def test_ganzer_weg_vom_klang_zum_tanz(tmp_path):
    """Browser-Analyse (Tempo, Eins, Klangbild) → Teile: das Stück wird richtig gegliedert, Tempo exakt."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    y, sr = _song()
    roh = tmp_path / "song.f32"
    roh.write_bytes(y.tobytes())
    code = ("import { readFileSync } from 'fs'; import { analysiere } from '" + (STATIC / "tanz.js").as_uri() + "';"
            f"const b = readFileSync('{roh.as_posix()}'); const s = new Float32Array(b.buffer, b.byteOffset, b.length / 4);"
            f"console.log(JSON.stringify(analysiere(s, {sr})));")
    r = subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, timeout=120)
    if r.returncode:
        pytest.skip("tanz.js lässt sich ohne Browser nicht laden: " + r.stderr[:200])
    a = json.loads(r.stdout)
    assert abs(a["bpm"] - 120) < 0.3                                    # vorher 119,1 – nach einer Minute verrutscht
    assert abs(((a["start"] + 0.01) % 2.0) - 0.01) < 0.06                # auf der Eins (Takte zu 2 s)
    c = C.plane(a)
    namen = [x["name"] for x in c["abschnitte"]]
    assert namen == ["Intro", "Strophe", "Refrain", "Strophe", "Refrain", "Bridge", "Refrain", "Outro"]
    refrains = [x["gruppe"] for x in c["abschnitte"] if x["name"] == "Refrain"]
    assert len(set(refrains)) == 1


def test_klangbild_bleibt_beim_tanz():
    """0.38.24: Das Klangbild je Takt wird mit dem Tanz gespeichert – Neuplanen im Editor nutzt es weiter, und eine
    bessere Erkennung später braucht die Musik nicht erneut."""
    energie, klang = _merkmale()
    c = C.plane({"bpm": 120, "start": 0.0, "energie": energie, "klang": klang})
    assert len(c["klang"]) == len(energie) and len(c["klang"][0]) == 18
    gesp = C.pruefe(c)
    assert gesp["klang"] == c["klang"]
    for kaputt in ([["x"] * 18] * len(energie), [[1, 2]] * len(energie), "laut", [[0.1] * 18] * 3):
        assert "klang" not in C.pruefe({**c, "klang": kaputt})
    js = (STATIC / "tanz.js").read_text(encoding="utf-8")
    assert "klang: choreo.klang, teile" in js
