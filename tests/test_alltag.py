"""Alltagsbuddy: Zeiten verstehen, Planer, Kalenderimport, einfache Befehle, Alarme und Ruhe/Aktiv."""

import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from duckpilot import settings as S
from duckpilot.buddy import Planner, fmt_when, parse_duration, parse_ics, parse_when, say_time
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app
from duckpilot.skills.alltag import quick

H = {"Origin": "http://127.0.0.1:8765"}
WS = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
NOW = datetime(2026, 10, 28, 14, 10).astimezone()      # Mittwoch


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.mark.parametrize("text,secs", [
    ("5 Minuten", 300), ("eine halbe Stunde", 1800), ("1 h 30 min", 5400), ("anderthalb Stunden", 5400),
    ("eine Viertelstunde", 900), ("zweieinhalb Stunden", 9000), ("90 Sekunden", 90), ("zehn Minuten", 600),
    ("1,5 Stunden", 5400),
])
def test_durations(text, secs):
    assert parse_duration(text) == secs


@pytest.mark.parametrize("text,expect", [
    ("in 10 Minuten an Tee", "heute um 14:20 Uhr"),
    ("um 15 Uhr", "heute um 15:00 Uhr"),
    ("morgen um halb 9", "morgen um 08:30 Uhr"),
    ("am Freitag um 14:30", "übermorgen um 14:30 Uhr"),
    ("am 3.11. um 9", "Dienstag, 3. November um 09:00 Uhr"),
    ("heute Abend um 8", "heute um 20:00 Uhr"),
    ("um 7", "heute um 19:00 Uhr"),                  # 7 Uhr ist vorbei → 19 Uhr
    ("um 13 Uhr 45", "morgen um 13:45 Uhr"),         # vorbei, nachmittags → morgen
    ("um viertel vor 4", "heute um 15:45 Uhr"),
    ("nächsten Montag um 10", "Montag, 2. November um 10:00 Uhr"),
    ("morgen früh", "morgen um 08:00 Uhr"),
])
def test_when(text, expect):
    assert fmt_when(parse_when(text, NOW), NOW) == expect


def test_when_without_time_is_none():
    assert parse_when("irgendwann mal", NOW) is None
    assert "Mittwoch, der 28. Oktober 2026" in say_time(NOW)


def test_planner_timer_reminder_event_and_repeat(tmp_path):
    clock = Clock(NOW)
    p = Planner(tmp_path / "alltag.json", clock)
    p.add_timer(60, "Tee")
    r = p.add_reminder("Pflanzen gießen", NOW + timedelta(minutes=5), "taeglich")
    p.add_event("Zahnarzt", NOW + timedelta(minutes=40), place="Praxis", lead_min=30)
    with pytest.raises(ValueError):
        p.add_reminder("zu spät", NOW - timedelta(hours=1))
    assert p.tick() == []
    clock.t = NOW + timedelta(seconds=61)
    [a] = p.tick()
    assert a.art == "timer" and "Tee" in a.text and p.data["timer"] == []
    clock.t = NOW + timedelta(minutes=11)
    arts = sorted(x.art for x in p.tick())
    assert arts == ["erinnerung", "termin"]
    again = next(x for x in p.data["erinnerungen"] if x["id"] == r["id"])
    assert again["faellig"].startswith("2026-10-29T14:15") and not again["erledigt"]    # morgen wieder
    assert p.tick() == []                                    # jeder Eintrag nur einmal
    term = next(a for a in p.alarms if a.art == "termin")
    assert "Praxis" in term.text and "in 29 Minuten" in term.text
    # bestätigen und schlummern
    assert p.ack(term.id) and not p.ack(term.id)
    timer_alarm = next(a for a in p.alarms if a.art == "timer")
    item = p.snooze(timer_alarm.id, 5)
    assert item["faellig"].startswith("2026-10-28T14:26")
    # Speichern übersteht Neustart
    assert len(Planner(tmp_path / "alltag.json", clock).data["erinnerungen"]) == 2


def test_all_day_event_rings_at_eight(tmp_path):
    from duckpilot.buddy import local

    clock = Clock(local(datetime(2026, 10, 29, 7, 0)))
    p = Planner(tmp_path / "a.json", clock)
    p.add_event("Feiertag", local(datetime(2026, 10, 29)), all_day=True)
    assert p.tick() == []
    clock.t = local(datetime(2026, 10, 29, 8, 1))
    [a] = p.tick()
    assert a.art == "termin" and "heute" in a.text


def test_repeating_and_exact_times_are_not_pushed_to_the_evening():
    nine = datetime(2026, 10, 28, 9, 0).astimezone()
    assert fmt_when(parse_when("um 8", nine, pm_shift=False), nine) == "morgen um 08:00 Uhr"
    assert fmt_when(parse_when("um 7:30", nine), nine) == "morgen um 07:30 Uhr"
    assert fmt_when(parse_when("um 8", nine), nine) == "heute um 20:00 Uhr"
    assert fmt_when(parse_when("heute morgen um 10", nine), nine) == "heute um 10:00 Uhr"


def test_snooze_keeps_clean_text_and_survives_full_list(tmp_path):
    clock = Clock(NOW)
    p = Planner(tmp_path / "a.json", clock)
    p.add_event("Zahnarzt", NOW + timedelta(minutes=10))
    [a] = p.tick()
    item = p.snooze(a.id, 5)
    assert item["text"] == "Zahnarzt" and not p.alarms
    p.add_timer(1, "Eier")
    clock.t = NOW + timedelta(seconds=2)
    [b] = p.tick()
    p.data["erinnerungen"] = [{"id": str(i), "text": "x", "faellig": NOW.isoformat(), "erledigt": True}
                              for i in range(500)]
    with pytest.raises(ValueError):
        p.snooze(b.id, 5)
    assert p.alarms and p.alarms[0].id == b.id                # Alarm bleibt, wenn nichts gespeichert wurde


def test_todo_matching_is_strict(tmp_path):
    p = Planner(tmp_path / "a.json", Clock(NOW))
    old = p.add_todo("Milch kaufen")
    p.finish_todo(old["id"])
    new = p.add_todo("Milch kaufen")
    assert p.finish_todo("Milch kaufen")["id"] == new["id"]     # das offene, nicht das alte
    p.add_todo("Geschenk kaufen")
    p.add_todo("Brot kaufen")
    assert p.finish_todo("es") is None                         # zu kurz, keine Teilwörter
    with pytest.raises(ValueError):
        p.finish_todo("kaufen")                                # passt auf zwei
    assert p.finish_todo("brot")["text"] == "Brot kaufen"


def test_overdue_event_after_pc_was_off_does_not_ring(tmp_path):
    clock = Clock(NOW)
    p = Planner(tmp_path / "a.json", clock)
    p.add_event("Gestern", NOW - timedelta(hours=5))
    assert p.tick() == []


def test_todos_agenda_and_brief(tmp_path):
    p = Planner(tmp_path / "a.json", Clock(NOW))
    p.add_todo("Milch kaufen")
    assert p.add_todo("milch kaufen")["text"] == "Milch kaufen"            # keine Doppelten
    p.add_todo("Steuer")
    p.add_event("Training", NOW + timedelta(hours=3))
    assert p.finish_todo("steuer")["erledigt"]
    assert p.clear_done() == 1
    brief = p.brief()
    assert "17:10 Training" in brief and "1 offene To-dos: Milch kaufen" in brief
    assert p.agenda()[0]["text"] == "Training"
    with pytest.raises(ValueError):
        p.set_options(ruhe_nach_min=7)
    assert p.set_options(ruhe_nach_min=30, wecken="ton")["wecken"] == "ton"


ICS = """BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
UID:abc-1\r
DTSTART:20261029T090000\r
DTEND:20261029T100000\r
SUMMARY:Team\\, Planung\r
LOCATION:Raum <b>2</b>\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:abc-2\r
DTSTART;VALUE=DATE:20261030\r
SUMMARY:Feiertag\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:old\r
DTSTART:20250101T090000Z\r
SUMMARY:Alt\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:weekly\r
DTSTART:20261102T080000\r
RRULE:FREQ=WEEKLY\r
SUMMARY:Jeden Montag\r
 mit Fortsetzung\r
END:VEVENT\r
END:VCALENDAR\r
"""


def test_ics_import_dedupes_and_expands_series(tmp_path):
    events, series, unsupported = parse_ics(ICS, NOW)
    titles = [e["titel"] for e in events]
    assert titles[:3] == ["Team, Planung", "Feiertag", "Jeden Montagmit Fortsetzung"] and series == 1 and unsupported == 0
    mondays = [e for e in events if e["titel"].startswith("Jeden Montag")]
    assert len(mondays) >= 15 and all(e["start"].weekday() == 0 and e["start"].hour == 8 for e in mondays)
    assert events[1]["ganztags"] and events[0]["ort"] == "Raum <b>2</b>"    # Text bleibt Text
    p = Planner(tmp_path / "a.json", Clock(NOW))
    r = p.import_ics(ICS)
    assert r["importiert"] == len(events) and r["serien"] == 1
    p.import_ics(ICS)
    assert len(p.data["termine"]) == len(events)             # zweiter Import aktualisiert nur
    # verschobener Termin wird zur neuen Zeit wieder gemeldet
    team = next(e for e in p.data["termine"] if e["titel"] == "Team, Planung")
    team["gemeldet"] = True
    p.import_ics(ICS.replace("DTSTART:20261029T090000", "DTSTART:20261029T110000"))
    assert not next(e for e in p.data["termine"] if e["titel"] == "Team, Planung")["gemeldet"]


def test_ics_complicated_series_keeps_first():
    ics = ICS.replace("RRULE:FREQ=WEEKLY", "RRULE:FREQ=MONTHLY;BYDAY=1MO")
    events, series, unsupported = parse_ics(ics, NOW)
    assert unsupported == 1 and len([e for e in events if e["titel"].startswith("Jeden")]) == 1


@pytest.fixture()
def berlin(monkeypatch):
    if not hasattr(time, "tzset"):
        pytest.skip("braucht tzset")
    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    yield
    monkeypatch.delenv("TZ")
    time.tzset()


def test_wall_times_survive_the_dst_change(berlin, tmp_path):
    from duckpilot.buddy import local

    sat = local(datetime(2026, 10, 24, 20, 0))                 # noch Sommerzeit
    tomorrow = parse_when("morgen um 9", sat)                  # Sonntag: Winterzeit
    assert (tomorrow.hour, tomorrow.utcoffset()) == (9, timedelta(hours=1))
    assert parse_when("am 3.11. um 9", sat).utcoffset() == timedelta(hours=1)
    p = Planner(tmp_path / "a.json", Clock(sat))
    r = p.add_reminder("Tabletten", local(datetime(2026, 10, 24, 20, 5)), "taeglich")
    p.clock = Clock(local(datetime(2026, 10, 24, 20, 6)))
    p.tick()
    nxt = datetime.fromisoformat(next(x for x in p.data["erinnerungen"] if x["id"] == r["id"])["faellig"])
    assert (nxt.day, nxt.hour, nxt.minute) == (25, 20, 5) and nxt.utcoffset() == timedelta(hours=1)
    ev, _, _ = parse_ics(ICS.replace("DTSTART:20261029T090000", "DTSTART;TZID=Europe/Berlin:20261029T090000"), sat)
    assert ev[0]["start"].hour == 9


@pytest.mark.parametrize("text,aktion", [
    ("Wie spät ist es?", "uhrzeit"), ("Welcher Tag ist heute", "uhrzeit"), ("Was steht heute an?", "ueberblick"),
    ("Stell einen Timer auf 5 Minuten", "timer"), ("Stell mir einen Nudel-Timer auf 9 Minuten", "timer"),
    ("Timer für eine halbe Stunde", "timer"),
    ("Erinnere mich in 10 Minuten an den Tee", "erinnerung"), ("Erinnere mich morgen um 9 an den Arzt", "erinnerung"),
    ("Setz Milch auf die Einkaufsliste", "todo"), ("Milch erledigt", "todo_erledigt"),
    ("Was steht auf meiner Liste?", "todos"), ("Ruhemodus", "ruhe"), ("Ruh dich aus", "ruhe"),
    ("Aktivmodus", "aktiv"), ("Wach auf!", "aktiv"),
])
def test_quick_phrases(text, aktion):
    assert quick(text)["aktion"] == aktion


@pytest.mark.parametrize("text", [
    "das erinnert mich an früher", "es ist erledigt", "ok erledigt", "ich bin erledigt", "lauf vor", "dreh dich",
    "steh auf", "wie spät ist es wohl in Tokio, erzähl mal eine Geschichte", "die Uhrzeit des Spiels war super",
])
def test_quick_ignores_ordinary_sentences(text):
    assert quick(text) is None


def test_quick_reminder_wins_over_mode_words():
    assert quick("Erinner mich morgen um 7 ans Aufwachen")["aktion"] == "erinnerung"
    assert quick("Erinnere mich an die Ruhepause um 15 Uhr")["aktion"] == "erinnerung"


def test_quick_extracts_details():
    q = quick("Erinnere mich in 10 Minuten an den Tee")
    assert q["text"] == "den tee" and "10 minuten" in q["wann"]
    assert quick("Stell mir einen Nudel-Timer auf 9 Minuten")["text"] == "Nudel-Timer"
    assert quick("Erinnere mich jeden Tag um 8 an Tabletten")["wiederholung"] == "taeglich"
    assert quick("lauf vor") is None and quick("dreh dich") is None


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        c.runtime = rt
        yield c


def _wait(pred, seconds=6.0):
    end = time.time() + seconds
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


def test_chat_without_claude_uses_buddy_and_timer_rings(client):
    rt = client.runtime
    sent = []
    orig = rt.broadcast

    async def spy(msg):
        sent.append(msg)
        await orig(msg)

    rt.broadcast = spy
    with client.websocket_connect("/ws", headers=WS) as ws:
        ws.send_json({"type": "chat", "text": "Wie spät ist es?"})
        assert _wait(lambda: any(m.get("role") == "duck" and "Es ist" in (m.get("text") or "") for m in sent))
        r = client.post("/api/alltag/befehl", json={"aktion": "timer", "dauer": "1 Sekunde", "text": "Eier"}, headers=H).json()
        assert r["ok"] and "Eier" in r["antwort"]
        assert _wait(lambda: any(m.get("type") == "alltag_alarm" for m in sent), 5)
        alarm = next(m for m in sent if m.get("type") == "alltag_alarm")["alarm"]
        assert alarm["art"] == "timer"
        assert any(m.get("source") == "alltag" and "Eier" in m.get("text", "") for m in sent)
        assert client.post(f"/api/alltag/alarm/{alarm['id']}", json={}, headers=H).json()["ok"]
        assert rt.alltag.planner.alarms == []


def test_rest_mode_wakes_on_alarm_but_not_after_emergency_stop(client):
    rt = client.runtime
    assert client.post("/api/alltag/optionen", json={"modus": "ruhe"}, headers=H).json()["ok"]
    assert _wait(lambda: not rt.backend.state().powered)
    # Alarm weckt sie auf
    rt.alltag.planner.add_timer(1, "Wecker")
    assert _wait(lambda: rt.backend.state().powered and rt.backend.state().enabled, 8)
    assert rt.alltag.mode == "ruhe" and rt.alltag.woke_for_alarm
    for a in list(rt.alltag.planner.alarms):
        rt.alltag.ack(a.id)
    # Not-Aus: der nächste Alarm lässt sie nicht aufstehen
    client.post("/api/alltag/optionen", json={"modus": "ruhe"}, headers=H)
    assert _wait(lambda: not rt.backend.state().powered)
    with client.websocket_connect("/ws", headers=WS) as ws:
        ws.send_json({"type": "stop"})
        assert _wait(lambda: rt.alltag.estop_at > 0)
    rt.alltag.planner.add_timer(1, "Zweiter")
    assert _wait(lambda: len(rt.alltag.planner.alarms) == 1, 5)
    time.sleep(1.0)
    assert not rt.backend.state().powered                   # nur Ton und Durchsage


def test_talking_wakes_her_from_rest(client):
    rt = client.runtime
    client.post("/api/alltag/optionen", json={"modus": "ruhe"}, headers=H)
    assert _wait(lambda: not rt.backend.state().powered)
    with client.websocket_connect("/ws", headers=WS) as ws:
        ws.send_json({"type": "chat", "text": "Hallo Ente"})
        assert _wait(lambda: rt.alltag.mode == "aktiv" and rt.backend.state().powered, 8)
        ws.send_json({"type": "chat", "text": "Ruhemodus"})
        assert _wait(lambda: rt.alltag.mode == "ruhe" and not rt.backend.state().powered, 8)


def test_lead_zero_and_bad_minutes(client):
    r = client.post("/api/alltag/befehl", json={"aktion": "termin", "text": "Call", "wann": "morgen um 10",
                                               "minuten_vorher": 0}, headers=H).json()
    assert r["ok"] and r["termin"]["vorher_min"] == 0
    assert client.post("/api/alltag/befehl", json={"aktion": "termin", "text": "Call", "wann": "morgen um 10",
                                                  "minuten_vorher": [1]}, headers=H).status_code == 400
    assert client.post("/api/alltag/alarm/x", json={"schlummern": True, "minuten": "x"}, headers=H).status_code == 400


def test_stop_tool_and_head_drag_do_not_wake_after_estop(client):
    rt = client.runtime
    client.post("/api/alltag/optionen", json={"modus": "ruhe"}, headers=H)
    assert _wait(lambda: not rt.backend.state().powered)
    with client.websocket_connect("/ws", headers=WS) as ws:
        ws.send_json({"type": "tool", "name": "stop", "args": {}})          # wie Claudes stop-Werkzeug
        assert _wait(lambda: rt.alltag.since_estop() < 5)
        ws.send_json({"type": "drive", "vx": 0, "vy": 0, "vyaw": 0, "head": {"pitch": 0.1, "yaw": 0.2}})
        ws.send_json({"type": "chat", "text": "hör auf!"})
        time.sleep(1.5)
        assert rt.alltag.mode == "aktiv" and not rt.backend.state().powered   # wach, aber steht nicht auf
    rt.alltag.planner.add_timer(1, "Nach Stopp")
    assert _wait(lambda: len(rt.alltag.planner.alarms) == 1, 5)
    time.sleep(1.0)
    assert not rt.backend.state().powered


def test_back_to_rest_after_alarm_is_acknowledged(client, monkeypatch):
    import duckpilot.skills.alltag as A

    monkeypatch.setattr(A, "BACK_TO_REST_S", 0.5)
    rt = client.runtime
    client.post("/api/alltag/optionen", json={"modus": "ruhe"}, headers=H)
    assert _wait(lambda: not rt.backend.state().powered)
    rt.alltag.planner.add_timer(1, "Wecker")
    assert _wait(lambda: rt.backend.state().powered and rt.alltag.planner.alarms, 8)
    aid = rt.alltag.planner.alarms[0].id
    assert client.post(f"/api/alltag/alarm/{aid}", json={}, headers=H).json()["ok"]
    assert _wait(lambda: not rt.backend.state().powered, 6)              # schläft wieder ein


def test_api_validation_and_ics(client):
    assert client.post("/api/alltag/optionen", json={"wecken": "laut"}, headers=H).status_code == 400
    assert client.post("/api/alltag/befehl", json={"aktion": "erinnerung", "text": "x"}, headers=H).status_code == 400
    bad = client.post("/api/alltag/ics", content=b"kein kalender", headers=H)
    assert bad.status_code == 400
    soon = (datetime.now() + timedelta(days=2)).strftime("%Y%m%d")
    ics = ICS.replace("20261029", soon).replace("20261030", soon).replace("20261102", soon)
    ok = client.post("/api/alltag/ics", content=ics.encode(), headers=H).json()
    assert ok["ok"] and ok["importiert"] >= 2
    todo = client.post("/api/alltag/befehl", json={"aktion": "todo", "text": "Brot"}, headers=H).json()["todo"]
    assert client.post(f"/api/alltag/todo/{todo['id']}", json={"erledigt": True}, headers=H).json()["ok"]
    assert client.delete(f"/api/alltag/todo/{todo['id']}", headers=H).json()["ok"]
    assert client.delete("/api/alltag/quatsch/1", headers=H).status_code == 400
    # aus: keine Befehle
    client.post("/api/skills", json={"id": "alltag", "an": False}, headers=H)
    assert client.post("/api/alltag/befehl", json={"aktion": "uhrzeit"}, headers=H).status_code == 400
