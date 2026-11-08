"""Windows-Installer und Paket-Start (0.38.31, Wunsch beim Launch: „start.bat … wirkt seriöser“ als Installer)."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISS = (ROOT / "tools" / "installer" / "knowlin.iss").read_text(encoding="utf-8")
WF = (ROOT / "tools" / "github" / "workflows" / "installer.yml").read_text(encoding="utf-8")


def test_installer_fuer_den_benutzer_ohne_adminrechte_und_ohne_personennamen():
    assert "PrivilegesRequired=lowest" in ISS and r"DefaultDirName={localappdata}\Programs\Knowlin" in ISS
    assert "AppPublisher=Knowlin" in ISS and "VersionInfoCompany=Knowlin" in ISS
    assert re.search(r"AppId=\{\{[0-9A-F-]{36}\}", ISS)                     # feste Kennung: Updates ersetzen sauber
    # Gedächtnis und Einstellungen (%LOCALAPPDATA%\duckpilot) fasst die Deinstallation nicht an
    assert "duckpilot\\" not in ISS.split("[UninstallDelete]")[1] and "{app}\\python" in ISS.split("[UninstallDelete]")[1]
    # Verknüpfungen starten Knowlin ohne Konsole, wie start.bat
    assert ISS.count('Filename: "{app}\\python\\pythonw.exe"') >= 3 and 'Parameters: "-m duckpilot --app"' in ISS
    assert "taskkill" not in ISS                                            # nie fremde Python-Programme beenden


def test_workflow_baut_prueft_und_haengt_an():
    assert "runs-on: windows-latest" in WF and "embed-amd64.zip" in WF and "import site" in WF
    assert "--target" in WF and "Probelauf" in WF and "ISCC.exe" in WF
    assert "types: [published]" in WF and "gh release upload" in WF and "contents: write" in WF


def test_symbol_auch_ohne_projektordner(monkeypatch, tmp_path):
    from duckpilot import desktop

    monkeypatch.setattr(desktop, "code_dir", lambda: tmp_path)              # wie nach pipx/Installer: kein Projektordner
    p = desktop.symbol("duckpilot.ico")
    assert p is not None and p.name == "knowlin.ico" and p.parent.name == "static"
    assert p.read_bytes()[:4] == b"\x00\x00\x01\x00"                          # echtes .ico


def test_verknuepfung_als_befehl(capsys, monkeypatch):
    from duckpilot.__main__ import main

    monkeypatch.setattr(sys, "platform", "linux")
    main(["--verknuepfung"])
    assert "nur unter Windows" in capsys.readouterr().out
