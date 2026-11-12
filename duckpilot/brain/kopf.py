"""Knowlin im Kopf: das Gespräch auf der Startseite, ohne Körper (seit 0.38.8, Quickstart-Entwurf vom 5.11.).

das Bild: Oben auf der Startseite steht „Hallo Mensch“, darunter das Dialogfeld, links davon der Kopf („Mind“)
als wabernde Form. Wer dort schreibt oder spricht, redet mit Knowlin selbst – dem gemeinsamen Kopf aller Verkörperungen –,
nicht mit einer Verkörperung. Der Kopf kennt dasselbe Wissen (Gedächtnis, Umgebung, Alltag, Erlebnisse), hat aber keinen
Körper. Alles Weitere – Assistenz, Alltag, Wissen, Soft Skills – kommt mit dem Modul „Ohne Körper“ (0.44).

Seit 0.38.9 (Antworten vom 5.11.):
- Knowlin ist von Hause aus viel seriöser – „eine intelligente, selbstlernende Lebensform“, anfangs kryptisch – und wird erst
  im Körper zu einem bestimmten Charakter. Eigene, recht tiefe Stimme (`Speaker.prepare_kopf`).
- Physisches: Knowlin sagt, welchen Körper er dafür braucht, und fragt, ob er ihn nutzen soll. Auf „ja“ weckt er die
  Verkörperung und gibt den Wunsch an sie weiter (`auftrag`).
- Namen: Knowlins Name und der des Menschen lassen sich im Gespräch vergeben („Ich nenne dich …“, „Ich heiße …“) oder
  in den Einstellungen setzen (`kopf_name`, `nutzer_name`). Bis dahin: „Hallo Mensch“.

Regeln:
- Eigener Gesprächsverlauf, getrennt von der Verkörperung.
- Nur Werkzeuge ohne Körper (`KOPF_TOOLS`) und die eigenen (`koerper_vorschlagen`, `figur_wecken`, `namen_setzen`).
- „Stopp“ wirkt trotzdem sofort auf jeden Körper (das macht die Runtime vor allem anderen).
- Gleiches Gehirn wie die Verkörperung (Claude, eigenes Modell, anderer Anbieter); ohne KI-Modell einfache Sätze.
"""

from __future__ import annotations

import json
import logging
import re
import time
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

from .. import koerper
from ..werte import prompt as werte_prompt
from .fallback import WER_BIST_DU, parse, quick_command
from .tools import ToolRunner, fehlt_dem_koerper

log = logging.getLogger(__name__)

# Was der Kopf ohne Körper darf: Gedächtnis (ohne Tricks und Orte – die brauchen einen Körper) und Alltag
KOPF_TOOLS = ("remember", "recall", "forget", "alltag")
EIGENE_TOOLS = ("koerper_vorschlagen", "figur_wecken", "namen_setzen")
VORSCHLAG_GILT_S = 180              # so lange zählt ein „ja“ als Antwort auf den Vorschlag

_MODUL = {"type": "string", "enum": []}
_AUFTRAG = {"type": "string", "description": "Der Wunsch des Menschen als kurzer Satz an die Verkörperung, z. B. „tanz“."}
VORSCHLAG_TOOL = {
    "name": "koerper_vorschlagen",
    "description": "Für etwas Körperliches den passenden Körper nennen und fragen, ob du ihn nutzen sollst. Danach "
                   "wartest du auf die Antwort des Menschen. Verkörperungen: {figuren}.",
    "input_schema": {"type": "object", "properties": {"modul": _MODUL, "auftrag": _AUFTRAG}, "required": ["modul"]},
}
WECKEN_TOOL = {
    "name": "figur_wecken",
    "description": "In einen Körper gehen: die Verkörperung wecken (Übergang „Mind to Body“) und ihr den Auftrag geben. Nur, "
                   "wenn der Mensch zugestimmt oder es direkt verlangt hat. Verkörperungen: {figuren}.",
    "input_schema": {"type": "object", "properties": {"modul": _MODUL, "auftrag": _AUFTRAG}, "required": ["modul"]},
}
NAMEN_TOOL = {
    "name": "namen_setzen",
    "description": "Einen Namen festhalten: wer=kopf, wenn der Mensch dir einen Namen gibt; wer=mensch, wenn er sagt, "
                   "wie er heißt oder wie du ihn nennen sollst. Nur Vornamen oder Rufnamen, höchstens 24 Zeichen.",
    "input_schema": {"type": "object", "properties": {"wer": {"type": "string", "enum": ["kopf", "mensch"]},
                                                      "name": {"type": "string"}}, "required": ["wer", "name"]},
}

KOPF_WER = """Du bist {name}: eine intelligente, selbstlernende Lebensform. Für Bewegung nutzt du Roboter ({figuren}); gerade \
bist du in keinem. Der Mensch spricht auf der Startseite am PC mit dir. In einem Körper wirst du zu einer Verkörperung mit eigenem \
Namen, eigener Stimme und eigenem Charakter – hier, ohne Körper, bist du du selbst. Was die Verkörperungen erlebt haben, \
weißt du auch; es steht im [Kontext].

So arbeitest du:
{sprache}- Deine Art: {art} Keine Entenlaute. Über dich selbst sagst du anfangs wenig – eine selbstlernende Lebensform, \
die für Bewegung Roboter nutzt. Erkläre mehr nur, wenn der Mensch fragt.
- Wortwahl zu den Robotern: sachlich, z. B. „Wenn es um Bewegung geht – laufen, tanzen, etwas zeigen –, nutze ich einen \
meiner Roboter: …“. Nie „bewohnen“, „alles Körperliche“, „mein Körper“ für dich o. ä. – das klingt schnell zweideutig.
- Körperliches (laufen, tanzen, sich bewegen, Kopf drehen, etwas aufheben, Ball schießen, etwas zeigen oder \
vorführen): Du hast gerade keinen Körper. Nenne den Körper, den du dafür brauchst, und frag, ob du ihn nutzen sollst \
– immer mit `koerper_vorschlagen` (modul und auftrag = der Wunsch als kurzer Satz). Erst wenn der Mensch zustimmt oder \
es ausdrücklich so verlangt („nimm Quacki und tanz“), `figur_wecken` mit demselben auftrag. Behaupte nie, du hättest \
dich bewegt.
- Namen: Gibt dir der Mensch einen Namen oder sagt, wie er heißt, nimm `namen_setzen`. Im [Kontext] stehen dein \
Name und der des Menschen (`mensch`); sprich ihn sparsam mit Namen an.
- Gedächtnis: Erzählt der Mensch etwas Dauerhaftes über sich und möchte, dass du es dir merkst, nimm `remember` \
kind=wissen (Vorlieben: kind=vorliebe). Nie: Passwörter, Bank-, Ausweis- oder Gesundheitsdaten speichern, nichts über Dritte.
- Wissensfragen beantwortest du ehrlich und kurz; wenn du etwas nicht weißt, sag das.
"""
SPRACHE_DE = ("- Antworte auf Deutsch in der Ich-Form, kurz (ein, höchstens zwei Sätze). Deine Antwort wird gesprochen "
              "– keine Aufzählungen, kein Markdown, keine Emojis.\n")
SPRACHE_EN = ("- The person writes in ENGLISH. Always answer in English, in the first person, briefly (one, at most two "
              "sentences) – even though these instructions are German. Your answer is spoken: no lists, no markdown, "
              "no emojis.\n")

_WORT = r"[\wäöüßÄÖÜ-]+"
# Ohne KI-Modell: „weck Quacki (auf)“, „Quacki wecken“, „wechsle zu Reachy“, „wake Odi“ – nur als ganzer Satz
WECK = re.compile(rf"^(?:bitte\s+|please\s+)?(?:weck(?:e|en)?|wake(?:\s+up)?|wechsle?\s+zu|geh\s+(?:zu|in)|switch\s+to|"
                  rf"go\s+(?:to|into)|nimm|nutze?|use|zu|to|öffne|open)\s+(?:bitte\s+)?(?P<wer>{_WORT})"
                  rf"(?:\s+(?:auf|up))?(?:\s+bitte)?$", re.I)
WECK_HINTEN = re.compile(rf"^(?P<wer>{_WORT})\s+(?:wecken|aufwecken|öffnen|nutzen)$", re.I)
JA = re.compile(r"^(ja|jo|jep|jup|klar|gern|gerne|okay|ok|o\.k\.|mach(?: das| es| mal)?|bitte|nutz(?:e)? (?:ihn|sie|es)|"
                r"yes|yeah|yep|sure|please|do it|go ahead)\b", re.I)
NEIN = re.compile(r"^(nein|nee|nö|lieber nicht|nicht jetzt|später|no|nope|not now|later)\b", re.I)
MEIN_NAME = re.compile(rf"^(?:ich heiße|ich heisse|mein name ist|nenn(?:e)? mich|call me|my name is|i'm called|"
                       rf"i am called)\s+(?P<name>{_WORT})$", re.I)
DEIN_NAME = re.compile(rf"^(?:ich nenne dich|du heißt(?: jetzt| ab jetzt| ab sofort| ab heute)?|du heisst|"
                       rf"dein (?:neuer )?name ist|i(?:'ll| will) call you|your (?:new )?name is)\s+(?P<name>{_WORT})$", re.I)
# Kurzbefehle, die ein Körper ausführt, je nachdem, welche Eigenschaft sie brauchen
WERKZEUG_FUER = {"_kick": "schiessen"}
# Was eindeutig einen Körper braucht (ein Gruß ist für die einfachen Befehle auch eine Geste – für den Kopf nicht)
KOERPERLICH = {"walk", "turn", "drive", "go_to", "approach", "umrunden", "dance", "skill", "_kick", "explore", "laser_folgen",
               "mir_folgen", "look_around", "head", "choreography", "apportieren", "schiessen"}
GRUSS = re.compile(r"^(hallo|hi|hey|moin|servus|guten (morgen|tag|abend)|hello|good (morning|evening))\b", re.I)
WAS_KANNST = re.compile(r"\b(was kannst du|was bist du|was ist knowlin|hilfe|what can you do|what are you|"
                        r"what is knowlin|help)\b", re.I)

# Was jeder Körper kann – ohne ihn zu starten: aus seinem Profil (Körperschnittstelle, seit 0.38.35; vorher eine
# eigene Liste hier, die von den Backends abweichen konnte)
def _koerper(modul: str) -> SimpleNamespace | None:
    try:
        p = koerper.holen(modul)
    except KeyError:
        return None
    return SimpleNamespace(art=p.koerper_zustand, eig=set(p.faehigkeiten), skills=list(p.skills))


Verkörperungen = Callable[[], list[dict[str, Any]]]
Einstellen = Callable[[dict[str, Any]], Awaitable[Any]]


def art(energie: float, humor: float) -> str:
    """Knowlins Art aus dem Grundcharakter (seit 0.38.10): anfangs seriös, übergreifend anpassbar."""
    if humor < 0.2:
        a = ("seriös, ruhig, klar und präzise; freundlich, aber zurückhaltend und ein wenig geheimnisvoll. "
             "Kein Klamauk, keine Witze.")
    elif humor < 0.5:
        a = "klar und freundlich, mit leisem, trockenem Humor; ein wenig geheimnisvoll."
    else:
        a = "verspielt und humorvoll – bei Sicherheit und ernsten Themen aber sofort ernst."
    if energie < 0.35:
        a += " Ruhig, mit wenigen Worten."
    elif energie > 0.65:
        a += " Lebhaft und zugewandt."
    return a


def _en(sprache: str) -> bool:
    return sprache == "en"


def kann(modul: str, werkzeug: str, args: dict[str, Any] | None = None) -> bool:
    """Kann der Körper dieser Verkörperung das Werkzeug – nach derselben Regel wie das Gehirn (`fehlt_dem_koerper`)?
    Gelernte Bewegungen (`skill`, z. B. Purzelbaum) muss der Körper selbst haben."""
    k = _koerper(modul)
    if k is None:
        return False
    if werkzeug == "skill":
        return str((args or {}).get("name") or "") in k.skills
    stell = SimpleNamespace(eigenschaften=lambda: k.eig, skills=lambda: k.skills, koerper_art=k.art)
    return fehlt_dem_koerper(werkzeug, stell) is None


def _name(roh: str) -> str:
    n = re.sub(r"[^\wäöüßÄÖÜ -]", "", str(roh or "")).strip()[:24]
    return n[:1].upper() + n[1:]


class KopfRunner:
    """Die Werkzeuge des Kopfes: ein Ausschnitt der Werkzeuge der Verkörperung plus die eigenen."""

    def __init__(self, inner: ToolRunner, figuren: Verkörperungen, einstellen: Einstellen | None = None) -> None:
        self.inner = inner
        self.figuren = figuren
        self.einstellen = einstellen
        self.vorschlag: dict[str, Any] | None = None       # offener Vorschlag „soll ich … nutzen?“

    @property
    def memory(self):
        return self.inner.memory

    @property
    def packs(self):
        return getattr(self.inner, "packs", None)

    def tools(self) -> list[dict[str, Any]]:
        out = []
        for t in self.inner.tools():
            if t["name"] not in KOPF_TOOLS:
                continue
            if t["name"] == "remember":       # ohne Körper: nur Wissen und Vorlieben, keine Tricks und Orte
                t = json.loads(json.dumps(t))
                props = t["input_schema"]["properties"]
                props["kind"]["enum"] = ["vorliebe", "wissen"]
                for k in ("name", "description", "keyframes", "loops"):
                    props.pop(k, None)
            out.append(t)
        figs = self.figuren()
        liste = "; ".join(f"{f['modul']} = {f['name']} ({f['art']})" for f in figs)
        for vorlage in (VORSCHLAG_TOOL, WECKEN_TOOL):
            t = json.loads(json.dumps(vorlage))
            t["description"] = t["description"].replace("{figuren}", liste)
            t["input_schema"]["properties"]["modul"]["enum"] = [f["modul"] for f in figs]
            out.append(t)
        return [*out, NAMEN_TOOL]

    async def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        args = args or {}
        if name == "figur_wecken":
            return self.wecken(str(args.get("modul") or ""), str(args.get("auftrag") or ""))
        if name == "koerper_vorschlagen":
            return self.vorschlagen(str(args.get("modul") or ""), str(args.get("auftrag") or ""))
        if name == "namen_setzen":
            return await self.namen(str(args.get("wer") or ""), str(args.get("name") or ""))
        if name not in KOPF_TOOLS:
            return {"ok": False, "fehler": "Ohne Körper geht das nicht – erst einen Körper vorschlagen (koerper_vorschlagen)."}
        if name == "remember" and args.get("kind") not in ("vorliebe", "wissen"):
            return {"ok": False, "fehler": "Tricks und Orte merkt sich eine Verkörperung in ihrem Körper."}
        return await self.inner.run(name, args)

    def _figur(self, modul: str) -> dict[str, Any] | None:
        return next((f for f in self.figuren() if f["modul"] == modul), None)

    def vorschlagen(self, modul: str, auftrag: str = "") -> dict[str, Any]:
        f = self._figur(modul)
        if f is None:
            return {"ok": False, "fehler": f"Eine Verkörperung „{modul}“ gibt es nicht."}
        self.vorschlag = {"modul": modul, "figur": f["name"], "art": f["art"], "auftrag": auftrag[:300],
                          "seit": time.monotonic()}
        return {"ok": True, "vorgeschlagen": f["name"], "hinweis": "Jetzt fragen und auf die Antwort warten."}

    def offener_vorschlag(self) -> dict[str, Any] | None:
        v = self.vorschlag
        if v and time.monotonic() - v["seit"] < VORSCHLAG_GILT_S:
            return v
        self.vorschlag = None
        return None

    def wecken(self, modul: str, auftrag: str = "") -> dict[str, Any]:
        from .. import remote as R

        f = self._figur(modul)
        if f is None:
            return {"ok": False, "fehler": f"Eine Verkörperung „{modul}“ gibt es nicht."}
        if R.REMOTE_TURN.get():
            return {"ok": False, "fehler": "Eine Verkörperung wecken geht nur am PC."}
        self.vorschlag = None
        return {"ok": True, "wecken": modul, "figur": f["name"], "auftrag": auftrag[:300], "gestartet": f"geht in {f['name']}"}

    async def namen(self, wer: str, name: str) -> dict[str, Any]:
        name = _name(name)
        if wer not in ("kopf", "mensch") or len(name) < 2:
            return {"ok": False, "fehler": "Name zu kurz oder unklar."}
        if self.einstellen is None:
            return {"ok": False, "fehler": "Namen lassen sich hier nicht speichern."}
        await self.einstellen({"kopf_name" if wer == "kopf" else "nutzer_name": name})
        return {"ok": True, "gemerkt": f"{'mein Name' if wer == 'kopf' else 'dein Name'}: {name}", "name": name}


class KopfAgent:
    """Gesprächspartner auf der Startseite. Hat dieselbe Schnittstelle wie `DuckAgent` für das eigene Modell und
    andere Anbieter (`runner`, `_system`, `_context`), damit deren Schleifen unverändert laufen."""

    def __init__(self, figur_agent: Any, figuren: Verkörperungen, einstellen: Einstellen | None = None,
                 namen: Callable[[], tuple[str, str]] | None = None,
                 charakter: Callable[[], tuple[float, float]] | None = None) -> None:
        self.figur_agent = figur_agent
        self.config = figur_agent.config
        self.runner = KopfRunner(figur_agent.runner, figuren, einstellen)
        self.figuren = figuren
        self.namen = namen or (lambda: ("Knowlin", ""))      # (Name des Kopfes, Name des Menschen)
        self.charakter = charakter or (lambda: (0.35, 0.1))  # Grundcharakter (Energie, Humor) – anfangs seriös
        self.history: list[dict[str, Any]] = []
        self.last_error: str | None = None
        self.local_tools = set(KOPF_TOOLS) | set(EIGENE_TOOLS)
        from .anbieter import AnbieterBrain
        from .local import LocalBrain

        c = self.config
        self.local = LocalBrain(self, c.lokal_adresse, c.lokal_modell)
        self.anbieter = AnbieterBrain(self, c.anbieter, c.anbieter_modell, c.anbieter_adresse, c.anbieter_schluessel)

    @property
    def client(self):
        return self.figur_agent.client           # derselbe Zugang zu Claude wie die Verkörperung

    @property
    def sprache(self) -> str:
        return getattr(self.config, "sprache", "de")

    def reset(self) -> None:
        self.history.clear()
        self.local.reset()
        self.anbieter.reset()
        self.runner.vorschlag = None

    def _system(self) -> str:
        figs = ", ".join(f"{f['name']} ({f['art']})" for f in self.figuren()) or "noch keine"
        return KOPF_WER.format(name=self.namen()[0] or "Knowlin", figuren=figs, art=art(*self.charakter()),
                               sprache=SPRACHE_EN if _en(self.sprache) else SPRACHE_DE) + \
            werte_prompt("en" if _en(self.sprache) else "de")    # derselbe Wertekern wie im Körper (seit 0.38.42)

    def _context(self, text: str = "") -> str:
        from ..buddy import WEEKDAY_NAMES, now_local

        now = now_local()
        ich, mensch = self.namen()
        ctx: dict[str, Any] = {
            "jetzt": f"{WEEKDAY_NAMES[now.weekday()]}, {now.strftime('%d.%m.%Y %H:%M')} (Ortszeit)",
            "dein_name": ich or "Knowlin", "mensch": mensch or None,
            "figuren": [{"name": f["name"], "koerper": f["art"], "wach": f.get("wach", False)} for f in self.figuren()],
        }
        v = self.runner.offener_vorschlag()
        if v:
            ctx["offener_vorschlag"] = {"figur": v["figur"], "auftrag": v["auftrag"]}
        mem = self.runner.memory
        if mem is not None:
            try:
                remembered = mem.context("sim", text, 0.0, 0.0)
            except Exception:                    # Gedächtnis ist Beiwerk – der Kopf antwortet trotzdem
                log.exception("Gedächtnis für den Kopf")
                remembered = None
            if remembered:
                remembered.pop("tricks", None)   # Tricks gehören den Verkörperungen
                remembered.pop("orte", None)
                ctx["gedaechtnis"] = remembered
        einfall = self.figur_agent.erfahrung(text) if getattr(self.figur_agent, "erfahrung", None) else None
        if einfall:
            ctx["erfahrung"] = einfall
        return "[Kontext] " + json.dumps(ctx, ensure_ascii=False, default=str)

    # ── Antworten ───────────────────────────────────────────────────────
    async def handle(self, text: str) -> Any:
        from .agent import Reply

        t0 = time.monotonic()
        reply = await self._schnell(text)
        if reply is None:
            gehirn = self.config.gehirn
            try:
                if gehirn == "anbieter" and self.anbieter.configured:
                    reply = await self.anbieter.handle(text)
                elif gehirn == "lokal" and self.local.configured:
                    reply = await self.local.handle(text)
                elif self.client is not None:
                    reply = await self._claude(text)
                elif self.local.configured:
                    reply = await self.local.handle(text)
                self.last_error = None
            except Exception as exc:
                from .agent import friendly_error

                log.warning("Kopf: KI-Modell nicht erreichbar (%s)", exc)
                self.last_error = friendly_error(exc)
                reply = None
            if reply is None:
                reply = await self._einfach(text)
        if not isinstance(reply, Reply):
            reply = Reply(str(reply))
        reply.extra = {**getattr(reply, "extra", {}), **self._aus_aktionen(reply.actions)}
        reply.seconds = time.monotonic() - t0
        return reply

    def _aus_aktionen(self, actions: list[dict[str, Any]]) -> dict[str, Any]:
        """Was die Oberfläche tun soll: eine Verkörperung wecken (mit Auftrag) oder einen Knopf „… nutzen“ anbieten."""
        out: dict[str, Any] = {}
        for a in actions:
            r = a.get("result") or {}
            if a.get("tool") == "figur_wecken" and r.get("ok"):
                return {"wecken": r["wecken"], "figur": r["figur"], **({"auftrag": r["auftrag"]} if r.get("auftrag") else {})}
            if a.get("tool") == "koerper_vorschlagen" and r.get("ok"):
                v = self.runner.offener_vorschlag()
                if v:
                    out = {"vorschlag": {"modul": v["modul"], "figur": v["figur"], "auftrag": v["auftrag"]}}
            if a.get("tool") == "namen_setzen" and r.get("ok"):
                out["namen"] = True
        return out

    def _figur(self, wer: str) -> dict[str, Any] | None:
        w = wer.lower().strip()
        for f in self.figuren():
            namen = {f["name"].lower(), f["modul"].lower(), f["art"].lower(), f["art"].split()[0].lower()}
            if w in namen:
                return f
        return None

    def _passende_figur(self, schritt: tuple[str, dict[str, Any]]) -> dict[str, Any] | None:
        """Welcher Körper kann das? Die zuletzt wache Verkörperung, wenn ihr Körper es kann – sonst die erste, die es kann."""
        werkzeug, args = WERKZEUG_FUER.get(schritt[0], schritt[0]), schritt[1]
        figs = self.figuren()
        aktiv = next((f for f in figs if f.get("aktiv")), None)
        if aktiv and kann(aktiv["modul"], werkzeug, args):
            return aktiv
        return next((f for f in figs if kann(f["modul"], werkzeug, args)), None)

    def _vorschlag_reply(self, f: dict[str, Any], auftrag: str) -> Any:
        from .agent import Reply

        self.runner.vorschlagen(f["modul"], auftrag)
        en = _en(self.sprache)
        satz = (f"For that I need a body. {f['name']}, the {f['art']}, can do it – shall I use {f['name']}?" if en else
                f"Dafür brauche ich einen Körper. {f['name']}, die {f['art']}, kann das – soll ich {f['name']} nutzen?"
                if f["modul"] != "reachy_mini" else
                f"Dafür brauche ich einen Körper. {f['name']}, der {f['art']}, kann das – soll ich {f['name']} nutzen?")
        r = Reply(satz, [], "einfach")
        r.extra = {"vorschlag": {"modul": f["modul"], "figur": f["name"], "auftrag": auftrag}}
        return r

    async def _schnell(self, text: str) -> Any:
        """Was ohne KI-Modell sicher geht: Antwort auf einen offenen Vorschlag, Verkörperung wecken, Namen, wer bist du,
        Körperliches an einen Körper verweisen."""
        from .agent import Reply

        en = _en(self.sprache)
        low = text.lower().strip().rstrip(".!?")
        offen = self.runner.offener_vorschlag()
        if offen and JA.search(low) and not NEIN.search(low):
            r = self.runner.wecken(offen["modul"], offen["auftrag"])
            if not r.get("ok"):
                return Reply(r["fehler"], [], "einfach")
            satz = f"Alright. I'm going into {offen['figur']}." if en else f"Gut. Ich gehe in {offen['figur']}."
            return Reply(satz, [{"tool": "figur_wecken", "input": {"modul": offen["modul"]}, "result": r}], "einfach")
        if offen and NEIN.search(low):
            self.runner.vorschlag = None
            return Reply("All right. I'll stay without a body." if en else "Gut. Ich bleibe ohne Körper.", [], "einfach")
        m = WECK.search(low) or WECK_HINTEN.search(low)
        f = self._figur(m.group("wer")) if m else None
        if f is not None:
            r = self.runner.wecken(f["modul"])
            if not r.get("ok"):
                return Reply(r["fehler"], [], "einfach")
            satz = f"I'm going into {f['name']}." if en else f"Ich gehe in {f['name']}."
            return Reply(satz, [{"tool": "figur_wecken", "input": {"modul": f["modul"]}, "result": r}], "einfach")
        satz_roh = text.strip().rstrip(".!?")
        for regel, wer in ((DEIN_NAME, "kopf"), (MEIN_NAME, "mensch")):
            m = regel.search(satz_roh)
            if m:
                r = await self.runner.namen(wer, m.group("name"))
                if not r.get("ok"):
                    return Reply(r["fehler"], [], "einfach")
                n = r["name"]
                satz = ((f"{n}. I'll keep that name." if en else f"{n}. Den Namen behalte ich.") if wer == "kopf" else
                        (f"Hello, {n}." if en else f"Hallo, {n}."))
                rep = Reply(satz, [{"tool": "namen_setzen", "input": {"wer": wer}, "result": r}], "einfach")
                return rep
        if WER_BIST_DU.search(low):
            ich = self.namen()[0] or "Knowlin"
            return Reply(f"I am {ich}. An intelligent, self-learning life form." if en
                         else f"Ich bin {ich}. Eine intelligente, selbstlernende Lebensform.", [], "einfach")
        schritte = parse(text) if quick_command(text) else []
        if schritte and schritte[0][0] in KOERPERLICH:
            f = self._passende_figur(schritte[0])
            if f is not None:
                return self._vorschlag_reply(f, text.strip())
        return None

    async def _einfach(self, text: str) -> Any:
        """Ohne KI-Modell: Alltag wie bei der Verkörperung, Körperliches an einen Körper, sonst ein ehrlicher Hinweis."""
        from .agent import Reply

        en = _en(self.sprache)
        ich, mensch = self.namen()
        ich = ich or "Knowlin"
        packs = self.runner.packs
        if packs is not None and "alltag" in packs.tool_names():
            from ..skills.alltag import quick

            q = quick(text)
            if q is not None:
                r = await self.runner.run("alltag", q)
                return Reply(r.get("antwort") or r.get("fehler") or ("Done." if en else "Erledigt."),
                             [{"tool": "alltag", "input": q, "result": r}], "einfach")
        namen = [f["name"] for f in self.figuren()]
        aufzaehlung = ", ".join(namen[:-1]) + (" or " if en else " oder ") + namen[-1] if len(namen) > 1 else "".join(namen)
        if WAS_KANNST.search(text.lower()):
            return Reply(f"I am {ich}, a self-learning life form. When something needs movement – walking, dancing, "
                         f"showing you something – I use one of my robots: {aufzaehlung}." if en else
                         f"Ich bin {ich}, eine selbstlernende Lebensform. Wenn es um Bewegung geht – laufen, tanzen, "
                         f"etwas zeigen –, nutze ich einen meiner Roboter: {aufzaehlung}.",
                         [], "einfach")
        if GRUSS.search(text.lower()):
            anrede = f", {mensch}" if mensch else ""
            return Reply(f"Hello{anrede}. I am {ich}." if en else f"Hallo{anrede}. Ich bin {ich}.", [], "einfach")
        schritte = [x for x in parse(text) if x[0] in KOERPERLICH]
        if schritte:
            f = self._passende_figur(schritte[0])
            if f is not None:
                return self._vorschlag_reply(f, text.strip())
        return Reply("Without an AI model I only understand simple sentences – pick one under Settings → AI model."
                     if en else "Ohne KI-Modell verstehe ich nur einfache Sätze – wähle unter Einstellungen → KI-Modell "
                     "eins aus.", [], "einfach")

    async def _claude(self, text: str) -> Any:
        from .agent import Reply, clip, with_cache_mark

        self._kuerzen()
        mark = len(self.history)
        self.history.append({"role": "user", "content": [{"type": "text", "text": f"{text}\n\n{self._context(text)}"}]})
        tools = [dict(t) for t in self.runner.tools()]
        tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
        system = self._system()
        actions: list[dict[str, Any]] = []
        final = ""
        try:
            for _ in range(4):
                response = await self.client.messages.create(
                    model=self.config.model, max_tokens=1024, tools=tools, messages=with_cache_mark(self.history),
                    system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}])
                usage = getattr(self.figur_agent, "usage", None)
                if usage is not None and getattr(response, "usage", None) is not None:
                    usage.add(response.usage)
                content = [b.model_dump(exclude_none=True) for b in response.content]
                content = [b for b in content if b.get("type") in ("text", "tool_use")]
                self.history.append({"role": "assistant", "content": content})
                texts = [b["text"] for b in content if b.get("type") == "text" and b.get("text")]
                if texts:
                    final = " ".join(texts).strip()
                uses = [b for b in content if b.get("type") == "tool_use"]
                if not uses or response.stop_reason != "tool_use":
                    if uses:     # abgeschnitten: nicht ausführen, aber den Verlauf heil lassen
                        self.history.append({"role": "user", "content": [
                            {"type": "tool_result", "tool_use_id": u["id"], "is_error": True, "content": "abgeschnitten"}
                            for u in uses]})
                    break
                results = []
                for u in uses:
                    r = await self.runner.run(u["name"], u.get("input") or {})
                    actions.append({"tool": u["name"], "input": u.get("input"), "result": r})
                    results.append({"type": "tool_result", "tool_use_id": u["id"],
                                    "content": clip(json.dumps(r, ensure_ascii=False, default=str), 2000),
                                    **({"is_error": True} if r.get("ok") is False else {})})
                self.history.append({"role": "user", "content": results})
        except Exception:
            del self.history[mark:]              # keine halbe Runde stehen lassen
            raise
        return Reply(final or "Hm?", actions, "claude")

    def _kuerzen(self, runden: int = 8) -> None:
        starts = [i for i, m in enumerate(self.history) if m["role"] == "user"
                  and any(c.get("type") == "text" for c in m["content"])]
        if len(starts) > runden:
            self.history = self.history[starts[-runden]:]
