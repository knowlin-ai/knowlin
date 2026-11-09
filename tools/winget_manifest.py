"""winget-Manifeste für ein Knowlin-Release erzeugen (seit 0.38.35).

    python tools/winget_manifest.py 0.38.34 <sha256 des Installers> [zielordner]

Schreibt die drei Dateien (Version, Installer, Beschreibung) im Schema 1.9 nach
`<zielordner>/manifests/k/Knowlin/Knowlin/<version>/` – genau so, wie sie in `microsoft/winget-pkgs` liegen müssen.
Einreichen: Fork von microsoft/winget-pkgs, Ordner hineinkopieren, Pull Request (oder unter Windows
`wingetcreate submit <ordner>`). Die Prüfsumme steht nach jedem Release im Release (Asset → sha256).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PAKET = "Knowlin.Knowlin"
SCHEMA = "1.9.0"
APP_ID = "{6F1C2B7A-4E0B-4C59-9E5B-2B1E4C0A7D31}"          # AppId aus tools/installer/knowlin.iss
REPO = "https://github.com/knowlin-ai/knowlin"


def manifeste(version: str, sha256: str) -> dict[str, str]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Version wie 0.38.34")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
        raise ValueError("sha256: 64 Hex-Zeichen")
    kopf = "# Erzeugt von tools/winget_manifest.py\n"
    url = f"{REPO}/releases/download/v{version}/Knowlin-Setup-{version}.exe"
    return {
        f"{PAKET}.yaml": kopf + f"""# yaml-language-server: $schema=https://aka.ms/winget-manifest.version.{SCHEMA}.schema.json
PackageIdentifier: {PAKET}
PackageVersion: {version}
DefaultLocale: en-US
ManifestType: version
ManifestVersion: {SCHEMA}
""",
        f"{PAKET}.installer.yaml": kopf + f"""# yaml-language-server: $schema=https://aka.ms/winget-manifest.installer.{SCHEMA}.schema.json
PackageIdentifier: {PAKET}
PackageVersion: {version}
InstallerType: inno
Scope: user
InstallModes:
- interactive
- silent
UpgradeBehavior: install
ProductCode: '{APP_ID}_is1'
Installers:
- Architecture: x64
  InstallerUrl: {url}
  InstallerSha256: {sha256.upper()}
ManifestType: installer
ManifestVersion: {SCHEMA}
""",
        f"{PAKET}.locale.en-US.yaml": kopf + f"""# yaml-language-server: $schema=https://aka.ms/winget-manifest.defaultLocale.{SCHEMA}.schema.json
PackageIdentifier: {PAKET}
PackageVersion: {version}
PackageLocale: en-US
Publisher: Knowlin
PublisherUrl: {REPO}
PublisherSupportUrl: {REPO}/issues
PackageName: Knowlin
PackageUrl: https://knowlin.de
License: Apache-2.0
LicenseUrl: {REPO}/blob/main/LICENSE
ShortDescription: Self-learning companion for robots – one mind, many bodies (Microduck, Reachy Mini, Open Duck Mini, LeRobot), with simulator.
Description: Knowlin gives robots a mind that remembers – memory, character, conversation and spatial knowledge on your PC. Try everything in the built-in simulator before your robot arrives, then switch to the real one.
Moniker: knowlin
Tags:
- robotics
- robot
- simulator
- microduck
- reachy-mini
- lerobot
- ai
ReleaseNotesUrl: {REPO}/releases/tag/v{version}
ManifestType: defaultLocale
ManifestVersion: {SCHEMA}
""",
    }


def schreiben(version: str, sha256: str, ziel: Path) -> Path:
    ordner = ziel / "manifests" / "k" / "Knowlin" / "Knowlin" / version
    ordner.mkdir(parents=True, exist_ok=True)
    for name, text in manifeste(version, sha256).items():
        (ordner / name).write_text(text, encoding="utf-8")
    return ordner


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    print(schreiben(sys.argv[1], sys.argv[2], Path(sys.argv[3] if len(sys.argv) > 3 else "dist/winget")))
