"""Wetter (seit 0.40, „Gespräch in Echtzeit“): heute und morgen über Open-Meteo – ohne Konto, ohne Schlüssel.

Entscheidung des Maintainers (19.11.): Open-Meteo, der Ort nur als Stadt aus den Einstellungen (`wetter_ort`) oder aus
der Frage („Wie ist das Wetter in Wien?“) – nie eine Standortabfrage, nie GPS oder IP-Ortung. An Open-Meteo gehen nur
der Stadtname (Suche nach Koordinaten) und die Koordinaten der Stadt; nichts über Personen, nichts aus dem Gedächtnis.
Gefragt wird nur, wenn jemand nach dem Wetter fragt; Ergebnisse bleiben 15 Minuten im Speicher (nicht auf der Platte).
Im Offline-Modus (`DUCKPILOT_OFFLINE`) wird nichts abgefragt.

Die Sätze entstehen ohne Sprachmodell aus den Zahlen (`satz`), damit auch der Modus ohne KI das Wetter sagen kann und
nichts dazuerfunden wird. Wetter-Codes nach WMO (wie Open-Meteo sie liefert).
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.parse
from typing import Any, Callable


def offline() -> bool:
    """Wie `modell.offline` – hier nachgebaut, weil der Kern nicht von den Körpern abhängen darf."""
    return os.environ.get("DUCKPILOT_OFFLINE", "") not in ("", "0")


GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WETTER_URL = "https://api.open-meteo.com/v1/forecast"
GUELTIG_S = 15 * 60
ORT_MAX = 60

# WMO-Code → (deutsch, englisch)
CODES: dict[int, tuple[str, str]] = {
    0: ("klar", "clear"), 1: ("überwiegend klar", "mainly clear"), 2: ("teils bewölkt", "partly cloudy"),
    3: ("bedeckt", "overcast"), 45: ("Nebel", "fog"), 48: ("Raureifnebel", "rime fog"),
    51: ("leichter Nieselregen", "light drizzle"), 53: ("Nieselregen", "drizzle"), 55: ("starker Nieselregen", "heavy drizzle"),
    56: ("gefrierender Nieselregen", "freezing drizzle"), 57: ("gefrierender Nieselregen", "freezing drizzle"),
    61: ("leichter Regen", "light rain"), 63: ("Regen", "rain"), 65: ("starker Regen", "heavy rain"),
    66: ("gefrierender Regen", "freezing rain"), 67: ("gefrierender Regen", "freezing rain"),
    71: ("leichter Schneefall", "light snow"), 73: ("Schneefall", "snow"), 75: ("starker Schneefall", "heavy snow"),
    77: ("Schneegriesel", "snow grains"), 80: ("leichte Regenschauer", "light showers"), 81: ("Regenschauer", "showers"),
    82: ("heftige Regenschauer", "heavy showers"), 85: ("Schneeschauer", "snow showers"), 86: ("starke Schneeschauer", "heavy snow showers"),
    95: ("Gewitter", "thunderstorm"), 96: ("Gewitter mit Hagel", "thunderstorm with hail"),
    99: ("schweres Gewitter mit Hagel", "severe thunderstorm with hail"),
}
NASS = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}


def beschreibung(code: Any, en: bool = False) -> str:
    try:
        d = CODES.get(int(code))
    except (TypeError, ValueError):
        d = None
    return (d[1] if en else d[0]) if d else ("unknown weather" if en else "unbekanntes Wetter")


def ort_pruefen(ort: str) -> str:
    """Nur ein Stadtname: eine Zeile, höchstens 60 Zeichen, ohne Steuerzeichen."""
    o = " ".join(str(ort or "").split())
    if len(o) > ORT_MAX or any(ord(c) < 32 for c in o):
        raise ValueError(f"Ort: höchstens {ORT_MAX} Zeichen, eine Zeile")
    return o


def _hole(url: str) -> dict[str, Any]:
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "Knowlin duckpilot (Wetter)"})
    with urllib.request.urlopen(req, timeout=8) as res:          # noqa: S310 – feste https-Adressen oben
        return json.loads(res.read(256 * 1024).decode("utf-8"))


class Wetter:
    def __init__(self, fetch: Callable[[str], dict[str, Any]] | None = None) -> None:
        self.fetch = fetch or _hole
        self._orte: dict[str, tuple[float, dict[str, Any] | None]] = {}
        self._wetter: dict[str, tuple[float, dict[str, Any]]] = {}

    def ort_suchen(self, name: str, en: bool = False) -> dict[str, Any] | None:
        schluessel = name.lower()
        jetzt = time.time()
        if schluessel in self._orte and jetzt - self._orte[schluessel][0] < 24 * 3600:
            return self._orte[schluessel][1]
        q = urllib.parse.urlencode({"name": name, "count": 1, "language": "en" if en else "de", "format": "json"})
        daten = self.fetch(f"{GEO_URL}?{q}")
        treffer = (daten.get("results") or [None])[0]
        ort = None
        if treffer and "latitude" in treffer and "longitude" in treffer:
            ort = {"name": str(treffer.get("name") or name), "land": str(treffer.get("country") or ""),
                   "lat": round(float(treffer["latitude"]), 3), "lon": round(float(treffer["longitude"]), 3)}
        self._orte[schluessel] = (jetzt, ort)
        return ort

    def abfrage(self, ort_name: str, tag: str = "heute", en: bool = False) -> dict[str, Any]:
        """Wetter für `heute` (jetzt + Tageswerte) oder `morgen`. Ehrlich, wenn etwas fehlt."""
        if offline():
            return {"ok": False, "fehler": "Offline mode – I don't look up the weather." if en else
                    "Offline-Modus – ich frage kein Wetter ab."}
        try:
            name = ort_pruefen(ort_name)
        except ValueError as exc:
            return {"ok": False, "fehler": str(exc)}
        if not name:
            return {"ok": False, "ort_fehlt": True,
                    "fehler": "For the weather I need a city – enter it under System → Settings → Knowlin or ask e.g. "
                              "“What's the weather in Vienna?”." if en else
                              "Für das Wetter brauche ich eine Stadt – trag sie unter System → Einstellungen → Knowlin "
                              "ein oder frag z. B. „Wie ist das Wetter in Wien?“."}
        try:
            ort = self.ort_suchen(name, en)
            if ort is None:
                return {"ok": False, "fehler": f"I can't find “{name}”." if en else f"Den Ort „{name}“ finde ich nicht."}
            key = f"{ort['lat']},{ort['lon']}"
            jetzt = time.time()
            if key in self._wetter and jetzt - self._wetter[key][0] < GUELTIG_S:
                daten = self._wetter[key][1]
            else:
                q = urllib.parse.urlencode({
                    "latitude": ort["lat"], "longitude": ort["lon"], "timezone": "auto", "forecast_days": 2,
                    "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,precipitation",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"})
                daten = self.fetch(f"{WETTER_URL}?{q}")
                self._wetter[key] = (jetzt, daten)
        except Exception as exc:  # noqa: BLE001 – Netz, Proxy, Dienst: ehrlich sagen, nie raten
            return {"ok": False, "fehler": f"The weather service is not reachable right now ({type(exc).__name__})." if en
                    else f"Das Wetter ist gerade nicht erreichbar ({type(exc).__name__})."}
        i = 1 if tag == "morgen" else 0
        d = daten.get("daily") or {}

        def wert(reihe: str) -> float | None:
            try:
                v = (d.get(reihe) or [])[i]
                return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)
            except (IndexError, TypeError, ValueError):
                return None

        r: dict[str, Any] = {"ok": True, "ort": ort["name"], "land": ort["land"], "tag": "morgen" if i else "heute",
                             "max": wert("temperature_2m_max"), "min": wert("temperature_2m_min"),
                             "regen_prozent": wert("precipitation_probability_max"), "code": wert("weather_code"),
                             "quelle": "Open-Meteo"}
        if not i:
            c = daten.get("current") or {}
            r["jetzt"] = {"temperatur": c.get("temperature_2m"), "gefuehlt": c.get("apparent_temperature"),
                          "code": c.get("weather_code"), "wind_kmh": c.get("wind_speed_10m"),
                          "niederschlag_mm": c.get("precipitation")}
        r["text"] = satz(r, en)
        return r


def _grad(v: Any) -> str:
    return f"{round(float(v))} Grad" if v is not None else "?"


def satz(r: dict[str, Any], en: bool = False) -> str:
    """Das Wetter in ein, zwei Sätzen – ohne Sprachmodell."""
    if not r.get("ok"):
        return str(r.get("fehler") or "")
    ort = r["ort"]
    teile: list[str] = []
    j = r.get("jetzt")
    if j and j.get("temperatur") is not None:
        teile.append(f"In {ort} it is {round(float(j['temperatur']))} °C and {beschreibung(j.get('code'), True)} right now."
                     if en else f"In {ort} sind es gerade {_grad(j['temperatur'])}, {beschreibung(j.get('code'))}.")
    if r.get("max") is not None and r.get("min") is not None:
        wann = ("Tomorrow" if r["tag"] == "morgen" else "Today") if en else ("Morgen" if r["tag"] == "morgen" else "Heute")
        art = beschreibung(r.get("code"), en)
        if en:
            teile.append(f"{wann}: {art}, {round(r['min'])} to {round(r['max'])} °C"
                         + (f" in {ort}" if not j else "") + ".")
        else:
            teile.append(f"{wann} {('in ' + ort + ' ') if not j else ''}{art}, {round(r['min'])} bis {_grad(r['max'])}.")
    p = r.get("regen_prozent")
    if p is not None:
        if p >= 60:
            teile.append("Better take an umbrella." if en else "Nimm lieber einen Schirm mit.")
        elif p >= 30:
            teile.append(f"Chance of rain {round(p)} %." if en else f"Regenrisiko {round(p)} Prozent.")
    return " ".join(teile) or ("I have no numbers for that right now." if en else "Dazu habe ich gerade keine Zahlen.")
