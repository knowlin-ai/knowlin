"""Kalender-Abo aus einer lokalen Datei (seit 0.42, Fahrplan „Alltag“).

Statt eine .ics-Datei einmal zu übernehmen, merkt sich der Alltagsbuddy ihren Pfad und liest sie neu ein, sobald sie
sich ändert (Größe oder Änderungszeit). Das passt zu Kalendern, die eine Datei auf dem PC aktuell halten – etwa ein
Export, den Thunderbird, Outlook oder ein Sync-Programm regelmäßig überschreibt. Eine Anmeldung bei Google, Microsoft
oder Apple gibt es nicht; ins Netz geht nichts.

Was aus der Datei verschwindet und noch in der Zukunft lag, verschwindet auch hier – aber nur Termine aus dem Abo, nie
von Hand eingetragene oder einmal übernommene.

Den Pfad setzt man nur direkt am PC (`remote.PC_ONLY`); im Überblick steht nur der Dateiname, nicht der ganze Pfad.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .buddy import Planner

MAX_BYTES = 2_000_000
PRUEF_ALLE_S = 60.0
QUELLE = "abo"


def pfad_pruefen(roh: Any) -> Path:
    text = str(roh or "").strip().strip('"').strip("'")
    if not text:
        raise ValueError("Welche Datei? Den vollständigen Pfad zur .ics-Datei angeben.")
    p = Path(text).expanduser()
    if not p.is_absolute():
        raise ValueError("Bitte den vollständigen Pfad angeben, z. B. C:\\Users\\…\\kalender.ics.")
    if p.suffix.lower() != ".ics":
        raise ValueError("Das ist keine Kalenderdatei – sie muss auf .ics enden.")
    if not p.is_file():
        raise ValueError("Diese Datei gibt es nicht (oder es ist ein Ordner).")
    return p


def setzen(planner: Planner, roh: Any) -> dict[str, Any]:
    """Abo auf eine Datei setzen und gleich einlesen. Ein anderes Abo vorher sauber beenden."""
    p = pfad_pruefen(roh)
    with planner.lock:
        if (planner.data.get("abo") or {}).get("pfad") not in (None, "", str(p)):
            _entfernen(planner, alle=True)
        planner.data["abo"] = {"pfad": str(p)}
        planner.save()
    lesen(planner, erzwingen=True)
    return anzeige(planner)


def beenden(planner: Planner) -> int:
    """Abo aus: Termine aus dem Abo löschen, Pfad vergessen."""
    with planner.lock:
        n = _entfernen(planner, alle=True)
        planner.data["abo"] = {}
        planner.save()
    return n


def lesen(planner: Planner, erzwingen: bool = False) -> dict[str, Any] | None:
    """Neu einlesen, wenn sich die Datei geändert hat. Gibt den neuen Stand zurück – oder None, wenn nichts zu tun war."""
    abo = planner.data.get("abo") or {}
    pfad = abo.get("pfad")
    if not pfad:
        return None
    try:
        st = Path(pfad).stat()
    except OSError:
        return _fehler(planner, "Die Datei ist gerade nicht da – ich schaue in einer Minute wieder nach.")
    kennung = [st.st_mtime_ns, st.st_size]
    if not erzwingen and abo.get("kennung") == kennung:
        return None
    if st.st_size > MAX_BYTES:
        return _fehler(planner, "Die Datei ist zu groß (höchstens 2 MB).", kennung)
    try:
        text = Path(pfad).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return _fehler(planner, "Die Datei lässt sich gerade nicht lesen.")
    if "BEGIN:VCALENDAR" not in text[:2000]:
        return _fehler(planner, "Die Datei ist keine Kalenderdatei (mehr).", kennung)
    res = planner.import_ics(text, source=QUELLE)
    with planner.lock:
        weg = _entfernen(planner, behalten=set(res.get("uids", ())))
        planner.data["abo"] = {"pfad": pfad, "kennung": kennung, "stand": planner.clock().isoformat(timespec="minutes"),
                               "anzahl": res["importiert"], "entfernt": weg, "fehler": ""}
        planner.save()
    return planner.data["abo"]


def anzeige(planner: Planner) -> dict[str, Any]:
    """Für die Oberfläche: nur der Dateiname, nie der ganze Pfad."""
    abo = planner.data.get("abo") or {}
    if not abo.get("pfad"):
        return {"an": False}
    return {"an": True, "datei": Path(abo["pfad"]).name, "stand": abo.get("stand", ""),
            "anzahl": abo.get("anzahl", 0), "fehler": abo.get("fehler", "")}


def _fehler(planner: Planner, text: str, kennung: list[int] | None = None) -> dict[str, Any] | None:
    with planner.lock:
        abo = planner.data.get("abo") or {}
        if abo.get("fehler") == text and (kennung is None or abo.get("kennung") == kennung):
            return None                                     # schon gemeldet
        abo["fehler"] = text
        if kennung is not None:
            abo["kennung"] = kennung
        planner.data["abo"] = abo
        planner.save()
        return abo


def _entfernen(planner: Planner, behalten: set[str] | None = None, alle: bool = False) -> int:
    """Abo-Termine löschen, die nicht mehr in der Datei stehen und noch kommen (Vergangenes räumt der Planer selbst)."""
    jetzt = planner.clock()
    vorher = len(planner.data["termine"])

    def bleibt(ev: dict[str, Any]) -> bool:
        if ev.get("quelle") != QUELLE:
            return True
        if alle:
            return False
        return ev.get("uid") in (behalten or set()) or datetime.fromisoformat(ev["start"]) < jetzt

    planner.data["termine"] = [ev for ev in planner.data["termine"] if bleibt(ev)]
    uebrig = {ev["id"] for ev in planner.data["termine"]}
    planner.alarms = [a for a in planner.alarms if a.art != "termin" or a.quelle in uebrig]
    return vorher - len(planner.data["termine"])
