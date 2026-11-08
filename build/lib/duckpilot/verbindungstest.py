"""Verbindungstest vor dem ersten Start am echten Roboter (seit 0.38.16).

Prüft eine Adresse, **bevor** Knowlin sich dauerhaft damit verbindet – nur lesend: Adresse, erreichbar, Version des
Dienstes auf dem Roboter, Akku. Es bewegt sich dabei nichts; die erste Bewegung macht der Mensch danach selbst über
die Oberfläche, mit Not-Aus und Sperre wie immer.

Ergebnis: eine Liste von Schritten `{was, stand, text}` mit `stand` = "ok", "hinweis" oder "fehler" – die Oberfläche
zeigt jeden Schritt mit Zeichen *und* Text (nie Farbe allein).
"""

from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
from typing import Any

from .backends.robotd import API_VERSION, RpcConnection, _find_fraction, parse_address

KOERPER = ("microduck", "reachy_mini", "open_duck_mini")
WARTEN_S = 3.0


def _schritt(was: str, stand: str, text: str) -> dict[str, str]:
    return {"was": was, "stand": stand, "text": text}


def _ergebnis(schritte: list[dict[str, str]], **mehr: Any) -> dict[str, Any]:
    return {"ok": all(s["stand"] != "fehler" for s in schritte), "schritte": schritte, **mehr}


def _akku(anteil: float | None) -> dict[str, str]:
    if anteil is None:
        return _schritt("Akku", "hinweis", "Der Roboter meldet keinen Akkustand – vor dem Laufen selbst nachsehen.")
    prozent = round(anteil * 100)
    if prozent < 20:
        return _schritt("Akku", "hinweis", f"{prozent} % – erst laden, bevor sie läuft.")
    return _schritt("Akku", "ok", f"{prozent} %")


async def pruefe_microduck(adresse: str, warten: float = WARTEN_S) -> dict[str, Any]:
    """robotd der Microduck: hello (Protokollversion), robot.health (Akku). Keine Bewegung, keine Policy."""
    schritte = []
    adresse = (adresse or "").strip()
    try:
        parse_address(adresse)
    except ValueError:
        return _ergebnis([_schritt("Adresse", "fehler", "Adresse nicht verstanden – Beispiel: tcp:127.0.0.1:7900")])
    schritte.append(_schritt("Adresse", "ok", adresse))
    conn = RpcConnection(adresse, "verbindungstest")
    try:
        try:
            await asyncio.wait_for(conn.connect(), warten)
        except OSError as exc:              # TimeoutError gehört dazu
            grund = ("keine Antwort" if isinstance(exc, TimeoutError) else "Verbindung abgelehnt"
                     if isinstance(exc, ConnectionRefusedError) else (exc.strerror or str(exc)))
            schritte.append(_schritt("Erreichbar", "fehler",
                                     f"{grund}. Läuft der Tunnel (ssh -N -L 7900:/run/robotd.sock …) und ist die Ente an?"))
            return _ergebnis(schritte)
        schritte.append(_schritt("Erreichbar", "ok", "robotd antwortet"))
        try:
            info = await conn.call("hello", {"api_version": API_VERSION}, timeout=warten) or {}
        except Exception as exc:  # noqa: BLE001 – jede Antwort ist hier ein Befund, kein Absturz
            schritte.append(_schritt("Version", "fehler", f"robotd versteht die Begrüßung nicht ({exc})."))
            return _ergebnis(schritte)
        theirs = info.get("api_version") if isinstance(info, dict) else None
        dienst = info.get("daemon_version") if isinstance(info, dict) else None
        if isinstance(theirs, int) and theirs != API_VERSION:
            schritte.append(_schritt("Version", "hinweis",
                                     f"robotd spricht Protokoll {theirs}, Knowlin {API_VERSION}. Meist geht es trotzdem – "
                                     "bei Fehlern die Software der Ente aktualisieren."))
        else:
            schritte.append(_schritt("Version", "ok", f"Protokoll {theirs or API_VERSION}" + (f", robotd {dienst}" if dienst else "")))
        try:
            health = await conn.call("robot.health", timeout=warten)
        except Exception:  # noqa: BLE001
            health = None
        schritte.append(_akku(_find_fraction(health)))
        if isinstance(health, dict) and health.get("healthy") is False:
            schritte.append(_schritt("Zustand", "hinweis", "robotd meldet ein Problem – Details unter Roboter-Pflege."))
        return _ergebnis(schritte, api_version=theirs, dienst=dienst)
    finally:
        await conn.close()


def _http_json(url: str, warten: float) -> Any:
    with urllib.request.urlopen(urllib.request.Request(url), timeout=warten) as r:  # noqa: S310 – geprüfte http(s)-Adresse
        return json.loads(r.read().decode() or "null")


async def pruefe_reachy(adresse: str, warten: float = WARTEN_S) -> dict[str, Any]:
    """Pollens Reachy-Mini-Daemon: /api/daemon/status (Version, Zustand), /api/state/full (Kopf lesbar). Nur GET."""
    schritte = []
    adresse = (adresse or "").strip().rstrip("/")
    teile = urllib.parse.urlsplit(adresse)
    if teile.scheme not in ("http", "https") or not teile.hostname:
        return _ergebnis([_schritt("Adresse", "fehler", "Adresse beginnt mit http:// – z. B. http://reachy-mini.local:8000")])
    schritte.append(_schritt("Adresse", "ok", adresse))
    try:
        status = await asyncio.to_thread(_http_json, f"{adresse}/api/daemon/status", warten)
    except Exception as exc:  # noqa: BLE001
        grund = getattr(exc, "reason", None) or exc
        schritte.append(_schritt("Erreichbar", "fehler",
                                 f"{grund}. Ist Reachy Mini an und im selben Netz (Wireless) bzw. per USB verbunden (Lite)?"))
        return _ergebnis(schritte)
    schritte.append(_schritt("Erreichbar", "ok", "Pollens Daemon antwortet"))
    status = status if isinstance(status, dict) else {}
    version = status.get("version") or status.get("daemon_version")
    zustand = status.get("state")
    schritte.append(_schritt("Version", "ok", f"Daemon {version}" if version else "Daemon meldet keine Version"))
    if zustand and str(zustand).lower() not in ("running", "ready"):
        schritte.append(_schritt("Zustand", "hinweis", f"Daemon meldet „{zustand}“ – in Pollens App einmal starten."))
    try:
        await asyncio.to_thread(_http_json, f"{adresse}/api/state/full", warten)
        schritte.append(_schritt("Kopf", "ok", "Stellung lesbar"))
    except Exception:  # noqa: BLE001
        schritte.append(_schritt("Kopf", "hinweis", "Stellung nicht lesbar – Bewegungen könnten fehlschlagen."))
    return _ergebnis(schritte, dienst=version)


async def pruefen(koerper: str, adresse: str) -> dict[str, Any]:
    if koerper == "microduck":
        return await pruefe_microduck(adresse)
    if koerper == "reachy_mini":
        return await pruefe_reachy(adresse)
    if koerper == "open_duck_mini":
        return _ergebnis([_schritt("Open Duck Mini", "fehler", "Am echten Roboter noch nicht unterstützt – kommt ab Lieferung.")])
    return _ergebnis([_schritt("Körper", "fehler", "Unbekannter Körper")])
