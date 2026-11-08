"""Zusagen einhalten (seit 0.37.14).

Befund aus dem Test mit 0.37.13: „Ich hatte mehrmals den Befehl für Purzelbaum gegeben und er hat immer nur geantwortet,
aber nicht ausgeführt.“ Das Sprachmodell schrieb „Hier kommt die neue Fassung … ich rolle ab“, rief aber kein Werkzeug
auf (oder nur eine Choreografie). Bewegen geht nur über Werkzeuge – eine Antwort, die eine Bewegung ankündigt, ohne
sie auszuführen, ist für den Menschen schlicht falsch.

Absicherung in zwei Stufen:

1. Verlangt der Mensch eine eindeutige Vorführung („mach einen Purzelbaum“, „tanz“, „schieß zum Sofa“) oder kündigt
   die Antwort eine Bewegung an („ich rolle ab“, „hier kommt …“), aber es lief kein passendes Werkzeug, fragt
   duckpilot einmal nach – mit einem kurzen Hinweis an das Modell, es jetzt auszuführen oder ehrlich zu sagen, warum
   nicht.
2. Fehlt es danach immer noch und der Befehl ist eindeutig, führt duckpilot ihn selbst aus (dieselben Werkzeuge wie
   ohne KI – alle Sicherheitsregeln gelten dort unverändert) und sagt das.

Fragen, Bedingungen und Verneinungen („kannst du …?“, „mach keinen Purzelbaum“) lösen nichts aus.
"""

from __future__ import annotations

import re
from typing import Any

from .fallback import NOT_QUICK, parse

# Vorführungen, die der Mensch sehen will – Gehen/Drehen/Kopf zählen nicht (die macht das Modell oft absichtlich anders)
VORFUEHRUNG = {"skill", "_kick", "schiessen", "dance", "apportieren", "_pick", "laser_folgen", "mir_folgen", "karte"}
# Welche Werkzeuge eine verlangte Vorführung erfüllen (Werkzeug der Befehlsregel → Werkzeuge des Modells)
ERFUELLT = {
    "skill": {"skill"},
    "_kick": {"skill", "schiessen", "handeln"},
    "schiessen": {"schiessen", "skill", "handeln"},
    "dance": {"dance", "choreography", "choreo"},
    "apportieren": {"apportieren", "handeln", "team"},
    "_pick": {"skill", "approach", "apportieren", "handeln"},
    "laser_folgen": {"laser_folgen"},
    "mir_folgen": {"mir_folgen"},
    "karte": {"karte"},
}
MAX_WOERTER = 14
# Antwort kündigt eine Bewegung in der Gegenwart an
KUENDIGT_AN = re.compile(
    r"\b(hier kommt|jetzt (läuft|kommt|mache|zeige|rolle|tanze)|los geht'?s|schau( mal)? her|pass auf|"
    r"ich (mache|mach|zeige|zeig|führe|rolle|tanze|schieße|schiesse|hole|drehe|springe|lege los)\b|"
    r"here (it )?comes|watch (this|me)|i'?m (doing|rolling|dancing|kicking|showing)|let'?s go)", re.I)
# Antwort sagt ehrlich, dass sie es nicht macht
LEHNT_AB = re.compile(r"\b(geht (gerade |leider )?nicht|kann ich (gerade |leider )?nicht|mache ich (lieber )?nicht|"
                      r"lieber nicht|nicht sicher|zu gefährlich|erst aufstehen|can'?t|won'?t|not safe|rather not)\b", re.I)
BEWEGUNGS_WERKZEUGE = {"skill", "schiessen", "dance", "choreography", "walk", "turn", "approach", "apportieren",
                       "handeln", "laser_folgen", "mir_folgen", "explore", "karte", "do_trick", "go_to_place",
                       "look_around", "emote", "head", "power", "team", "choreo", "drive", "go_to", "enten"}


def verlangt(text: str) -> list[tuple[str, dict[str, Any]]]:
    """Eindeutig verlangte Vorführungen in der Nachricht – leer bei Fragen, Bedingungen, Verneinungen."""
    t = text.lower().strip().rstrip(".!")
    if not t or len(t.split()) > MAX_WOERTER or NOT_QUICK.search(t):
        return []
    return [(name, args) for name, args in parse(t) if name in VORFUEHRUNG]


def erfuellt(schritte: list[tuple[str, dict[str, Any]]], actions: list[dict[str, Any]]) -> bool:
    """Lief für jede verlangte Vorführung ein passendes Werkzeug? (Abgelehnt zählt: dann sagt das Modell, warum.)"""
    gelaufen = [a.get("tool") for a in actions]
    for name, args in schritte:
        passend = ERFUELLT.get(name, {name})
        if name == "skill":
            want = args.get("name")
            if not any(a.get("tool") == "skill" and (a.get("input") or {}).get("name") == want for a in actions):
                return False
            continue
        if not any(g in passend for g in gelaufen):
            return False
    return True


def leere_ankuendigung(antwort: str, actions: list[dict[str, Any]]) -> bool:
    """Kündigt die Antwort eine Bewegung an, ohne dass sich irgendetwas bewegt hat?"""
    if not KUENDIGT_AN.search(antwort or "") or LEHNT_AB.search(antwort or ""):
        return False
    return not any(a.get("tool") in BEWEGUNGS_WERKZEUGE for a in actions)


def hinweis(schritte: list[tuple[str, dict[str, Any]]], englisch: bool = False) -> str:
    """Nachfrage an das Modell (steht im Verlauf als Nachricht von duckpilot, nicht vom Menschen)."""
    was = ", ".join(_name(n, a) for n, a in schritte) or "die angekündigte Bewegung"
    if englisch:
        return (f"[duckpilot] You did not run a tool, so nothing moved. Do it now ({was}) with the matching tool – "
                "or say honestly in one sentence why not. Only describe what the tools really did.")
    return (f"[duckpilot] Du hast kein Werkzeug aufgerufen, es hat sich also nichts bewegt. Führe es jetzt aus ({was}) "
            "– mit dem passenden Werkzeug – oder sag ehrlich in einem Satz, warum nicht. Beschreibe nur, was die "
            "Werkzeuge wirklich gemacht haben.")


def _name(name: str, args: dict[str, Any]) -> str:
    if name == "skill":
        return f"skill {args.get('name')}"
    if name == "schiessen":
        return "schiessen " + ", ".join(f"{k}={v}" for k, v in args.items())
    if name == "_kick":
        return "Ball schießen"
    if name == "_pick":
        return f"{args.get('target')} aufheben"
    return name
