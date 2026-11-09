"""winget-Manifeste (seit 0.38.35): gültiges YAML, richtige Adresse, Prüfsumme, AppId wie im Installer."""

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import winget_manifest as W  # noqa: E402

SHA = "aac8007f999b77311dd4be6d545285dea966635238a26ac83e06b068049ada47"


def test_manifeste_fuer_ein_release(tmp_path):
    ordner = W.schreiben("0.38.34", SHA, tmp_path)
    assert ordner.parts[-4:] == ("k", "Knowlin", "Knowlin", "0.38.34")
    d = {p.name: yaml.safe_load(p.read_text(encoding="utf-8")) for p in ordner.iterdir()}
    inst = d["Knowlin.Knowlin.installer.yaml"]
    assert inst["InstallerType"] == "inno" and inst["Scope"] == "user"
    assert inst["Installers"][0]["InstallerUrl"].endswith("/releases/download/v0.38.34/Knowlin-Setup-0.38.34.exe")
    assert inst["Installers"][0]["InstallerSha256"] == SHA.upper()
    iss = (ROOT / "tools" / "installer" / "knowlin.iss").read_text(encoding="utf-8")
    assert W.APP_ID[1:-1] in iss and inst["ProductCode"] == f"{W.APP_ID}_is1"
    assert {x["ManifestType"] for x in d.values()} == {"version", "installer", "defaultLocale"}
    assert d["Knowlin.Knowlin.locale.en-US.yaml"]["License"] == "Apache-2.0"


def test_falsche_eingaben_werden_abgelehnt():
    with pytest.raises(ValueError):
        W.manifeste("v1", SHA)
    with pytest.raises(ValueError):
        W.manifeste("0.38.34", "kurz")
