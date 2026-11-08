"""Updates (seit 0.38.32, Frage beim Launch: „Bekommen die Leute eine Update-Info und können aus dem Programm heraus
aktualisieren?“).

* **Prüfen:** höchstens einmal am Tag eine Anfrage an die GitHub-API (`releases/latest` von knowlin-ai/knowlin) – nur die
  übliche Anfrage mit IP-Adresse, keine Daten über dich. Abschaltbar (Einstellung `updates_suchen`), im Offline-Modus nie.
* **Aktualisieren** je nach Installationsart:
  - *installer* (Knowlin-Setup.exe): neuen Installer aus genau diesem Release laden, Prüfsumme gegen die Angabe von
    GitHub prüfen, Knowlin beenden, still installieren – der Installer startet Knowlin danach wieder.
  - *paket* (pipx/pip): `python -m pip install --upgrade knowlin==<version>` in der eigenen Umgebung, dann Neustart.
  - *quelle* (Repository mit start.bat): nur Hinweis und Link – der Code-Stand gehört dem, der ihn pflegt.
* **Nie mitten in einer Bewegung:** mit dem echten Roboter verbunden wird nicht aktualisiert.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from . import __version__

log = logging.getLogger(__name__)

REPO = "knowlin-ai/knowlin"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
TAG = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
ASSET = re.compile(r"Knowlin-Setup-(\d+\.\d+\.\d+)\.exe")
ERLAUBTE_HOSTS = ("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")
MAX_BYTES = 300 * 1024 * 1024
TAG_S = 24 * 3600


class UpdateFehler(RuntimeError):
    pass


def version_tupel(text: str) -> tuple[int, int, int] | None:
    m = TAG.fullmatch((text or "").strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def neuer(kandidat: str, jetzt: str = __version__) -> bool:
    a, b = version_tupel(kandidat), version_tupel(jetzt)
    return bool(a and b and a > b)


def offline() -> bool:
    return os.environ.get("DUCKPILOT_OFFLINE", "") not in ("", "0")


def installart(exe: str | Path | None = None, paket: Path | None = None) -> str:
    """installer | paket | quelle – woran Knowlin erkennt, wie es aktualisiert werden kann."""
    exe = Path(exe or sys.executable)
    if exe.parent.name.lower() == "python" and (exe.parent.parent / "unins000.exe").exists():
        return "installer"                      # %LOCALAPPDATA%\Programs\Knowlin\python\pythonw.exe
    projekt = (paket or Path(__file__).resolve().parent).parent
    if (projekt / "start.bat").exists() or (projekt / ".git").exists() or (projekt / "pyproject.toml").exists():
        return "quelle"
    return "paket"


def _lesen(url: str, limit: int = 2_000_000) -> bytes:
    kopf = {"User-Agent": f"Knowlin/{__version__}"}
    if url.startswith("https://api.github.com/"):
        kopf["Accept"] = "application/vnd.github+json"
    req = urllib.request.Request(url, headers=kopf)
    with urllib.request.urlopen(req, timeout=15) as r:          # noqa: S310 – feste https-Adresse
        return r.read(limit + 1)[:limit]


def auswerten(daten: dict[str, Any]) -> dict[str, Any] | None:
    """Antwort von releases/latest → {version, notizen, seite, installer: {url, groesse, sha256}}; None ohne Version."""
    if daten.get("draft") or daten.get("prerelease"):
        return None
    t = version_tupel(str(daten.get("tag_name") or ""))
    if not t:
        return None
    version = ".".join(map(str, t))
    installer = None
    for a in daten.get("assets") or []:
        m = ASSET.fullmatch(str(a.get("name") or ""))
        digest = str(a.get("digest") or "")
        if m and m.group(1) == version and digest.startswith("sha256:"):
            installer = {"url": str(a.get("browser_download_url") or ""), "groesse": int(a.get("size") or 0),
                         "sha256": digest.split(":", 1)[1].lower()}
    seite = str(daten.get("html_url") or f"https://github.com/{REPO}/releases/latest")
    if not seite.startswith(f"https://github.com/{REPO}/"):
        seite = f"https://github.com/{REPO}/releases/latest"
    return {"version": version, "titel": str(daten.get("name") or "")[:120], "seite": seite, "installer": installer,
            "notizen": str(daten.get("body") or "")[:4000]}


class Aktualisierer:
    """Merkt sich den letzten Blick (Datei im Datenordner) und führt das Update aus."""

    def __init__(self, ordner: Path, lesen=_lesen):
        self.ordner = Path(ordner)
        self.datei = self.ordner / "update.json"
        self._lesen = lesen
        self.art = installart()
        self.laeuft = False

    def _stand(self) -> dict[str, Any]:
        try:
            d = json.loads(self.datei.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def status(self) -> dict[str, Any]:
        s = self._stand()
        neu = s.get("neu") if isinstance(s.get("neu"), dict) and neuer(s["neu"].get("version", "")) else None
        return {"version": __version__, "art": self.art, "neu": neu, "geprueft": s.get("zeit"),
                "letztes_update": self.letztes_update(),
                "kann": bool(neu) and (self.art == "paket" or (self.art == "installer" and bool(neu.get("installer"))))}

    def pruefen(self, erzwingen: bool = False) -> dict[str, Any]:
        """Höchstens einmal am Tag (außer erzwungen) bei GitHub nachsehen."""
        if offline():
            raise UpdateFehler("Knowlin ist offline gestellt – keine Suche nach Updates.")
        s = self._stand()
        if not erzwingen and time.time() - float(s.get("zeit_s") or 0) < TAG_S:
            return self.status()
        try:
            neu = auswerten(json.loads(self._lesen(API)))
        except UpdateFehler:
            raise
        except Exception as exc:
            raise UpdateFehler(f"GitHub antwortet nicht: {str(exc)[:120]}") from exc
        self.ordner.mkdir(parents=True, exist_ok=True)
        self.datei.write_text(json.dumps({"zeit_s": time.time(), "zeit": time.strftime("%Y-%m-%d %H:%M"),
                                          "neu": neu if neu and neuer(neu["version"]) else None}, ensure_ascii=False),
                              encoding="utf-8")
        return self.status()

    # ── Ausführen ─────────────────────────────────────────────────────────
    def installer_laden(self, info: dict[str, Any]) -> Path:
        """Installer aus dem Release laden und gegen die Prüfsumme von GitHub prüfen."""
        url = str(info.get("url") or "")
        host = urllib.request.urlparse(url).hostname or ""
        if not url.startswith(f"https://github.com/{REPO}/releases/download/") or host not in ERLAUBTE_HOSTS:
            raise UpdateFehler("Unerwartete Download-Adresse – Update abgebrochen.")
        if not re.fullmatch(r"[0-9a-f]{64}", str(info.get("sha256") or "")):
            raise UpdateFehler("Keine Prüfsumme von GitHub – Update abgebrochen.")
        roh = self._lesen(url, MAX_BYTES)
        if len(roh) >= MAX_BYTES:
            raise UpdateFehler("Der Installer ist unerwartet groß – Update abgebrochen.")
        if hashlib.sha256(roh).hexdigest() != info["sha256"]:
            raise UpdateFehler("Die Prüfsumme stimmt nicht – Update abgebrochen, nichts installiert.")
        ziel = self.ordner / "updates" / Path(urllib.request.urlparse(url).path).name
        ziel.parent.mkdir(parents=True, exist_ok=True)
        for alt in ziel.parent.glob("Knowlin-Setup-*.exe"):
            if alt != ziel:
                alt.unlink(missing_ok=True)
        ziel.write_bytes(roh)
        return ziel

    def installer_befehl(self, setup: Path, pid: int | None = None) -> list[str]:
        """Wartet, bis dieses Knowlin beendet ist, und installiert dann still (der Installer startet Knowlin neu).

        Seit 0.38.34 mit Protokoll (`updates/update.log`, Inno-Protokoll `updates/setup.log`) und
        /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS: Das erste echte Update (0.38.32 → 0.38.33) brach still ab – vermutlich,
        weil Knowlin von Hand wieder gestartet war, während der Installer noch lief, und Dateien belegt waren."""
        skript = self.installer_skript(pid)
        # kodiert übergeben: keine Anführungszeichen-Fallen bei Pfaden mit Leerzeichen (Benutzernamen)
        kodiert = base64.b64encode(skript.encode("utf-16-le")).decode("ascii")
        return ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                "-EncodedCommand", kodiert]

    def installer_skript(self, pid: int | None = None) -> str:
        pid = pid or os.getpid()
        return (
            "$d = Split-Path -Parent $env:KN_SETUP; $log = Join-Path $d 'update.log'; "
            "function L($t) { Add-Content -LiteralPath $log -Value ((Get-Date -Format s) + ' ' + $t) }; "
            f"L 'warte auf Knowlin (PID {int(pid)})'; "
            f"Wait-Process -Id {int(pid)} -Timeout 120 -ErrorAction SilentlyContinue; "
            "L ('starte ' + (Split-Path -Leaf $env:KN_SETUP)); "
            "try { $p = Start-Process -FilePath $env:KN_SETUP -PassThru -Wait -ArgumentList "
            "'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/CLOSEAPPLICATIONS','/FORCECLOSEAPPLICATIONS',"
            "('/LOG=\"' + (Join-Path $d 'setup.log') + '\"'); L ('fertig, Code ' + $p.ExitCode) } "
            "catch { L ('Fehler: ' + $_) }")

    def installer_starten(self, setup: Path, pid: int | None = None) -> None:
        env = {**os.environ, "KN_SETUP": str(setup)}
        kw: dict[str, Any] = {"env": env, "close_fds": True, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                              "stderr": subprocess.DEVNULL}
        if sys.platform != "win32":
            subprocess.Popen(self.installer_befehl(setup, pid), **kw)
            return
        # Kein Konsolenfenster, eigene Prozessgruppe und – wo erlaubt – raus aus einem Job-Objekt, damit das Beenden von
        # Knowlin den Installer-Start nicht mitreißt
        ohne_fenster, gruppe, ausbrechen = 0x08000000, 0x00000200, 0x01000000
        try:
            subprocess.Popen(self.installer_befehl(setup, pid), creationflags=ohne_fenster | gruppe | ausbrechen, **kw)
        except OSError:
            subprocess.Popen(self.installer_befehl(setup, pid), creationflags=ohne_fenster | gruppe, **kw)

    def letztes_update(self) -> str | None:
        """Letzte Zeile aus updates/update.log – zeigt unter Einstellungen → Über, wie das letzte Update ausging."""
        try:
            zeilen = (self.ordner / "updates" / "update.log").read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None
        return zeilen[-1][:200] if zeilen else None

    def paket_befehl(self, version: str) -> list[str]:
        if not version_tupel(version):
            raise UpdateFehler("Ungültige Version.")
        return [sys.executable, "-m", "pip", "install", "--upgrade", "--disable-pip-version-check", f"knowlin=={version}"]

    def paket_aktualisieren(self, version: str) -> None:
        r = subprocess.run(self.paket_befehl(version), capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            raise UpdateFehler(f"pip meldet einen Fehler: {(r.stderr or r.stdout).strip()[-300:]}")
