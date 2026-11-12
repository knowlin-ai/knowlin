"""Öffentliche Fassung in den Klon (seit 0.38.41): kopiert Änderungen, entfernt Verschwundenes nur per git rm."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import oeffentlich_abgleichen as O  # noqa: E402


def test_abgleichen_kopiert_und_entfernt(tmp_path):
    klon, fassung = tmp_path / "klon", tmp_path / "fassung"
    for o in (klon, fassung):
        (o / "a").mkdir(parents=True)
    (klon / "a" / "bleibt.txt").write_text("gleich")
    (klon / "a" / "alt.txt").write_text("weg")
    (klon / "geaendert.txt").write_text("vorher")
    subprocess.run(["git", "init", "-q"], cwd=klon, check=True)
    subprocess.run(["git", "add", "-A"], cwd=klon, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"], cwd=klon, check=True)
    (fassung / "a" / "bleibt.txt").write_text("gleich")
    (fassung / "geaendert.txt").write_text("nachher")
    (fassung / "a" / "neu.txt").write_text("neu")
    geaendert, entfernt = O.abgleichen(fassung, klon)
    assert geaendert == ["a/neu.txt", "geaendert.txt"] and entfernt == ["a/alt.txt"]
    assert not (klon / "a" / "alt.txt").exists() and (klon / "geaendert.txt").read_text() == "nachher"
    assert (klon / ".git").is_dir()


def test_release_zeile_aus_der_update_probe():
    import release_nachpruefen as R
    zeilen = ["B: installiert 0.38.39", "B: Start nach dem Installer 5 s; gemeldete Schritte: …",
              "B: Update auf 0.38.40 durchgelaufen, Knowlin läuft wieder"]
    ok, zeile = R.zusammenfassen("e1604d01f058", True, zeilen, "0.38.40")
    assert ok and zeile == ("✅ Release, Installer sha256 e1604d01…, PyPI 0.38.40, Update 0.38.39 → 0.38.40 bestanden, "
                            "Start nach dem Installer 5 s")
    assert not R.zusammenfassen("e1604d01f058", False, zeilen[:1], "0.38.40")[0]
