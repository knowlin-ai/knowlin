"""Einfache Sprachbefehle ohne Claude – für Tests, ohne API-Schlüssel oder offline.

Versteht kurze deutsche Kommandos wie "lauf einen Meter vor", "dreh dich nach
links", "tanz", "setz dich", "schieß den Ball", "stopp". Mehrere Teile mit
"und dann" / "danach" werden nacheinander ausgeführt.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agent import Reply
    from .tools import ToolRunner

NUM_WORDS = {
    "einen": 1, "ein": 1, "eine": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "halben": 0.5, "halb": 0.5,
}


def _number(text: str, default: float) -> float:
    m = re.search(r"(\d+(?:[.,]\d+)?)", text)
    if m:
        return float(m.group(1).replace(",", "."))
    if re.search(r"\b(einen |ein )?halbe[nr]?\b", text):
        return 0.5
    if re.search(r"\b(ein|einen|eine)(n)? viertel\b", text):
        return 0.25
    for word, val in NUM_WORDS.items():
        if re.search(rf"\b{word}\b", text):
            return val
    return default


def _distance(text: str, default: float = 0.4) -> float:
    n = _number(text, default)
    if "zentimeter" in text or re.search(r"\d\s*cm\b", text):
        return n / 100
    if "schritt" in text:
        return n * 0.08
    if "meter" in text or re.search(r"\d\s*m\b", text):
        return n
    return n if n <= 5 else n / 100


def parse(text: str) -> list[tuple[str, dict[str, Any]]]:
    t = text.lower().strip()
    if re.search(r"\b(stopp?|halt|anhalten|aufhören|stehen bleiben|freeze|stand still|stop it)\b", t):
        return [("stop", {})]
    steps: list[tuple[str, dict[str, Any]]] = []
    for part in re.split(r"\b(?:und dann|danach|anschließend|dann|and then|then|afterwards)\b|,", t):
        p = part.strip()
        if not p:
            continue
        cmd = _szene(p) or _team(p) or _schuss(p) or _handeln(p) or _parse_part_en(p) or _parse_part(p)
        if cmd:
            steps.append(cmd)
    return steps


# Kurzbefehle, die auch mit Claude nur „mach ich“ ergäben – die erledigt duckpilot selbst (keine Tokens, schneller).
QUICK_TOOLS = {"stop", "power", "walk", "turn", "approach", "umrunden", "dance", "explore", "look_around", "laser_folgen", "mir_folgen", "_kick", "skill"}
NOT_QUICK = re.compile(r"\?|\b(was|wie|warum|wieso|weshalb|wer|wo|wohin|woher|wann|welche\w*|kannst|könntest|magst|"
                       r"willst|möchtest|darfst|sollst|bist|hast|nicht|nie|kein\w*|lieber|vielleicht|erzähl\w*|"
                       r"wenn|falls|ob|what|how|why|who|where|when|which|can|could|would|should|do you|don't|not|"
                       r"never|maybe|tell|if|whether)\b")
QUICK_MAX_WORDS = 4


def quick_command(text: str) -> bool:
    """Ein kurzer, eindeutiger Bewegungsbefehl ohne Frage, Bedingung oder Verneinung?"""
    t = text.lower().strip().rstrip(".!")
    if not t or len(t.split()) > QUICK_MAX_WORDS or NOT_QUICK.search(t):
        return False
    steps = parse(t)
    return bool(steps) and all(name in QUICK_TOOLS for name, _ in steps)


EN_NUM = {"one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "half a": 0.5, "half": 0.5}


def _distance_en(p: str, default: float) -> float:
    m = re.search(r"(\d+(?:[.,]\d+)?)", p)
    n = float(m.group(1).replace(",", ".")) if m else next((v for w, v in EN_NUM.items() if re.search(rf"\b{w}\b", p)),
                                                           None)
    if n is None:
        return default
    if re.search(r"centimet|\d\s*cm\b", p):
        return n / 100
    if "step" in p:
        return n * 0.08
    return n if re.search(r"met(er|re)|\d\s*m\b", p) or n <= 5 else n / 100


def _parse_part_en(p: str) -> tuple[str, dict[str, Any]] | None:
    """Kurze englische Befehle (seit 0.34) – dieselben Werkzeuge wie die deutschen. Wörter, die auch deutsch sein
    könnten, sind bewusst ausgelassen; ohne Treffer geht es mit den deutschen Mustern weiter."""
    sek = lambda d: _number(p, d) if "second" in p else d    # noqa: E731
    if re.search(r"\b(stand up|get up|wake up|motors on)\b", p):
        return ("power", {"action": "stand_up"})
    if re.search(r"\bsit( down)?\b", p):
        return ("power", {"action": "sit_down"})
    if re.search(r"\b(go to sleep|sleep|rest|motors off)\b", p):
        return ("power", {"action": "rest"})
    if re.search(r"\b(shoot|kick)\b", p):
        return ("_kick", {"side": "kick_right" if "right" in p else "kick_left"})
    if re.search(r"\b(bring me|bring (it|the \w+( \w+)?) (back|here|to me)|fetch|retrieve)\b", p):
        return ("apportieren", {"ding": _ding(p)})
    if re.search(r"\b(pick up|pick (it|the \w+) up|grab)\b", p):
        return ("_pick", {"target": _ding(p)})
    if re.search(r"\b(put (it )?down|drop it|let (it )?go)\b", p):
        return ("skill", {"name": "ground_pick"})
    if re.search(r"\b(somersault|roll|tumble|forward roll)\b", p):
        return ("skill", {"name": "roulade"})
    if re.search(r"\bdance\b", p):
        return ("dance", {"style": "party", "seconds": sek(10)})
    if re.search(r"\b(follow me|come with me|come along)\b", p):
        return ("mir_folgen", {"seconds": _number(p, 5) * 60 if "minute" in p else sek(300)})
    if re.search(r"\b(chase|follow)\b.*\b(laser|dot)\b|\blaser\b", p):
        return ("laser_folgen", {"seconds": sek(120)})
    if re.search(r"\bmap (the|this|my) (room|flat|apartment|house)\b|\bmapping\b", p):
        return ("karte", {"aktion": "start", "sekunden": _number(p, 2) * 60 if "minute" in p else 120})
    um = _umziel(p) if re.search(r"\baround\b", p) else None
    if um:
        return ("umrunden", {"target": um[0], "richtung": "rechts" if um[1] == "rechts" else "links"})
    if re.search(r"\b(explore|wander|walk around|roam)\b", p):
        return ("explore", {"seconds": sek(40)})
    if re.search(r"\blook around\b", p):
        return ("look_around", {"seconds": 6})
    if re.search(r"\b(again|repeat( that)?|one more time)\b", p):
        return ("_repeat", {})
    for word, emo in (("happy", "freude"), ("sad", "traurig"), ("curious", "neugierig"), ("surprised", "ueberrascht"),
                      ("tired", "muede"), ("angry", "wuetend"), ("nod", "ja"), ("shake your head", "nein"),
                      ("say hello", "begruessen"), ("hello", "begruessen"), ("greet", "begruessen")):
        if re.search(rf"\b{word}\b", p):
            return ("emote", {"emotion": emo})
    if re.search(r"\b(quack|make a sound)\b", p):
        return ("sound", {"tag": "chirp"})
    if re.search(r"\b(turn|spin)\b", p):
        deg = _number(p, 90) if re.search(r"\d", p) else (180 if "around" in p else 90)
        return ("turn", {"degrees": (-1 if "right" in p else 1) * abs(deg)})
    for word, args in (("left", {"yaw_deg": 45}), ("right", {"yaw_deg": -45}), ("up", {"pitch_deg": -30}),
                       ("down", {"pitch_deg": 30})):
        if re.search(rf"\blook {word}\b", p):
            return ("head", {**args, "seconds": 3})
    if re.search(r"\b(back|backwards?|reverse)\b", p) and re.search(r"\b(go|walk|move|step|back up)\b|^back", p):
        return ("walk", {"distance_m": -abs(_distance_en(p, 0.3))})
    if re.search(r"\b(left|right)\b", p) and re.search(r"\b(step|sideways|go|walk|move)\b", p):
        return ("walk", {"distance_m": (-1 if "right" in p else 1) * abs(_distance_en(p, 0.2)), "sideways": True})
    ziel = _hinziel(p) if re.search(r"\b(go|walk|run|head)\w*\b.*\bto\b", p) else None
    if ziel:
        return ("approach", {"target": ziel})
    if re.search(r"\b(forward|walk|go ahead|come here|move)\b", p):
        return ("walk", {"distance_m": abs(_distance_en(p, 0.4))})
    return None


# „Wo hast du die Socke zuletzt gesehen?“, „Wo ist der Klemmbaustein?“, „where did you last see the sock?“ (seit 0.37)
WO_GESEHEN = re.compile(r"\bwo (hast du\b.*\bgesehen|ist|liegt|sind|war)\b|\bwhere (is|are|did you (last )?see|was)\b")


def _ding(p: str, sonst: str = "socke") -> str:
    """Welches aufhebbare Ding gemeint ist (deutsch und englisch)."""
    for muster, ding in ((r"klemmbau|baustein|\blego|\bbrick", "klemmbaustein"),
                         (r"schach|figur|\bbauer\b|\bpawn|\bchess", "schachfigur"),
                         (r"klötz|kloetz|\bblock", "klötzchen"), (r"socke|\bsock", "socke")):
        if re.search(muster, p):
            return ding
    return sonst


ENTEN_NAMEN = ("kiki", "pip", "lotte", "bruno")      # die weiteren Enten im Simulator (backends/begleiter.NAMEN)

# „Lauf zum Ball“ (Fund 7.11.: Odi lief nur 40 cm geradeaus): Ziel aus dem Satz – Dinge, Möbel, weitere Enten.
# Rückgabe ist der Name, den Approach in der Wahrnehmung sucht.
HINZIELE = ((r"\bb[aä]ll", "ball"), (r"socke|\bsock", "socke"), (r"klötz|kloetz|\bblock", "klötzchen"),
            (r"klemmbau|baustein|\blego|\bbrick", "klemmbaustein"), (r"schach|figur|\bchess|\bpawn", "schachfigur"),
            (r"couchtisch|wohnzimmertisch|coffee table|\btisch|\btable", "couchtisch"), (r"sofa|couch", "sofa"),
            (r"regal|shelf", "regal"), (r"kiste|\bbox|\bcrate", "kiste"), (r"hocker|stool", "hocker"),
            (r"pflanze|plant", "pflanze"))
HIN = re.compile(r"\b(geh|lauf|watschel|renn|komm|flitz|go|walk|run|head)\w*\b.*?\b(zum|zur|zu|hin|to|towards?)\b(.*)")


UM = re.compile(r"\b(?:(?:geh|lauf|watschel|renn|flitz|lauf|go|walk|run)\w*\b.*?\bum\b(.*)|umrund\w*\b(.*)|"
                r"(?:go|walk|run|circle)\w*\b.*?\baround\b(.*))")


def _umziel(p: str) -> tuple[str, str] | None:
    """„Lauf um den Tisch (herum)“, „umrunde das Sofa“, „walk around the table“ → (Ziel, Richtung)."""
    m = UM.search(p)
    if not m:
        return None
    rest = next(g for g in m.groups() if g is not None)
    richtung = "rechts" if re.search(r"rechts|uhrzeigersinn|clockwise", p) and not re.search(r"gegen den uhrzeigersinn|counter", p) else "links"
    for muster, ziel in HINZIELE:
        if re.search(muster, rest):
            return ziel, richtung
    return None


def _hinziel(p: str) -> str | None:
    m = HIN.search(p)
    if not m:
        return None
    rest = m.group(3)
    for muster, ziel in HINZIELE:
        if re.search(muster, rest):
            return ziel
    return next((n for n in ENTEN_NAMEN if re.search(rf"\b{n}\b", rest)), None)


def _gemeint(p: str) -> str | None:
    """Angewähltes Ding aus „… (gemeint: Socke)“ (seit 0.37.3) oder der Name einer weiteren Ente im Satz."""
    m = re.search(r"\(gemeint: ([^)]+)\)", p)
    if m:
        return m.group(1).strip()
    return next((n for n in ENTEN_NAMEN if re.search(rf"\b{n}\b", p)), None)


TEAM_AUFRAEUMEN = re.compile(r"\b(räumt|raeumt|aufräum|aufraeum|bringt (alle|die|alles)|tidy up|clean up|"
                             r"everyone bring|bring all)\w*")
TEAM_SUCHEN = re.compile(r"\b(sucht|helft mir\b.*such|alle such|help me (find|search|look)|everyone (find|search|look))")


def _team(p: str) -> tuple[str, dict[str, Any]] | None:
    """Die anderen Enten um Hilfe bitten (seit 0.37.4): „Räumt alle Socken zum Sofa“, „Helft mir die Schachfigur
    suchen“, „everyone bring the blocks to me“."""
    if TEAM_SUCHEN.search(p):
        ding = _ding(p, "")
        return ("team", {"aktion": "suchen", "ding": ding}) if ding else None
    if TEAM_AUFRAEUMEN.search(p) and re.search(r"\b(alle|all|everyone|räumt|raeumt|helft|help)\b", p):
        m = re.search(r"\b(?:zum|zur|ans|aufs|ins|in die|in den|zu|to the|to)\s+(\w+)", p)
        ziel = (m.group(1) if m else "mir")
        ziel = "mir" if ziel in ("mir", "me", "dir") else ziel
        dinge = next((w for w in ("socke", "klötz", "baustein", "figur", "sock", "block", "brick", "chess") if w in p),
                     "alles")
        return ("team", {"aktion": "aufraeumen", "ziel": ziel, "dinge": dinge})
    return None


SCHUSS = re.compile(r"\b(schie(ß|ss)\w*|schuss|kick\w*|shoot\w*)\b")
SCHUSS_RICHTUNG = {"links": "links", "left": "links", "rechts": "rechts", "right": "rechts", "geradeaus": "geradeaus",
                   "straight": "geradeaus", "zurück": "zurück", "zurueck": "zurück", "back": "zurück"}


def _schuss(p: str) -> tuple[str, dict[str, Any]] | None:
    """Gezielt schießen (seit 0.37.9): „schieß den Ball zum Sofa“, „schieß zu Kiki“, „schieß nach links“,
    „kick the ball to the shelf“. Ohne Ziel bleibt es beim einfachen Schuss."""
    if not SCHUSS.search(p):
        return None
    m = re.search(r"\b(?:nach|to the|to)\s+(links|rechts|geradeaus|zurück|zurueck|left|right|straight|back)\b", p)
    if m:
        return ("schiessen", {"richtung": SCHUSS_RICHTUNG[m.group(1)]})
    m = re.search(r"\b(?:zum|zur|zu|ans|aufs|auf (?:den|die|das)|in richtung|richtung|to the|to|at the|at)\s+(\w+)", p)
    if m and m.group(1) not in ("ball", "the"):
        ziel = m.group(1)
        return ("schiessen", {"ziel": "mir" if ziel in ("mir", "me", "dir") else ziel})
    return None


def _handeln(p: str) -> tuple[str, dict[str, Any]] | None:
    """Mit einer anderen Ente oder dem angewählten Ding etwas tun – deutsch und englisch."""
    ding = _gemeint(p)
    if ding is None:
        return None
    ente = ding.lower() in ENTEN_NAMEN
    if re.search(r"\b(ärger|aerger|neck|foppe?|tease|annoy|bug)\w*", p):
        return ("handeln", {"ding": ding, "aktion": "aergern"})
    if ente and re.search(r"\b(begrüß|begruess|grüß|gruess|sag\w* hallo|hallo|greet|say hello)\w*", p):
        return ("handeln", {"ding": ding, "aktion": "begruessen"})
    if ente and re.search(r"\b(folg|hinterher|nach\b|follow)\w*", p):
        return ("handeln", {"ding": ding, "aktion": "folgen"})
    if re.search(r"\b(schau|guck|sieh|look)\w*", p):
        return ("handeln", {"ding": ding, "aktion": "anschauen"})
    if re.search(r"\b(geh|lauf|watschel|go|walk)\w* (hin|dahin|dorthin|there|to it)\b", p):
        return ("handeln", {"ding": ding, "aktion": "hinlaufen"})
    return None


SZENE_RESET = re.compile(r"\b(szene|simulator)\b.*\b(zurücksetzen|zuruecksetzen|zurück ?setzen|reset\w*)\b|"
                         r"\bsetz\w* (die szene|den simulator|alles) zurück\b|\breset (the )?(scene|simulator)\b")
# „leg den Ball zurück“ – aber nicht „bring die Socke zurück“ (das heißt: bring sie mir, Apportieren)
ZURUECKLEGEN = re.compile(r"\bleg\w*\b.*\bzurück\b|\bzurücklegen\b|\ban (seinen|ihren|den) (start)?platz\b|"
                          r"\bput (the \w+ |it )?back\b")


def _szene(p: str) -> tuple[str, dict[str, Any]] | None:
    """Simulator aufräumen (seit 0.37.14): „Szene zurücksetzen“, „leg den Ball zurück“, „reset the scene“."""
    if SZENE_RESET.search(p):
        return ("szene", {"aktion": "zuruecksetzen"})
    if ZURUECKLEGEN.search(p) and re.search(r"\b(ball|socke|sock|klötz|kloetz|block|baustein|klemm|figur|schach|lego)", p):
        return ("szene", {"aktion": "zuruecklegen", "ding": "ball" if re.search(r"\bball", p) else _ding(p)})
    return None


def _parse_part(p: str) -> tuple[str, dict[str, Any]] | None:
    if re.search(r"steh\w* auf|aufstehen|wach auf|motoren an", p):
        return ("power", {"action": "stand_up"})
    if re.search(r"setz\w* dich|hinsetzen|sitz\b", p):
        return ("power", {"action": "sit_down"})
    if re.search(r"schlaf|ausruhen|feierabend|motoren aus", p):
        return ("power", {"action": "rest"})
    if re.search(r"schieß|schiess|kick|tritt", p):
        side = "kick_right" if "recht" in p else "kick_left"
        return ("_kick", {"side": side})
    if re.search(r"\bwiederhol\w*\b", p):              # „wiederhole den Steptanz“: die gespeicherte Vorführung
        return ("_repeat", {})
    if re.search(r"\bbring\w*\b|apportier|\bhol\w* .*\b(her|mir)\b", p):
        return ("apportieren", {"ding": _ding(p)})
    if re.search(r"\bheb\w* .*auf|aufheben|\bnimm\b|\bhol\w* ", p):
        return ("_pick", {"target": _ding(p)})
    if re.search(r"leg\w* .*ab|ablegen|lass .*fallen", p):
        return ("skill", {"name": "ground_pick"})
    if "purzel" in p or "rolle" in p or "roulade" in p:
        return ("skill", {"name": "roulade"})
    if "tanz" in p:
        style = next((s for s in ("wackeln", "nicken", "drehen") if s[:4] in p), "party")
        return ("dance", {"style": style, "seconds": _number(p, 10) if "sekund" in p else 10})
    if re.search(r"\bfolg\w* mir|\bkomm mit\b|\blauf mir nach|\bhinter mir her", p):
        return ("mir_folgen", {"seconds": _number(p, 5) * 60 if "minut" in p else _number(p, 300) if "sekund" in p else 300})
    if re.search(r"laser", p):
        return ("laser_folgen", {"seconds": _number(p, 120) if "sekund" in p else 120})
    if re.search(r"kartier|karte (vom|des) (raum|zimmer|wohnung)|erkunde\w* (das|den|die) (raum|zimmer|wohnung)", p):
        return ("karte", {"aktion": "start", "sekunden": _number(p, 2) * 60 if "minut" in p else 120})
    if re.search(r"erkund|lauf herum|streif|spazier", p):
        return ("explore", {"seconds": _number(p, 40) if "sekund" in p else 40})
    if re.search(r"(?:schau|guck)\w* dich (?:(?:mal|doch|ein ?bisschen|etwas|kurz) )*um\b|umschauen|umgucken|look around", p):
        return ("look_around", {"seconds": 6})
    # „nochmal“ allein wiederholt das Letzte – mit einem benannten Trick („Purzelbaum nochmal“) gilt der Trick (seit 0.37.14)
    if re.search(r"\b(nochmal|noch ?mal|noch einmal)\b", p):
        return ("_repeat", {})
    for word, emo in (("freu", "freude"), ("trauri", "traurig"), ("neugier", "neugierig"), ("überrasch", "ueberrascht"),
                      ("müde", "muede"), ("wütend", "wuetend"), ("böse", "wuetend"), ("nick", "ja"), ("schüttel", "nein"),
                      ("begrüß", "begruessen"), ("hallo", "begruessen")):
        if word in p:
            return ("emote", {"emotion": emo})
    if re.search(r"quak|mach .*laut", p):
        return ("sound", {"tag": "chirp"})
    if re.search(r"dreh|wende|umdrehen", p):
        if re.search(r"\d", p):
            deg = _number(p, 90)
        else:
            deg = 180 if ("umdreh" in p or "dich um" in p) else 90
        sign = -1 if "recht" in p else 1
        return ("turn", {"degrees": sign * abs(deg)})
    if re.search(r"schau\w* (nach )?links", p):
        return ("head", {"yaw_deg": 45, "seconds": 3})
    if re.search(r"schau\w* (nach )?rechts", p):
        return ("head", {"yaw_deg": -45, "seconds": 3})
    if re.search(r"schau\w* (nach )?(hoch|oben)", p):
        return ("head", {"pitch_deg": -30, "seconds": 3})
    if re.search(r"schau\w* (nach )?(runter|unten)", p):
        return ("head", {"pitch_deg": 30, "seconds": 3})
    um = _umziel(p)
    if um:                                           # „lauf um den Tisch“: einmal ringsum (seit 0.38.21)
        return ("umrunden", {"target": um[0], "richtung": um[1]})
    ziel = _hinziel(p)
    if ziel:                                         # „lauf zum Ball“: hinlaufen und davor stehen bleiben
        return ("approach", {"target": ziel})
    if re.search(r"rückwärts|zurück", p):
        return ("walk", {"distance_m": -abs(_distance(p, 0.3))})
    if re.search(r"links|rechts", p) and re.search(r"seit|geh|lauf", p):
        sign = 1 if "links" in p else -1
        return ("walk", {"distance_m": sign * abs(_distance(p, 0.2)), "sideways": True})
    if re.search(r"vor|lauf|geh|komm", p):
        return ("walk", {"distance_m": abs(_distance(p, 0.4))})
    return None


OK_REPLIES = ["Quak, mach ich!", "Wird gemacht!", "Bin schon dabei!", "Okay, los geht's!"]
# Englisch (seit 0.34): dieselben Antworten in der eingestellten Sprache der Ente
EN = {
    "ok": ["Quack, on it!", "Will do!", "On my way!", "Okay, here we go!"],
    "goofy_ok": ["Quack! Uh … sure, on it!", "Me? Now? Okay, because it's you!", "Yes sir! Duck's honour."],
    "goofy_trotz": ["Nope! … Oh fine, since you asked so nicely.", "Hmpf. Do I have to? … Okay, okay."],
    "goofy_huh": ["Quack? I didn't get that. Was that Duckish?", "Huh? My feathers didn't catch that. Say it simpler?"],
    "huh": "I didn't understand that without Claude. Try “walk forward”, “turn” or “dance”.",
    "huh_ohne_beine": "I didn't understand that without Claude. Try “look around”, “turn” or “dance”.",
    "goofy_huh_roboter": ["Huh? That went right past my antennas. Say it simpler?",
                          "Beep? I didn't get that. Say it once more, simpler?"],
    "repeat": "What should I repeat? I haven't performed anything just now.",
    "nicht": "Not possible right now: {why}",
}


def _en() -> bool:
    from .. import i18n
    return i18n.sprache() == "en"

GOOFY_OK = [
    "Quak! Äh … ja klar, mach ich!",
    "Ich? Jetzt? Okay, weil du es bist!",
    "Bin schon unterwegs! Glaube ich. Quak!",
    "Ach so meinst du das! Hätte ich auch selbst drauf kommen können.",
    "Jawoll! Entenehrenwort.",
    "Mach ich – mit Watschel-Turbo!",
]
GOOFY_TROTZ = [
    "Nö! … Na gut, weil du so nett fragst.",
    "Hmpf. Muss das sein? … Okay, okay.",
    "Will nicht! … Ach, doch. Quak.",
    "Ich bin doch keine Laufente! … Na schön.",
]
GOOFY_HUH = [
    "Quak? Das hab ich nicht verstanden. War das Entisch?",
    "Hä? Meine Federn haben das nicht kapiert. Sag's nochmal einfacher?",
]
# Für Körper, die keine Ente sind (Reachy): keine Federn, kein Quak (Fund aus dem Test 5.11.2026)
GOOFY_HUH_ROBOTER = [
    "Hä? Das ist an meinen Antennen vorbeigerauscht. Sag's nochmal einfacher?",
    "Piep? Das hab ich nicht verstanden. Nochmal, bitte etwas einfacher?",
]
_LEAD = r"^\s*(?:ente[,!]?\s+)?(?:(?:bitte|jetzt|mal|doch)\s+)*"
HEAD_STEADY = re.compile(r"^\W*(?:ente\W+)?(?:(?:kopf|blick)\w*[- ]?(?:stabili\w*|ruhig\w*)(?:[- ]?modus)?\s*(?:(?P<an>an|ein)|(?P<aus>aus))"
                         r"|.*\b(?:kopf|blick)\w*\b.*\bwie (?:ein |eine )?(?:huhn|taube))\W*$")
GOOFY_ON = re.compile(_LEAD + r"(?:(?:sei|werd\w*)\b.*\b(?:albern|goofy|lustig|quatschig)\b"
                      r"|(?:goofy|albern)\w*[- ]?(?:modus)?\s*(?:an|ein)\b)")
GOOFY_OFF = re.compile(_LEAD + r"(?:(?:sei|werd\w*)\b.*\b(?:normal|ernst|vernünftig)\b"
                       r"|(?:goofy|albern)\w*[- ]?(?:modus)?\s*aus\b|schluss mit (?:dem )?(?:quatsch|albern))")
SERIOUS_TOOLS = {"stop", "power"}
# Gruppenbefehle an die weiteren Enten (seit 0.36.3): „alle tanzen“, „alle mir nach“, „everyone sit“ …
GRUPPE = re.compile(r"^\W*(?:ihr\s+)?(?:alle|alle enten|everyone|all ducks)\b\W*(?P<was>.+?)\W*$", re.I)
GRUPPE_MODUS = (("folgen", r"folg|nach|zu mir|komm|follow|come"), ("tanzen", r"tanz|dance"),
                ("sitzen", r"setz|sitz|sit"), ("frei", r"frei|spiel|lauf|herum|free|play|roam"))


WER_BIST_DU = re.compile(r"\b(wie hei(ß|ss)t du|wer bist du|dein name|what(?:'| i)s your name|who are you)\b", re.I)


def spiel_befehl(low: str, wb: Any) -> dict[str, Any] | None:
    """„Lass uns Tic-Tac-Toe spielen“, „Feld 5“, „Spiel beenden“ (seit 0.38.54)."""
    if re.search(r"tic.?tac.?toe|drei gewinnt|noughts", low):
        return {"aktion": "ende"} if re.search(r"\b(beend|stopp|aufhör|end|quit)", low) else {"aktion": "start"}
    if getattr(wb, "spiel", None) is None:
        return None
    m = re.search(r"\b(?:feld|field|square)\s*(\d)\b", low)
    if m:
        return {"aktion": "zug", "feld": int(m.group(1))}
    if re.search(r"spiel\w* (beend|stopp|aus)|\bgenug gespielt|\bend the game", low):
        return {"aktion": "ende"}
    return None


def werkbank_befehl(low: str, wb: Any) -> dict[str, Any] | None:
    """Kurze Befehle für den Arm → Argumente fürs Werkzeug „auftrag“ (None: kein Werkbank-Befehl)."""
    low = low.lower()
    for en, de in (("red", "rot"), ("blue", "blau"), ("yellow", "gelb"), ("green", "grün"), ("orange", "orang")):
        low = re.sub(rf"\b{en}\b", de, low)
    if re.search(r"\bsortier|\bsort\b", low):
        return {"auftrag": "sortieren"}
    if re.search(r"\bturm\b|\bstapel|\btower\b|\bstack\b", low) and not re.search(r"\bauf (den|dem|die)\b", low):
        return {"auftrag": "turm"}
    if re.search(r"räum\w* .*auf|\baufräum|\baufraeum|tidy up|clean up", low):
        return {"auftrag": "aufraeumen"}
    farben = [w for w in re.findall(r"\w+", low) if any(w.startswith(d["name"].split()[0][:-2].lower()) for d in wb.dinge)]
    if not re.search(r"\b(leg|stell|pack|tu|setz|put|place)\w*\b", low):
        return None
    if not farben and not (wb.haelt and re.search(r"\b(ihn|es|den|das|it)\b", low)):
        return None
    ding = next(d["name"] for d in wb.dinge if farben[0].startswith(d["name"].split()[0][:-2].lower())) if farben \
        else wb.haelt
    from ..werkbank_auftrag import stelle_aus
    kiste = re.search(r"kiste|\bbox\b", low)
    if kiste and ("link" in low or "left" in low):
        ziel = "linke Kiste"
    elif kiste and ("recht" in low or "right" in low):
        ziel = "rechte Kiste"
    elif re.search(r"\bauf (den|dem|die)\b|\bon top of\b|\bonto\b", low) and len(farben) > 1:
        ziel = "auf " + next(d["name"] for d in wb.dinge if farben[1].startswith(d["name"].split()[0][:-2].lower()))
    elif re.search(r"zurück|zurueck|platz|\bback\b", low):
        ziel = "platz"
    elif stelle_aus(low) is not None:                     # „leg ihn vorne links ab“ (seit 0.38.55)
        ziel = " ".join(w for w in re.findall(r"\w+", low) if stelle_aus(w))
    else:
        return None
    return {"schritte": [{"ding": ding, "ziel": ziel}]}


class FallbackBrain:
    def __init__(self, runner: "ToolRunner", name=None) -> None:
        self.runner = runner
        self.name = name or (lambda: "Quacki")

    async def handle(self, text: str) -> "Reply":
        from .agent import Reply

        low = text.lower()
        eng = self.runner.engine
        goofy = eng.config.goofy
        # Erzählt der Mensch, dass es ihm nicht gut geht, ist das kein Befehl – Mitgefühl geht vor
        from ..motion.mood import USER_LOW

        if USER_LOW.search(low) and re.search(r"\b(ich|mir|mich|bin|mein|meine)\b", low):
            return Reply("Oh. Ich bin bei dir. Sag einfach, wenn ich dich ein bisschen aufmuntern soll.", [], "einfach")
        # Nach dem Namen fragen geht auch ohne Claude (seit 0.38.7, Prüfung aus Anwendersicht)
        if WER_BIST_DU.search(low):
            name = self.name() or "Quacki"
            return Reply(f"I'm {name}." if _en() else f"Ich bin {name}.", [], "einfach")
        # Arm an der Werkbank (seit 0.38.54): „sortier die Würfel“, „räum auf“, „bau einen Turm“, „leg den roten in die
        # linke Kiste“ – auch ohne Sprachmodell
        if hasattr(eng.backend, "auftrag_starten"):
            spiel = spiel_befehl(low, eng.backend.werkbank)
            arm = werkbank_befehl(low, eng.backend.werkbank) if spiel is None else None
            if spiel is not None or arm is not None:
                r = await self.runner.run("tictactoe", spiel) if spiel is not None else await self.runner.run("auftrag", arm)
                text_ok = r.get("info") or "mach ich"
                return Reply(text_ok if r.get("ok") else r.get("fehler", "geht gerade nicht"), [], "einfach")
        # Goofy-Modus per Sprache
        if GOOFY_OFF.search(low):
            r = await self.runner.run("set_goofy", {"an": False})
            return Reply("Gut, ich bin wieder ganz ordentlich." if goofy else "Ich bin doch schon ganz normal!",
                         [{"tool": "set_goofy", "input": {"an": False}, "result": r}], "einfach")
        stab = HEAD_STEADY.search(low)
        if stab:
            on = not stab.group("aus")
            r = await self.runner.run("kopf_ruhig", {"an": on})
            return Reply("Kopf bleibt ruhig – wie bei einem Huhn." if on else "Kopf wieder locker.",
                         [{"tool": "kopf_ruhig", "input": {"an": on}, "result": r}], "einfach")
        if GOOFY_ON.search(low):
            r = await self.runner.run("set_goofy", {"an": True})
            await self.runner.run("emote", {"emotion": "schuetteln"})
            return Reply("Quak quak! Ab jetzt wird's albern!",
                         [{"tool": "set_goofy", "input": {"an": True}, "result": r}], "einfach")
        g = GRUPPE.match(text)
        if g and getattr(self.runner, "schwarm", None) is not None:
            modus = next((m for m, muster in GRUPPE_MODUS if re.search(muster, g.group("was"), re.I)), None)
            if modus:
                r = await self.runner.run("enten", {"aktion": "modus", "modus": modus})
                antwort = {"folgen": "Alle mir nach!", "tanzen": "Alle tanzen!", "sitzen": "Alle hinsetzen.",
                           "frei": "Lauft los!"}[modus]
                if _en():
                    antwort = {"folgen": "Everyone follow me!", "tanzen": "Everyone dance!", "sitzen": "Everyone sit.",
                               "frei": "Off you go!"}[modus]
                return Reply(antwort if r.get("ok") else (r.get("fehler") or "Geht gerade nicht"),
                             [{"tool": "enten", "input": {"modus": modus}, "result": r}], "einfach")
        if WO_GESEHEN.search(low) and getattr(self.runner, "raum", None) is not None:
            r = await self.runner.run("wo_gesehen", {"ding": text})
            return Reply(r.get("text") or r.get("fehler") or "Weiß ich nicht.",
                         [{"tool": "wo_gesehen", "input": {"ding": text}, "result": r}], "einfach")
        packs = getattr(self.runner, "packs", None)
        if packs is not None and "alltag" in packs.tool_names():
            from ..skills.alltag import quick

            q = quick(text)
            if q is not None:
                r = await self.runner.run("alltag", q)
                answer = r.get("antwort") or r.get("fehler") or "Erledigt."
                return Reply(answer, [{"tool": "alltag", "input": q, "result": r}], "einfach")
        if self.runner.memory is not None:
            remembered = await self._memory_command(text)
            if remembered is not None:
                return remembered
        steps = parse(text)
        if not steps:
            from ..motion.mood import PRAISE, USER_JOY, USER_LOW, USER_SCOLD

            if USER_LOW.search(low):
                return Reply("Oh. Ich bin bei dir. Sag einfach, wenn ich dich ein bisschen aufmuntern soll.", [], "einfach")
            koerper = eng.backend.eigenschaften()
            ente = "schnabel" in koerper or "beine" in koerper
            if PRAISE.search(low):
                return Reply("Danke! Da bin ich aber stolz." if not goofy else
                             ("Hihi, danke! Ich werd ganz rot unterm Gefieder." if ente else
                              "Hihi, danke! Da wackeln mir die Antennen."), [], "einfach")
            if USER_JOY.search(low):
                return Reply("Juhu, ich freu mich mit!", [], "einfach")
            if USER_SCOLD.search(low):
                return Reply("Oh, tut mir leid. Ich versuch's gleich nochmal besser.", [], "einfach")
            if goofy:
                await self.runner.run("emote", {"emotion": "verlegen"})
                await self.runner.run("emote", {"emotion": "schuetteln", "then": True})
                if ente:
                    return Reply(eng.rng.choice(EN["goofy_huh"] if _en() else GOOFY_HUH), [], "einfach")
                return Reply(eng.rng.choice(EN["goofy_huh_roboter"] if _en() else GOOFY_HUH_ROBOTER), [], "einfach")
            await self.runner.run("emote", {"emotion": "neugierig"})
            if "beine" not in koerper:      # Reachy läuft nicht – also nicht „lauf vor“ vorschlagen
                return Reply(EN["huh_ohne_beine"] if _en() else
                             "Das habe ich ohne Claude nicht verstanden. Versuch es mit ‚schau dich um‘, ‚dreh dich‘ oder ‚tanz‘.",
                             [], "einfach")
            return Reply(EN["huh"] if _en() else "Das habe ich ohne Claude nicht verstanden. Versuch es mit ‚lauf vor‘, ‚dreh dich‘ oder ‚tanz‘.",
                         [], "einfach")
        actions = []
        first = True
        serious = any(name in SERIOUS_TOOLS for name, _ in steps)
        trotz = goofy and not serious and not eng.mood.empathic and eng.rng.random() < eng.goofy_params()["trotz"]
        if trotz:
            # Erst kurz bocken, dann schütteln und gackern – dann ordentlich machen
            for emo in ("trotzig", "schuetteln"):
                targs = {"emotion": emo, "then": not first}
                actions.append({"tool": "emote", "input": targs, "result": await self.runner.run("emote", targs)})
                first = False
        for name, args in steps:
            for tool, targs in self._expand(name, args):
                if tool not in ("stop", "power", "sound"):
                    targs = {**targs, "then": not first}
                    first = False
                if tool == "_repeat":
                    last = self.runner.last_choreography
                    if not last:
                        return Reply(EN["repeat"] if _en() else "Was soll ich wiederholen? Ich habe gerade nichts vorgeführt.",
                                     actions, "einfach")
                    tool, targs = "choreography", {"keyframes": last["keyframes"], "loops": last["loops"],
                                                   "title": last.get("title") or "", "then": targs.get("then", False)}
                result = await self.runner.run(tool, targs)
                actions.append({"tool": tool, "input": targs, "result": result})
        # Ehrlich bleiben: wurde alles abgelehnt (umgefallen, Not-Aus-Sperre …), nicht „mach ich“ sagen
        tried = [a for a in actions if a["tool"] not in ("sound", "emote")]
        failed = [a for a in tried if isinstance(a["result"], dict) and a["result"].get("ok") is False]
        if tried and len(failed) == len(tried):
            why = failed[0]["result"].get("fehler") or failed[0]["result"].get("grund") or "geht gerade nicht"
            return Reply(EN["nicht"].format(why=why) if _en() else f"Geht gerade nicht: {why}", actions, "einfach")
        await self.runner.run("sound", {"tag": "chirp"})
        if trotz:
            return Reply(eng.rng.choice(EN["goofy_trotz"] if _en() else GOOFY_TROTZ), actions, "einfach")
        if goofy and not serious and not eng.mood.empathic:
            return Reply(eng.rng.choice(EN["goofy_ok"] if _en() else GOOFY_OK), actions, "einfach")
        return Reply(eng.rng.choice(EN["ok"] if _en() else OK_REPLIES), actions, "einfach")

    async def ausfuehren(self, steps: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        """Befehle nacheinander ausführen, ohne Antworttext (für die Absicherung in zusage.py, seit 0.37.14)."""
        actions: list[dict[str, Any]] = []
        first = True
        for name, args in steps:
            for tool, targs in self._expand(name, args):
                if tool == "_repeat":
                    continue
                if tool not in ("stop", "power", "sound"):
                    targs = {**targs, "then": not first}
                    first = False
                actions.append({"tool": tool, "input": targs, "result": await self.runner.run(tool, targs)})
        return actions

    @staticmethod
    def _expand(name: str, args: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        if name == "_kick":
            return [("skill", {"name": args["side"]})]          # läuft selbst zum Ball (KickBall)
        if name == "_repeat":
            return [("_repeat", {})]
        if name == "_pick":
            return [("approach", {"target": args["target"]}), ("skill", {"name": "ground_pick"})]
        return [(name, args)]

    # ── Gedächtnis ohne Claude ────────────────────────────────────────────
    async def _memory_command(self, text: str) -> "Reply | None":
        from .agent import Reply

        mem = self.runner.memory
        t = text.strip().rstrip(".!?")
        low = t.lower()

        async def act(tool: str, args: dict[str, Any], ok_text: str) -> Reply:
            result = await self.runner.run(tool, args)
            action = {"tool": tool, "input": args, "result": result}
            if result.get("ok") is False:
                return Reply(f"Das ging nicht: {result.get('fehler')}", [action], "einfach")
            return Reply(ok_text, [action], "einfach")

        # Vergessen
        m = re.match(r"^vergiss\s+(?:den trick|den ort|die vorliebe|das|den|die)?\s*[„\"']?(.+?)[“\"']?$", low)
        if m:
            name = m.group(1).strip()
            if re.fullmatch(r"(alles|dein gedächtnis|dein gedaechtnis)", name):
                return Reply("Alles vergessen geht über den Knopf im Gedächtnis-Fenster – sicher ist sicher.", [], "einfach")
            for kind in ("trick", "ort", "vorliebe"):
                try:
                    key = mem.forget(kind, name)
                except KeyError:
                    continue
                self.runner.engine.note({"type": "memory", "message": f"Vergessen: {key}"})
                return Reply(f"Okay, „{key}“ habe ich vergessen.", [], "einfach")
            return Reply(f"Zu „{name}“ habe ich nichts gespeichert.", [], "einfach")

        # Trick speichern: "merk dir das als Verbeugung"
        m = re.match(r"^(?:merk|speicher)\w*\s+(?:dir\s+)?(?:das|den tanz|die bewegung|diese bewegung)\s+(?:als|unter)\s+(?:dem namen\s+)?[„\"']?(.+?)[“\"']?$", t, re.I)
        if m:
            name = m.group(1).strip()
            return await act("remember", {"kind": "trick", "name": name}, f"Gemerkt! Sag einfach „{name}“, dann mache ich es wieder.")

        # Ort speichern: "das hier ist die Küche", "merk dir diesen Ort als Küche"
        m = (re.match(r"^(?:das hier|hier)\s+ist\s+(?:die|der|das|mein|meine|unser|unsere)?\s*(.+)$", t, re.I)
             or re.match(r"^merk\w*\s+(?:dir\s+)?(?:diesen ort|diese stelle|den ort|die stelle|hier)\s+als\s+(?:die|der|das)?\s*(.+)$", t, re.I))
        if m:
            name = m.group(1).strip()
            return await act("remember", {"kind": "ort", "name": name}, f"Gemerkt, hier ist {name}.")

        # Vorliebe: "merk dir: lauf langsamer", "merk dir, dass ich ..."
        m = re.match(r"^merk\w*\s+dir[:,]?\s+(?:dass\s+)?(.+)$", t, re.I)
        if m:
            pref = m.group(1).strip()
            return await act("remember", {"kind": "vorliebe", "text": pref}, "Gemerkt.")

        # Was weißt du?
        if re.search(r"was (?:weißt|weisst|kennst) du|was hast du dir gemerkt|dein gedächtnis|dein gedaechtnis", low):
            st = self.runner.engine.backend.state()
            summary = mem.summary(st.backend or "sim")
            parts = []
            if summary["tricks"]:
                parts.append("Tricks: " + ", ".join(summary["tricks"]))
            if summary["orte"]:
                parts.append("Orte: " + ", ".join(summary["orte"]))
            if summary["vorlieben"]:
                parts.append("Vorlieben: " + "; ".join(summary["vorlieben"]))
            return Reply(". ".join(parts) + "." if parts else "Mein Gedächtnis ist noch leer.", [], "einfach")

        # Gespeicherten Ort ansteuern: "geh in die Küche"
        if re.search(r"\b(geh|lauf|komm|watschel|bring)\w*\b", low) and not (
                re.search(r"\bbring", low) and _ding(low, "") != ""):
            st = self.runner.engine.backend.state()
            place = mem.find_place(t, st.backend or "sim")
            if place:
                return await act("go_to_place", {"name": place}, f"Ich watschle zu {place}.")

        # Gespeicherten Trick ausführen: "verbeug dich"
        trick = mem.find_trick(t)
        if trick:
            return await act("do_trick", {"name": trick}, f"{trick} – kommt sofort!")
        return None
