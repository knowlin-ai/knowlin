"""Wächter vor jedem Push (seit 0.38.42): Namen, Schlüssel und private Dateien im öffentlichen Repo fallen auf."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import release_nachpruefen as R  # noqa: E402
import waechter as W  # noqa: E402


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "duckpilot").mkdir()
    return tmp_path


def test_waechter_findet_namen_schluessel_und_private_dateien(tmp_path):
    repo = _repo(tmp_path)
    liste = tmp_path.parent / f"{tmp_path.name}-namen.txt"     # die Liste liegt nie im Repo
    liste.write_text("# privat\nBeispielname\n", encoding="utf-8")
    (repo / "duckpilot" / "a.py").write_text("# Hinweis von Beispielname\nx = 1\n", encoding="utf-8")
    assert W.pruefen(repo, W.namen_muster(liste)) == ["duckpilot/a.py:1: privater Name"]
    (repo / "duckpilot" / "a.py").write_text("KEY = 'sk-ant-" + "a" * 30 + "'\n", encoding="utf-8")
    assert W.pruefen(repo, W.namen_muster(liste)) == ["duckpilot/a.py:1: Anthropic-Schlüssel"]
    (repo / "duckpilot" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "Gespraechsnotizen.md").write_text("privat\n", encoding="utf-8")
    assert W.pruefen(repo, W.namen_muster(liste)) == ["Gespraechsnotizen.md: darf nie öffentlich sein"]


def test_release_zeile_aus_der_update_probe():
    zeilen = ["B: installiert 0.38.39", "B: Start nach dem Installer 5 s; gemeldete Schritte: …",
              "B: Update auf 0.38.40 durchgelaufen, Knowlin läuft wieder"]
    ok, zeile = R.zusammenfassen("e1604d01f058", True, zeilen, "0.38.40")
    assert ok and zeile == ("✅ Release, Installer sha256 e1604d01…, PyPI 0.38.40, Update 0.38.39 → 0.38.40 bestanden, "
                            "Start nach dem Installer 5 s")
    assert not R.zusammenfassen("e1604d01f058", False, zeilen[:1], "0.38.40")[0]
    # seit 0.38.53: eine rote Prüfung bei GitHub macht das Release rot (sie war ab 0.38.42 unbemerkt fehlgeschlagen)
    ok, zeile = R.zusammenfassen("e1604d01f058", True, zeilen, "0.38.40", "fehlgeschlagen")
    assert not ok and zeile.startswith("❌") and "Prüfung bei GitHub fehlgeschlagen" in zeile
    assert R.zusammenfassen("e1604d01f058", True, zeilen, "0.38.40", "läuft")[0]
