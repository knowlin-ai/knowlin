"""Eigenes Programmfenster: Edge (oder Chrome) im App-Modus.

Warum kein eingebettetes Webview? In WebView2 & Co. fehlt die Spracherkennung
des Browsers. Edge im App-Modus ist auf jedem Windows 10/11 vorhanden, hat ein
eigenes Fenster ohne Adressleiste, ein eigenes Symbol in der Taskleiste – und
kann alles, was die Oberfläche braucht (Mikrofon, Sprache, WebGL).

Ein eigenes Browser-Profil unter %LOCALAPPDATA%\\duckpilot\\fenster hält die
Mikrofon-Freigabe fest und trennt das Fenster von deinem normalen Browser.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from .settings import data_dir

log = logging.getLogger(__name__)


def _candidates() -> list[str]:
    if sys.platform == "win32":
        roots = [os.environ.get(k) for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
        rel = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
        return [str(Path(r) / p) for p in rel for r in roots if r]
    if sys.platform == "darwin":
        return [
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    found = [shutil.which(n) for n in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser")]
    return [f for f in found if f]


def find_browser() -> str | None:
    for path in _candidates():
        if path and Path(path).exists():
            return path
    return None


def open_window(url: str) -> subprocess.Popen | None:
    """Fenster öffnen. Ohne Edge/Chrome: normaler Browser als Notlösung."""
    exe = find_browser()
    if exe is None:
        log.warning("Weder Edge noch Chrome gefunden – öffne den Standardbrowser")
        webbrowser.open(url)
        return None
    profile = data_dir() / "fenster"
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        exe,
        f"--app={url}",
        f"--user-data-dir={profile}",
        "--window-size=1440,900",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
    ]
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    log.info("Öffne Programmfenster mit %s", exe)
    return subprocess.Popen(args, creationflags=flags, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def already_running(url: str) -> bool:
    """Läuft duckpilot schon auf diesem Port? Dann nur ein Fenster dazu öffnen."""
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"{url}/api/ping", timeout=0.8) as r:
            return json.load(r).get("app") == "duckpilot"
    except Exception:
        return False


def setup_file_logging() -> Path:
    """Im App-Modus gibt es keine Konsole – Meldungen gehen in eine Datei."""
    path = data_dir() / "duckpilot.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 2_000_000:
        try:
            path.replace(path.with_suffix(".log.1"))
        except OSError:                 # noch von einem alten Prozess geöffnet (Neustart) – dann eben weiterschreiben
            pass
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    return path


# ── Verknüpfungen: Namen und Symbole (seit 0.38.27 überall „Knowlin“) ───────────
# Die Startseite trägt das Knowlin-Zeichen (knowlin.ico), die Direktstarts in eine Verkörperung zeigen ihren Körper
# (duckpilot.ico = die Ente). Alte Namen von früher benennt der Start einmal um – nur Knowlins eigene Verknüpfungen
# (Ziel ist Python mit „-m duckpilot“); fremde fasst das nie an, gelöscht wird nichts.
VERKNUEPFUNGEN = {
    "": ("Knowlin.lnk", "-m duckpilot --app", "Knowlin – Startseite mit allen Verkörperungen", "knowlin.ico"),
    "duckpilot": ("Knowlin - Microduck.lnk", "-m duckpilot --app --modul duckpilot", "Knowlin – direkt zur Microduck",
                  "duckpilot.ico"),
    "reachy-mini": ("Knowlin - Reachy Mini.lnk", "-m duckpilot --app --modul reachy_mini", "Knowlin – direkt zu Reachy Mini",
                    "knowlin.ico"),
    "open-duck-mini": ("Knowlin - Open Duck Mini.lnk", "-m duckpilot --app --modul open_duck_mini",
                       "Knowlin – direkt zu Open Duck Mini", "knowlin.ico"),
    "so101": ("Knowlin - SO-101.lnk", "-m duckpilot --app --modul so101", "Knowlin – direkt zu Ari (SO-101)", "knowlin.ico"),
}
ALTE_NAMEN = {"duckpilot.lnk": "Knowlin - Microduck.lnk", "Reachy Mini.lnk": "Knowlin - Reachy Mini.lnk",
              "Open Duck Mini.lnk": "Knowlin - Open Duck Mini.lnk"}
AUTOSTART_NAME, AUTOSTART_ALT = "Knowlin im Hintergrund.lnk", "duckpilot.lnk"
AUTOSTART_ARGS = "-m duckpilot --app --hintergrund"


def code_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def ist_zweig(ordner: Path | None = None) -> bool:
    """Liegt dieser Stand unter „Zweige“ (zum Ausprobieren)? Dann biegt er die Verknüpfungen nicht auf sich um –
    sonst zeigten sie nach dem Aufräumen des Zweigs ins Leere."""
    return any(teil.lower() == "zweige" for teil in (ordner or code_dir()).parts)


def symbol(datei: str) -> Path | None:
    """Icon für Verknüpfungen – fehlt knowlin.ico (alter Stand), tut es das Enten-Icon."""
    for name in (datei, "duckpilot.ico"):
        p = code_dir() / name
        if p.exists():
            return p
    # Installiert als Paket (pipx, Installer): kein Projektordner – das Knowlin-Zeichen liegt bei der Oberfläche
    p = Path(__file__).resolve().parent / "server" / "static" / "knowlin.ico"
    return p if p.exists() else None


# ── Mit Windows starten (für die Handy-Fernbedienung) ──────────────────────
def autostart_path() -> Path | None:
    if sys.platform != "win32":
        return None
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / AUTOSTART_NAME


def autostart_enabled() -> bool:
    p = autostart_path()
    return bool(p and (p.exists() or p.with_name(AUTOSTART_ALT).exists()))


def set_autostart(on: bool) -> None:
    """Verknüpfung im Autostart-Ordner anlegen/entfernen: Knowlin startet ohne Fenster im Hintergrund."""
    path = autostart_path()
    if path is None:
        raise RuntimeError("Mit dem System starten gibt es nur unter Windows")
    if not on:
        path.unlink(missing_ok=True)
        path.with_name(AUTOSTART_ALT).unlink(missing_ok=True)      # die eigene von früher (vor 0.38.27)
        return
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    src = symbol("knowlin.ico")
    icon = _icon_kopie(src) if src else None
    env = {**os.environ, "DP_LNK": str(path), "DP_EXE": str(pyw if pyw.exists() else exe), "DP_DIR": str(code_dir()),
           "DP_ICON": str(icon) if icon else "", "DP_ARGS": AUTOSTART_ARGS}
    # Pfade über Umgebungsvariablen – nichts davon landet ungeprüft im Befehlstext
    script = ("$w = New-Object -ComObject WScript.Shell; $s = $w.CreateShortcut($env:DP_LNK); "
              "$s.TargetPath = $env:DP_EXE; $s.Arguments = $env:DP_ARGS; "
              "$s.WorkingDirectory = $env:DP_DIR; if ($env:DP_ICON) { $s.IconLocation = $env:DP_ICON }; "
              "$s.Description = 'Knowlin im Hintergrund (Handy-Fernbedienung)'; $s.Save()")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                       capture_output=True, text=True, timeout=30, creationflags=flags)
    if r.returncode != 0 or not path.exists():
        raise RuntimeError(f"Autostart-Verknüpfung ließ sich nicht anlegen: {(r.stderr or r.stdout).strip()[:200]}")


def _icon_kopie(src: Path) -> Path:
    """Windows merkt sich das Symbol einer Verknüpfung nach Dateipfad und zeigt nach einem Update weiter das alte. Darum
    liegt jedes Icon als Kopie mit Prüfsumme im Namen im lokalen Datenordner (nicht in OneDrive)."""
    data = src.read_bytes()
    folder = data_dir() / "icons"
    target = folder / f"{src.stem}-{hashlib.sha1(data).hexdigest()[:8]}.ico"
    if not target.exists():
        folder.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        for old in folder.glob(f"{src.stem}-*.ico"):
            if old != target:
                old.unlink(missing_ok=True)
    return target


def refresh_shortcut_icons() -> list[str]:
    """Knowlins eigene Verknüpfungen auf Desktop, im Startmenü und im Autostart nachziehen (bei jedem App-Start).

    * alte Namen („duckpilot“, „Reachy Mini“ …) einmal in „Knowlin …“ umbenennen,
    * Symbol: Knowlin-Zeichen für die Startseite und den Autostart, die Ente für den Direktstart zur Microduck,
    * Ziel und Arbeitsordner auf diesen Stand – außer er liegt unter „Zweige“ (dann nur Name und Symbol).
    Fremde Verknüpfungen (Ziel ohne „-m duckpilot“) fasst das nicht an. Gibt die geänderten zurück.
    """
    if sys.platform != "win32":
        return []
    eintraege = []                                  # Name|Symbol|Argumente je eigener Verknüpfung
    for name, argumente, _, datei in VERKNUEPFUNGEN.values():
        src = symbol(datei)
        if src:
            eintraege.append(f"{name}|{_icon_kopie(src)}|{argumente}")
    knowlin = symbol("knowlin.ico")
    if knowlin:
        eintraege.append(f"{AUTOSTART_NAME}|{_icon_kopie(knowlin)}|{AUTOSTART_ARGS}")
    # alt|neu|wo: „start“ = nur im Autostart-Ordner, „menue“ = nur auf dem Desktop und im Startmenü
    alt = [f"{a}|{n}|menue" for a, n in ALTE_NAMEN.items()] + [f"{AUTOSTART_ALT}|{AUTOSTART_NAME}|start"]
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    # Ziel nur umbiegen, wenn dieser Stand aus der Programm-Umgebung läuft (start.bat) und kein Zweig ist
    umbiegen = not ist_zweig() and "venv" in (p.lower() for p in exe.parts)
    env = {**os.environ, "DP_EINTRAEGE": "\n".join(eintraege), "DP_ALT": "\n".join(alt),
           "DP_EXE": str(pyw if pyw.exists() else exe) if umbiegen else "", "DP_DIR": str(code_dir())}
    # Pfade und Namen über Umgebungsvariablen – nichts davon landet ungeprüft im Befehlstext
    script = ("$w = New-Object -ComObject WScript.Shell; $start = [Environment]::GetFolderPath('Startup'); "
              "$dirs = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'), $start); "
              "foreach ($d in $dirs) { $wo = if ($d -eq $start) { 'start' } else { 'menue' }; "
              # 1. alte Namen umbenennen – nur eigene, und nur, wenn der neue Name noch frei ist
              "foreach ($z in ($env:DP_ALT -split \"`n\")) { $a, $n, $o = $z -split '\\|'; if ($o -ne $wo) { continue }; "
              "$l = Join-Path $d $a; if ((Test-Path $l) -and -not (Test-Path (Join-Path $d $n))) { "
              "$s = $w.CreateShortcut($l); if ($s.Arguments -like '*-m duckpilot*') { "
              "Rename-Item -LiteralPath $l -NewName $n; Write-Output (Join-Path $d $n) } } }; "
              # 2. Symbol, Argumente, Ziel und Arbeitsordner der eigenen nachziehen
              "foreach ($z in ($env:DP_EINTRAEGE -split \"`n\")) { $n, $ico, $arg = $z -split '\\|'; $l = Join-Path $d $n; "
              "if (-not (Test-Path $l)) { continue }; $s = $w.CreateShortcut($l); "
              "if ($s.Arguments -notlike '*-m duckpilot*') { continue }; $neu = $false; "
              "if ($s.IconLocation -notlike ($ico + '*')) { $s.IconLocation = $ico; $neu = $true }; "
              "if ($s.Arguments -ne $arg) { $s.Arguments = $arg; $neu = $true }; "
              "if ($env:DP_EXE -and $s.TargetPath -ne $env:DP_EXE) { $s.TargetPath = $env:DP_EXE; $neu = $true }; "
              "if ($env:DP_EXE -and $s.WorkingDirectory -ne $env:DP_DIR) { $s.WorkingDirectory = $env:DP_DIR; $neu = $true }; "
              "if ($neu) { $s.Save(); Write-Output $l } } }")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                           capture_output=True, text=True, timeout=30, creationflags=flags)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.info("Verknüpfungen nicht aufgefrischt: %s", exc)
        return []
    changed = sorted({line.strip() for line in r.stdout.splitlines() if line.strip()})
    if changed:
        try:                                   # Explorer bitten, Symbole neu zu zeichnen (SHCNE_ASSOCCHANGED)
            import ctypes

            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        except Exception:  # noqa: BLE001 – nur Kosmetik
            pass
        log.info("Verknüpfungen aufgefrischt: %s", ", ".join(changed))
    return changed


# ── Verknüpfungen für die Suite (seit 0.38) ──────────────────────────────
def verknuepfung_anlegen(modul: str = "") -> list[str]:
    """Verknüpfung auf dem Desktop und im Startmenü: „Knowlin“ öffnet die Startseite, „Knowlin - Microduck“ & Co. gleich
    die Verkörperung.
    Ans Taskleiste-Anheften erlaubt Windows Programmen nicht – das geht nur von Hand."""
    if sys.platform != "win32":
        raise RuntimeError("Verknüpfungen legt Knowlin nur unter Windows an")
    if modul not in VERKNUEPFUNGEN:
        raise ValueError(f"unbekanntes Modul „{modul}“")
    name, argumente, beschreibung, datei = VERKNUEPFUNGEN[modul]
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    src = symbol(datei)
    icon = _icon_kopie(src) if src else None
    env = {**os.environ, "DP_NAME": name, "DP_ARGS": argumente, "DP_DESC": beschreibung,
           "DP_EXE": str(pyw if pyw.exists() else exe), "DP_DIR": str(code_dir()), "DP_ICON": str(icon) if icon else ""}
    script = ("$w = New-Object -ComObject WScript.Shell; "
              "foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) { "
              "$l = Join-Path $d $env:DP_NAME; $s = $w.CreateShortcut($l); $s.TargetPath = $env:DP_EXE; "
              "$s.Arguments = $env:DP_ARGS; $s.WorkingDirectory = $env:DP_DIR; if ($env:DP_ICON) { "
              "$s.IconLocation = $env:DP_ICON }; $s.Description = $env:DP_DESC; $s.Save(); Write-Output $l }")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                       capture_output=True, text=True, timeout=30, creationflags=flags)
    angelegt = [line.strip() for line in r.stdout.splitlines() if line.strip()]
    if r.returncode != 0 or not angelegt:
        raise RuntimeError(f"Verknüpfung ließ sich nicht anlegen: {(r.stderr or r.stdout).strip()[:200]}")
    return angelegt
