"""Fehlerbericht mit Aufzeichnung – „Das lief schief“ (seit 0.36.2, Launch-Paket).

Ab der Lieferwelle sind die Berichte der ersten Besitzer das Wertvollste. Ein Klick hält fest, was in den letzten
30 Sekunden passiert ist: Zustand der Ente fünfmal pro Sekunde (Haltung, Position, Befehl, Verhalten, Sturz …), die
Ereignisse der Bewegungs-Engine, Version, Körper und Einstellungen.

Was nie hineinkommt (Projektregel): Gespräche, Personen, Bilder, Schlüssel. Deshalb arbeitet der
Bericht mit einer **Erlaubt-Liste** – nur ausdrücklich genannte Felder gehen mit, alles andere bleibt draußen. Der
Name der Ente wird ersetzt, Pfade mit dem Benutzernamen gekürzt. Der Bericht wird nur gespeichert und angezeigt;
abschicken tut ihn der Mensch selbst (GitHub-Issue mit angehängter Datei).
"""

from __future__ import annotations

import json
import platform
import re
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import quote

SEKUNDEN = 30
TAKT_S = 0.2
REPO = "knowlin-ai/knowlin"             # Ziel für „Auf GitHub melden“ (Organisation knowlin-ai, Maintainer knowlin-dev)

# Erlaubt-Listen: nur diese Felder gehen in den Bericht
ZUSTAND = ("t", "connected", "powered", "enabled", "fallen", "fall_side", "sitting", "picked_up", "x", "y", "yaw",
           "twist", "requested", "limited_by", "skill", "skill_progress", "battery", "backend", "kopf_stabil", "holding",
           "gait_phase")
ENGINE = ("aktuell", "laufzeit_s", "warteschlange", "reflex", "ziel")
EREIGNIS_FELDER = ("type", "message", "what", "item", "side", "skill", "grund", "reason", "behavior", "result")
EREIGNIS_NIE = {"chat", "hear", "person", "personen", "face", "gesicht", "memory", "kamera", "bild", "image", "speech"}
EINSTELLUNGEN = ("backend", "sim_physik", "model_style", "pakete", "stt", "tts", "stimme_motor", "entenlaute", "plaudern",
                 "schnellbefehle", "mcp", "sprache", "gehirn", "anbieter", "model", "idle_life", "obstacle_guard",
                 "ausweichen", "auto_recover", "stopp_fenster_s", "kollision_protest", "kopf_stabil", "energie", "humor",
                 "emotions", "memory", "klang_hoehe", "klang_farbe")


def _rund(v: Any) -> Any:
    if isinstance(v, float):
        return round(v, 3)
    if isinstance(v, (list, tuple)):
        return [_rund(x) for x in v]
    if isinstance(v, dict):
        return {k: _rund(x) for k, x in v.items()}
    return v


def _sauber(text: str, ente: str = "") -> str:
    """Pfade mit Benutzernamen kürzen, den Namen der Ente ersetzen, Länge begrenzen."""
    text = re.sub(r"[A-Za-z]:\\+Users\\+[^\\\s\"']+", r"C:\\Users\\…", str(text))
    text = re.sub(r"/(home|Users)/[^/\s\"']+", r"/\1/…", text)
    if ente and len(ente) > 1:
        text = re.sub(re.escape(ente), "die Ente", text, flags=re.I)
    return text[:300]


class Blackbox:
    """Ringpuffer der letzten 30 Sekunden – nur erlaubte Felder, nie Gespräche, Personen, Bilder, Schlüssel."""

    def __init__(self, sekunden: float = SEKUNDEN) -> None:
        self.zustaende: deque[dict[str, Any]] = deque(maxlen=int(sekunden / TAKT_S) + 1)
        self.ereignisse: deque[dict[str, Any]] = deque(maxlen=200)
        self.sekunden = sekunden

    def zustand(self, st: dict[str, Any], engine: dict[str, Any] | None) -> None:
        z = {k: _rund(st[k]) for k in ZUSTAND if k in st}
        if isinstance(st.get("physik"), dict):
            z["policy"] = st["physik"].get("policy")
        if engine:
            z["engine"] = {k: _rund(engine.get(k)) for k in ENGINE if k in engine}
        z["zeit"] = round(time.time(), 2)
        self.zustaende.append(z)

    def ereignis(self, ev: dict[str, Any]) -> None:
        art = str(ev.get("type", ""))
        if art.lower() in EREIGNIS_NIE or any(w in art.lower() for w in ("person", "chat", "gesicht", "kamera")):
            return
        e = {k: _rund(ev[k]) for k in EREIGNIS_FELDER if k in ev and isinstance(ev[k], (str, int, float, bool))}
        e["zeit"] = round(time.time(), 2)
        self.ereignisse.append(e)

    def bericht(self, *, version: str, einstellungen: dict[str, Any], ente: str = "", beschreibung: str = "",
                log: list[str] | None = None) -> dict[str, Any]:
        jetzt = time.time()
        grenze = jetzt - self.sekunden
        zustaende = [z for z in self.zustaende if z["zeit"] >= grenze]
        ereignisse = [{**e, "message": _sauber(e.get("message", ""), ente)} if "message" in e else e
                      for e in self.ereignisse if e["zeit"] >= grenze]
        for z in zustaende + ereignisse:
            z["vor_s"] = round(jetzt - z.pop("zeit"), 2)
            if isinstance(z.get("engine"), dict) and z["engine"].get("aktuell"):
                z["engine"]["aktuell"] = _sauber(z["engine"]["aktuell"], ente)
        return {
            "art": "duckpilot-fehlerbericht",
            "format": 1,
            "erstellt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "version": version,
            "system": {"python": sys.version.split()[0], "os": platform.system(), "os_version": platform.release(),
                       "maschine": platform.machine()},
            "beschreibung": _sauber(beschreibung, ente)[:2000] if beschreibung else "",
            "einstellungen": {k: _rund(einstellungen[k]) for k in EINSTELLUNGEN if k in einstellungen},
            "zustand": zustaende,
            "ereignisse": ereignisse,
            "log": [_sauber(z, ente) for z in (log or [])][-60:],
            "nicht_enthalten": "Gespräche, Personen, Bilder, Schlüssel, Gedächtnis",
        }


def log_zeilen(pfad: Path, n: int = 400) -> list[str]:
    """Nur Warnungen und Fehler aus dem Protokoll (dort stehen keine Gespräche)."""
    try:
        zeilen = pfad.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []
    return [z for z in zeilen if re.search(r"\b(WARNING|ERROR|CRITICAL|Traceback)\b", z)]


def speichern(ordner: Path, bericht: dict[str, Any]) -> Path:
    ordner.mkdir(parents=True, exist_ok=True)
    pfad = ordner / f"bericht-{time.strftime('%Y%m%d-%H%M%S')}.json"
    pfad.write_text(json.dumps(bericht, ensure_ascii=False, indent=1), encoding="utf-8")
    return pfad


def issue_link(bericht: dict[str, Any], datei: str) -> str:
    """Neues GitHub-Issue, vorausgefüllt – die Datei hängt der Mensch selbst an (nichts geht automatisch raus)."""
    e = bericht["einstellungen"]
    titel = f"Das lief schief: {bericht['beschreibung'][:60] or 'Fehlerbericht'}"
    text = (f"**Was ist passiert?**\n{bericht['beschreibung'] or '…'}\n\n"
            f"**duckpilot** {bericht['version']} · {bericht['system']['os']} {bericht['system']['os_version']} · "
            f"Körper: {e.get('backend')}{' (echte Physik)' if e.get('sim_physik') else ''} · Gehirn: {e.get('gehirn')}\n\n"
            f"Bitte die Datei `{datei}` hier anhängen (Aufzeichnung der letzten 30 s – ohne Gespräche, Personen, Bilder, "
            f"Schlüssel).")
    return f"https://github.com/{REPO}/issues/new?labels=fehlerbericht&title={quote(titel)}&body={quote(text)}"
