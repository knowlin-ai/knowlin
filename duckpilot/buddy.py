"""Alltagsbuddy: Uhrzeit, Timer, Erinnerungen, Termine und To-dos – lokal auf dem PC.

Alles liegt in `alltag.json` im Datenordner (%LOCALAPPDATA%\\duckpilot), nichts geht in die Cloud. Termine kommen
von Hand, über Claude oder als .ics-Datei (Export aus Outlook, Google oder Apple Kalender) – eine Anmeldung bei
einem Kalenderdienst gibt es bewusst nicht.

Wird etwas fällig, entsteht ein **Alarm**: Die Oberfläche zeigt ihn an, die Ente meldet sich (Laut, Geste, auf
Wunsch gesprochen) und weckt sich dafür aus dem Ruhemodus. Ein Alarm bleibt, bis du ihn erledigst oder
schlummern lässt.

Ruhemodus: Die Ente setzt sich, schaltet die Motoren ab (spart Strom am Akku) und hört auf, sich im Leerlauf
zu bewegen. Sie wacht auf, wenn du sie ansprichst oder steuerst, oder wenn ein Alarm fällig ist.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

MAX_ITEMS = 500
TEXT_MAX = 200
WEEKDAYS = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"]
WEEKDAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTH_NAMES = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
               "November", "Dezember"]
REPEATS = ("taeglich", "werktags", "woechentlich")
WAKE_MODES = ("aufstehen", "ton")
NUMBERS = {
    "null": 0, "ein": 1, "eins": 1, "eine": 1, "einen": 1, "einer": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5,
    "fuenf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12, "zwoelf": 12,
    "dreizehn": 13, "vierzehn": 14, "fünfzehn": 15, "sechzehn": 16, "siebzehn": 17, "achtzehn": 18, "neunzehn": 19,
    "zwanzig": 20, "fünfundzwanzig": 25, "dreißig": 30, "dreissig": 30, "vierzig": 40, "fünfundvierzig": 45,
    "fünfzig": 50, "sechzig": 60, "neunzig": 90, "hundert": 100,
}
DAY_PARTS = {"früh": 8, "frueh": 8, "morgens": 8, "vormittag": 10, "vormittags": 10, "mittag": 12, "mittags": 12,
             "nachmittag": 15, "nachmittags": 15, "abend": 19, "abends": 19, "nacht": 22, "nachts": 22}


def now_local() -> datetime:
    return datetime.now().astimezone()


def local(wall: datetime) -> datetime:
    """Wanduhrzeit → Ortszeit mit dem Versatz, der an *diesem* Tag gilt (Sommer-/Winterzeit).

    Nie den Versatz von „jetzt“ auf einen anderen Tag übertragen: „morgen um 9“ über die Zeitumstellung
    hinweg läge sonst eine Stunde daneben."""
    return wall.replace(tzinfo=None).astimezone()


def wall(when: datetime) -> datetime:
    """Zeitpunkt → Wanduhrzeit (ohne Zone) in Ortszeit – zum Rechnen in Tagen."""
    return when.astimezone().replace(tzinfo=None)


def _clip(text: Any) -> str:
    return " ".join(str(text or "").split())[:TEXT_MAX]


def _num_token(tok: str) -> float | None:
    tok = tok.strip().lower().replace(",", ".")
    try:
        return float(tok)
    except ValueError:
        pass
    if tok in NUMBERS:
        return float(NUMBERS[tok])
    if tok.endswith("einhalb") and tok != "einhalb":        # zweieinhalb …
        base = _num_token(tok[: -len("einhalb")])
        return base + 0.5 if base is not None else None
    m = re.fullmatch(r"(\w+?)und(\w+)", tok)          # einundzwanzig …
    if m and m.group(1) in NUMBERS and m.group(2) in NUMBERS:
        return float(NUMBERS[m.group(1)] + NUMBERS[m.group(2)])
    return None


# ── Dauer und Zeitpunkt aus deutschem Text ──────────────────────────────────
_UNIT = r"(sekunden?|sek\.?|s\b|minuten?|min\.?|m\b|stunden?|std\.?|h\b|tagen?|tage?)"


def parse_duration(text: str) -> float | None:
    """„5 Minuten“, „eine halbe Stunde“, „1 h 30 min“, „anderthalb Stunden“, „eine Viertelstunde“ → Sekunden."""
    t = text.lower()
    total = 0.0
    found = False
    if re.search(r"\bviertelstunde\b", t):
        total += 900
        found = True
    if re.search(r"\bdreiviertelstunde\b", t):
        total += 2700 - (900 if found else 0)
        found = True
    m = re.search(r"\b(?:eine[rn]?\s+)?halbe[nr]?\s+stunde\b", t)
    if m:
        total += 1800
        found = True
        t = t.replace(m.group(0), " ")
    m = re.search(r"\b(?:anderthalb|eineinhalb)\s+stunden?\b", t)
    if m:
        total += 5400
        found = True
        t = t.replace(m.group(0), " ")
    for m in re.finditer(r"(\d+(?:[.,]\d+)?|[a-zäöüß]+)\s*" + _UNIT, t):
        n = _num_token(m.group(1))
        if n is None:
            continue
        unit = m.group(2)
        if unit.startswith(("st", "h")):
            mult = 3600
        elif unit.startswith("m"):
            mult = 60
        elif unit.startswith("t"):
            mult = 86400
        else:
            mult = 1
        total += n * mult
        found = True
    return total if found and total > 0 else None


def _hour_minute(t: str) -> tuple[int, int, bool] | None:
    """(Stunde, Minute, genau) – genau = als HH:MM geschrieben, dann nie um 12 Stunden verschieben."""
    m = re.search(r"\b(\d{1,2})[:.](\d{2})\b", t)
    if m:
        return int(m.group(1)), int(m.group(2)), True
    hm = _hour_minute_words(t)
    return (*hm, False) if hm else None


def _hour_minute_words(t: str) -> tuple[int, int] | None:
    m = re.search(r"\bhalb\s+(\w+)\b", t)
    if m and (h := _num_token(m.group(1))) is not None:
        return (int(h) - 1) % 24, 30
    m = re.search(r"\bviertel\s+(nach|vor)\s+(\w+)\b", t)
    if m and (h := _num_token(m.group(2))) is not None:
        return (int(h) % 24, 15) if m.group(1) == "nach" else ((int(h) - 1) % 24, 45)
    m = re.search(r"\b(\w+)\s+(?:minuten\s+)?(nach|vor)\s+(\w+)\b", t)
    if m and (mi := _num_token(m.group(1))) is not None and (h := _num_token(m.group(3))) is not None and mi < 30:
        return (int(h) % 24, int(mi)) if m.group(2) == "nach" else ((int(h) - 1) % 24, 60 - int(mi))
    m = re.search(r"\bum\s+(\w+)(?:\s+uhr)?(?:\s+(\w+))?\b", t)
    if m and (h := _num_token(m.group(1))) is not None and 0 <= h < 24:
        mi = _num_token(m.group(2)) if m.group(2) else None
        return int(h), int(mi) if mi is not None and 0 <= mi < 60 else 0
    m = re.search(r"\b(\d{1,2})\s*uhr\b", t)
    if m:
        return int(m.group(1)), 0
    return None


def parse_when(text: str, now: datetime | None = None, pm_shift: bool = True) -> datetime | None:
    """„in 10 Minuten“, „um 15 Uhr“, „morgen um halb 9“, „am Freitag um 14:30“, „am 3.11. um 9“, „heute Abend“.

    pm_shift: „um 7“ um 9 Uhr morgens heißt 19 Uhr. Für Wiederholungen („jeden Tag um 7“) aus – dann morgen."""
    now = now or now_local()
    t = " " + text.lower() + " "
    m = re.search(r"\bin\s+(.+?)(?:\s+(?:an|zu|daran|dass|mit|zum|zur)\b|$)", t)
    if m:
        d = parse_duration(m.group(1))
        if d:
            return now + timedelta(seconds=d)
    day: date | None = None
    explicit_day = True
    if re.search(r"\bübermorgen\b|\buebermorgen\b", t):
        day = now.date() + timedelta(days=2)
    elif re.search(r"\bheute\s+morgen\b", t):
        day = now.date()
        t = t.replace("heute morgen", "heute morgens")
    elif re.search(r"\bmorgen\b", t) and not re.search(r"\bmorgens\b", t):
        day = now.date() + timedelta(days=1)
    elif re.search(r"\bheute\b", t):
        day = now.date()
    else:
        m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})?", t)
        if m:
            year = int(m.group(3)) if m.group(3) else now.year
            year += 2000 if year < 100 else 0
            try:
                day = date(year, int(m.group(2)), int(m.group(1)))
                if not m.group(3) and day < now.date():
                    day = date(year + 1, day.month, day.day)
            except ValueError:
                day = None
        else:
            for i, wd in enumerate(WEEKDAYS):
                if re.search(rf"\b(?:am\s+|nächsten\s+|naechsten\s+|kommenden\s+)?{wd}\b", t):
                    ahead = (i - now.weekday()) % 7 or 7
                    day = now.date() + timedelta(days=ahead)
                    break
    if day is None:
        explicit_day = False
        day = now.date()
    hm = _hour_minute(re.sub(r"\b\d{1,2}\.\d{1,2}\.(?:\d{2,4})?", " ", t))
    part = next((h for w, h in DAY_PARTS.items() if re.search(rf"\b{w}\b", t)), None)
    if hm is None and part is None:
        if not explicit_day:
            return None
        hm = (9, 0, True)                              # nur ein Tag: morgens um 9 erinnern
    if hm is None:
        hm = (part, 0, True)
    h, mi, exact = hm
    if part is not None and part >= 15 and h < 12:     # „heute Abend um 8“ → 20 Uhr
        h += 12
    try:
        naive = datetime(day.year, day.month, day.day, h % 24, mi)
    except ValueError:
        return None
    if not explicit_day and local(naive) <= now:
        # „um 7“: das nächste 7 Uhr – erst 19 Uhr heute, wenn es ohne Tageszeit gemeint sein kann, sonst morgen
        if pm_shift and not exact and h < 12 and part is None and local(naive + timedelta(hours=12)) > now:
            naive += timedelta(hours=12)
        else:
            naive += timedelta(days=1)
    return local(naive)


def fmt_when(when: datetime, now: datetime | None = None) -> str:
    now = now or now_local()
    d = (when.date() - now.date()).days
    day = "heute" if d == 0 else "morgen" if d == 1 else "übermorgen" if d == 2 else \
        f"{WEEKDAY_NAMES[when.weekday()]}, {when.day}. {MONTH_NAMES[when.month - 1]}"
    return f"{day} um {when.strftime('%H:%M')} Uhr"


def fmt_duration(seconds: float) -> str:
    s = int(round(seconds))
    if s < 60:
        return f"{s} Sekunde{'n' if s != 1 else ''}"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} Minute{'n' if m != 1 else ''}" + (f" {s} Sekunden" if s else "")
    h, m = divmod(m, 60)
    return f"{h} Stunde{'n' if h != 1 else ''}" + (f" {m} Minute{'n' if m != 1 else ''}" if m else "")


def say_time(now: datetime | None = None) -> str:
    now = now or now_local()
    return (f"Es ist {now.strftime('%H:%M')} Uhr, {WEEKDAY_NAMES[now.weekday()]}, der {now.day}. "
            f"{MONTH_NAMES[now.month - 1]} {now.year}.")


# ── iCalendar (.ics) ────────────────────────────────────────────────────────
def _ics_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and out:
            out[-1] += raw[1:]
        else:
            out.append(raw)
    return out


def _zone(params: str):
    m = re.search(r"TZID=\"?([^;:\"]+)", params, re.I)
    if not m:
        return None
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(m.group(1).strip())
    except Exception:          # Windows-Namen („W. Europe Standard Time“) oder keine Zonendaten: als Ortszeit
        return None


def _ics_time(value: str, params: str) -> tuple[datetime, bool] | None:
    v = value.strip()
    try:
        if "VALUE=DATE" in params.upper() or re.fullmatch(r"\d{8}", v):
            return local(datetime.strptime(v[:8], "%Y%m%d")), True
        if v.endswith("Z"):

            return datetime.strptime(v, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).astimezone(), False
        naive = datetime.strptime(v[:15], "%Y%m%dT%H%M%S")
        zone = _zone(params)
        return (naive.replace(tzinfo=zone).astimezone() if zone else local(naive)), False
    except ValueError:
        return None


def _rrule(text: str) -> dict[str, str]:
    out = {}
    for part in text.split(";"):
        k, _, v = part.partition("=")
        out[k.strip().upper()] = v.strip().upper()
    return out


_BYDAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _occurrences(start: datetime, rule: dict[str, str], until_limit: datetime, cap: int = 60) -> list[datetime] | None:
    """Termine einer Serie bis until_limit (Wanduhrzeit bleibt gleich, auch über die Zeitumstellung).
    None = Regel zu kompliziert (dann nur der erste Termin)."""
    freq = rule.get("FREQ")
    if freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY") or any(k in rule for k in ("BYSETPOS", "BYMONTHDAY", "BYMONTH", "BYHOUR")):
        return None
    try:
        interval = max(1, int(rule.get("INTERVAL", "1")))
        count = int(rule["COUNT"]) if "COUNT" in rule else None
    except ValueError:
        return None
    until = None
    if "UNTIL" in rule:
        u = _ics_time(rule["UNTIL"], "")
        until = u[0] if u else None
    days = None
    if "BYDAY" in rule:
        codes = [c.strip() for c in rule["BYDAY"].split(",")]
        if freq != "WEEKLY" or any(c not in _BYDAY for c in codes):
            return None                                   # „1MO“ und Ähnliches
        days = {_BYDAY[c] for c in codes}
    s0 = wall(start)
    end_day = wall(until_limit).date()
    out: list[datetime] = []
    n = 0
    d = s0.date()
    monday0 = s0.date() - timedelta(days=s0.weekday())
    while d <= end_day and n < 5000:
        diff = (d - s0.date()).days
        if freq == "DAILY":
            hit = diff % interval == 0
        elif freq == "WEEKLY":
            weeks = ((d - timedelta(days=d.weekday())) - monday0).days // 7
            hit = weeks % interval == 0 and d.weekday() in (days if days is not None else {s0.weekday()})
        elif freq == "MONTHLY":
            months = (d.year - s0.year) * 12 + d.month - s0.month
            hit = d.day == s0.day and months % interval == 0
        else:
            hit = d.month == s0.month and d.day == s0.day and (d.year - s0.year) % interval == 0
        if hit and d >= s0.date():
            occ = local(datetime.combine(d, s0.time()))
            if until is not None and occ > until:
                break
            n += 1
            if count is not None and n > count:
                break
            out.append(occ)
        d += timedelta(days=1)
    return out[-cap:] if len(out) > cap else out


def _ics_text(v: str) -> str:
    return v.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def parse_ics(text: str, now: datetime | None = None, horizon_days: int = 120) -> tuple[list[dict[str, Any]], int, int]:
    """Termine aus einer .ics-Datei – vergangene und weiter als horizon_days entfernte bleiben draußen.
    Serien (RRULE) mit FREQ/INTERVAL/COUNT/UNTIL/BYDAY werden aufgelöst; kompliziertere Regeln liefern nur
    den ersten Termin. Ergebnis: (Termine, aufgelöste Serien, nicht aufgelöste Serien)."""
    now = now or now_local()
    limit = now + timedelta(days=horizon_days)
    events: list[dict[str, Any]] = []
    series = unsupported = 0
    cur: dict[str, Any] | None = None
    for line in _ics_lines(text[:2_000_000]):
        if line == "BEGIN:VEVENT":
            cur = {}
            continue
        if line == "END:VEVENT":
            if cur and cur.get("start"):
                start, all_day = cur["start"]
                end = cur.get("end", (None, False))[0]
                dur = (end - start) if end else None
                starts = [start]
                if cur.get("rrule"):
                    occ = _occurrences(start, _rrule(cur["rrule"]), limit)
                    if occ is None:
                        unsupported += 1
                    else:
                        series += 1
                        starts = occ
                uid = str(cur.get("uid") or "")[:180]
                for st in starts:
                    en = st + dur if dur else None
                    if (en or st) >= now - timedelta(hours=1) and st <= limit:
                        events.append({"titel": _clip(cur.get("summary") or "Termin"), "start": st, "ende": en,
                                       "ort": _clip(cur.get("location") or ""), "ganztags": all_day,
                                       "uid": f"{uid}@{wall(st).date().isoformat()}" if len(starts) > 1 or cur.get("rrule") else uid})
            cur = None
            continue
        if cur is None or ":" not in line:
            continue
        key, _, value = line.partition(":")
        name, _, params = key.partition(";")
        name = name.upper()
        if name == "DTSTART":
            st = _ics_time(value, params)
            if st:
                cur["start"] = st
        elif name == "DTEND":
            e = _ics_time(value, params)
            if e:
                cur["end"] = e
        elif name == "SUMMARY":
            cur["summary"] = _ics_text(value)
        elif name == "LOCATION":
            cur["location"] = _ics_text(value)
        elif name == "UID":
            cur["uid"] = value
        elif name == "RRULE":
            cur["rrule"] = value
    return events, series, unsupported


# ── Planer ──────────────────────────────────────────────────────────────────
@dataclass
class Alarm:
    id: str
    art: str            # timer | erinnerung | termin
    text: str
    faellig: float      # epoch
    quelle: str         # id des Eintrags
    seit: float = 0.0
    gemeldet: int = 0   # wie oft die Ente sich schon gemeldet hat
    basis: str = ""     # Text für „später nochmal“ (ohne „in 15 Minuten“)


class Planner:
    """Daten + Zeitlogik, ohne asyncio – `tick()` liefert neu fällige Alarme."""

    def __init__(self, path: Path, clock: Callable[[], datetime] = now_local) -> None:
        self.path = Path(path)
        self.clock = clock
        self.lock = threading.RLock()
        self.alarms: list[Alarm] = []
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        base = {"timer": [], "erinnerungen": [], "termine": [], "todos": [],
                "modus": "aktiv", "ruhe_nach_min": 0, "wecken": "aufstehen", "durchsagen": True,
                # Funktionen des Buddys (Alltag → Was der Buddy darf); Sehen und Personen bewusst aus
                "sehen": False, "personen": False, "begruessen": True, "augen": "simulator"}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in base.items():
                    if not isinstance(data.get(k), type(v)):
                        data[k] = v
                return data
        except (OSError, ValueError):
            pass
        return base

    def save(self) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)

    def _room(self, key: str) -> None:
        if len(self.data[key]) >= MAX_ITEMS:
            raise ValueError("Die Liste ist voll – erst alte Einträge löschen.")

    # ── Anlegen ──────────────────────────────────────────────────────────
    def add_timer(self, seconds: float, name: str = "") -> dict[str, Any]:
        if not 1 <= seconds <= 24 * 3600:
            raise ValueError("Ein Timer läuft zwischen 1 Sekunde und 24 Stunden.")
        with self.lock:
            self._room("timer")
            item = {"id": uuid.uuid4().hex[:8], "name": _clip(name) or f"Timer {fmt_duration(seconds)}",
                    "dauer_s": round(seconds), "ende": self.clock().timestamp() + seconds}
            self.data["timer"].append(item)
            self.save()
            return item

    def add_reminder(self, text: str, when: datetime, repeat: str | None = None) -> dict[str, Any]:
        text = _clip(text)
        if not text:
            raise ValueError("Woran soll ich erinnern?")
        if repeat not in (None, "", *REPEATS):
            raise ValueError("Wiederholung: täglich, werktags oder wöchentlich.")
        if when < self.clock() - timedelta(minutes=1):
            raise ValueError("Der Zeitpunkt liegt in der Vergangenheit.")
        with self.lock:
            self._room("erinnerungen")
            item = {"id": uuid.uuid4().hex[:8], "text": text, "faellig": when.isoformat(timespec="minutes"),
                    "wiederholung": repeat or None, "erledigt": False}
            self.data["erinnerungen"].append(item)
            self.save()
            return item

    def add_event(self, title: str, start: datetime, end: datetime | None = None, place: str = "",
                  lead_min: int = 15, source: str = "manuell", uid: str = "", all_day: bool = False,
                  save: bool = True) -> dict[str, Any]:
        title = _clip(title)
        if not title:
            raise ValueError("Wie heißt der Termin?")
        lead_min = max(0, min(24 * 60, int(lead_min)))
        with self.lock:
            if uid:
                for ev in self.data["termine"]:
                    if ev.get("uid") == uid:                      # erneuter Import: aktualisieren statt doppeln
                        new_start = start.isoformat(timespec="minutes")
                        if new_start != ev.get("start"):
                            ev["gemeldet"] = False                # verschoben: zur neuen Zeit wieder melden
                        ev.update(titel=title, start=new_start,
                                  ende=end.isoformat(timespec="minutes") if end else None, ort=_clip(place),
                                  ganztags=all_day)
                        if save:
                            self.save()
                        return ev
            self._room("termine")
            item = {"id": uuid.uuid4().hex[:8], "titel": title, "start": start.isoformat(timespec="minutes"),
                    "ende": end.isoformat(timespec="minutes") if end else None, "ort": _clip(place),
                    "vorher_min": lead_min, "quelle": source, "uid": uid, "ganztags": all_day, "gemeldet": False}
            self.data["termine"].append(item)
            if save:
                self.save()
            return item

    def add_todo(self, text: str) -> dict[str, Any]:
        text = _clip(text)
        if not text:
            raise ValueError("Was soll auf die Liste?")
        with self.lock:
            self._room("todos")
            for t in self.data["todos"]:
                if not t["erledigt"] and t["text"].lower() == text.lower():
                    return t
            item = {"id": uuid.uuid4().hex[:8], "text": text, "erledigt": False,
                    "erstellt": self.clock().isoformat(timespec="minutes")}
            self.data["todos"].append(item)
            self.save()
            return item

    # ── Ändern ───────────────────────────────────────────────────────────
    def _find(self, key: str, ref: str) -> dict[str, Any] | None:
        ref_l = (ref or "").strip().lower()
        items = self.data[key]
        for it in items:
            if it["id"] == ref:
                return it
        for field in ("text", "titel", "name"):
            for it in items:
                if ref_l and ref_l in str(it.get(field, "")).lower():
                    return it
        return None

    def finish_todo(self, ref: str, done: bool = True) -> dict[str, Any] | None:
        """Abhaken per id oder Text: erst genau, dann ganze Wörter – nur unter den offenen (bzw. beim
        Zurücknehmen den erledigten) Einträgen. Passt es auf mehrere, wird nichts abgehakt."""
        with self.lock:
            items = self.data["todos"]
            it = next((t for t in items if t["id"] == ref), None)
            if it is None:
                pool = [t for t in items if t["erledigt"] != done]
                key = " ".join(str(ref or "").lower().split())
                exact = [t for t in pool if t["text"].lower() == key]
                if exact:
                    it = exact[-1]
                elif len(key) >= 3:
                    hits = [t for t in pool if re.search(rf"(?<!\w){re.escape(key)}(?!\w)", t["text"].lower())]
                    if len(hits) > 1:
                        raise ValueError("Das passt auf mehrere Einträge: " + ", ".join(t["text"] for t in hits[:4]) + ".")
                    it = hits[0] if hits else None
            if it:
                it["erledigt"] = done
                it["erledigt_am"] = self.clock().isoformat(timespec="minutes") if done else None
                self.save()
            return it

    def remove(self, kind: str, ref: str) -> dict[str, Any] | None:
        key = {"timer": "timer", "erinnerung": "erinnerungen", "termin": "termine", "todo": "todos"}.get(kind)
        if key is None:
            raise ValueError("Art: timer, erinnerung, termin oder todo.")
        with self.lock:
            it = self._find(key, ref)
            if it:
                self.data[key].remove(it)
                self.alarms = [a for a in self.alarms if a.quelle != it["id"]]
                self.save()
            return it

    def clear_done(self) -> int:
        with self.lock:
            before = len(self.data["todos"])
            self.data["todos"] = [t for t in self.data["todos"] if not t["erledigt"]]
            self.save()
            return before - len(self.data["todos"])

    def set_options(self, **opts: Any) -> dict[str, Any]:
        with self.lock:
            if "ruhe_nach_min" in opts:
                v = int(opts["ruhe_nach_min"])
                if v not in (0, 10, 30, 60, 120):
                    raise ValueError("Ruhe nach: aus, 10, 30, 60 oder 120 Minuten.")
                self.data["ruhe_nach_min"] = v
            if "wecken" in opts:
                if opts["wecken"] not in WAKE_MODES:
                    raise ValueError("Wecken: aufstehen oder ton.")
                self.data["wecken"] = opts["wecken"]
            if "durchsagen" in opts:
                self.data["durchsagen"] = bool(opts["durchsagen"])
            for key in ("sehen", "personen", "begruessen"):
                if key in opts:
                    self.data[key] = bool(opts[key])
            if "augen" in opts:
                if opts["augen"] not in ("simulator", "webcam"):
                    raise ValueError("Augen im Simulator: simulator oder webcam.")
                self.data["augen"] = opts["augen"]
            if "modus" in opts:
                if opts["modus"] not in ("aktiv", "ruhe"):
                    raise ValueError("Modus: aktiv oder ruhe.")
                self.data["modus"] = opts["modus"]
            self.save()
            return self.options()

    def options(self) -> dict[str, Any]:
        return {k: self.data[k] for k in ("modus", "ruhe_nach_min", "wecken", "durchsagen", "sehen", "personen",
                                          "begruessen", "augen")}

    # ── Fällig? ──────────────────────────────────────────────────────────
    def tick(self) -> list[Alarm]:
        """Neu fällige Alarme (je Eintrag einmal) – Timer verschwinden, Wiederholungen rücken weiter."""
        now = self.clock()
        ts = now.timestamp()
        new: list[Alarm] = []
        changed = False
        with self.lock:
            for t in list(self.data["timer"]):
                if t["ende"] <= ts:
                    new.append(Alarm(uuid.uuid4().hex[:8], "timer", f"{t['name']} ist abgelaufen.", t["ende"], t["id"], ts,
                                     basis=t["name"]))
                    self.data["timer"].remove(t)
                    changed = True
            for r in self.data["erinnerungen"]:
                if r["erledigt"]:
                    continue
                due = datetime.fromisoformat(r["faellig"])
                if due <= now:
                    new.append(Alarm(uuid.uuid4().hex[:8], "erinnerung", r["text"], due.timestamp(), r["id"], ts,
                                     basis=r["text"]))
                    nxt = _next_repeat(due, r.get("wiederholung"), now)
                    if nxt:
                        r["faellig"] = nxt.isoformat(timespec="minutes")
                    else:
                        r["erledigt"] = True
                    changed = True
            for ev in self.data["termine"]:
                if ev.get("gemeldet"):
                    continue
                start = datetime.fromisoformat(ev["start"])
                if ev.get("ganztags"):
                    warn = local(wall(start).replace(hour=8, minute=0))
                else:
                    warn = start - timedelta(minutes=ev.get("vorher_min", 15))
                if warn <= now:
                    ev["gemeldet"] = True
                    changed = True
                    if now - warn > timedelta(hours=2):
                        continue                               # längst vorbei (PC war aus): nicht nachträglich wecken
                    mins = round((start - now).total_seconds() / 60)
                    when = "heute" if ev.get("ganztags") else (f"in {mins} Minuten" if mins > 0 else "jetzt")
                    place = f" ({ev['ort']})" if ev.get("ort") else ""
                    new.append(Alarm(uuid.uuid4().hex[:8], "termin", f"{ev['titel']}{place} – {when}.", warn.timestamp(),
                                     ev["id"], ts, basis=f"{ev['titel']}{place}"))
            # alte Termine aufräumen (eine Woche nach Ende)
            keep = []
            for ev in self.data["termine"]:
                end = datetime.fromisoformat(ev["ende"] or ev["start"])
                if now - end < timedelta(days=7):
                    keep.append(ev)
                else:
                    changed = True
            self.data["termine"] = keep
            if changed:
                self.save()
            self.alarms.extend(new)
        return new

    def ack(self, alarm_id: str) -> bool:
        with self.lock:
            before = len(self.alarms)
            self.alarms = [a for a in self.alarms if a.id != alarm_id]
            return len(self.alarms) < before

    def snooze(self, alarm_id: str, minutes: int = 5) -> dict[str, Any] | None:
        with self.lock:
            a = next((x for x in self.alarms if x.id == alarm_id), None)
            if a is None:
                return None
            when = self.clock() + timedelta(minutes=max(1, min(120, int(minutes))))
            item = self.add_reminder(a.basis or a.text, when)      # erst speichern, dann den Alarm wegnehmen
            self.alarms.remove(a)
            return item

    # ── Überblick ────────────────────────────────────────────────────────
    def agenda(self, day: date | None = None) -> list[dict[str, Any]]:
        day = day or self.clock().date()
        items = []
        for ev in self.data["termine"]:
            s = datetime.fromisoformat(ev["start"])
            if s.date() == day:
                items.append({"art": "termin", "zeit": None if ev.get("ganztags") else s.strftime("%H:%M"),
                              "text": ev["titel"] + (f" ({ev['ort']})" if ev.get("ort") else ""), "id": ev["id"]})
        for r in self.data["erinnerungen"]:
            s = datetime.fromisoformat(r["faellig"])
            if not r["erledigt"] and s.date() == day:
                items.append({"art": "erinnerung", "zeit": s.strftime("%H:%M"), "text": r["text"], "id": r["id"]})
        return sorted(items, key=lambda x: x["zeit"] or "00:00")

    def snapshot(self) -> dict[str, Any]:
        now = self.clock()
        with self.lock:
            timers = [{**t, "rest_s": max(0, round(t["ende"] - now.timestamp()))} for t in self.data["timer"]]
            return {
                "jetzt": now.isoformat(timespec="seconds"),
                "timer": sorted(timers, key=lambda t: t["ende"]),
                "erinnerungen": sorted([r for r in self.data["erinnerungen"] if not r["erledigt"]], key=lambda r: r["faellig"]),
                "termine": sorted(self.data["termine"], key=lambda e: e["start"]),
                "todos": self.data["todos"],
                "heute": self.agenda(now.date()),
                "morgen": self.agenda(now.date() + timedelta(days=1)),
                "alarme": [a.__dict__ for a in self.alarms],
                "optionen": self.options(),
            }

    def brief(self) -> str:
        """Ein kurzer Überblick für Claude und für „Was steht heute an?“."""
        now = self.clock()
        today = self.agenda(now.date())
        parts = [say_time(now)]
        later = [x for x in today if (x["zeit"] or "24:00") >= now.strftime("%H:%M")]
        if later:
            parts.append("Heute noch: " + "; ".join(f"{x['zeit'] or 'ganztags'} {x['text']}" for x in later[:6]) + ".")
        else:
            parts.append("Heute steht nichts mehr an.")
        tm = self.agenda(now.date() + timedelta(days=1))
        if tm:
            parts.append("Morgen: " + "; ".join(f"{x['zeit'] or 'ganztags'} {x['text']}" for x in tm[:4]) + ".")
        open_todos = [t["text"] for t in self.data["todos"] if not t["erledigt"]]
        if open_todos:
            parts.append(f"{len(open_todos)} offene To-dos: " + ", ".join(open_todos[:5]) + ("…" if len(open_todos) > 5 else "") + ".")
        timers = [t for t in self.data["timer"]]
        for t in timers[:3]:
            parts.append(f"{t['name']}: noch {fmt_duration(max(0, t['ende'] - now.timestamp()))}.")
        return " ".join(parts)

    def import_ics(self, text: str) -> dict[str, Any]:
        events, series, unsupported = parse_ics(text, self.clock())
        n = 0
        with self.lock:
            try:
                for ev in events[:MAX_ITEMS]:
                    self.add_event(ev["titel"], ev["start"], ev["ende"], ev["ort"], source="ics", uid=ev["uid"],
                                   all_day=ev["ganztags"], save=False)
                    n += 1
            except ValueError:
                pass                                   # Liste voll: was drin ist, bleibt
            self.save()
        return {"importiert": n, "serien": series, "nicht_aufgeloest": unsupported}


def _next_repeat(due: datetime, repeat: str | None, now: datetime) -> datetime | None:
    """Nächster Termin einer Wiederholung – in Wanduhrzeit gerechnet, damit 8 Uhr auch nach der
    Zeitumstellung 8 Uhr bleibt."""
    if repeat not in REPEATS:
        return None
    step = timedelta(days=7 if repeat == "woechentlich" else 1)
    nxt = wall(due) + step
    while local(nxt) <= now or (repeat == "werktags" and nxt.weekday() >= 5):
        nxt += timedelta(days=1) if repeat == "werktags" else step
    return local(nxt)
