"""Alltagsbuddy als Erweiterung: Uhrzeit, Timer, Erinnerungen, Termine, To-dos – und Ruhe/Aktiv.

Die Daten und die Zeitlogik stecken in `duckpilot/buddy.py` (Planner). Hier:

* `AlltagPack` – der Eintrag unter System → Erweiterungen und das Werkzeug `alltag` für Claude,
* `AlltagService` – hängt den Planer an die laufende Ente: prüft jede Sekunde, was fällig ist, weckt die Ente,
  lässt sie sich melden, schickt Durchsagen und schaltet zwischen Ruhe und Aktiv.

Sicherheit: Ein Not-Aus in den letzten zwei Minuten verhindert, dass ein Alarm die Ente aufstehen lässt – sie
meldet sich dann nur mit Ton und Durchsage. Gestürzt oder hochgehoben weckt der Alarm sie nicht hoch (nach einem
Sturz übernimmt das der Sturz-Reflex mit Stopp-Fenster).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..aio import spawn
from ..buddy import Alarm, Planner, fmt_duration, fmt_when, local, now_local, parse_duration, parse_when, say_time
from . import Pack, PackInfo

if TYPE_CHECKING:
    from ..server.app import Runtime
    from . import SkillManager

log = logging.getLogger(__name__)

ESTOP_GRACE_S = 120.0
NUDGE_EVERY_S = 60.0
NUDGE_MAX = 3
BACK_TO_REST_S = 20.0
ACTIONS = ["uhrzeit", "ueberblick", "timer", "erinnerung", "termin", "todo", "todo_erledigt", "todos",
           "loeschen", "ruhe", "aktiv", "ansehen", "wer_ist_da"]


class AlltagPack(Pack):
    tool_name = "alltag"

    def __init__(self) -> None:
        self.info = PackInfo(
            id="alltag", name="Alltagsbuddy",
            kurz="Uhrzeit, Timer, Erinnerungen, Termine und To-dos – die Verkörperung meldet sich, wenn etwas ansteht.",
            text="Ein kleiner Assistent wie Jarvis: Frag nach der Uhrzeit, stell Timer, lass dich "
                 "erinnern, trag Termine ein oder importiere sie als .ics-Datei aus deinem Kalender, führe eine "
                 "To-do-Liste. Im Ruhemodus spart die Verkörperung Strom und wacht auf, wenn etwas fällig ist. Alles bleibt "
                 "lokal auf deinem PC.",
            quelle="", lizenz="", herkunft="duckpilot",
            im_simulator="Geht vollständig im Simulator – die Verkörperung meldet sich dort genauso.",
            hinweis="Kalender werden nur als Datei importiert – keine Anmeldung bei Outlook oder Google.")

    def tool(self, items: list[dict[str, Any]] | None) -> dict[str, Any] | None:
        return {
            "name": self.tool_name,
            "description": (
                "Alltagsbuddy. aktion=uhrzeit: Uhrzeit und Datum. ueberblick: was heute/morgen ansteht, offene To-dos, "
                "laufende Timer. timer: dauer (z. B. „10 Minuten“) und optional text (Name). erinnerung: text und wann "
                "(deutsch wie „morgen um 9“, „in 20 Minuten“, oder ISO 2026-11-03T09:00), optional wiederholung "
                "(taeglich|werktags|woechentlich). termin: text (Titel), wann, optional ort, minuten_vorher (Standard 15). "
                "todo: text auf die Liste. todo_erledigt: text oder id abhaken. todos: Liste zeigen. loeschen: art "
                "(timer|erinnerung|termin|todo) und text/id. ruhe: Ruhemodus (hinsetzen, Motoren aus, wacht bei Fälligem "
                "auf). aktiv: aufwachen und wieder mitmachen. ansehen: ein Bild der Kamera (am Roboter die Kopfkamera, im "
                "Simulator die PC-Webcam oder die Simulator-Ansicht) bekommen, um es zu beschreiben, Text vorzulesen "
                "(aufgabe=vorlesen: wörtlich und vollständig vorlesen, nichts erfinden; Unleserliches sagen) oder eine "
                "frage dazu zu beantworten – nur wenn „Sehen“ an ist. Personen auf dem Bild nie identifizieren oder "
                "einschätzen (Alter, Herkunft o. Ä.). wer_ist_da: wen die Ente gerade erkennt – nur angelernte Personen "
                "mit Namen, sonst „unbekannt“. Zeiten immer in Ortszeit des Menschen."),
            "input_schema": {
                "type": "object",
                "properties": {
                    "aktion": {"type": "string", "enum": ACTIONS},
                    "text": {"type": "string"},
                    "wann": {"type": "string"},
                    "dauer": {"type": "string"},
                    "ort": {"type": "string"},
                    "minuten_vorher": {"type": "integer"},
                    "wiederholung": {"type": "string", "enum": ["taeglich", "werktags", "woechentlich"]},
                    "art": {"type": "string", "enum": ["timer", "erinnerung", "termin", "todo"]},
                    "id": {"type": "string"},
                    "aufgabe": {"type": "string", "enum": ["beschreiben", "vorlesen", "frage"]},
                    "frage": {"type": "string"},
                },
                "required": ["aktion"],
            },
        }

    async def run_tool(self, mgr: "SkillManager", args: dict[str, Any]) -> dict[str, Any]:
        svc = getattr(mgr.rt, "alltag", None)
        if svc is None:
            return {"ok": False, "fehler": "Alltagsbuddy nicht bereit."}
        return await svc.command(args)


def _when(value: Any, now: datetime, repeating: bool = False) -> datetime | None:
    if not value:
        return None
    v = str(value).strip()
    try:
        dt = datetime.fromisoformat(v)
        return dt.astimezone() if dt.tzinfo else local(dt)     # ohne Zone: Ortszeit an diesem Tag
    except ValueError:
        return parse_when(v, now, pm_shift=not repeating)


class AlltagService:
    def __init__(self, rt: "Runtime", planner: Planner) -> None:
        self.rt = rt
        self.planner = planner
        self.last_activity = time.monotonic()
        self.estop_at = -1e9
        self.woke_for_alarm = False
        self._ack_at: float | None = None
        self._task: asyncio.Task | None = None
        self._mode_lock = asyncio.Lock()

    @property
    def on(self) -> bool:
        return self.rt.skills.is_enabled("alltag")

    def _sperre(self) -> float:
        """Sperre nach dem Not-Aus – wie die Engine (nie unter ESTOP_GRACE_S, auf Wunsch länger)."""
        return max(ESTOP_GRACE_S, float(getattr(self.rt.engine, "sperre_s", ESTOP_GRACE_S)))

    def since_estop(self) -> float:
        """Sekunden seit dem letzten Not-Aus – egal ob Knopf, Esc, „Stopp“ oder Claudes stop-Werkzeug."""
        last = max(self.estop_at, getattr(self.rt.engine, "estop_at", -1e9))
        return time.monotonic() - last

    @property
    def mode(self) -> str:
        return self.planner.data.get("modus", "aktiv")

    # ── Schleife ─────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._task is None:
            self._task = spawn(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            try:
                await self.step()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Alltagsbuddy")

    async def step(self) -> None:
        if not self.on:
            return
        for alarm in self.planner.tick():
            await self._ring(alarm)
        now = time.time()
        for a in list(self.planner.alarms):                  # nicht bestätigt: alle 60 s nochmal melden
            if a.gemeldet < NUDGE_MAX and now - a.seit >= NUDGE_EVERY_S * a.gemeldet:
                await self._nudge(a, again=True)
        if self.since_estop() < self._sperre():
            return                                         # nach einem Not-Aus bewegt sie sich nicht von selbst
        # nach dem Alarm wieder einschlafen, wenn sie im Ruhemodus war
        if self.woke_for_alarm and not self.planner.alarms and self._ack_at is not None \
                and time.monotonic() - self._ack_at > BACK_TO_REST_S and time.monotonic() - self.last_activity > BACK_TO_REST_S:
            self.woke_for_alarm = False
            self._ack_at = None
            if self.mode == "ruhe":
                await self._rest()
        # von selbst zur Ruhe, wenn lange nichts los war
        idle_min = self.planner.data.get("ruhe_nach_min", 0)
        if idle_min and self.mode == "aktiv" and not self.planner.alarms and not self.rt.engine.busy() \
                and time.monotonic() - self.last_activity > idle_min * 60:
            await self.set_mode("ruhe", f"nach {int(idle_min)} Minuten ohne Beschäftigung")

    # ── Alarme ───────────────────────────────────────────────────────────
    async def _ring(self, alarm: Alarm) -> None:
        alarm.seit = time.time()
        await self._wake_for(alarm)
        await self._nudge(alarm)
        await self.push()

    async def _wake_for(self, alarm: Alarm) -> None:
        if self.mode != "ruhe" or self.planner.data.get("wecken") != "aufstehen":
            return
        st = self.rt.backend.state()
        if self.since_estop() < self._sperre() or st.fallen or st.picked_up:
            return                                          # Not-Aus gilt: kein Aufstehen von selbst
        if not (st.powered and st.enabled):
            self.woke_for_alarm = True
            await self.rt.engine.stand_up()
            await asyncio.sleep(2.0)

    async def _nudge(self, alarm: Alarm, again: bool = False) -> None:
        alarm.gemeldet += 1
        st = self.rt.backend.state()
        try:
            await self.rt.backend.sound("chirp")
        except Exception:
            pass
        if st.powered and st.enabled and not st.fallen and not self.rt.engine.busy() \
                and self.since_estop() > ESTOP_GRACE_S:            # nie mitten in eine laufende Bewegung
            try:
                await self.rt.runner.run("emote", {"emotion": "ueberrascht" if not again else "neugierig"})
            except Exception:
                log.debug("Geste beim Alarm", exc_info=True)
        label = {"timer": "Timer", "erinnerung": "Erinnerung", "termin": "Termin"}.get(alarm.art, "Hinweis")
        text = f"{label}: {alarm.text}" if not again else f"Noch einmal – {alarm.text}"
        speech = self.rt._speech(text, ernst=True) if self.planner.data.get("durchsagen", True) else None
        await self.rt.broadcast({"type": "alltag_alarm", "alarm": alarm.__dict__, "text": text, "nochmal": again})
        await self.rt.broadcast({"type": "chat", "role": "duck", "text": text, "source": "alltag", "seconds": 0,
                                 "sprache": speech})

    def ack(self, alarm_id: str) -> bool:
        ok = self.planner.ack(alarm_id)
        if ok and not self.planner.alarms:
            self._ack_at = time.monotonic()
        return ok

    def snooze(self, alarm_id: str, minutes: int = 5) -> dict[str, Any] | None:
        item = self.planner.snooze(alarm_id, minutes)
        if item and not self.planner.alarms:
            self._ack_at = time.monotonic()
        return item

    # ── Ruhe und Aktiv ───────────────────────────────────────────────────
    def touch(self, wake: bool = True) -> None:
        """Der Mensch tut etwas mit der Ente: Zeit merken, aus der Ruhe holen."""
        self.last_activity = time.monotonic()
        if wake:
            self.woke_for_alarm = False
        if wake and self.mode == "ruhe":
            # sanft: was der Mensch gerade verlangt (z. B. „schieß den Ball“), wartet aufs Aufstehen statt abzubrechen
            spawn(self.set_mode("aktiv", "angesprochen", sanft=True))

    def emergency_stop(self) -> None:
        self.estop_at = time.monotonic()
        self.last_activity = self.estop_at

    async def _rest(self) -> None:
        await self.rt.runner.run("power", {"action": "rest"})

    async def set_mode(self, mode: str, why: str = "", sanft: bool = False) -> dict[str, Any]:
        async with self._mode_lock:
            if mode not in ("aktiv", "ruhe"):
                raise ValueError("Modus: aktiv oder ruhe.")
            self.planner.set_options(modus=mode)
            self.last_activity = time.monotonic()
            stood = None
            if mode == "ruhe":
                await self._rest()
            else:
                st = self.rt.backend.state()
                resting_now = getattr(self.rt.backend, "skill", None) == "_rest"   # legt sich gerade hin
                if not (st.powered and st.enabled) or st.sitting or resting_now:
                    if self.since_estop() < self._sperre() or st.fallen or st.picked_up:
                        stood = False                      # wach, aber nach Not-Aus nicht von selbst aufstehen
                    elif sanft:
                        await self.rt.engine.stand_up()        # ohne stop_all: Befehle warten, bis sie steht
                        stood = True
                    else:
                        await self.rt.runner.run("power", {"action": "stand_up"})
                        stood = True
            await self.rt.broadcast({"type": "alltag_modus", "modus": mode, "grund": why})
            await self.push()
            return {"ok": True, "modus": mode, "aufgestanden": stood}

    # ── Nachrichten ──────────────────────────────────────────────────────
    def message(self) -> dict[str, Any]:
        return {"type": "alltag", "an": self.on, **self.planner.snapshot()}

    async def push(self) -> None:
        await self.rt.broadcast(self.message())

    # ── Befehle (Claude, einfache Befehle, Oberfläche) ───────────────────
    async def command(self, a: dict[str, Any]) -> dict[str, Any]:
        try:
            res = await self._command(a if isinstance(a, dict) else {})
        except (ValueError, TypeError) as exc:
            return {"ok": False, "fehler": str(exc) or "Ungültige Eingabe."}
        if res.get("ok") and a.get("aktion") not in ("uhrzeit", "ueberblick", "todos"):
            await self.push()
        return res

    async def _command(self, a: dict[str, Any]) -> dict[str, Any]:
        p = self.planner
        now = now_local()
        act = str(a.get("aktion") or "")
        text = str(a.get("text") or "").strip()
        if act == "uhrzeit":
            return {"ok": True, "antwort": say_time(now), "zeit": now.isoformat(timespec="minutes")}
        if act == "ueberblick":
            return {"ok": True, "antwort": p.brief(), "heute": p.agenda(), "todos": [t["text"] for t in p.data["todos"] if not t["erledigt"]]}
        if act == "timer":
            raw = a.get("dauer")
            secs = float(raw) if isinstance(raw, (int, float)) else parse_duration(str(raw or text))
            if not secs:
                raise ValueError("Wie lange soll der Timer laufen?")
            t = p.add_timer(secs, text if text and not parse_duration(text) else "")
            return {"ok": True, "antwort": f"{t['name']} läuft – ich melde mich in {fmt_duration(secs)}.", "timer": t}
        if act == "erinnerung":
            when = _when(a.get("wann"), now, repeating=bool(a.get("wiederholung")))
            if when is None:
                raise ValueError("Wann soll ich erinnern? Zum Beispiel „in 20 Minuten“ oder „morgen um 9“.")
            r = p.add_reminder(text, when, a.get("wiederholung"))
            rep = {"taeglich": " (täglich)", "werktags": " (werktags)", "woechentlich": " (wöchentlich)"}.get(r["wiederholung"] or "", "")
            return {"ok": True, "antwort": f"Ich erinnere dich {fmt_when(when, now)}{rep}: {r['text']}.", "erinnerung": r}
        if act == "termin":
            when = _when(a.get("wann"), now)
            if when is None:
                raise ValueError("Wann ist der Termin?")
            lead = a.get("minuten_vorher")
            ev = p.add_event(text, when, None, str(a.get("ort") or ""), 15 if lead is None or lead == "" else int(lead))
            return {"ok": True, "antwort": f"Termin eingetragen: {ev['titel']}, {fmt_when(when, now)}. "
                                           f"Ich melde mich {ev['vorher_min']} Minuten vorher.", "termin": ev}
        if act == "todo":
            t = p.add_todo(text)
            return {"ok": True, "antwort": f"Steht auf der Liste: {t['text']}.", "todo": t}
        if act == "todo_erledigt":
            t = p.finish_todo(str(a.get("id") or text))
            if not t:
                raise ValueError("Das finde ich nicht auf der Liste.")
            return {"ok": True, "antwort": f"Abgehakt: {t['text']}."}
        if act == "todos":
            open_ = [t["text"] for t in p.data["todos"] if not t["erledigt"]]
            return {"ok": True, "antwort": ("Auf der Liste: " + ", ".join(open_) + ".") if open_ else "Die Liste ist leer.",
                    "todos": open_}
        if act == "loeschen":
            it = p.remove(str(a.get("art") or ""), str(a.get("id") or text))
            if not it:
                raise ValueError("Das finde ich nicht.")
            return {"ok": True, "antwort": "Gelöscht."}
        if act == "ruhe":
            await self.set_mode("ruhe", "auf Wunsch")
            return {"ok": True, "antwort": "Ich ruhe mich aus und wecke mich, wenn etwas ansteht."}
        if act == "aktiv":
            r = await self.set_mode("aktiv", "auf Wunsch")
            if r.get("aufgestanden") is False:
                return {"ok": True, "antwort": "Bin wach – nach dem Not-Aus stehe ich aber nicht von selbst auf. "
                                               "Sag „steh auf“, wenn ich soll."}
            return {"ok": True, "antwort": "Bin wach!"}
        if act == "ansehen":
            return await self._look(a)
        if act == "wer_ist_da":
            return await self._who()
        raise ValueError(f"Unbekannte Aktion „{act}“.")

    # ── Sehen und Wiedererkennen ─────────────────────────────────────────
    async def _look(self, a: dict[str, Any]) -> dict[str, Any]:
        if not self.planner.data.get("sehen"):
            return {"ok": False, "fehler": "„Sehen“ ist aus – im Alltag unter „Was der Buddy darf“ einschalten."}
        if self.rt.config.gehirn == "lokal" or not self.rt.config.api_key:
            return {"ok": False, "fehler": "Sehen braucht Claude – mit dem eigenen Sprachmodell geht es noch nicht."}
        try:
            data, kind, quelle = await self.rt.eyes.image()
        except Exception as exc:
            return {"ok": False, "fehler": str(exc)}
        aufgabe = str(a.get("aufgabe") or "beschreiben")
        hint = {"vorlesen": "Lies den Text auf dem Bild wörtlich und vollständig vor. Unleserliches als unleserlich sagen.",
                "frage": f"Beantworte: {str(a.get('frage') or '').strip()[:300]}",
                }.get(aufgabe, "Beschreibe kurz und freundlich, was zu sehen ist – Dinge und Lage, keine Einschätzung von Personen.")
        from ..augen import Eyes

        return {"ok": True, "quelle": {"roboter": "Kopfkamera", "webcam": "PC-Webcam",
                                       "simulator": "Simulator-Ansicht"}[quelle], "aufgabe": aufgabe, "hinweis": hint,
                "_bild": Eyes.for_claude(data, kind)}

    async def _who(self) -> dict[str, Any]:
        from ..remote import REMOTE_TURN

        if REMOTE_TURN.get():
            return {"ok": False, "fehler": "Wer zu Hause ist, sagt die Ente nur direkt am PC – nicht übers Handy."}
        if not self.planner.data.get("personen"):
            return {"ok": False, "fehler": "„Personen erkennen“ ist aus (Alltag → Was der Buddy darf)."}
        faces = getattr(self.rt, "faces", None)
        ok, why = faces.available() if faces else (False, "nicht eingerichtet")
        if not ok:
            return {"ok": False, "fehler": f"Personen erkennen ist noch nicht eingerichtet: {why}"}
        try:
            data, _kind, _q = await self.rt.eyes.image()
            seen = await asyncio.to_thread(faces.who, data)
        except Exception as exc:
            return {"ok": False, "fehler": str(exc)}
        names = [f["name"] for f in seen]
        known = [n for n in names if n != "unbekannt"]
        if not names:
            return {"ok": True, "antwort": "Ich sehe gerade niemanden.", "personen": []}
        rest = len(names) - len(known)
        parts = known + ([f"{rest} {'Person' if rest == 1 else 'Personen'}, die ich nicht kenne"] if rest else [])
        return {"ok": True, "antwort": "Ich sehe " + " und ".join(parts) + ".", "personen": known, "unbekannt": rest}


# ── Einfache Befehle ohne Claude ────────────────────────────────────────────
_LEAD = r"^\W*(?:ente\W+)?(?:(?:bitte|mal|jetzt|doch)\s+)*"
_REST = re.compile(_LEAD + r"(?:ruhe\s?modus|chill\s?modus|ruh dich aus|leg dich schlafen|geh schlafen|chill mal|mach (?:eine )?ruhepause)\W*$")
_ACTIVE = re.compile(_LEAD + r"(?:aktiv\s?modus|sei wieder aktiv|wach auf|aufwachen|werd wach)\W*$")
_NOT_TODOS = {"es", "das", "alles", "ok", "okay", "gut", "nichts", "ich", "ich bin", "du bist", "heute", "der rest", "dann"}


def quick(text: str) -> dict[str, Any] | None:
    """Kurze Alltagssätze → Werkzeug-Argumente (für den Modus ohne Claude). Ganze Sätze, keine Teiltreffer:
    „Das erinnert mich an früher“ ist kein Auftrag."""
    t = text.lower().strip().rstrip("?!. ")
    m = re.search(_LEAD + r"erinner(?:e|)\s+(?:mich|uns)\s+(?P<rest>.+)$", t)
    if m:
        rest = m.group("rest")
        rep = "taeglich" if re.search(r"\b(jeden tag|täglich)\b", rest) else "werktags" if "werktags" in rest else \
            "woechentlich" if re.search(r"\b(jede woche|wöchentlich)\b", rest) else None
        what = re.search(r"\b(?:an|daran,?\s+(?:dass)?|zu|zum|zur)\s+(?P<was>.+)$", rest)
        thing = what.group("was") if what else ""
        thing = re.sub(r"\b(in \d+ \w+|in einer? \w+|morgen|heute|übermorgen|um [\w:.]+( uhr)?|jeden tag|täglich|werktags)\b", "", thing).strip(" ,")
        return {"aktion": "erinnerung", "wann": rest, "text": thing or "Erinnerung", **({"wiederholung": rep} if rep else {})}
    if _REST.search(t):
        return {"aktion": "ruhe"}
    if _ACTIVE.search(t):
        return {"aktion": "aktiv"}
    if re.search(_LEAD + r"(?:wie spät ist es|wieviel uhr ist es|wie viel uhr ist es|uhrzeit|welcher tag ist (?:heute|es)|welches datum(?: ist heute)?|der wievielte ist heute)\W*$", t):
        return {"aktion": "uhrzeit"}
    if re.search(_LEAD + r"(?:was steht (?:heute |morgen )?an|was hab ich heute(?: vor)?|termine heute|tagesüberblick|was ist heute los)\W*$", t):
        return {"aktion": "ueberblick"}
    m = re.search(_LEAD + r"(?:stell|setz|start)\w*\s+(?:mir\s+)?(?:einen\s+|den\s+)?(?:(?P<name>\w+)[- ]?)?timer\b(?:\s+(?:auf|für|von))?\s*(?P<dauer>.*)$", t) \
        or re.search(_LEAD + r"timer\s+(?:auf|für|von)\s+(?P<dauer>.+)$", t)
    if m:
        d = m.group("dauer") or ""
        name = (m.groupdict().get("name") or "").strip()
        if name in ("einen", "den", "neuen"):
            name = ""
        return {"aktion": "timer", "dauer": d, "text": name.capitalize() + "-Timer" if name else ""}
    m = re.search(_LEAD + r"(?:setz|schreib|pack|tu)\w*\s+(?P<was>.+?)\s+auf\s+(?:die|meine)\s+(?:to-?do|einkaufs)?-?\s*liste$", t)
    if m:
        return {"aktion": "todo", "text": m.group("was")}
    m = re.search(_LEAD + r"(?:hak\w*\s+(?P<a>.{3,60}?)\s+ab|(?P<b>.{3,60}?)\s+(?:ist\s+)?erledigt)$", t)
    if m:
        was = (m.group("a") or m.group("b") or "").strip()
        if was not in _NOT_TODOS and not was.startswith(("das ", "es ", "alles ", "ich ")):
            return {"aktion": "todo_erledigt", "text": was}
    if re.search(_LEAD + r"(?:was steht auf (?:der|meiner) liste|meine to-?dos|zeig (?:mir )?(?:die|meine) liste|to-?do-?liste)\W*$", t):
        return {"aktion": "todos"}
    return None
