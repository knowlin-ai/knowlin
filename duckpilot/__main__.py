"""Start: `python -m duckpilot` (Simulator) oder `python -m duckpilot --backend robotd`."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
import webbrowser

from . import __version__
from .config import load


def _safe_console() -> None:
    """Ausgaben dürfen nie abstürzen: Unter Windows ist die Ausgabe beim Neustart eine Datei in cp1252 – das 🦆 der
    Startmeldung ließ den neuen Prozess sterben (UnicodeEncodeError), und duckpilot kam nicht wieder."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> None:
    _safe_console()
    ap = argparse.ArgumentParser(prog="knowlin", description="Knowlin – ein Kopf, viele Körper. Startet die Oberfläche im "
                                 "Browser (Simulator oder echter Roboter). Python-Paket: duckpilot.")
    ap.add_argument("--config", help="Pfad zu duckpilot.toml")
    ap.add_argument("--backend", choices=["sim", "robotd"], help="sim (Standard) oder robotd (echter Roboter / duck-sim)")
    ap.add_argument("--robot", help="robotd-Adresse, z. B. tcp:127.0.0.1:7900 oder unix:/run/robotd.sock")
    ap.add_argument("--tof", help="tofd-Adresse für den Tiefensensor (optional)")
    ap.add_argument("--updater", help="updaterd-Adresse für Tricks vom Hub (optional)")
    ap.add_argument("--port", type=int, help="Port der Oberfläche (Standard 8765)")
    ap.add_argument("--host", help="Adresse der Oberfläche (Standard 127.0.0.1 – nur dieser PC)")
    ap.add_argument("--model", help="Claude-Modell, z. B. claude-sonnet-5-5 oder claude-haiku-5-5")
    ap.add_argument("--stt", choices=["browser", "whisper", "aus"], help="Spracherkennung")
    ap.add_argument("--memory", metavar="DATEI", help="Pfad der Gedächtnisdatei (Standard: lokaler App-Datenordner)")
    ap.add_argument("--no-memory", action="store_true", help="Gedächtnis ausschalten")
    ap.add_argument("--no-browser", action="store_true", help="Browser nicht automatisch öffnen")
    ap.add_argument("--app", action="store_true",
                    help="Als eigenes Programmfenster starten (ohne Konsole, beendet sich beim Schließen)")
    ap.add_argument("--modul", choices=["duckpilot", "reachy_mini", "open_duck_mini"],
                    help="gleich in einer Verkörperung starten statt auf der Knowlin-Startseite (Verknüpfungen "
                         "„Knowlin - Microduck“ & Co.)")
    ap.add_argument("--hintergrund", action="store_true",
                    help="Mit --app: ohne Fenster starten (z. B. mit Windows, für die Handy-Fernbedienung)")
    ap.add_argument("--neustart", action="store_true", help=argparse.SUPPRESS)   # nach „Neu starten“: kein neues Fenster
    ap.add_argument("--fake-robotd", metavar="ADRESSE",
                    help="Statt der Oberfläche: den Simulator als robotd-kompatiblen Server anbieten (zum Testen)")
    ap.add_argument("--verknuepfung", action="store_true",
                    help="Windows: Verknüpfungen „Knowlin“ und „Knowlin - Microduck“ auf Desktop und im Startmenü anlegen")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--version", action="version", version=f"Knowlin {__version__} (Paket duckpilot)")
    args = ap.parse_args(argv)

    if args.app:
        from .desktop import setup_file_logging

        setup_file_logging()
    else:
        logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                            format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")

    if args.verknuepfung:                 # seit 0.38.31: nach „pipx install knowlin“ – ohne start.bat
        from .desktop import verknuepfung_anlegen

        try:
            for modul in ("", "duckpilot"):
                for pfad in verknuepfung_anlegen(modul):
                    print(f"  Verknüpfung: {pfad}")
        except RuntimeError as exc:
            print(f"  {exc}")
        return

    if args.fake_robotd:
        from .backends.fake_robotd import serve

        asyncio.run(serve(args.fake_robotd))
        return

    cfg = load(args.config, backend=args.backend, robot=args.robot, tof=args.tof, updater=args.updater, port=args.port,
               host=args.host, model=args.model, stt=args.stt, memory_path=args.memory)
    if args.no_memory:
        cfg.memory = False
    if args.no_browser:
        cfg.open_browser = False

    import uvicorn

    url = f"http://{'127.0.0.1' if cfg.host in ('0.0.0.0', '::') else cfg.host}:{cfg.port}"
    fenster = f"{url}/?modul={args.modul}" if args.modul else url    # was das Fenster zeigt (Startseite oder Modul)
    if args.app:
        from .desktop import already_running, open_window, refresh_shortcut_icons

        cfg.app_mode = True
        threading.Thread(target=refresh_shortcut_icons, name="icons", daemon=True).start()
        cfg.hintergrund = bool(args.hintergrund)
        if args.neustart:          # nach „Neu starten“: warten, bis der alte Prozess den Port freigegeben hat
            import time

            restart_log(f"neuer Prozess {__version__} gestartet, warte auf freien Port {cfg.port}")
            for _ in range(240):   # bis 60 s – der alte fährt noch herunter
                if not already_running(url):
                    break
                time.sleep(0.25)
            restart_log("Port frei" if not already_running(url) else "alter Prozess antwortet noch – gebe auf")
        if already_running(url):  # zweiter Doppelklick: nur ein weiteres Fenster
            if not args.hintergrund:
                open_window(fenster)      # dasselbe laufende Knowlin – ein Kern, ein Gedächtnis
            return

    step = restart_log if args.app else (lambda _t: None)    # Programmfenster: Startschritte ins neustart.log
    step(f"Start {__version__}: lade Programm")
    from .server.app import Runtime, create_app

    step("baue Laufzeit auf (Körper, Stimme, Gedächtnis …)")
    try:
        runtime = Runtime(cfg)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    step("Laufzeit bereit")
    if args.hintergrund and not runtime.remote.enabled:
        print("  Handy-Fernbedienung ist aus – im Hintergrund gibt es nichts zu tun.")
        return
    app = create_app(runtime)
    print(f"\n  🧠 Knowlin {__version__} – Backend: {cfg.backend}"
          f"{' (' + cfg.robot + ')' if cfg.backend == 'robotd' else ''}")
    print(f"  Claude: {'an (' + cfg.model + ')' if cfg.api_key else 'aus – kein API-Schlüssel, einfache Befehle aktiv'}")
    if runtime.memory is not None:
        print(f"  Gedächtnis: {runtime.memory.path}")
    print(f"  Oberfläche: {url}\n")

    server = uvicorn.Server(uvicorn.Config(app, host=cfg.host, port=cfg.port, log_level="warning",
                                           log_config=None if args.app else uvicorn.config.LOGGING_CONFIG))

    def stop_server() -> None:
        server.should_exit = True

        def watchdog() -> None:            # hängt das Herunterfahren, nach 15 s hart beenden (Port wird frei)
            import os
            import time

            lernt = bool(getattr(getattr(runtime, "lernen", None), "running", False))
            time.sleep(75 if lernt else 15)     # beim Lernen am PC Zeit lassen, den besten Stand zu speichern
            restart_log("Herunterfahren hing – beende hart")
            os._exit(0)

        threading.Thread(target=watchdog, daemon=True).start()

    runtime.on_idle_exit = stop_server
    runtime.spawn_restart = lambda: _restart(argv if argv is not None else sys.argv[1:])

    def open_when_ready() -> None:
        import time

        for _ in range(100):
            if server.started:
                break
            time.sleep(0.1)
        if args.app and args.hintergrund:
            print("  Im Hintergrund gestartet – Fenster öffnen die Knowlin-Verknüpfungen.")
        elif args.app and args.neustart:
            # das offene Fenster lädt sich von selbst neu; ist keins mehr da, eins öffnen
            time.sleep(15)
            if not runtime.clients:
                from .desktop import open_window

                open_window(url)
        elif args.app:
            from .desktop import open_window

            open_window(fenster)
        elif cfg.open_browser:
            webbrowser.open(url)

    threading.Thread(target=open_when_ready, daemon=True).start()
    step("starte Server")
    server.run()
    if args.neustart:
        restart_log("Server beendet")


def restart_log(text: str) -> None:
    """Kurzes Protokoll des Neustarts im Programmordner (neustart.log) – zum Nachsehen, falls er hakt."""
    import os
    import time

    try:
        path = os.path.join(os.getcwd(), "neustart.log")
        if os.path.exists(path) and os.path.getsize(path) > 50_000:
            os.replace(path, path + ".1")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{os.getpid()}] {text}\n")
    except OSError:
        pass


def restart_command(argv: list[str]) -> list[str]:
    """Dieselben Startoptionen (Port, Konfiguration …) wie vorher, als Programmfenster, ohne „im Hintergrund“."""
    keep = [a for a in argv if a not in ("--hintergrund", "--neustart", "--app")]
    return [sys.executable, "-m", "duckpilot", *keep, "--app", "--neustart"]


def _restart(argv: list[str]) -> None:
    """Nach „Neu starten“: dieselbe Python-Umgebung, derselbe Ordner, dieselben Optionen."""
    import os
    import subprocess

    cmd = restart_command(list(argv))
    # Neue Pakete nötig (requirements.txt geändert)? Dann über start.bat, das sie vorher installiert
    here = os.getcwd()
    req, have = os.path.join(here, "requirements.txt"), os.path.join(sys.prefix, "requirements.txt")
    bat = os.path.join(here, "start.bat")
    try:
        changed = os.path.exists(req) and (not os.path.exists(have) or open(req, "rb").read() != open(have, "rb").read())
    except OSError:
        changed = False
    if sys.platform == "win32" and changed and os.path.exists(bat):
        cmd = ["cmd", "/c", bat]
    flags = 0
    if sys.platform == "win32":
        flags = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    restart_log(f"starte neu: {' '.join(cmd)}")
    for extra in (0x01000000, 0):          # erst mit CREATE_BREAKAWAY_FROM_JOB (falls in einem Job), sonst ohne
        try:
            p = subprocess.Popen(cmd, cwd=os.getcwd(), creationflags=flags | (extra if sys.platform == "win32" else 0),
                                 close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            restart_log(f"neuer Prozess {p.pid} gestartet")
            return
        except OSError as exc:
            restart_log(f"Start fehlgeschlagen ({exc})")
    print("  Neustart ging nicht – bitte über die Verknüpfung starten.")

def _run() -> int | None:
    """Start mit Absturz-Protokoll: Im Programmfenster gibt es keine Konsole – ein Fehler beim Start soll trotzdem
    sichtbar werden (neustart.log im Programmordner und duckpilot.log)."""
    try:
        return main()
    except SystemExit:
        raise
    except BaseException:
        import traceback

        text = traceback.format_exc()
        logging.getLogger("duckpilot").error("Absturz beim Start:\n%s", text)
        restart_log("Absturz: " + text.strip().replace("\n", "\n    "))
        raise


if __name__ == "__main__":
    sys.exit(_run())
