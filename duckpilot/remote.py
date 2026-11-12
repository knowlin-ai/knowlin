"""Handy-Fernbedienung: duckpilot im eigenen WLAN vom Handy aus bedienen.

Sicherheitsmodell (bewusst schlicht):
* Standardmäßig aus. Erst wenn man am PC einschaltet, lauscht ein zweiter Zugang im Heimnetz.
* Am PC lassen sich nur Geräte koppeln, die einen frischen Einmal-Code kennen (QR-Code, 5 Minuten gültig,
  einmal verwendbar, nach 5 Fehlversuchen verbraucht).
* Gekoppelte Geräte bekommen ein zufälliges Gerätezeichen als Cookie. Gespeichert wird nur dessen
  SHA-256-Prüfsumme – wer die Datei liest, kann sich damit nicht anmelden.
* Nur Adressen aus privaten Netzen (192.168.x, 10.x, 172.16–31.x, fe80::, fd00::) kommen überhaupt durch.
* Einiges bleibt dem PC vorbehalten: Schlüssel und Zugangsdaten, bezahltes Training, Installationen,
  Ordner öffnen, die Fernbedienung selbst verwalten.
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
import hashlib
import hmac
import ipaddress
import json
import logging
import re
import secrets
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

COOKIE = "duckpilot_geraet"
DEFAULT_PORT = 8766
CODE_SECONDS = 300
MAX_DEVICES = 8
MAX_TRIES = 5
KURZ_ZEICHEN = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # ohne 0/O und 1/I – gut abzutippen
KURZ_LAENGE = 6                                      # 32⁶ ≈ 1 Mrd., 5 Versuche, 5 Minuten, einmal verwendbar

# (Methode, Pfadmuster) – vom Handy aus gesperrt, nur am PC
PC_ONLY: list[tuple[str, re.Pattern[str]]] = [(m, re.compile(p)) for m, p in [
    ("*", r"^/api/key(/|$)"),
    ("*", r"^/api/anbieter(/|$)"),          # andere KI-Anbieter: Schlüssel, Adresse, Modelle (seit 0.35)
    ("*", r"^/mcp/?$"),
    ("*", r"^/api/mcp(/|$)"),
    ("*", r"^/api/training/token$"),
    ("*", r"^/api/kaggle/zugang$"),
    ("POST", r"^/api/training/start$"),
    ("POST", r"^/api/training/[^/]+/exportieren$"),
    ("POST", r"^/api/open-folder$"),
    ("POST", r"^/api/stimme/installieren$"),
    ("POST", r"^/api/gehirn/laden$"),
    ("POST", r"^/api/reachy/laden$"),           # Pollens Reachy-Modell und Bewegungen nachladen (seit 0.38.2)
    ("POST", r"^/api/reachy/apps/installieren$"),   # Pollens Apps auf den Reachy installieren nur am PC (seit 0.38.19)
    ("POST", r"^/api/pflege/einspielen$"),
    ("POST", r"^/api/modell/laden$"),       # Pollens Robotermodell von GitHub laden
    ("POST", r"^/api/verknuepfung$"),       # Verknüpfungen auf dem Desktop anlegen (seit 0.38)
    ("POST", r"^/api/szene$"),              # Simulator zurücksetzen nur am PC (seit 0.38)
    ("*", r"^/api/fernzugang(/|$)"),
    ("*", r"^/api/personen(/|$)"),          # Gesichtsmerkmale: anlernen, ansehen, löschen nur am PC
    ("*", r"^/api/augen(/|$)"),             # Bilder für die Augen liefert nur das Fenster am PC
    ("*", r"^/api/beenden$"),               # duckpilot beenden, in den Hintergrund schicken, neu starten
    ("*", r"^/api/kollision/reihe(/|$)"),   # Stoßreihe: rechnet minutenlang auf dem PC, Profile nur dort
    ("*", r"^/api/raum(/|$)"),              # Karte der Wohnung und Sichtungen bleiben am PC (seit 0.37)
    ("*", r"^/api/knowlets(/|$)"),          # Knowlets packen, laden, teilen nur am PC (seit 0.38.5)
    ("POST", r"^/api/stimme/(entwerfen|uebernehmen|laden)$"),   # Stimmen entwerfen (Grafikkarte), Modelle laden (0.38.6)
    ("DELETE", r"^/api/stimme/qwen/"),
    ("DELETE", r"^/api/gedankenspur$"),       # seit 0.38.44: Gedankenspur leeren nur am PC
    ("*", r"^/api/fehlerbericht(/|$)"),     # enthält Einstellungen und Protokollzeilen – nur am PC (seit 0.38.6)
    ("*", r"^/api/spiele(/|$)"),            # Kamera-Spiele mit Reachy: Webcam nur am PC (seit 0.38.13)
    ("*", r"^/api/verbindungstest$"),       # prüft Adressen im Heimnetz – nur am PC (seit 0.38.16)
    ("POST", r"^/api/update(/|$)"),          # Updates prüfen und installieren nur am PC (seit 0.38.32)
    ("POST", r"^/api/isaaclab(/|$)"),       # Policy-Dateien übernehmen und einsetzen nur am PC (seit 0.38.27)
]]
# Einstellungen, die ein Handy nicht ändern darf: wohin duckpilot sich verbindet, welches (bezahlte) Modell,
# wohin Gespräche gehen, ob es ein Gedächtnis gibt
PC_ONLY_SETTINGS = {"backend", "robot", "tof", "updater", "media", "configd", "model", "gehirn", "lokal_adresse",
                    "anbieter", "anbieter_modell", "anbieter_adresse",
                    "lokal_modell", "memory", "stt", "whisper_model", "sim_physik", "modul", "reachy_adresse",
                    "koerper_optionen"}
# Was die Augen und das Erkennen von Personen einschaltet – nur am PC (Einverständnis, Webcam)
PC_ONLY_OPTIONS = {"sehen", "personen", "begruessen", "augen"}
# Kopfzeilen, die ein Weiterleiter (Proxy) setzt: kommt so etwas von 127.0.0.1, ist es nicht „der PC selbst“
PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-host", "forwarded", "tailscale-user-login", "x-real-ip")
# Läuft gerade eine Bitte, die vom Handy kam? (für Werkzeuge, die nur am PC Auskunft geben, z. B. „wer ist da“)
REMOTE_TURN: contextvars.ContextVar[bool] = contextvars.ContextVar("duckpilot_remote_turn", default=False)


def proxied(headers) -> bool:
    return any(h in headers for h in PROXY_HEADERS)


# ohne Kopplung erlaubt: die Kopplungsseite selbst und Dateien ohne Inhalt über dich
OPEN_PATHS = re.compile(r"^(/koppeln|/static/.*|/manifest\.webmanifest|/favicon\.ico)$")


# Name dieses PCs im eigenen Tailnet: geraet.tailnet-name.ts.net (Anfragen kommen über „Tailscale Serve“ von 127.0.0.1)
TS_HOST = re.compile(r"((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+ts\.net)(?::(443|[0-9]{1,5}))?", re.I)


def ts_hostname(host_header: str | None) -> str | None:
    m = TS_HOST.fullmatch(host_header or "")
    return m.group(1).lower() if m else None


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def client_ip(host: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not host:
        return None
    try:
        ip = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip


def is_local(host: str | None) -> bool:
    """Anfrage vom PC selbst (127.0.0.1 / ::1)? Testclients ohne Adresse zählen auch dazu."""
    if host in (None, "testclient"):
        return True
    ip = client_ip(host)
    return bool(ip and ip.is_loopback)


HOME_NETS = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16",
                                                "fe80::/10", "fc00::/7")]


def is_home_network(host: str | None) -> bool:
    """Nur echte Heimnetz-Bereiche (RFC 1918, link-local, ULA) – keine Doku-, CGNAT- oder öffentlichen Adressen."""
    ip = client_ip(host)
    return bool(ip is not None and any(ip.version == n.version and ip in n for n in HOME_NETS))


def device_name(user_agent: str | None) -> str:
    ua = user_agent or ""
    if "iPhone" in ua:
        return "iPhone"
    if "iPad" in ua:
        return "iPad"
    if "Android" in ua:
        return "Android-Handy" if "Mobile" in ua else "Android-Tablet"
    if "Windows" in ua:
        return "Windows-PC"
    if "Macintosh" in ua:
        return "Mac"
    return "Gerät"


def lan_addresses() -> list[str]:
    """IPv4-Adressen dieses PCs im Heimnetz, die beste zuerst."""
    found: list[str] = []
    with contextlib.suppress(OSError):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.254.254.254", 1))  # schickt nichts, wählt nur die Schnittstelle
            found.append(s.getsockname()[0])
    with contextlib.suppress(OSError):
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    out = []
    for a in found:
        if a not in out and is_home_network(a):
            out.append(a)
    # 192.168.x zuerst (typisches Heim-WLAN), virtuelle Netze (172.x von WSL/Hyper-V) zuletzt
    out.sort(key=lambda a: (0 if a.startswith("192.168.") else 1 if a.startswith("10.") else 2))
    return out


class RemoteAccess:
    """Einstellungen, Geräte und Einmal-Codes der Handy-Fernbedienung (Datei im lokalen Datenordner)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self.data: dict[str, Any] = {"an": False, "port": DEFAULT_PORT, "geraete": [], "tailscale": False, "ts_name": None}
        self._code: dict[str, Any] | None = None
        self._seen_saved: dict[str, float] = {}
        self._load()

    # ── Datei ─────────────────────────────────────────────────────────────
    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        self.data["an"] = bool(raw.get("an"))
        self.data["tailscale"] = bool(raw.get("tailscale"))
        name = raw.get("ts_name")
        self.data["ts_name"] = name if isinstance(name, str) and ts_hostname(name) == name.lower() else None
        port = raw.get("port")
        if isinstance(port, int) and 1024 <= port <= 65535:
            self.data["port"] = port
        devs = []
        for d in raw.get("geraete") or []:
            if isinstance(d, dict) and isinstance(d.get("hash"), str) and len(d["hash"]) == 64 and isinstance(d.get("id"), str):
                devs.append({"id": d["id"], "hash": d["hash"], "name": str(d.get("name") or "Gerät")[:40],
                             "seit": float(d.get("seit") or 0), "zuletzt": float(d.get("zuletzt") or 0),
                             "adresse": str(d.get("adresse") or "")[:45]})
        self.data["geraete"] = devs[:MAX_DEVICES]

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(f"{self.path.stem}.{secrets.token_hex(4)}.tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)

    # ── Zustand ───────────────────────────────────────────────────────────
    @property
    def enabled(self) -> bool:
        return bool(self.data["an"])

    @property
    def port(self) -> int:
        return int(self.data["port"])

    def set_enabled(self, on: bool) -> None:
        self.data["an"] = bool(on)
        if not on:
            self._code = None
        self.save()

    @property
    def tailscale(self) -> bool:
        return bool(self.data["an"] and self.data["tailscale"])

    def set_tailscale(self, on: bool, name: str | None = None) -> None:
        self.data["tailscale"] = bool(on)
        if name is not None:
            self.data["ts_name"] = name if ts_hostname(name) == name.lower() else None
        self.save()

    def set_port(self, port: int) -> None:
        if not (1024 <= int(port) <= 65535):
            raise ValueError("Port muss zwischen 1024 und 65535 liegen")
        self.data["port"] = int(port)
        self.save()

    def devices(self) -> list[dict[str, Any]]:
        return [{k: d[k] for k in ("id", "name", "seit", "zuletzt", "adresse")} for d in self.data["geraete"]]

    # ── Kopplung ──────────────────────────────────────────────────────────
    def new_code(self) -> dict[str, Any]:
        if not self.enabled:
            raise ValueError("Die Handy-Fernbedienung ist aus")
        # dazu ein kurzer Code zum Eintippen (seit 0.38.28): wer knowlin.local oder die Adresse von Hand öffnet
        kurz = "".join(secrets.choice(KURZ_ZEICHEN) for _ in range(KURZ_LAENGE))
        self._code = {"code": secrets.token_urlsafe(12), "kurz": kurz, "bis": time.time() + CODE_SECONDS, "fehler": 0}
        return {"code": self._code["code"], "kurz": kurz, "gueltig_bis": self._code["bis"], "sekunden": CODE_SECONDS}

    def code_state(self) -> dict[str, Any] | None:
        c = self._code
        if not c or time.time() > c["bis"]:
            return None
        return {"code": c["code"], "kurz": c.get("kurz"), "gueltig_bis": c["bis"]}

    def _passt(self, code: str) -> bool:
        """Langer Code aus dem QR-Code oder der kurze zum Eintippen (Groß/klein, Leer- und Bindestriche egal)."""
        c = self._code
        if not c or not isinstance(code, str):
            return False
        if hmac.compare_digest(code.encode(), c["code"].encode()):
            return True
        roh = re.sub(r"[\s-]", "", code).upper()
        return bool(c.get("kurz")) and len(roh) == KURZ_LAENGE and hmac.compare_digest(roh.encode(), c["kurz"].encode())

    def cancel_code(self) -> None:
        self._code = None

    def code_valid(self, code: str) -> bool:
        """Prüft, ohne zu verbrauchen (für die Bestätigungsseite)."""
        c = self._code
        return bool(self.enabled and c and time.time() <= c["bis"] and self._passt(code))

    def pair(self, code: str, name: str, address: str | None) -> str:
        """Einmal-Code gegen ein Gerätezeichen tauschen. Gibt das Zeichen zurück (nur fürs Cookie)."""
        if not self.enabled:
            raise PermissionError("Die Handy-Fernbedienung ist am PC ausgeschaltet.")
        c = self._code
        if not c or time.time() > c["bis"]:
            self._code = None
            raise PermissionError("Der Code ist abgelaufen. Am PC einen neuen QR-Code anzeigen.")
        if not self._passt(code):
            c["fehler"] += 1
            if c["fehler"] >= MAX_TRIES:
                self._code = None
            raise PermissionError("Der Code stimmt nicht.")
        if len(self.data["geraete"]) >= MAX_DEVICES:
            raise PermissionError(f"Schon {MAX_DEVICES} Geräte gekoppelt – am PC erst eines abmelden.")
        self._code = None  # einmal verwendbar
        token = secrets.token_urlsafe(32)
        now = time.time()
        clean = re.sub(r"[\x00-\x1f\x7f]", "", name or "").strip()[:40] or "Gerät"
        self.data["geraete"].append({"id": secrets.token_hex(6), "hash": _hash(token), "name": clean,
                                     "seit": now, "zuletzt": now, "adresse": (address or "")[:45]})
        self.save()
        log.info("Handy-Fernbedienung: Gerät „%s“ gekoppelt", clean)
        return token

    def device_for(self, token: str | None, address: str | None = None) -> dict[str, Any] | None:
        if not token or not isinstance(token, str) or len(token) > 100:
            return None
        h = _hash(token)
        for d in self.data["geraete"]:
            if hmac.compare_digest(d["hash"], h):
                now = time.time()
                d["zuletzt"] = now
                if address:
                    d["adresse"] = address[:45]
                if now - self._seen_saved.get(d["id"], 0) > 600:  # „zuletzt gesehen“ höchstens alle 10 min schreiben
                    self._seen_saved[d["id"]] = now
                    with contextlib.suppress(OSError):
                        self.save()
                return d
        return None

    def revoke(self, did: str) -> bool:
        before = len(self.data["geraete"])
        self.data["geraete"] = [d for d in self.data["geraete"] if d["id"] != did]
        if len(self.data["geraete"]) != before:
            self.save()
            return True
        return False

    def revoke_all(self) -> int:
        n = len(self.data["geraete"])
        self.data["geraete"] = []
        self.save()
        return n

    # ── Zugriffsprüfung ───────────────────────────────────────────────────
    def check(self, host: str | None, token: str | None, method: str, path: str,
              via_tailscale: bool = False) -> tuple[int, str] | None:
        """None = erlaubt. Sonst (Statuscode, Grund) für Anfragen, die nicht vom PC selbst kommen.

        via_tailscale: kam über Tailscale Serve (Host *.ts.net, technisch von 127.0.0.1) – zählt nie als „PC selbst“.
        """
        if via_tailscale:
            if not self.tailscale:
                return 403, "Der Zugang über Tailscale ist am PC ausgeschaltet."
        else:
            if is_local(host):
                return None
            if not is_home_network(host):
                return 403, "Nur aus dem eigenen Heimnetz erreichbar."
            if not self.enabled:
                return 403, "Die Handy-Fernbedienung ist am PC ausgeschaltet."
        if OPEN_PATHS.match(path):
            return None
        address = "über Tailscale" if via_tailscale else (client_ip(host).compressed if client_ip(host) else None)
        device = self.device_for(token, address)
        if device is None:
            return 401, "Dieses Gerät ist nicht gekoppelt."
        if pc_only(method, path):
            return 403, "Das geht nur direkt am PC."
        return None

    # ── Für die Oberfläche ────────────────────────────────────────────────
    def status(self, listening: bool, error: str | None = None) -> dict[str, Any]:
        addrs = lan_addresses()
        return {
            "an": self.enabled, "port": self.port, "lauscht": listening, "fehler": error,
            "adressen": [f"http://{a}:{self.port}" for a in addrs],
            "geraete": self.devices(), "code": self.code_state(), "max_geraete": MAX_DEVICES,
            "tailscale": {"an": self.tailscale, "name": self.data.get("ts_name"),
                          "adresse": f"https://{self.data['ts_name']}" if self.data.get("ts_name") else None},
        }


def pc_only(method: str, path: str) -> bool:
    return any((m == "*" or m == method) and p.match(path) for m, p in PC_ONLY)


class RemoteListener:
    """Zweiter Zugang im Heimnetz – derselbe Server, eigener Port, startet und stoppt im laufenden Betrieb."""

    def __init__(self) -> None:
        from .mdns import Ansage

        self.server = None
        self.task: asyncio.Task | None = None
        self.error: str | None = None
        self.port: int | None = None
        self.ansage = Ansage()            # knowlin.local im Heimnetz, solange der Zugang läuft (seit 0.38.28)

    @property
    def listening(self) -> bool:
        return bool(self.server is not None and self.server.started and self.task and not self.task.done())

    async def start(self, app: Any, port: int) -> None:
        await self.stop()
        self.error = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", port))
            sock.listen(64)
            sock.setblocking(False)
        except OSError as exc:
            with contextlib.suppress(Exception):
                sock.close()
            self.error = f"Port {port} ist belegt oder gesperrt ({exc.strerror or exc})."
            log.warning("Handy-Fernbedienung: %s", self.error)
            return
        import uvicorn

        cfg = uvicorn.Config(app, lifespan="off", log_level="warning", log_config=None, ws="auto")
        server = uvicorn.Server(cfg)
        self.server = server
        self.port = port

        async def run() -> None:
            try:
                serve = getattr(server, "_serve", None)   # ohne eigene Signal-Handler (die hat der Hauptserver)
                await (serve([sock]) if serve else server.serve([sock]))
            except BaseException as exc:                  # uvicorn beendet bei Fehlern mit SystemExit
                if isinstance(exc, asyncio.CancelledError):
                    raise
                self.error = f"Zugang gestoppt: {type(exc).__name__}"
                log.exception("Handy-Fernbedienung")
            finally:
                with contextlib.suppress(Exception):
                    sock.close()

        self.task = asyncio.create_task(run(), name="fernzugang")
        for _ in range(50):
            if server.started or self.task.done():
                break
            await asyncio.sleep(0.05)
        log.info("Handy-Fernbedienung lauscht auf Port %s", port)
        if self.listening:
            await self.ansage.start(port, lan_addresses())

    async def stop(self) -> None:
        await self.ansage.stop()
        if self.server is not None:
            self.server.should_exit = True
            self.server.force_exit = True
        if self.task is not None:
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError, Exception):
                await asyncio.wait_for(asyncio.shield(self.task), timeout=3.0)
            if not self.task.done():
                self.task.cancel()
        self.server = None
        self.task = None
        self.port = None
